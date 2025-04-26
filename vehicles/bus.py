import os
import sys
import datetime
import random
import time
from typing import Optional, Generator, Tuple, Any

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from common.patterns import CommandExecutor
from common.utils import *
from vehicles.base_vehicle import *
from vehicles.route_vehicle import RouteVehicle


class ShuttleClient(RouteVehicle, CommandExecutor):
    """
    ShuttleClient manages a shuttle vehicle client capable of executing commands,
    moving along a predefined route, and handling active/passive modes based on schedule.
    """

    def __init__(self, vehicle_id: Optional[str] = None) -> None:
        """
        Initialize the ShuttleClient.
        :param vehicle_id: Optional custom vehicle ID. If not provided, one is generated.
        :return: None
        """
        if not vehicle_id:
            next_number = random.randint(1, 99)
            vehicle_id = f"S{next_number}"
        super().__init__(vehicle_id, VehicleType.SHUTTLE, SHUTTLE_ROUTE.copy(), Status.STANDBY)
        self.start_time: str = "08:00"
        self.is_active: bool = False
        self.__passive_counter: int = 0
        self.next_departure_time: str = self.start_time
        self.location: Tuple[float, float] = get_coordinates_for_stop(self._route[self._current_stop_index])

    def _movement_step(self, last_tcp_timestamp: float) -> float:
        """
        Simulate shuttle movement along its route and send status updates.
        :param last_tcp_timestamp: The timestamp of the last TCP message sent.
        :return: The timestamp after movement.
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
            now = datetime.datetime.now().strftime("%H:%M")
            network_status = Status.ACTIVE if now >= "08:00" else Status.STANDBY
            speed = random.uniform(20, 50)

            self.send_status_update()
            self.log_location_update(lat, long, network_status, speed)
            time.sleep(pause)

        return last_tcp_timestamp

    # region RouteVehicle Overrides
    def _in_passive_mode(self) -> bool:
        """
        Determine whether the shuttle is currently in passive (standby) mode.
        :return: True if inactive, False otherwise.
        """
        return not self.is_active

    def _simulate_passive(self) -> None:
        """
        Simulate passive behavior by sending periodic UDP beacons and TCP updates.
        :return: None
        """
        self.__passive_counter += 1
        if self.__passive_counter % 5 == 0:
            self.send_status_update()

        lat, lon = self.location
        self.send_udp_beacon(lat, lon)
        self.logger.log(f"[UDP] Passive beacon from {self.vehicle_id}")
        self.logger.log(
            f"Shuttle {self.vehicle_id} | Status: {self.status} | "
            f"Next Departure: {self.next_departure_time}"
        )
        time.sleep(10)

    def _progress_generator(self) -> Generator[Tuple[int, int], None, None]:
        """
        Generate simulated travel progress percentages with pauses between updates.
        :yield: Tuple of (progress_percentage, pause_seconds).
        """
        travel_time: int = 30
        start: float = time.time()

        while True:
            elapsed: float = time.time() - start
            pct: int = min(100, int(elapsed / travel_time * 100))
            yield pct, 5
            if pct >= 100:
                break

    def _on_arrival(self, arrived_stop: str) -> None:
        """
        Handle shuttle arrival at a stop.
        :param arrived_stop: The name of the stop where the shuttle arrived.
        :return: None
        """
        self.notify_observers(
            "ARRIVAL",
            f"Shuttle {self.vehicle_id} arrived at {arrived_stop}"
        )

        if not self._current_stop_index == 0:
            self.logger.log(f"Arrived at {arrived_stop}, next stop {self._next_stop}")
            return

        self.logger.log(
            f"Shuttle {self.vehicle_id} completed route, returning to standby",
            also_print=True
        )
        self.is_active = False
        self.status = Status.STANDBY
        self.next_departure_time = self.calculate_next_departure()
        self.logger.log(f"Next scheduled departure: {self.next_departure_time}")

    # endregion

    # region Vehicle Overrides
    def _pre_step(self) -> None:
        """
        Perform pre-movement step check to activate shuttle if the scheduled time has passed.
        :return: None
        """
        now = datetime.datetime.now().strftime("%H:%M")
        if not self.is_active and now >= self.start_time:
            self.logger.log(
                f"Scheduled start ({self.start_time}) reached; activating {self.vehicle_id}",
                also_print=True
            )
            self.is_active = True
            self.status = Status.ACTIVE

    # endregion

    def calculate_next_departure(self) -> str:
        """
        Calculate the next scheduled departure time, 30 minutes after the last.
        :return: Next departure time in HH:MM format.
        """
        now = datetime.datetime.now()
        hh, mm = map(int, self.next_departure_time.split(':'))
        last_dep = now.replace(hour=hh, minute=mm)
        next_dep = last_dep + datetime.timedelta(minutes=30)
        if next_dep <= now:
            next_dep += datetime.timedelta(minutes=30)
        return next_dep.strftime("%H:%M")

    def handle_command(self, command_message: dict[str, Any]) -> None:
        """
        Handle a command message received from the server.
        :param command_message: The command message containing type and parameters.
        :return: None
        """
        command_type = command_message["command"]
        params = command_message.get("params", {})

        if command_type == Command.START_ROUTE:
            current_time = datetime.datetime.now().strftime("%H:%M")
            if current_time >= self.start_time:
                self.execute(Command.START_ROUTE)
                self.send_command_ack(command_type, "Starting route")
            else:
                reason = f"Cannot start before scheduled time ({self.start_time})"
                self.send_command_rejected(command_type, reason)
                self.logger.log(f"Rejected START_ROUTE command: {reason}")

        elif command_type == Command.SHUTDOWN:
            self.execute(Command.SHUTDOWN)
            self.send_command_ack(command_type, "Shutting down")
            self.running = False

        elif command_type == Command.DELAY:
            duration = params.get("duration", 30)
            self.execute(Command.DELAY, {"duration": duration})
            self.send_command_ack(command_type, f"Delayed for {duration} seconds")

        else:
            self.send_command_rejected(command_type, "Unknown command")

    def execute(self, command: str, params: Optional[dict[str, Any]] = None) -> None:
        """
        Execute a specific command on the shuttle.
        :param command: The command to execute.
        :param params: Optional parameters associated with the command.
        :return: None
        """
        if command == Command.START_ROUTE:
            self.is_active = True
            self.status = Status.ACTIVE
            self.logger.log(f"Shuttle activated")

        elif command == Command.SHUTDOWN:
            self.logger.log(f"Shuttle shutting down")
            self.running = False

        elif command == Command.DELAY:
            duration = params.get("duration", 30) if params else 30
            self._is_delayed = True
            self.status = Status.DELAYED
            self._delay_until = time.time() + duration
            self.logger.log(f"Shuttle delayed for {duration} seconds")


if __name__ == "__main__":
    vehicle_id: Optional[str] = None
    if len(sys.argv) > 1:
        vehicle_id = sys.argv[1]

    shuttle = ShuttleClient(vehicle_id)
    shuttle.start()
