import os
import sqlite3
import sys
from typing import Optional

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

import json
import threading
import time
import socket
import datetime
from common.config import *
from common.patterns import Subject
from common.utils import get_formatted_coords, Logger, get_current_time_string, send_udp_beacon
from abc import ABC, abstractmethod


class Vehicle(Subject, ABC):
    """
    Represents a vehicle in the transport system.
    """
    def __init__(self, vehicle_id, vehicle_type):
        super().__init__()
        self.vehicle_id: str = vehicle_id
        self.vehicle_type: str = vehicle_type
        self.status: str = Status.ON_TIME
        self.tcp_socket: socket = None
        self.udp_socket: socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.running: bool = True
        self.location: tuple[float, float] = get_formatted_coords()
        self.logger: Logger = Logger(vehicle_id)
        self.server_shutdown_detected: bool = False
        self.db_lock: threading.Lock = threading.Lock()
        self.init_database()

    def simulate_movement(self) -> None:
        """
        Moves this vehicle while running and connected.
        Allows for child classes to override pre_step, movement_step, and post_step.
        """
        last_tcp: float = 0.0
        while self.running and self._check_connection():
            if self._handle_delay(): continue
            self._pre_step()
            last_tcp = self._movement_step(last_tcp)
            self._post_step()

    # region Shared Utilities
    def _check_connection(self) -> bool:
        """
        Checks if the vehicle is still connected to the server.
        :return: True if connected, False otherwise.
        """
        if not self.server_shutdown_detected and self.tcp_socket:
            return True
        self.logger.log(
            "Lost connection to server and reconnection failed. Shutting down.",
            also_print=True
        )
        return False

    def _handle_delay(self) -> bool:
        """
        If delayed, simulates a delay period, and if the delay period is over, resumes normal operation.
        :return: True if still delayed, False otherwise.
        """
        now: float = time.time()
        is_delayed: bool = getattr(self, "is_delayed", False)
        delay_until: float = getattr(self, "delay_until", 0.0)

        if is_delayed and now < delay_until:
            time.sleep(1)
            return True

        if is_delayed:
            self.is_delayed = False
            self.logger.log("Delay period over, resuming normal operation")
        return False

    def send_udp_beacon(self, lat: float, long: float, next_stop: Optional[str] = None,
                        eta: Optional[int] = None) -> None:
        message = {
            "type": MessageType.LOCATION_UPDATE,
            "vehicle_id": self.vehicle_id,
            "vehicle_type": self.vehicle_type,
            "status": self.status,
            "location": {"lat": lat, "long": long},
            "timestamp": get_current_time_string()
        }

        optional_args: list[str] = ["next_stop", "eta"]
        given_args: list = [next_stop, eta]

        for arg, given in zip(optional_args, given_args):
            if given:
                message[arg] = given

        try:
            self.udp_socket.sendto(json.dumps(message).encode(), (TCP_SERVER_HOST, UDP_SERVER_PORT))
        except Exception as e:
            self.logger.log(f"Error sending UDP beacon: {e}", also_print=True)
    # endregion

    # region Movement Steps
    def _pre_step(self) -> None:
        """
        Optional override for any pre-movement logic.
        :return: None
        """
        pass

    @abstractmethod
    def _movement_step(self, last_tcp_timestamp: float) -> float:
        """
        Mandatory override for the movement logic.
        :param last_tcp_timestamp: The timestamp of the last TCP message sent.
        :return: The timestamp of the last TCP message sent.
        """
        pass

    def _post_step(self) -> None:
        """
        Optional override for any post-movement logic.
        :return: None
        """
        pass

    # endregion

    # region Database Methods
    def init_database(self) -> None:
        """Initialize the SQLite database for this vehicle."""
        with self.db_lock:
            conn = sqlite3.connect(f"{self.vehicle_id}.db")
            cursor = conn.cursor()

            # Create tables
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS location_updates
                           (
                               update_id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               vehicle_id
                               TEXT,
                               lat
                               REAL,
                               long
                               REAL,
                               speed
                               REAL,
                               timestamp
                               TEXT,
                               network_status
                               TEXT
                           )
                           """)
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS admin_commands
                           (
                               command_id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               command_type
                               TEXT,
                               parameters
                               TEXT,
                               sent_time
                               TEXT,
                               response_time
                               TEXT,
                               status
                               TEXT
                           )
                           """)
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS event_logs
                           (
                               event_id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               event_type
                               TEXT,
                               details
                               TEXT,
                               timestamp
                               TEXT
                           )
                           """)
            conn.commit()
            conn.close()

    def log_location_update(self, lat: float, long: float, network_status: str, speed: float = 0.0) -> None:
        """
        Log a location update to the database.
        :param lat: The latitude of the location.
        :param long: The longitude of the location.
        :param network_status: String describing the network status of the vehicle.
        :param speed: Speed of the vehicle in mph.
        :return: None
        """
        with self.db_lock:
            conn = sqlite3.connect(f"{self.vehicle_id}.db")
            cursor = conn.cursor()
            cursor.execute("""
                           INSERT INTO location_updates (vehicle_id, lat, long, speed, timestamp, network_status)
                           VALUES (?, ?, ?, ?, datetime('now'), ?)
                           """, (self.vehicle_id, lat, long, speed, network_status))
            conn.commit()
            conn.close()

    def log_event(self, event_type: str, details: str) -> None:
        """
        Log an event to the database.
        :param event_type: String description of the event.
        :param details: String description of the event details.
        :return: None
        """
        with self.db_lock:
            conn = sqlite3.connect(f"{self.vehicle_id}.db")
            cursor = conn.cursor()
            cursor.execute("""
                           INSERT INTO event_logs (event_type, details, timestamp)
                           VALUES (?, ?, datetime('now'))
                           """, (event_type, details))
            conn.commit()
            conn.close()

    # endregion

    def start(self) -> None:
        """
        Starts this vehicle client. Connects to the server, listens for commands, and simulates movement.
        :return: None
        """
        vehicle_type: str = "Uber" if self.vehicle_type == "Uber" else self.vehicle_type.lower()
        self.logger.log(
            f"Starting {vehicle_type} client {self.vehicle_id}. " +
            f"Logs will be saved to {self.vehicle_id}.db",
            also_print=True
        )

        if not self.connect_to_server():
            return

        # Start the command listener thread
        command_thread = threading.Thread(target=self.listen_for_commands)
        command_thread.daemon = True
        command_thread.start()

        # Start movement simulation
        try:
            self.simulate_movement()
        except KeyboardInterrupt:
            self.logger.log(f"Shutting down {vehicle_type} client...", also_print=True)
        finally:
            self.close()

    def connect_to_server(self) -> bool:
        """
        Attempts to establish a connection to the server.
        :return: True if a connection was established, False otherwise.
        """
        retry_count = 0
        max_retries = 5
        # While not timed out and running.
        while retry_count < max_retries and self.running:
            try:
                self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.tcp_socket.connect((TCP_SERVER_HOST, TCP_SERVER_PORT))

                # Register with server
                registration_message = {
                    "type": MessageType.REGISTRATION,
                    "vehicle_id": self.vehicle_id,
                    "vehicle_type": self.vehicle_type
                }
                self.tcp_socket.send(json.dumps(registration_message).encode())
                self.logger.log(f"Connected to server and registered as {self.vehicle_id}")
                self.server_shutdown_detected = False
                return True

            except Exception as e:
                retry_count += 1
                wait_time = 2 ** retry_count  # Exponential backoff
                self.logger.log(f"Connection failed: {e}. Retrying in {wait_time} seconds...", also_print=True)
                time.sleep(wait_time)
        # Connection failed.
        if self.server_shutdown_detected:
            self.logger.log(
                f"Server appears to be down. Terminating client after {max_retries} failed reconnection attempts.",
                also_print=True
            )
        else:
            self.logger.log(
                f"Failed to connect after {max_retries} attempts. Exiting.",
                also_print=True
            )
        self.running = False
        return False

    def listen_for_commands(self) -> None:
        """
        Listens for commands from the server and handles them accordingly.
        :return: None
        """
        while self.running:
            try:
                if not self.tcp_socket:
                    continue

                data = self.tcp_socket.recv(BUFFER_SIZE)
                if data:
                    message = json.loads(data.decode())
                    if message.get("type") == MessageType.COMMAND:
                        self.handle_command(message)
                    continue

                # If no data, server likely closed the connection
                self.handle_server_disconnect()

            except Exception as e:
                self.logger.log(f"Error receiving command: {e}", also_print=True)
                self.handle_reconnect()

    def handle_server_disconnect(self) -> None:
        """
        Handles logic for when the server disconnects from the client.
        Logs the event, closes the connection, and attempts to reconnect.
        :return:
        """
        self.server_shutdown_detected = True
        self.logger.log(f"Server connection lost. Attempting to reconnect...", also_print=True)
        self.tcp_socket.close()
        if not self.connect_to_server():
            self.running = False

    def handle_reconnect(self) -> None:
        """
        Handles logic for when the client reconnects to the server.
        Logs the event and attempts to reconnect.
        :return:
        """
        self.server_shutdown_detected = True
        self.logger.log(f"Attempting to reconnect...", also_print=True)
        if not self.connect_to_server() and self.running:
            time.sleep(5)

    def handle_command(self, command_message: dict[str, str]) -> None:
        """
        Handles a command received from the server.
        :param command_message: The message from the server
        :return: None
        """
        command_type: str = command_message["command"]
        self.logger.log(f"Received command: {command_type}")

        # Default implementation to be overridden by subclasses
        self.send_command_ack(command_type, "Acknowledged")

    def send_command_ack(self, command_type: str, message: str) -> None:
        """
        Sends a command acknowledgment to the server.
        :param command_type: The command type that was acknowledged.
        :param message: The message to send in the acknowledgment.
        :return: None
        """
        if self.tcp_socket:
            response = {
                "type": MessageType.COMMAND_ACK,
                "vehicle_id": self.vehicle_id,
                "command": command_type,
                "message": message,
                "status": self.status
            }
            try:
                self.tcp_socket.send(json.dumps(response).encode())
                self.logger.log(f"Sent acknowledgment for {command_type}")
            except Exception as e:
                self.logger.log(f"Error sending acknowledgment: {e}", also_print=True)
                self.server_shutdown_detected = True

    def send_command_rejected(self, command_type: str, reason: str) -> None:
        """
        Sends a command rejection to the server.
        :param command_type: The command type that was rejected.
        :param reason: The reason for the rejection.
        :return: None
        """
        if self.tcp_socket:
            response = {
                "type": MessageType.COMMAND_REJECTED,
                "vehicle_id": self.vehicle_id,
                "command": command_type,
                "reason": reason
            }
            try:
                self.tcp_socket.send(json.dumps(response).encode())
                self.logger.log(f"Rejected command {command_type}: {reason}")
            except Exception as e:
                self.logger.log(f"Error sending rejection: {e}", also_print=True)
                self.server_shutdown_detected = True

    def send_status_update(self) -> None:
        """
        Sends a status update to the server.
        :return: None
        """
        if self.tcp_socket:
            lat, long = self.location

            # Determine network status based on the vehicle type
            if self.vehicle_type == VehicleType.BUS or self.vehicle_type == VehicleType.TRAIN:
                network_status = Status.ON_TIME
            elif self.vehicle_type == VehicleType.UBER:
                network_status = "Private"
            elif self.vehicle_type == VehicleType.SHUTTLE:
                now = datetime.datetime.now().strftime("%H:%M")
                network_status = Status.ACTIVE if now >= "08:00" else Status.STANDBY
            else:
                network_status = "Unknown"

            update: dict[str, str | dict[str, str]] = {
                "type": MessageType.STATUS_UPDATE,
                "vehicle_id": self.vehicle_id,
                "vehicle_type": self.vehicle_type,
                "status": self.status,
                "location": {"lat": lat, "long": long},
                "timestamp": get_current_time_string(),
                "network_status": network_status
            }
            try:
                self.tcp_socket.send(json.dumps(update).encode())
                self.logger.log(
                    f"[TCP] Sent status update: Location: ({lat:.4f}, {long:.4f}) | Status: {network_status}")
            except Exception as e:
                self.logger.log(f"Error sending status update: {e}", also_print=True)
                self.server_shutdown_detected = True

    def close(self) -> None:
        """
        Gracefully close the vehicle client's network connections and shut down.
        :return: None
        """
        self.running = False

        for sock_name, sock in [("TCP", self.tcp_socket), ("UDP", self.udp_socket)]:
            if sock:
                try:
                    sock.close()
                    self.logger.log(f"{sock_name} socket closed")
                except Exception as e:
                    self.logger.log(f"Error closing {sock_name} socket: {e}")

        self.logger.log("Client shutting down", also_print=True)

