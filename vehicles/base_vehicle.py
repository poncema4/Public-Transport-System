import json
import time
import socket

from common.config import *
from common.patterns import Subject
from common.utils import get_formatted_coords, Logger, get_current_time_string


class Vehicle(Subject):
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
        if self.tcp_socket:
            lat, long = self.location
            update = {
                "type": MessageType.STATUS_UPDATE,
                "vehicle_id": self.vehicle_id,
                "vehicle_type": self.vehicle_type,
                "status": self.status,
                "location": {"lat": lat, "long": long},
                "timestamp": get_current_time_string()
            }
            try:
                self.tcp_socket.send(json.dumps(update).encode())
                self.logger.log(f"[TCP] Sent status update: Location: ({lat:.4f}, {long:.4f}) | Status: {self.status}")
            except Exception as e:
                self.logger.log(f"Error sending status update: {e}", also_print=True)
                self.server_shutdown_detected = True
                # Try to reconnect
                self.tcp_socket.close()
                if not self.connect_to_server():
                    # Reconnection failed after max attempts
                    self.running = False

    def close(self):
        self.running = False
        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except:
                pass
        self.logger.log("Client shutting down", also_print=True)