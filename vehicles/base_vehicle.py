import os
import sqlite3
import sys
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

import json
import threading
import time
import socket
import datetime
from common.config import *
from common.patterns import Subject
from common.utils import get_formatted_coords, Logger, get_current_time_string
from abc import ABC, abstractmethod

class Vehicle(Subject, ABC):
    def __init__(self, vehicle_id, vehicle_type):
        super().__init__()
        self.vehicle_id = vehicle_id
        self.vehicle_type = vehicle_type
        self.status = Status.ON_TIME
        self.tcp_socket = None
        self.running = True
        self.location = get_formatted_coords()
        self.logger = Logger(vehicle_id)
        self.server_shutdown_detected = False
        # Initialize SQL Database
        self.db_lock = threading.Lock()
        self.init_database()

    def simulate_movement(self):
        last_tcp: float  = 0.0
        while self.running and self._check_connection():
            # 1) Handle delay logic. If delayed, skip this iteration.
            if self._handle_delay(): continue
            # 2) Hook for any pre-loop logic
            self._pre_step()
            # 3) Do one movement step
            last_tcp = self._movement_step(last_tcp)
            # 4) Cleanup after each loop
            self._post_step()

    #region Shared Utilities
    def _check_connection(self) -> bool:
        # If everything is fine, return True
        if not self.server_shutdown_detected and self.tcp_socket:
            return True
        # Else log and return False
        self.logger.log(
            "Lost connection to server and reconnection failed. Shutting down.",
            also_print=True
        )
        return False

    def _handle_delay(self) -> bool:
        now: float  = time.time()
        is_delayed: bool = getattr(self, "is_delayed", False)
        delay_until: float = getattr(self, "delay_until", 0.0)

        # If delayed, wait for delay period to end
        if is_delayed and now < delay_until:
            time.sleep(1)
            return True  # skip the rest of this loop
        # If delayed but delay period is over, resume normal operation
        if is_delayed:
            self.is_delayed = False
            self.logger.log("Delay period over, resuming normal operation")
        return False
    #endregion

    #region Movement Steps
    def _pre_step(self):
        pass

    @abstractmethod
    def _movement_step(self, last_tcp_timestamp: float) -> float:
        pass

    def _post_step(self):
        pass
    #endregion

    #region Database Methods
    def init_database(self):
        """Initialize the SQLite database for this vehicle."""
        with self.db_lock:
            conn = sqlite3.connect(f"{self.vehicle_id}.db")
            cursor = conn.cursor()

            # Create tables
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS location_updates (
                    update_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehicle_id TEXT,
                    lat REAL,
                    long REAL,
                    speed REAL, 
                    timestamp TEXT,
                    network_status TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admin_commands (
                    command_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    command_type TEXT,
                    parameters TEXT,
                    sent_time TEXT,
                    response_time TEXT,
                    status TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_logs (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT,
                    details TEXT,
                    timestamp TEXT
                )
            """)
            conn.commit()
            conn.close()

    def log_location_update(self, lat, long, network_status, speed=0.0):
        """Log a location update to the database."""
        with self.db_lock:
            conn = sqlite3.connect(f"{self.vehicle_id}.db")
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO location_updates (vehicle_id, lat, long, speed, timestamp, network_status)
                VALUES (?, ?, ?, ?, datetime('now'), ?)
            """, (self.vehicle_id, lat, long, speed, network_status))
            conn.commit()
            conn.close()

    def log_event(self, event_type, details):
        """Log an event to the database."""
        with self.db_lock:
            conn = sqlite3.connect(f"{self.vehicle_id}.db")
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO event_logs (event_type, details, timestamp)
                VALUES (?, ?, datetime('now'))
            """, (event_type, details))
            conn.commit()
            conn.close()
    #endregion

    def start(self):
        vehicle_type: str = "Uber" if self.vehicle_type == "Uber" else self.vehicle_type.lower()
        self.logger.log(
            f"Starting {vehicle_type} client {self.vehicle_id}. " +
            f"Logs will be saved to {self.vehicle_id}.db",
            also_print=True
        )

        if not self.connect_to_server():
            return

        # Start command listener thread
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

    def connect_to_server(self):
        retry_count = 0
        max_retries = 5

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

        if retry_count >= max_retries:
            if self.server_shutdown_detected:
                self.logger.log \
                    (f"Server appears to be down. Terminating client after {max_retries} failed reconnection attempts.", also_print=True)
                self.running = False
            else:
                self.logger.log(f"Failed to connect after {max_retries} attempts. Exiting.", also_print=True)
                self.running = False
            return False

    def listen_for_commands(self):
        while self.running:
            try:
                if self.tcp_socket:
                    data = self.tcp_socket.recv(BUFFER_SIZE)
                    if not data:
                        # Connection closed by server - try to reconnect
                        self.server_shutdown_detected = True
                        self.logger.log(f"Server connection lost. Attempting to reconnect...", also_print=True)
                        self.tcp_socket.close()
                        if not self.connect_to_server():
                            # Reconnection failed after max attempts
                            break
                        continue

                    message = json.loads(data.decode())
                    if message["type"] == MessageType.COMMAND:
                        self.handle_command(message)
            except Exception as e:
                self.logger.log(f"Error receiving command: {e}", also_print=True)
                self.server_shutdown_detected = True
                # Try to reconnect
                self.logger.log(f"Attempting to reconnect...")
                if self.connect_to_server():
                    self.logger.log(f"Reconnected successfully")
                else:
                    # If connect_to_server returned False, it means reconnection failed after max attempts
                    # The method already sets running to False if max retries exceeded
                    if self.running:
                        time.sleep(5)  # Wait before next retry attempt

    def handle_command(self, command_message):
        command_type = command_message["command"]
        self.logger.log(f"Received command: {command_type}")

        # Default implementation to be overridden by subclasses
        self.send_command_ack(command_type, "Acknowledged")

    def send_command_ack(self, command_type, message):
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

    def send_command_rejected(self, command_type, reason):
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

    def send_status_update(self):
        """Send a status update to the server."""
        if self.tcp_socket:
            lat, long = self.location

            # Determine network status based on vehicle type
            if self.vehicle_type == VehicleType.BUS or self.vehicle_type == VehicleType.TRAIN:
                network_status = Status.ON_TIME
            elif self.vehicle_type == VehicleType.UBER:
                network_status = "Private"
            elif self.vehicle_type == VehicleType.SHUTTLE:
                now = datetime.datetime.now().strftime("%H:%M")
                network_status = Status.ACTIVE if now >= "08:00" else Status.STANDBY
            else:
                network_status = "Unknown"

            update = {
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
                self.logger.log(f"[TCP] Sent status update: Location: ({lat:.4f}, {long:.4f}) | Status: {network_status}")
            except Exception as e:
                self.logger.log(f"Error sending status update: {e}", also_print=True)
                self.server_shutdown_detected = True

    def close(self):
        self.running = False
        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except:
                pass
        self.logger.log("Client shutting down", also_print=True)