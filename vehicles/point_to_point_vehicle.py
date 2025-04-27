import os
import sys
import time

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from vehicles.base_vehicle import Vehicle
from abc import ABC, abstractmethod
from common.config import Status
from common.utils import get_coordinates_for_stop


class PointToPointVehicle(Vehicle, ABC):
    """
    Represents a point-to-point vehicle, i.e., a vehicle that moves from one location to another w/o a specific route.
    Ex: Uber, Lift, Taxi, etc.
    """

    def __init__(self, vehicle_id: str, vehicle_type: str, start_location: str, end_location: str,
                 current_location: str, eta: int, network_dropout_threshold: 50):
        super().__init__(vehicle_id, vehicle_type)
        self._start_location: str = start_location
        self._end_location: str = end_location
        self._current_location: str = current_location
        self._eta: int = eta
        self._network_dropout_threshold: int = network_dropout_threshold
        self._status: str = Status.ACTIVE
        self._progress: float = 0.0
        self._in_network_dropout: bool = False
        self._location: tuple[float, float] = get_coordinates_for_stop(self._current_location)

    def _movement_step(self, last_tcp_timestamp: float) -> float:
        """
        Moves the vehicle along its route and sends status updates.
        :param last_tcp_timestamp: The timestamp of the last TCP message sent.
        :return: The timestamp after movement.
        """
        last_tcp_time: float = last_tcp_timestamp

        # send initial status
        self.send_status_update()

        # drive until complete
        while self.running and self._progress < 100.0:
            now: float = time.time()
            # Send TCP status update relatively infrequently
            if now - last_tcp_time > 30 or self._progress % 20 == 0:  # Every 30 seconds or 20% progress
                self.send_status_update()
                last_tcp_time = now

            # Perform one progress step
            pause: float = self._progress_generator()
            lat, long = self._location
            self.send_udp_beacon(lat, long, eta=self._eta)
            self.logger.log(
                f"[UDP] At {self._current_location} | Progress: {self._progress}% | Location: ({lat:.4f}, {long:.4f}) | ETA: {self._eta} min")
            time.sleep(pause)
        # Completion
        if self._progress >= 100:
            self._on_completion()
        return last_tcp_time

    @abstractmethod
    def _progress_generator(self) -> float:
        """
        Generates progress updates for the vehicle.
        :return: Pause duration in seconds before the next update.
        """
        pass

    @abstractmethod
    def _on_completion(self) -> None:
        """
        Defines the behavior when the vehicle reaches its destination.
        :return: None
        """
        pass
