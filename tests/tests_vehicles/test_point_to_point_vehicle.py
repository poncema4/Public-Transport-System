import os, sys

from common.config import TCP_SERVER_HOST, UDP_SERVER_PORT
from common.utils import get_coordinates_for_stop, get_current_time_string

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

import pytest
from unittest.mock import MagicMock, patch, call
import time
import json
from vehicles.point_to_point_vehicle import PointToPointVehicle, Status


# Create a concrete test subclass
class TestPointToPointVehicle(PointToPointVehicle):
    def _progress_generator(self) -> float:
        self._progress += 10
        self._eta = max(0, self._eta - 1)
        return 0.1  # Short pause for testing

    def _on_completion(self) -> None:
        self._status = Status.ON_TIME
        self.running = False


@pytest.fixture
def test_vehicle():
    with patch('common.utils.get_coordinates_for_stop', return_value=(40.7128, -74.0060)):
        vehicle = TestPointToPointVehicle(
            vehicle_id="test_123",
            vehicle_type="Uber",
            start_location="Downtown",
            end_location="Airport",
            current_location="Midtown",
            eta=30,
            network_dropout_threshold=50
        )
        vehicle.logger = MagicMock()
        vehicle.udp_socket = MagicMock()
        vehicle.tcp_socket = MagicMock()
        yield vehicle


def test_initialization(test_vehicle):
    assert test_vehicle._start_location == "Downtown"
    assert test_vehicle._end_location == "Airport"
    assert test_vehicle._current_location == "Midtown"
    assert test_vehicle._eta == 30
    assert test_vehicle._network_dropout_threshold == 50
    assert test_vehicle._status == Status.ACTIVE
    assert test_vehicle._progress == 0.0
    assert test_vehicle._in_network_dropout is False
    assert test_vehicle._location == get_coordinates_for_stop("Midtown")


def test_movement_step_progress(test_vehicle):
    test_vehicle.running = True
    test_vehicle.send_status_update = MagicMock()

    with patch('time.sleep') as mock_sleep:
        last_tcp = test_vehicle._movement_step(time.time())

        # Verify progress was made
        assert test_vehicle._progress > 0
        assert test_vehicle._eta < 30

        # Verify status updates were sent
        assert test_vehicle.send_status_update.call_count >= 1

        # Verify UDP beacons were sent
        assert test_vehicle.udp_socket.sendto.call_count > 0

        # Verify sleep was called between steps
        assert mock_sleep.call_count > 0


def test_movement_step_completion(test_vehicle):
    test_vehicle.running = True
    test_vehicle._progress = 90

    last_tcp = test_vehicle._movement_step(time.time())

    assert test_vehicle._progress >= 100
    assert test_vehicle._status == Status.ON_TIME
    assert test_vehicle.running is False


def test_udp_beacon_sending(test_vehicle):
    test_vehicle.send_udp_beacon(40.7128, -74.0060, eta=15)

    expected_message = {
        "type": "LOCATION_UPDATE",
        "vehicle_id": "test_123",
        "vehicle_type": "Uber",
        "status": Status.ON_TIME,
        "location": {"lat": 40.7128, "long": -74.0060},
        "timestamp": get_current_time_string(),
        "eta": 15
    }

    test_vehicle.udp_socket.sendto.assert_called_once_with(
        json.dumps(expected_message).encode(),
        (TCP_SERVER_HOST, UDP_SERVER_PORT)
    )


def test_progress_generator_implementation():
    # Test the concrete implementation
    vehicle = TestPointToPointVehicle(
        "test_123", "Uber", "A", "B", "C", 10, 50
    )

    pause = vehicle._progress_generator()
    assert pause == 0.1
    assert vehicle._progress == 10
    assert vehicle._eta == 9


def test_on_completion_implementation():
    vehicle = TestPointToPointVehicle(
        "test_123", "Uber", "A", "B", "C", 10, 50
    )
    vehicle._on_completion()
    assert vehicle._status == Status.ON_TIME