import datetime
from unittest.mock import MagicMock, patch

import pytest

from common.config import Status, VehicleType, Command, SHUTTLE_ROUTE
from common.utils import get_coordinates_for_stop
from vehicles.shuttle import ShuttleClient


@pytest.fixture
def test_shuttle():
    with patch('random.randint', return_value=42), \
            patch('random.uniform', return_value=35.0), \
            patch('common.utils.get_coordinates_for_stop', return_value=(40.7128, -74.0060)):
        shuttle = ShuttleClient("S42")
        shuttle.logger = MagicMock()
        shuttle.udp_socket = MagicMock()
        shuttle.tcp_socket = MagicMock()
        yield shuttle


def test_initialization_default_id():
    with patch('random.randint', return_value=99):
        shuttle = ShuttleClient()
        assert shuttle.vehicle_id == "S99"
        assert shuttle.vehicle_type == VehicleType.SHUTTLE


def test_initialization_with_id(test_shuttle):
    assert test_shuttle.vehicle_id == "S42"
    assert test_shuttle.vehicle_type == VehicleType.SHUTTLE
    assert test_shuttle._route == SHUTTLE_ROUTE.copy()
    assert test_shuttle.status == Status.ON_TIME
    assert test_shuttle.start_time == "08:00"
    assert test_shuttle.is_active is False
    assert test_shuttle.location == get_coordinates_for_stop(test_shuttle._route[0])


def test_passive_mode_detection(test_shuttle):
    assert test_shuttle._in_passive_mode() is True  # Starts in standby
    test_shuttle.is_active = True
    assert test_shuttle._in_passive_mode() is False


def test_simulate_passive_behavior(test_shuttle):
    with patch('time.sleep') as mock_sleep:
        test_shuttle.logger.log = MagicMock()
        test_shuttle._simulate_passive()

        test_shuttle.udp_socket.sendto.assert_called_once()
        test_shuttle.logger.log.assert_any_call("[UDP] Passive beacon from S42")
        mock_sleep.assert_called_once_with(10)


def test_progress_generator(test_shuttle):
    with patch('time.time', side_effect=[0, 0, 5, 10, 15, 20, 25, 30]):
        gen = test_shuttle._progress_generator()

        assert next(gen) == (0, 5)
        assert next(gen) == (16, 5)
        assert next(gen) == (33, 5)
        assert next(gen) == (50, 5)
        assert next(gen) == (66, 5)
        assert next(gen) == (83, 5)
        assert next(gen) == (100, 5)

        with pytest.raises(StopIteration):
            next(gen)




def test_on_arrival_behavior(test_shuttle):
    test_shuttle.notify_observers = MagicMock()
    test_shuttle.logger.log = MagicMock()
    test_shuttle._current_stop_index = 1
    test_shuttle._next_stop = "Stop C"

    test_shuttle._on_arrival("Stop B")

    test_shuttle.notify_observers.assert_called_once_with(
        "ARRIVAL",
        "Shuttle S42 arrived at Stop B"
    )
    test_shuttle.logger.log.assert_called_with(
        "Arrived at Stop B, next stop Stop C"
    )


from freezegun import freeze_time

@freeze_time("2025-01-01 09:30:00")
def test_on_arrival_complete_route(test_shuttle):
    test_shuttle.logger.log = MagicMock()
    test_shuttle._current_stop_index = 0
    test_shuttle.is_active = True
    test_shuttle.status = Status.ACTIVE
    test_shuttle.next_departure_time = "09:00"

    test_shuttle._on_arrival("Terminal")

    assert test_shuttle.is_active is False
    assert test_shuttle.status == Status.STANDBY
    test_shuttle.logger.log.assert_any_call(
        "Shuttle S42 completed route, returning to standby",
        also_print=True
    )



def test_pre_step_activation(test_shuttle):
    test_shuttle.is_active = False
    test_shuttle.logger.log = MagicMock()

    with patch('datetime.datetime') as mock_datetime:
        mock_datetime.now.return_value.strftime.return_value = "08:01"

        test_shuttle._pre_step()

        assert test_shuttle.is_active is True
        assert test_shuttle.status == Status.ACTIVE
        test_shuttle.logger.log.assert_called_with(
            "Scheduled start (08:00) reached; activating S42",
            also_print=True
        )


def test_handle_command_start_route(test_shuttle):
    test_shuttle.execute = MagicMock()
    test_shuttle.send_command_ack = MagicMock()

    with patch('datetime.datetime') as mock_datetime:
        mock_datetime.now.return_value.strftime.return_value = "08:01"

        test_shuttle.handle_command({"command": Command.START_ROUTE})

        test_shuttle.execute.assert_called_with(Command.START_ROUTE)
        test_shuttle.send_command_ack.assert_called_with(
            Command.START_ROUTE,
            "Starting route"
        )


def test_handle_command_delay(test_shuttle):
    test_shuttle.execute = MagicMock()
    test_shuttle.send_command_ack = MagicMock()

    test_shuttle.handle_command({
        "command": Command.DELAY,
        "params": {"duration": 60}
    })

    test_shuttle.execute.assert_called_with(
        Command.DELAY,
        {"duration": 60}
    )
    test_shuttle.send_command_ack.assert_called_with(
        Command.DELAY,
        "Delayed for 60 seconds"
    )


def test_execute_shutdown(test_shuttle):
    test_shuttle.logger.log = MagicMock()
    test_shuttle.running = True
    test_shuttle.execute(Command.SHUTDOWN)
    assert test_shuttle.running is False
    test_shuttle.logger.log.assert_called_with("Shuttle shutting down")