import os
import sys
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from base_vehicle import Vehicle
from abc import ABC, abstractmethod
from common.config import Status
from common.utils import get_coordinates_for_stop


class PointToPointVehicle(Vehicle, ABC):
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
        self._in_network: bool = False
        self._location: tuple[float, float] = get_coordinates_for_stop(self._current_location)