import time
from typing import Generator, Optional, Dict, Any, Tuple

from common.config import VehicleType, BUS_ROUTE, Status, Command
from common.patterns import CommandExecutor
from common.utils import *
from vehicles.route_vehicle import RouteVehicle

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)


class BusClient(RouteVehicle, CommandExecutor):
    """
    A client representing a bus vehicle that follows a defined route and responds to server commands.
    """

    def __init__(self, vehicle_id: Optional[str] = None):
        if not vehicle_id:
            next_number = random.randint(101, 999)
            vehicle_id = f"B{next_number}"
        super().__init__(vehicle_id, VehicleType.BUS, BUS_ROUTE.copy(), Status.ON_TIME)
        self.eta: int = random.randint(1, 5)
        self.location: Tuple[float, float] = get_coordinates_for_stop(self._route[self._current_stop_index])

    def _movement_step(self, last_tcp_timestamp: float) -> float:
        """
        Simulate a single movement step along the bus route, updating location and sending status.
        :param last_tcp_timestamp: Timestamp of the last TCP communication.
        :returns: Updated last TCP timestamp.
        """
        for progress, pause in self._progress_generator():
            if not self.running:
                break

            # Update location dynamically
            self.location = calculate_realistic_movement(
                get_coordinates_for_stop(self._route[self._current_stop_index]),
                get_coordinates_for_stop(self._next_stop),
                progress
            )
            lat, long = self.location
            network_status = Status.ON_TIME
            speed = random.uniform(10, 30)

            self.send_status_update()
            self.log_location_update(lat, long, network_status, speed)
            time.sleep(pause)
        return last_tcp_timestamp

    # region RouteVehicle Overrides

    def _progress_generator(self) -> Generator[Tuple[float, int], None, None]:
        """
        Generate simulated travel progress increments between two stops
        :returns: Yields tuples of (progress percentage, pause seconds).
        """
        progress: float = 0.0
        iteration: int = 0
        while progress < 100.0 and self.running:
            if iteration % 3 == 0:
                self.send_status_update()
            iteration += 1

            delta = random.uniform(2, 8)
            progress += delta
            yield min(progress, 100.0), 3

    def _on_arrival(self, arrived_stop: str) -> None:
        """
        Handle the event of the bus arriving at a stop.
        :param arrived_stop: Name of the stop the bus has arrived at.
        :returns: None
        """
        self.current_stop_index = (self._current_stop_index + 1) % len(self._route)
        self.next_stop = self._route[(self.current_stop_index + 1) % len(self._route)]

        # Congestion at Union Square
        if arrived_stop == "Union Square" and random.random() < 0.5:
            self.status = Status.DELAYED
            self.eta += 2
            self.logger.log("Experiencing congestion at Union Square")

        self.logger.log(f"Arrived at {arrived_stop}, next stop: {self.next_stop}")
        self.notify_observers(
            "ARRIVAL",
            f"Bus {self.vehicle_id} arrived at {arrived_stop}"
        )

        # Reset ETA & location
        self.eta = random.randint(1, 5)
        self.location = get_coordinates_for_stop(arrived_stop)

    # endregion

    def handle_command(self, command_message: Dict[str, Any]) -> None:
        """
        Handle incoming commands from the server.
        :param command_message: Dictionary containing the command type and optional parameters.
        :returns: None
        """
        command_type = command_message["command"]
        params = command_message.get("params", {})

        if command_type == Command.DELAY:
            duration = params.get("duration", 30)  # Default 30 seconds
            self.execute(Command.DELAY, {"duration": duration})
            self.send_command_ack(command_type, f"Delayed for {duration} seconds")

        elif command_type == Command.REROUTE:
            self.execute(Command.REROUTE)
            self.send_command_ack(command_type, "Route changed")

        elif command_type == Command.SHUTDOWN:
            self.execute(Command.SHUTDOWN)
            self.send_command_ack(command_type, "Shutting down")
            self.running = False

        else:
            self.send_command_rejected(command_type, "Unknown command")

    def execute(self, command: str, params: Optional[Dict[str, Any]] = None) -> None:
        """
        Execute a specific command received from the server.
        :param command: Command type to execute.
        :param params: Optional parameters related to the command.
        :returns: None
        """
        if command == Command.DELAY:
            duration = params.get("duration", 30)
            self._is_delayed = True
            self._status = Status.DELAYED
            self._delay_until = time.time() + duration
            self.logger.log(f"Bus delayed for {duration} seconds")

        elif command == Command.REROUTE:
            if len(self._route) > 3:
                middle_stops = self._route[1:-1]
                random.shuffle(middle_stops)
                self._route = [self._route[0]] + middle_stops + [self._route[-1]]
                self.logger.log(f"Bus rerouted: {' -> '.join(self._route)}")
            else:
                self.logger.log(f"Route too short to reroute")

        elif command == Command.SHUTDOWN:
            self.logger.log(f"Received shutdown command")


if __name__ == "__main__":
    vehicle_id: Optional[str] = None
    if len(sys.argv) > 1:
        vehicle_id = sys.argv[1]

    bus = BusClient(vehicle_id)
    bus.start()
