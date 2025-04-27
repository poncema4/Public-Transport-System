import pytest
from unittest.mock import MagicMock, patch
from vehicles.uber import UberClient
from common.config import Status, VehicleType, Command, UBER_START, UBER_END


@pytest.fixture
def test_uber():
    with patch('random.randint', return_value=5), \
            patch('common.utils.get_coordinates_for_stop', return_value=(40.7128, -74.0060)):
        uber = UberClient("U123")
        uber.logger = MagicMock()
        uber.udp_socket = MagicMock()
        uber.tcp_socket = MagicMock()
        yield uber


def test_initialization_default_id():
    with patch('random.randint', return_value=999):
        uber = UberClient()
        assert uber.vehicle_id == "U999"
        assert uber.vehicle_type == VehicleType.UBER


def test_initialization_with_id(test_uber):
    assert test_uber.vehicle_id == "U123"
    assert test_uber.vehicle_type == VehicleType.UBER
    assert test_uber._start_location == UBER_START
    assert test_uber._end_location == UBER_END
    assert test_uber._current_location == "Near NYU"
    assert test_uber._eta == 5
    assert test_uber._network_dropout_threshold == 50
    assert test_uber._status == Status.ACTIVE


def test_progress_generator_normal(test_uber):
    test_uber._progress = 30  # Below dropout threshold
    with patch('random.random', return_value=0.5), \
            patch('random.randint', return_value=3):
        pause = test_uber._progress_generator()

        assert test_uber._progress == 33
        assert test_uber.eta == 10  # 15 * (100-33)/100 ≈ 10.05 → max(1, 10)
        assert pause == 5
        assert test_uber.current_location in [
            "Near NYU", "Greenwich Village", "Union Square",
            "Near Flatiron", "Near Bryant Park", "Midtown",
            "Columbus Circle", "Upper West Side", "Near Columbia University"
        ]


def test_progress_generator_dropout(test_uber):
    test_uber._progress = 50  # At dropout threshold
    test_uber.logger.log = MagicMock()
    with patch('random.random', return_value=0.9):
        pause = test_uber._progress_generator()

        assert pause == 5
        test_uber.logger.log.assert_called_with(
            "Simulating network dropout near Lincoln Tunnel",
            also_print=True
        )


def test_on_completion(test_uber):
    test_uber._end_location = "Airport"
    test_uber.send_status_update = MagicMock()
    test_uber.logger.log = MagicMock()

    test_uber._on_completion()

    assert test_uber.status == Status.ON_TIME
    assert test_uber.running is False
    test_uber.send_status_update.assert_called_once()
    test_uber.udp_socket.sendto.assert_called_once()
    test_uber.logger.log.assert_called_with(
        "Uber U123 reached destination: Airport",
        also_print=True
    )


def test_handle_command_shutdown(test_uber):
    test_uber.send_command_rejected = MagicMock()
    test_uber.log_event = MagicMock()

    test_uber.handle_command({"command": Command.SHUTDOWN})

    test_uber.send_command_rejected.assert_called_with(
        Command.SHUTDOWN,
        "Cannot shutdown/cancel private ride"
    )
    test_uber.log_event.assert_called_with(
        "COMMAND_FAILURE",
        "Cannot shutdown/cancel private ride"
    )


def test_handle_command_unknown(test_uber):
    test_uber.send_command_rejected = MagicMock()

    test_uber.handle_command({"command": "UNKNOWN"})

    test_uber.send_command_rejected.assert_called_with(
        "UNKNOWN",
        "Unknown or unsupported command"
    )


def test_execute_method(test_uber):
    # Should do nothing but not raise errors
    test_uber.execute("some_command", {"param": "value"})
    # No assertions needed since method is empty