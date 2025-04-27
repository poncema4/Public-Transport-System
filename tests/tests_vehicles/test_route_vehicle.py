import json

import pytest
from unittest.mock import MagicMock, patch, call
import time
from vehicles.route_vehicle import RouteVehicle
from common.config import Status, TCP_SERVER_HOST, UDP_SERVER_PORT


# Create a concrete test subclass
class TestRouteVehicle(RouteVehicle):
    def _progress_generator(self):
        # Simulate movement in 20% increments with 0.1s pauses
        for progress in [20, 40, 60, 80, 100]:
            yield progress, 0.1

    def _on_arrival(self, arrived_stop: str) -> None:
        self.logger.log(f"Arrived at {arrived_stop}")
        if arrived_stop == "Terminus":
            self._status = Status.ACTIVE


@pytest.fixture
def test_vehicle():
    with patch('common.utils.get_coordinates_for_stop', return_value=(40.7128, -74.0060)):
        vehicle = TestRouteVehicle(
            vehicle_id="bus_123",
            vehicle_type="Bus",
            route=["Stop A", "Stop B", "Terminus"],
            status=Status.ACTIVE
        )
        vehicle.logger = MagicMock()
        vehicle.udp_socket = MagicMock()
        vehicle.tcp_socket = MagicMock()
        yield vehicle


def test_initialization(test_vehicle):
    assert test_vehicle._route == ["Stop A", "Stop B", "Terminus"]
    assert test_vehicle._current_stop_index == 0
    assert test_vehicle._next_stop == "Stop B"
    assert test_vehicle._status == Status.ACTIVE
    assert test_vehicle._is_delayed is False


def test_movement_step_progression(test_vehicle):
    test_vehicle.running = True
    test_vehicle.send_status_update = MagicMock()

    with patch('time.sleep') as mock_sleep, \
            patch('common.utils.calculate_realistic_movement',
                  side_effect=[(40.7130, -74.0060), (40.7135, -74.0065)]):
        last_tcp = test_vehicle._movement_step(time.time())

        # Verify movement progression
        assert test_vehicle._current_stop_index == 1  # Moved to next stop
        assert test_vehicle.send_status_update.call_count >= 1

        # Verify UDP beacons were sent
        assert test_vehicle.udp_socket.sendto.call_count > 0

        # Verify sleep was called between steps
        assert mock_sleep.call_count == 4


def test_arrival_behavior(test_vehicle):
    test_vehicle.logger.log = MagicMock()
    test_vehicle.running = True
    test_vehicle._current_stop_index = 1  # At Stop B heading to Terminus

    test_vehicle._movement_step(time.time())

    # Verify arrival handling
    assert test_vehicle._current_stop_index == 2  # At Terminus
    test_vehicle.logger.log.assert_called_with("Arrived at Terminus")
    assert test_vehicle._status == Status.ACTIVE


def test_passive_mode_handling(test_vehicle):
    # Override passive mode detection
    test_vehicle._in_passive_mode = lambda: True
    test_vehicle._simulate_passive = MagicMock()

    test_vehicle.send_status_update = MagicMock()

    last_tcp = test_vehicle._movement_step(time.time())

    test_vehicle._simulate_passive.assert_called_once()
    assert test_vehicle.send_status_update.call_count == 0  # No active updates


def test_route_completion_cycle(test_vehicle):
    test_vehicle.running = True
    test_vehicle._route = ["Stop A", "Stop B"]

    # First leg
    test_vehicle._movement_step(time.time())
    assert test_vehicle._current_stop_index == 1

    # Second leg should loop back to start
    test_vehicle._movement_step(time.time())
    assert test_vehicle._current_stop_index == 0

def test_early_termination(test_vehicle):
    test_vehicle.running = True

    # Simulate external shutdown during movement
    def progress_gen():
        yield 20, 0.1
        test_vehicle.running = False
        yield 40, 0.1

    test_vehicle._progress_generator = progress_gen
    test_vehicle._movement_step(time.time())

    assert test_vehicle._current_stop_index == 0  # Didn't complete movement
