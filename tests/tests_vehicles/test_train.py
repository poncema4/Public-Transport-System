from unittest.mock import patch, MagicMock

import pytest

from common.config import Status, Command
from vehicles.train import TrainClient


@pytest.fixture
def test_train():
    train = TrainClient(vehicle_id="T42")
    train.logger = MagicMock()
    train.notify_observers = MagicMock()
    return train

def test_initialization_defaults():
    train = TrainClient()
    assert train.vehicle_id.startswith("T")
    assert train._status == Status.ON_TIME
    assert 2 <= train.eta <= 8
    assert train.is_shutdown is False
    assert train.running is True

def test_in_passive_mode(test_train):
    test_train.is_shutdown = False
    assert test_train._in_passive_mode() is False
    test_train.is_shutdown = True
    assert test_train._in_passive_mode() is True

def test_simulate_passive_mode(test_train):
    test_train.logger.log = MagicMock()
    test_train._TrainClient__standby_reported = False
    with patch('time.sleep') as mock_sleep:
        test_train._simulate_passive()
        test_train.logger.log.assert_called_with("Train is in standby mode", also_print=True)
        mock_sleep.assert_called_with(5)

def test_progress_generator(test_train):
    with patch('time.time', side_effect=[0, 5, 10, 15]):
        gen = test_train._progress_generator()
        progress1, pause1 = next(gen)
        assert 0 <= progress1 <= 40
        progress2, pause2 = next(gen)
        assert 30 <= progress2 <= 70
        progress3, pause3 = next(gen)
        assert 66 <= progress3 <= 100
        with pytest.raises(StopIteration):
            next(gen)

def test_on_arrival(test_train):
    test_train.logger.log = MagicMock()
    test_train.notify_observers = MagicMock()
    test_train._route = ["Stop A", "Stop B", "Stop C"]
    test_train._current_stop_index = 0
    test_train._next_stop = "Stop B"

    with patch('random.randint', return_value=7):
        test_train._on_arrival("Stop B")
        test_train.notify_observers.assert_called_with(
            "ARRIVAL", "Train T42 arrived at Stop B"
        )
        test_train.logger.log.assert_any_call("Train T42 arrived at Stop B", also_print=True)
        assert test_train._current_stop_index == 1
        assert test_train._next_stop == "Stop C"
        assert test_train.eta == 7
        assert test_train._TrainClient__standby_reported is False

def test_handle_command_delay(test_train):
    message = {"command": Command.DELAY, "params": {"duration": 60}}
    with patch.object(test_train, 'execute') as mock_exec, \
         patch.object(test_train, 'send_command_ack') as mock_ack:
        test_train.handle_command(message)
        mock_exec.assert_called_with(Command.DELAY, {"duration": 60})
        mock_ack.assert_called_with(Command.DELAY, "Delayed for 60 seconds")

def test_handle_command_shutdown(test_train):
    message = {"command": Command.SHUTDOWN}
    with patch.object(test_train, 'execute') as mock_exec, \
         patch.object(test_train, 'send_command_ack') as mock_ack:
        test_train.handle_command(message)
        mock_exec.assert_called_with(Command.SHUTDOWN)
        mock_ack.assert_called_with(Command.SHUTDOWN, "Entering standby mode")

def test_handle_command_reroute(test_train):
    message = {"command": Command.REROUTE}
    with patch.object(test_train, 'execute') as mock_exec, \
         patch.object(test_train, 'send_command_ack') as mock_ack:
        test_train.handle_command(message)
        mock_exec.assert_called_with(Command.REROUTE)
        mock_ack.assert_called_with(Command.REROUTE, "Route changed")

def test_handle_command_start_route_when_shutdown(test_train):
    test_train.is_shutdown = True
    message = {"command": Command.START_ROUTE}
    with patch.object(test_train, 'execute') as mock_exec, \
         patch.object(test_train, 'send_command_ack') as mock_ack:
        test_train.handle_command(message)
        mock_exec.assert_called_with(Command.START_ROUTE)
        mock_ack.assert_called_with(Command.START_ROUTE, "Resuming route")

def test_handle_command_start_route_when_active(test_train):
    test_train.is_shutdown = False
    message = {"command": Command.START_ROUTE}
    with patch.object(test_train, 'send_command_ack') as mock_ack:
        test_train.handle_command(message)
        mock_ack.assert_called_with(Command.START_ROUTE, "Already active")

def test_handle_command_invalid(test_train):
    message = {"command": "INVALID"}
    with patch.object(test_train, 'send_command_rejected') as mock_rejected:
        test_train.handle_command(message)
        mock_rejected.assert_called_with("INVALID", "Unknown command")

def test_execute_delay_command(test_train):
    test_train.logger.log = MagicMock()
    with patch('time.time', return_value=1000):
        test_train.execute(Command.DELAY, {"duration": 60})
        assert test_train._is_delayed is True
        assert test_train._status == Status.DELAYED
        assert test_train._delay_until == 1060
        test_train.logger.log.assert_called_with("Train delayed for 60 seconds")

def test_execute_shutdown_command(test_train):
    test_train.logger.log = MagicMock()
    test_train.execute(Command.SHUTDOWN)
    assert test_train.is_shutdown is True
    assert test_train._status == Status.STANDBY
    test_train.logger.log.assert_called_with("Train entering standby mode")

def test_execute_reroute_command(test_train):
    test_train._route = ["Start", "Middle1", "Middle2", "End"]
    test_train.execute(Command.REROUTE)
    # Just check if the middle elements are shuffled
    assert test_train._route[0] == "Start"
    assert test_train._route[-1] == "End"
    assert set(test_train._route[1:-1]) == {"Middle1", "Middle2"}

def test_execute_reroute_too_short(test_train):
    test_train.logger.log = MagicMock()
    test_train._route = ["Start", "End"]
    test_train.execute(Command.REROUTE)
    test_train.logger.log.assert_called_with("Route too short to reroute")

def test_execute_start_route(test_train):
    test_train.logger.log = MagicMock()
    test_train.is_shutdown = True
    test_train.execute(Command.START_ROUTE)
    assert test_train.is_shutdown is False
    assert test_train._status == Status.ON_TIME
    test_train.logger.log.assert_called_with("Train resuming route")
