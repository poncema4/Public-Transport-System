import os
import sys
from typing import Generator

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

import time
from vehicles.base_vehicle import Vehicle
from abc import ABC, abstractmethod
from common.utils import calculate_realistic_movement, get_coordinates_for_stop

class RouteVehicle(Vehicle, ABC):
    """
    Represents a vehicle that moves along a predefined route.
    Ex: Bus, Train, Shuttle, etc.
    """
    def __init__(self, vehicle_id: str, vehicle_type: str, route: list[str], status: str):
        super().__init__(vehicle_id, vehicle_type)
        self._route: list[str] = route
        self._current_stop_index: int = 0
        self._next_stop: str | None = self._route[1] if len(self._route) > 1 else None
        self._status: str = status
        self._delay_until: float = 0.0
        self._is_delayed: bool = False

    def _movement_step(self, last_tcp_timestamp: float) -> float:
        """
        Moves the vehicle along its route and sends status updates.
        :param last_tcp_timestamp: The timestamp of the last TCP message sent.
        :return: The timestamp after movement.
        """
        # Passive standby?
        if self._in_passive_mode():
            self._simulate_passive()
            return last_tcp_timestamp

        # Active: send a TCP status update at start of each leg
        self.send_status_update()

        # Identify points
        current = self._route[self._current_stop_index]
        next_idx = (self._current_stop_index + 1) % len(self._route)
        next_stop = self._route[next_idx]
        self.next_stop = next_stop

        self.logger.log(f"{self.vehicle_type} at {current}, heading to {next_stop}")

        # Step through progress until arrival
        for progress, pause in self._progress_generator():
            if not self.running:
                break

            if progress >= 100:
                # Arrived
                self._current_stop_index = next_idx
                self.location = get_coordinates_for_stop(next_stop)
                self._on_arrival(next_stop)
                return last_tcp_timestamp

            # In‑flight update
            self.location = calculate_realistic_movement(
                get_coordinates_for_stop(current),
                next_stop,
                progress
            )
            lat, long = self.location
            self.send_udp_beacon(lat, long, next_stop=self.next_stop, eta=getattr(self, "eta", None))
            self.logger.log(f"[UDP] Progress: {progress:.1f}% to {next_stop} | Location: ({lat:.4f}, {long:.4f})")

            time.sleep(pause)

        return last_tcp_timestamp

    def _in_passive_mode(self) -> bool:
        """
        Optional to override. Determines whether the vehicle is currently in passive/standby mode.
        :return: True if in passive mode, False otherwise.
        """
        return False

    def _simulate_passive(self) -> None:
        """
        Optional to override. Simulates passive behavior by sending periodic UDP beacons and TCP updates.
        :return: None
        """
        pass

    @abstractmethod
    def _progress_generator(self) -> Generator[tuple[int, int], None, None]:
        """
        Yields progress percentages and pause durations for each leg of the route.
        :return: Progress percentages and pause durations pairs.
        """
        pass

    @abstractmethod
    def _on_arrival(self, arrived_stop: str) -> None:
        """
        Defines the behavior when the vehicle reaches its destination.
        :param arrived_stop: The name of the stop where the vehicle arrived.
        :return: None
        """
        pass