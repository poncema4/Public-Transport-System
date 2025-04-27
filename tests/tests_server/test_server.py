import json
import sqlite3
import threading
from unittest.mock import MagicMock, patch

import pytest

from common.config import MessageType, Command
from server.server import CommandHandler, LogObserver, TransportServer


def test_command_handler_to_dict():
    command = CommandHandler(command_type="DELAY", params={"duration": 30})
    command_dict = command.to_dict()

    assert command_dict["type"] == MessageType.COMMAND
    assert command_dict["command"] == "DELAY"
    assert command_dict["params"] == {"duration": 30}
    assert isinstance(command_dict["timestamp"], str)
    assert command_dict["timestamp"] != ""

def test_command_handler_default_params():
    command = CommandHandler(command_type="REROUTE")
    command_dict = command.to_dict()

    assert command_dict["command"] == "REROUTE"
    assert command_dict["params"] == {}

def test_log_observer_update_logs_event():
    logger_mock = MagicMock()
    observer = LogObserver(logger=logger_mock)

    observer.update(event="VEHICLE_CONNECTED", data="Bus B123")

    logger_mock.log.assert_called_once_with("[LOG] VEHICLE_CONNECTED: Bus B123")

def test_transport_server_init():
        server = TransportServer()

        # Basic attribute checks
        assert server.running is True
        assert isinstance(server.vehicle_registry, dict)
        assert isinstance(server.vehicle_types, dict)
        assert isinstance(server.lock, type(threading.Lock()))
        assert isinstance(server.db_lock, type(threading.Lock()))
        assert server.log_observer in server._observers

@pytest.fixture
def server_instance():
    with patch("server.server.sqlite3.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        server = TransportServer()

        # Reset call history AFTER __init__ finished (important!)
        mock_conn.reset_mock()
        mock_cursor.reset_mock()

        yield server, mock_connect, mock_conn, mock_cursor


def test_init_routes(server_instance):
    server, mock_connect, mock_conn, mock_cursor = server_instance

    # Clear call history because __init__ already called init_routes once
    mock_cursor.reset_mock()

    server.init_routes()

    expected_routes = [
        ("BUS_ROUTE", "Port Authority Terminal", "Wall Street", "Port Authority Terminal,Times Square,Flatiron,Union Square,Wall Street"),
        ("TRAIN_ROUTE", "Queens Plaza", "Middle Village", "Queens Plaza,Herald Square,Delancey St,Middle Village"),
        ("SHUTTLE_ROUTE", "Penn Station", "JFK Airport", "Penn Station,JFK Airport"),
        ("UBER_ROUTE", "Washington Square", "Columbia University", "Washington Square,Greenwich Village,Union Square,Near Flatiron,Near Bryant Park,Midtown,Columbus Circle,Upper West Side,Near Columbia University")
    ]

    mock_cursor.executemany.assert_called_once_with(
        """
                               INSERT
                               OR IGNORE INTO routes (route_id, origin, destination, stop_sequence)
                VALUES (?, ?, ?, ?)
                               """, expected_routes
    )
    mock_conn.commit.assert_called_once()
    mock_conn.close.assert_called_once()

def test_log_admin_command(server_instance):
    server, mock_connect, mock_conn, mock_cursor = server_instance

    server.log_admin_command(
        vehicle_id="V123",
        command_type="DELAY",
        parameters={"duration": 30},
        status="SENT"
    )

    mock_cursor.execute.assert_called_once_with(
        """
                           INSERT INTO admin_commands (vehicle_id, command_type, parameters, sent_time, status)
                           VALUES (?, ?, ?, datetime('now'), ?)
                           """,
        ("V123", "DELAY", json.dumps({"duration": 30}), "SENT")
    )
    mock_conn.commit.assert_called_once()
    mock_conn.close.assert_called_once()

def test_log_location_update(server_instance):
    server, mock_connect, mock_conn, mock_cursor = server_instance

    server.log_location_update(
        vehicle_id="V456",
        latitude=40.7128,
        longitude=-74.0060,
        speed=25.0,
        network_status="Online"
    )

    mock_cursor.execute.assert_called_once_with(
        """
                           INSERT INTO location_updates (vehicle_id, latitude, longitude, speed, timestamp, network_status)
                           VALUES (?, ?, ?, ?, datetime('now'), ?)
                           """,
        ("V456", 40.7128, -74.0060, 25.0, "Online")
    )
    mock_conn.commit.assert_called_once()
    mock_conn.close.assert_called_once()

def test_log_event(server_instance):
    server, mock_connect, mock_conn, mock_cursor = server_instance

    server.log_event(vehicle_id="V789", event_type="VEHICLE_CONNECTED", details="Vehicle connected successfully.")

    mock_cursor.execute.assert_called_once_with(
        """
                           INSERT INTO event_logs (vehicle_id, event_type, details, event_time)
                           VALUES (?, ?, ?, datetime('now'))
                           """,
        ("V789", "VEHICLE_CONNECTED", "Vehicle connected successfully.")
    )
    mock_conn.commit.assert_called_once()
    mock_conn.close.assert_called_once()

def test_update_vehicle_status(server_instance):
    server, mock_connect, mock_conn, mock_cursor = server_instance

    server.vehicle_types["V123"] = "Bus"  # Simulate registered vehicle type

    server.update_vehicle_status(vehicle_id="V123", status="On Time", last_seen="2024-04-26 18:00")

    mock_cursor.execute.assert_called_once_with(
        """
                INSERT OR REPLACE INTO vehicles (vehicle_id, vehicle_type, route_id, status, last_seen)
                VALUES (?, ?, ?, ?, ?)
            """,
        ("V123", "Bus", None, "On Time", "2024-04-26 18:00")
    )
    mock_conn.commit.assert_called_once()
    mock_conn.close.assert_called_once()

def test_start_method():
    with patch("server.server.socket.socket") as mock_socket, \
         patch("server.server.threading.Thread") as mock_thread, \
         patch("server.server.time.sleep", side_effect=KeyboardInterrupt), \
         patch("server.server.get_current_time_string", return_value="2024-04-26 18:00"):

        server = TransportServer()

        server.start()

        # Should have created TCP and UDP sockets
        assert mock_socket.call_count >= 2

        # Should have created 3 threads
        assert mock_thread.call_count == 3

        # Each thread should have been started
        for call in mock_thread.call_args_list:
            args, kwargs = call
            target = kwargs.get("target") or args[0]
            assert callable(target)

        # Server should close sockets after KeyboardInterrupt
        assert server.running is False

def test_calculate_speed():
    server = TransportServer()

    assert server.calculate_speed("Bus", 0) == 30
    assert server.calculate_speed("Bus", 100) == 10
    assert server.calculate_speed("Train", 0) == 80
    assert server.calculate_speed("Train", 100) == 40
    assert server.calculate_speed("Shuttle", 50) == 35
    assert server.calculate_speed("Uber", 100) == 5
    assert server.calculate_speed("Unknown", 0) == 20

def test_process_tcp_message_status_update():
    server = TransportServer()

    with patch.object(server, "log_location_update") as mock_log_location, \
         patch.object(server, "update_vehicle_status") as mock_update_status, \
         patch("server.server.get_current_time_string", return_value="2024-04-26 18:00"):

        message = {
            "type": MessageType.STATUS_UPDATE,
            "location": {"lat": 40.7128, "long": -74.0060},
            "status": "Active",
            "network_status": "Online"
        }

        server.process_tcp_message(message, "V100")

        mock_log_location.assert_called_once_with("V100", 40.7128, -74.0060, 0.0, "Online")
        mock_update_status.assert_called_once_with("V100", "Active", "2024-04-26 18:00")

def test_process_tcp_message_command_rejected():
    server = TransportServer()

    with patch.object(server, "log_event") as mock_log_event:
        message = {
            "type": MessageType.COMMAND_REJECTED,
            "reason": "Not authorized"
        }
        server.process_tcp_message(message, "V101")

        mock_log_event.assert_called_once_with("V101", "COMMAND_FAILURE", "Not authorized")

def test_handle_client_registration():
    server = TransportServer()

    fake_socket = MagicMock()
    fake_socket.recv.side_effect = [
        json.dumps({
            "type": MessageType.REGISTRATION,
            "vehicle_id": "V123",
            "vehicle_type": "Bus"
        }).encode(),
        b''  # simulate client disconnect
    ]

    with patch.object(server, "notify_observers") as mock_notify, \
         patch.object(server, "log_event") as mock_log_event, \
         patch.object(server, "process_tcp_message") as mock_process:

        server.handle_client(fake_socket)

        # Vehicle should be removed after disconnect
        assert "V123" not in server.vehicle_registry
        assert "V123" not in server.vehicle_types

        mock_notify.assert_any_call("VEHICLE_CONNECTED", "V123 (Bus)")
        mock_notify.assert_any_call("VEHICLE_DISCONNECTED", "V123")

        mock_log_event.assert_any_call("V123", "VEHICLE_CONNECTED", "V123 (Bus) connected")
        mock_log_event.assert_any_call("V123", "VEHICLE_DISCONNECTED", "V123 disconnected")

        fake_socket.close.assert_called_once()

def test_handle_tcp_connections():
    server = TransportServer()
    server.running = True

    fake_client_socket = MagicMock()
    fake_addr = ("127.0.0.1", 12345)

    mock_accept = MagicMock(return_value=(fake_client_socket, fake_addr))
    mock_thread = MagicMock()

    with patch.object(server, "tcp_server", create=True) as mock_tcp_server, \
         patch("server.server.threading.Thread", return_value=mock_thread) as mock_thread_class:

        mock_tcp_server.accept = mock_accept

        # Simulate one connection then stop
        def stop_after_first_call(*args, **kwargs):
            server.running = False
            return (fake_client_socket, fake_addr)

        mock_tcp_server.accept.side_effect = stop_after_first_call

        server.handle_tcp_connections()

        mock_thread_class.assert_called_once_with(target=server.handle_client, args=(fake_client_socket, fake_addr))
        mock_thread.start.assert_called_once()

def test_send_command_success():
    server = TransportServer()

    mock_socket = MagicMock()
    server.vehicle_registry["V123"] = mock_socket

    with patch.object(server, "notify_observers") as mock_notify, \
         patch.object(server, "log_admin_command") as mock_log_admin:

        success = server.send_command("V123", "DELAY", {"duration": 30})

        assert success is True
        mock_socket.send.assert_called_once()

        sent_data = json.loads(mock_socket.send.call_args[0][0].decode())
        assert sent_data["command"] == "DELAY"
        assert sent_data["params"] == {"duration": 30}

        mock_notify.assert_called_once_with("COMMAND_SENT", "DELAY to V123")
        mock_log_admin.assert_called_once_with("V123", "DELAY", {"duration": 30}, "SENT")

def test_send_command_fail_send_exception():
    server = TransportServer()

    broken_socket = MagicMock()
    broken_socket.send.side_effect = Exception("socket error")
    server.vehicle_registry["V456"] = broken_socket

    with patch.object(server, "notify_observers"), \
         patch.object(server, "log_admin_command") as mock_log_admin:

        success = server.send_command("V456", "REROUTE")

        assert success is False
        mock_log_admin.assert_called_once_with("V456", "REROUTE", None, "FAILED")

def test_send_command_vehicle_not_found():
    server = TransportServer()

    with patch.object(server, "log_admin_command") as mock_log_admin:
        success = server.send_command("NONEXISTENT", "SHUTDOWN")

        assert success is False
        mock_log_admin.assert_called_once_with("NONEXISTENT", "SHUTDOWN", None, "NOT_FOUND")

def test_handle_admin_commands_exit():
    server = TransportServer()

    server.running = True

    with patch("builtins.input", side_effect=["EXIT"]), \
         patch.object(server.logger, "log") as mock_log:

        server.handle_admin_commands()

        mock_log.assert_called_with("Server shutdown initiated by admin", also_print=True)
        assert server.running is False

def test_handle_admin_commands_registry():
    server = TransportServer()

    server.vehicle_registry = {"V123": MagicMock()}
    server.vehicle_types = {"V123": "Bus"}

    with patch("builtins.input", side_effect=["REGISTRY", "EXIT"]), \
         patch.object(server.logger, "log") as mock_log:

        server.handle_admin_commands()

        # Should log registry and shutdown
        mock_log.assert_any_call("Admin requested registry summary")
        mock_log.assert_any_call("Server shutdown initiated by admin", also_print=True)

def test_handle_admin_commands_delay_command():
    server = TransportServer()

    with patch("builtins.input", side_effect=["DELAY V123 60", "EXIT"]), \
         patch.object(server, "send_command", return_value=True) as mock_send, \
         patch.object(server.logger, "log"):

        server.handle_admin_commands()

        mock_send.assert_called_with("V123", Command.DELAY, {"duration": 60})

def test_handle_admin_commands_invalid_format(capsys):
    server = TransportServer()

    with patch("builtins.input", side_effect=["INVALIDCMD", "EXIT"]), \
         patch.object(server.logger, "log"):

        server.handle_admin_commands()

        captured = capsys.readouterr()
        assert "Invalid command format." in captured.out

def test_print_registry_with_vehicles(capsys):
    server = TransportServer()

    server.vehicle_registry = {"V123": MagicMock(), "V456": MagicMock()}
    server.vehicle_types = {"V123": "Bus", "V456": "Train"}

    server.print_registry()

    captured = capsys.readouterr()
    assert "V123" in captured.out
    assert "Bus" in captured.out
    assert "V456" in captured.out
    assert "Train" in captured.out

def test_print_registry_no_vehicles(server_instance, capsys):
    server = TransportServer()

    server.vehicle_registry = {}

    server.print_registry()

    captured = capsys.readouterr()
    assert "No vehicles connected." in captured.out