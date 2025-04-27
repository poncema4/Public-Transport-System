from unittest.mock import MagicMock, patch

import pytest

from common.config import Status, VehicleType, Command, BUS_ROUTE
from common.utils import get_coordinates_for_stop
from vehicles.bus import BusClient


@pytest.fixture
def test_bus():
    with patch('random.randint', return_value=42), \
            patch('random.uniform', return_value=20.0), \
            patch('common.utils.get_coordinates_for_stop', return_value=(40.7128, -74.0060)):
        bus = BusClient("B42")
        bus.logger = MagicMock()
        bus.udp_socket = MagicMock()
        bus.tcp_socket = MagicMock()
        yield bus


def test_initialization_default_id():
    with patch('random.randint', side_effect=[999, 3]):  # First for ID, second for ETA
        bus = BusClient()
        assert bus.vehicle_id == "B999"
        assert bus.vehicle_type == VehicleType.BUS


def test_initialization_with_id(test_bus):
    assert test_bus.vehicle_id == "B42"
    assert test_bus.vehicle_type == VehicleType.BUS
    assert test_bus._route == BUS_ROUTE.copy()
    assert test_bus.status == Status.ON_TIME
    assert test_bus.eta == 42
    assert test_bus.location == get_coordinates_for_stop(test_bus._route[0])


def test_progress_generator(test_bus):
    test_bus.send_status_update = MagicMock()
    test_bus.running = True
    with patch('random.uniform', return_value=5.0):
        gen = test_bus._progress_generator()

        # First few progress points
        assert next(gen) == (5.0, 3)
        assert next(gen) == (10.0, 3)
        assert next(gen) == (15.0, 3)

        # Verify status update is sent every 3 iterations
        test_bus.send_status_update.assert_called_once()


def test_on_arrival_normal(test_bus):
    test_bus.notify_observers = MagicMock()
    test_bus._current_stop_index = 2
    test_bus._route = ["Stop A", "Stop B", "Stop C"]

    with patch('random.random', return_value=0.6):  # No congestion
        test_bus._on_arrival("Stop B")

        assert test_bus._current_stop_index == 2
        assert test_bus.status == Status.ON_TIME
        test_bus.notify_observers.assert_called_with(
            "ARRIVAL",
            "Bus B42 arrived at Stop B"
        )


def test_on_arrival_congestion(test_bus):
    test_bus.logger.log = MagicMock()
    test_bus._current_stop_index = 1
    test_bus._route = ["Stop A", "Union Square", "Stop C"]
    test_bus._eta = 42

    with patch('random.random', return_value=0.4), \
         patch('random.randint', return_value=5):  # patch eta reset too

        test_bus._on_arrival("Union Square")

        assert test_bus.status == Status.DELAYED
        test_bus.logger.log.assert_any_call("Experiencing congestion at Union Square")



def test_handle_command_delay(test_bus):
    test_bus.execute = MagicMock()
    test_bus.send_command_ack = MagicMock()

    test_bus.handle_command({
        "command": Command.DELAY,
        "params": {"duration": 60}
    })

    test_bus.execute.assert_called_with(Command.DELAY, {"duration": 60})
    test_bus.send_command_ack.assert_called_with(
        Command.DELAY,
        "Delayed for 60 seconds"
    )


def test_handle_command_reroute(test_bus):
    test_bus.execute = MagicMock()
    test_bus.send_command_ack = MagicMock()

    test_bus.handle_command({"command": Command.REROUTE})

    test_bus.execute.assert_called_with(Command.REROUTE)
    test_bus.send_command_ack.assert_called_with(
        Command.REROUTE,
        "Route changed"
    )


def test_execute_delay(test_bus):
    test_bus.logger.log = MagicMock()
    with patch('time.time', return_value=1000):
        test_bus.execute(Command.DELAY, {"duration": 30})

        assert test_bus._is_delayed is True
        assert test_bus._status == Status.DELAYED
        assert test_bus._delay_until == 1030
        test_bus.logger.log.assert_called_with("Bus delayed for 30 seconds")


def test_execute_reroute(test_bus):
    test_bus.logger.log = MagicMock()
    original_route = test_bus._route.copy()
    with patch('random.shuffle') as mock_shuffle:
        mock_shuffle.side_effect = lambda x: x.reverse()
        test_bus.execute(Command.REROUTE)

        assert test_bus._route[0] == original_route[0]
        assert test_bus._route[-1] == original_route[-1]
        test_bus.logger.log.assert_called_with(
            f"Bus rerouted: {' -> '.join(test_bus._route)}"
        )