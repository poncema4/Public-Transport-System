import os
import sys
import random
from typing import Optional, Any

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from vehicles.point_to_point_vehicle import PointToPointVehicle
from vehicles.base_vehicle import *
from common.patterns import CommandExecutor
from common.utils import *


class UberClient(PointToPointVehicle, CommandExecutor):
    """
    UberClient simulates a private ride vehicle, moving from a start to an end location
    with limited acceptance of external commands.
    """

    def __init__(self, vehicle_id: Optional[str] = None) -> None:
        if not vehicle_id:
            next_number = random.randint(900, 999)
            vehicle_id = f"U{next_number}"
        super().__init__(vehicle_id, VehicleType.UBER, UBER_START, UBER_END, "Near NYU",
                         random.randint(5, 15), 50)

    # region PointToPointVehicle Overrides
    def _progress_generator(self) -> float:
        """
        Simulate progress updates, network dropout behavior, and location movement during the ride.
        :return: Pause duration in seconds before the next update.
        """
        if self._network_dropout_threshold <= self._progress < self._network_dropout_threshold + 10:
            if not self._in_network_dropout:
                self._in_network_dropout = True
                self.logger.log(
                    "Simulating network dropout near Lincoln Tunnel",
                    also_print=True
                )
            if random.random() < 0.8:
                self.logger.log("Network unstable, retrying...", also_print=True)
                return 5
        elif self._in_network_dropout:
            self._in_network_dropout = False
            self.logger.log("Network connection re-established", also_print=True)

        inc = random.randint(2, 5)
        self._progress = min(100, int(self._progress + inc))
        self.eta = max(1, int(15 * (100 - self._progress) / 100))

        waypoints = [
            "Near NYU", "Greenwich Village", "Union Square",
            "Near Flatiron", "Near Bryant Park", "Midtown",
            "Columbus Circle", "Upper West Side", "Near Columbia University"
        ]
        idx = min(int(self._progress / 100 * len(waypoints)), len(waypoints) - 1)
        self.current_location = waypoints[idx]

        if idx < len(waypoints) - 1:
            segment_pct = (self._progress % (100 / len(waypoints))) * len(waypoints)
            self.location = calculate_realistic_movement(
                get_coordinates_for_stop(waypoints[idx]),
                waypoints[idx + 1],
                segment_pct
            )
        else:
            self.location = calculate_realistic_movement(
                self.location,
                self._end_location,
                min(100, (self._progress - 90) * 10)
            )

        return 5

    def _on_completion(self) -> None:
        """
        Handle logic when the Uber ride reaches its destination.
        :return: None
        """
        self.location = get_coordinates_for_stop(self._end_location)
        self.logger.log(
            f"Uber {self.vehicle_id} reached destination: {self._end_location}",
            also_print=True
        )
        self.status = Status.ON_TIME
        self.send_status_update()

        lat, lon = self.location
        send_udp_beacon(
            self.vehicle_id,
            self.vehicle_type,
            self.status,
            {"lat": lat, "long": lon},
            None,
            0
        )
        self.running = False

    # endregion

    def handle_command(self, command_message: dict[str, Any]) -> None:
        """
        Handle commands received from the server.
        :param command_message: A dictionary containing the command type and parameters.
        :return: None
        """
        command_type = command_message["command"]

        if command_type == Command.SHUTDOWN:
            reason = "Cannot shutdown/cancel private ride"
            self.send_command_rejected(command_type, reason)
            self.log_event("COMMAND_FAILURE", reason)

        elif command_type == Command.REROUTE:
            reason = "Cannot reroute private ride"
            self.send_command_rejected(command_type, reason)
            self.log_event("COMMAND_FAILURE", reason)

        elif command_type == Command.DELAY:
            reason = "Cannot delay the uber ride"
            self.send_command_rejected(command_type, reason)
            self.log_event("COMMAND_FAILURE", reason)

        else:
            self.send_command_rejected(command_type, "Unknown or unsupported command")

    def execute(self, command: str, params: Optional[dict[str, Any]] = None) -> None:
        """
        Execute a command (part of the Command pattern).
        UberClient does not support executing external commands.
        :param command: The command to execute.
        :param params: Optional parameters for the command.
        :return: None
        """
        pass


if __name__ == "__main__":
    vehicle_id: Optional[str] = None
    if len(sys.argv) > 1:
        vehicle_id = sys.argv[1]

    uber = UberClient(vehicle_id)
    uber.start()
