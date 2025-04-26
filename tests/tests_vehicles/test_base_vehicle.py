import json
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from common.utils import normalize_whitespace

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from vehicles.base_vehicle import Vehicle, Status, MessageType, VehicleType
from common.config import TCP_SERVER_HOST, TCP_SERVER_PORT, UDP_SERVER_PORT


# Create a concrete subclass for testing
class TestVehicle(Vehicle):
    def _movement_step(self, last_tcp_timestamp: float) -> float:
        # Simple implementation for testing
        return time.time()


@pytest.fixture
def test_vehicle():
    with patch('socket.socket'), \
            patch('sqlite3.connect'), \
            patch('vehicles.base_vehicle.get_formatted_coords', return_value=(40.7128, -74.0060)):
        vehicle = TestVehicle("test_vehicle", VehicleType.BUS)
        vehicle.logger = MagicMock()
        yield vehicle


def test_initialization(test_vehicle):
    assert test_vehicle.vehicle_id == "test_vehicle"
    assert test_vehicle.vehicle_type == "Bus"
    assert test_vehicle.status == Status.ON_TIME
    assert test_vehicle.running is True
    assert test_vehicle.location == (40.7128, -74.0060)
    assert test_vehicle.server_shutdown_detected is False


def test_init_database(test_vehicle):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch('sqlite3.connect', return_value=mock_conn):
        test_vehicle.init_database()

        # Verify tables were created
        assert mock_cursor.execute.call_count == 3
        calls = [call[0][0] for call in mock_cursor.execute.call_args_list]
        assert "CREATE TABLE IF NOT EXISTS location_updates" in calls[0]
        assert "CREATE TABLE IF NOT EXISTS admin_commands" in calls[1]
        assert "CREATE TABLE IF NOT EXISTS event_logs" in calls[2]
        mock_conn.commit.assert_called_once()


def test_log_location_update(test_vehicle):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch('sqlite3.connect', return_value=mock_conn):
        test_vehicle.log_location_update(40.7128, -74.0060, "online", 30.5)

        mock_cursor.execute.assert_called_once_with(
            normalize_whitespace("""
            INSERT INTO location_updates (vehicle_id, lat, long, speed, timestamp, network_status)
            VALUES (?, ?, ?, ?, datetime('now'), ?)
            """),
            ("test_vehicle", 40.7128, -74.0060, 30.5, "online")
        )
        mock_conn.commit.assert_called_once()


def test_log_event(test_vehicle):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch('sqlite3.connect', return_value=mock_conn):
        test_vehicle.log_event("test_event", "test_details")

        mock_cursor.execute.assert_called_once_with(
            normalize_whitespace("INSERT INTO event_logs (event_type, details, timestamp) VALUES (?, ?, datetime('now'))"),
            ("test_event", "test_details")
        )
        mock_conn.commit.assert_called_once()


def test_send_udp_beacon(test_vehicle):
    mock_socket = MagicMock()
    test_vehicle.udp_socket = mock_socket

    with patch('vehicles.base_vehicle.get_current_time_string', return_value="2023-01-01 12:00:00"):
        test_vehicle.send_udp_beacon(40.7128, -74.0060, "stop1", 5)

        expected_message = {
            "type": MessageType.LOCATION_UPDATE,
            "vehicle_id": "test_vehicle",
            "vehicle_type": "Bus",
            "status": Status.ON_TIME,
            "location": {"lat": 40.7128, "long": -74.0060},
            "timestamp": "2023-01-01 12:00:00",
            "next_stop": "stop1",
            "eta": 5
        }

        mock_socket.sendto.assert_called_once_with(
            json.dumps(expected_message).encode(),
            (TCP_SERVER_HOST, UDP_SERVER_PORT)
        )


def test_connect_to_server_success(test_vehicle):
    mock_socket = MagicMock()
    test_vehicle.tcp_socket = mock_socket

    with patch('socket.socket', return_value=mock_socket), \
            patch('time.sleep'):
        result = test_vehicle.connect_to_server()

        assert result is True
        mock_socket.connect.assert_called_once_with((TCP_SERVER_HOST, TCP_SERVER_PORT))
        mock_socket.send.assert_called_once()


def test_connect_to_server_failure(test_vehicle):
    mock_socket = MagicMock()
    # Use OSError instead of socket.error
    mock_socket.connect.side_effect = OSError("Connection failed")
    test_vehicle.tcp_socket = mock_socket

    with patch('socket.socket', return_value=mock_socket), \
            patch('time.sleep'):
        result = test_vehicle.connect_to_server()

        assert result is False
        assert test_vehicle.running is False


def test_handle_command(test_vehicle):
    mock_socket = MagicMock()
    test_vehicle.tcp_socket = mock_socket

    command_message = {
        "type": MessageType.COMMAND,
        "command": "test_command"
    }

    test_vehicle.handle_command(command_message)

    # Verify the socket received the expected data
    expected_response = {
        "type": MessageType.COMMAND_ACK,
        "vehicle_id": test_vehicle.vehicle_id,
        "command": "test_command",
        "message": "Acknowledged",
        "status": test_vehicle.status
    }

    mock_socket.send.assert_called_once_with(
        json.dumps(expected_response).encode()
    )


def test_send_status_update(test_vehicle):
    mock_socket = MagicMock()
    test_vehicle.tcp_socket = mock_socket
    test_vehicle.location = (40.7128, -74.0060)

    with patch('vehicles.base_vehicle.get_current_time_string', return_value="2023-01-01 12:00:00"), \
            patch('datetime.datetime') as mock_datetime:
        mock_datetime.now.return_value.strftime.return_value = "12:00"

        test_vehicle.send_status_update()

        expected_message = {
            "type": MessageType.STATUS_UPDATE,
            "vehicle_id": "test_vehicle",
            "vehicle_type": "Bus",
            "status": Status.ON_TIME,
            "location": {"lat": 40.7128, "long": -74.0060},
            "timestamp": "2023-01-01 12:00:00",
            "network_status": Status.ON_TIME
        }

        mock_socket.send.assert_called_once_with(json.dumps(expected_message).encode())


def test_close(test_vehicle):
    tcp_mock = MagicMock()
    udp_mock = MagicMock()
    test_vehicle.logger.log = MagicMock()
    test_vehicle.tcp_socket = tcp_mock
    test_vehicle.udp_socket = udp_mock

    test_vehicle.close()

    assert test_vehicle.running is False
    tcp_mock.close.assert_called_once()
    udp_mock.close.assert_called_once()
    test_vehicle.logger.log.assert_called_with("Client shutting down", also_print=True)


def test_simulate_movement(test_vehicle):
    test_vehicle._check_connection = MagicMock(side_effect=[True, True, False])
    test_vehicle._handle_delay = MagicMock(return_value=False)
    test_vehicle._pre_step = MagicMock()
    test_vehicle._movement_step = MagicMock(return_value=time.time())
    test_vehicle._post_step = MagicMock()

    test_vehicle.simulate_movement()

    assert test_vehicle._pre_step.call_count == 2
    assert test_vehicle._movement_step.call_count == 2
    assert test_vehicle._post_step.call_count == 2


def test_handle_delay(test_vehicle):
    # Test when not delayed
    assert test_vehicle._handle_delay() is False

    # Test when delayed but time hasn't passed
    test_vehicle.is_delayed = True
    test_vehicle.delay_until = time.time() + 10
    assert test_vehicle._handle_delay() is True

    # Test when delayed and time has passed
    test_vehicle.is_delayed = True
    test_vehicle.delay_until = time.time() - 1
    assert test_vehicle._handle_delay() is False
    assert test_vehicle.is_delayed is False
