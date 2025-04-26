import os
import sys
import time
import random
from typing import Optional, Generator, Tuple, Any

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from common.config import VehicleType, TRAIN_ROUTE, Status, Command
from common.patterns import CommandExecutor
from common.utils import *
from vehicles.route_vehicle import RouteVehicle


class TrainClient(RouteVehicle, CommandExecutor):
    """
    TrainClient represents a train vehicle client that simulates movement,
    handles commands, and manages active/passive states.
    """

    def __init__(self, vehicle_id: Optional[str] = None) -> None:
        """
        Initialize the TrainClient.
        :param vehicle_id: Optional vehicle ID. If not provided, a random ID is generated.
        :return: None
        """
        if not vehicle_id:
            next_number = random.randint(1, 99)
            vehicle_id = f"T{next_number}"
        super().__init__(vehicle_id, VehicleType.TRAIN, TRAIN_ROUTE.copy(), Status.ON_TIME)
        self.eta: int = random.randint(2, 8)
        self.is_shutdown: bool = False
        self.__standby_reported: bool = False
        self.location: Tuple[float, float] = get_coordinates_for_stop(self._route[self._current_stop_index])

    def _movement_step(self, last_tcp_timestamp: float) -> float:
        """
        Simulate movement along the train's route and send updates.
        :param last_tcp_timestamp: Timestamp of the last TCP communication.
        :return: Updated timestamp after movement.
        """
        for progress, pause in self._progress_generator():
            if not self.running:
                break

            self.location = calculate_realistic_movement(
                get_coordinates_for_stop(self._route[self._current_stop_index]),
                get_coordinates_for_stop(self._next_stop),
                progress
            )
            lat, long = self.location
            network_status = Status.ON_TIME
            speed = random.uniform(40, 80)

            self.send_status_update()
            self.log_location_update(lat, long, network_status, speed)
            time.sleep(pause)

        return last_tcp_timestamp

    # region RouteVehicle Overrides
    def _in_passive_mode(self) -> bool:
        """
        Determine if the train is in passive (standby) mode.
        :return: True if in shutdown mode, False otherwise.
        """
        return self.is_shutdown

    def _simulate_passive(self) -> None:
        """
        Simulate passive mode behavior, sending occasional updates.
        :return: None
        """
        if not self.__standby_reported:
            self.send_status_update()
            self.__standby_reported = True

        self.logger.log(f"Train is in standby mode", also_print=True)
        time.sleep(5)

    def _progress_generator(self) -> Generator[Tuple[float, int], None, None]:
        """
        Generate progress percentages and simulate elapsed travel time.
        :yield: Tuple of (progress percentage, pause duration).
        """
        travel_time: float = 15.0
        start: float = time.time()

        while True:
            elapsed = time.time() - start
            pct = min(100.0, (elapsed / travel_time) * 100.0)
            self.eta = max(1, int(8 * (1 - pct / 100)))
            yield pct, 5
            if pct >= 100.0:
                break

    def _on_arrival(self, arrived_stop: str) -> None:
        """
        Handle logic when the train arrives at a stop.
        :param arrived_stop: The stop where the train arrived.
        :return: None
        """
        self.__standby_reported = False

        self.notify_observers(
            "ARRIVAL",
            f"Train {self.vehicle_id} arrived at {arrived_stop}"
        )
        self.logger.log(f"Train {self.vehicle_id} arrived at {arrived_stop}", also_print=True)

        self._current_stop_index = (self._current_stop_index + 1) % len(self._route)
        self._next_stop = self._route[(self._current_stop_index + 1) % len(self._route)]
        self.eta = random.randint(2, 8)

    # endregion

    def handle_command(self, command_message: dict[str, Any]) -> None:
        """
        Handle commands received from the server.
        :param command_message: A dictionary containing the command and its parameters.
        :return: None
        """
        command_type = command_message["command"]
        params = command_message.get("params", {})

        if command_type == Command.DELAY:
            duration = params.get("duration", 30)
            self.execute(Command.DELAY, {"duration": duration})
            self.send_command_ack(command_type, f"Delayed for {duration} seconds")

        elif command_type == Command.SHUTDOWN:
            self.execute(Command.SHUTDOWN)
            self.send_command_ack(command_type, "Entering standby mode")

        elif command_type == Command.REROUTE:
            self.execute(Command.REROUTE)
            self.send_command_ack(command_type, "Route changed")

        elif command_type == Command.START_ROUTE:
            if self.is_shutdown:
                self.execute(Command.START_ROUTE)
                self.send_command_ack(command_type, "Resuming route")
            else:
                self.send_command_ack(command_type, "Already active")
        else:
            self.send_command_rejected(command_type, "Unknown command")

    def execute(self, command: str, params: Optional[dict[str, Any]] = None) -> None:
        """
        Execute a specific command on the train.
        :param command: The command to execute.
        :param params: Optional parameters for the command.
        :return: None
        """
        if command == Command.DELAY:
            duration = params.get("duration", 30) if params else 30
            self._is_delayed = True
            self._status = Status.DELAYED
            self._delay_until = time.time() + duration
            self.logger.log(f"Train delayed for {duration} seconds")

        elif command == Command.SHUTDOWN:
            self.is_shutdown = True
            self._status = Status.STANDBY
            self.logger.log(f"Train entering standby mode")

        elif command == Command.REROUTE:
            if len(self._route) > 3:
                middle_stops = self._route[1:-1]
                random.shuffle(middle_stops)
                self._route = [self._route[0]] + middle_stops + [self._route[-1]]
                self.logger.log(f"Train rerouted: {' -> '.join(self._route)}")
            else:
                self.logger.log(f"Route too short to reroute")

        elif command == Command.START_ROUTE:
            if self.is_shutdown:
                self.is_shutdown = False
                self._status = Status.ON_TIME
                self.logger.log(f"Train resuming route")


if __name__ == "__main__":
    vehicle_id: Optional[str] = None
    if len(sys.argv) > 1:
        vehicle_id = sys.argv[1]

    train = TrainClient(vehicle_id)
    train.start()
