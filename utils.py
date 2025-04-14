import json
import datetime
import time
import threading
import socket
import random
import os
import math

# Constants
TCP_SERVER_HOST = "localhost"
TCP_SERVER_PORT = 5000
UDP_SERVER_PORT = 5001
BUFFER_SIZE = 1024

# Vehicle IDs and routes
BUS_ROUTE = ["Port Authority Terminal", "Times Square", "Flatiron", "Union Square", "Wall Street"]
TRAIN_ROUTE = ["Queens Plaza", "Herald Square", "Delancey St", "Middle Village"]
UBER_START = "Washington Square"
UBER_END = "Columbia University"
SHUTTLE_ROUTE = ["Penn Station", "JFK Airport"]

# Route coordinates (approximate NYC coordinates)
ROUTE_COORDS = {
    # Bus route coordinates
    "Port Authority Terminal": (40.7577, -73.9901),
    "Times Square": (40.7580, -73.9855),
    "Flatiron": (40.7411, -73.9897),
    "Union Square": (40.7359, -73.9911),
    "Wall Street": (40.7068, -74.0090),
    
    # Train route coordinates
    "Queens Plaza": (40.7489, -73.9375),
    "Herald Square": (40.7497, -73.9876),
    "Delancey St": (40.7183, -73.9593),
    "Middle Village": (40.7147, -73.8878),
    
    # Shuttle route coordinates
    "Penn Station": (40.7506, -73.9939),
    "JFK Airport": (40.6413, -73.7781),
    
    # Uber route coordinates
    "Washington Square": (40.7308, -73.9973),
    "Greenwich Village": (40.7336, -74.0027),
    "Near NYU": (40.7295, -73.9965),
    "Near Flatiron": (40.7411, -73.9897),
    "Near Bryant Park": (40.7536, -73.9832),
    "Midtown": (40.7549, -73.9840),
    "Columbus Circle": (40.7682, -73.9819),
    "Upper West Side": (40.7870, -73.9754),
    "Near Columbia University": (40.8075, -73.9626),
    "Columbia University": (40.8075, -73.9626)
}

# Message types
class MessageType:
    STATUS_UPDATE = "STATUS_UPDATE"
    LOCATION_UPDATE = "LOCATION_UPDATE"
    COMMAND = "COMMAND"
    COMMAND_ACK = "COMMAND_ACK"
    COMMAND_REJECTED = "COMMAND_REJECTED"
    REGISTRATION = "REGISTRATION"

# Commands
class Command:
    DELAY = "DELAY"
    REROUTE = "REROUTE"
    SHUTDOWN = "SHUTDOWN"
    START_ROUTE = "START_ROUTE"

# Status
class Status:
    ON_TIME = "On Time"
    DELAYED = "Delayed"
    ACTIVE = "Active"
    STANDBY = "Standby"

# Vehicle types
class VehicleType:
    BUS = "Bus"
    TRAIN = "Train"
    UBER = "Uber"
    SHUTTLE = "Shuttle"

# Logging functionality
class Logger:
    def __init__(self, name, is_server=False):
        # Create logs directory if it doesn't exist
        if not os.path.exists("logs"):
            os.makedirs("logs")
            
        self.name = name
        self.is_server = is_server
        self.log_file = os.path.join("logs", f"{name}.txt")
        
        # Create or clear the log file
        with open(self.log_file, 'w') as f:
            timestamp = get_current_time_string()
            if is_server:
                f.write(f"[{timestamp}] SERVER STARTED at Bryant Park Control Center\n")
            else:
                f.write(f"[{timestamp}] {name} client started\n")
                
    def log(self, message, also_print=False):
        timestamp = get_current_time_string()
        log_entry = f"[{timestamp}] {message}\n"
        
        # Write to log file
        with open(self.log_file, 'a') as f:
            f.write(log_entry)
            
        # Optionally print to console as well
        if also_print:
            print(f"[{timestamp}] {message}")
            
# Helper functions
def get_current_time_string():
    return datetime.datetime.now().strftime("%H:%M:%S")

def get_formatted_coords():
    # Generate random coordinates in NYC area (Manhattan)
    lat = random.uniform(40.7, 40.8)
    long = random.uniform(-74.0, -73.9)
    return lat, long

def calculate_realistic_movement(current_location, next_stop, progress_percent=None):
    """
    Calculate realistic coordinates between current location and next stop
    
    Args:
        current_location: Tuple (lat, long) of current position
        next_stop: String name of next stop
        progress_percent: Optional percentage of progress towards next stop (0-100)
    
    Returns:
        Tuple (lat, long) of new coordinates
    """
    # If no progress specified, move 5-15% towards destination
    if progress_percent is None:
        progress_percent = random.uniform(5, 15)
    
    # Ensure progress is between 0 and 100
    progress_percent = max(0, min(100, progress_percent))
    progress_ratio = progress_percent / 100.0
    
    # Get destination coordinates
    if next_stop in ROUTE_COORDS:
        dest_lat, dest_long = ROUTE_COORDS[next_stop]
    else:
        # If next stop not found, use default NYC coordinates with small jitter
        dest_lat = current_location[0] + random.uniform(0.001, 0.003)
        dest_long = current_location[1] + random.uniform(0.001, 0.003)
    
    # Calculate linear interpolation with small random jitter (simulates lane changes, etc.)
    jitter_lat = random.uniform(-0.0005, 0.0005)
    jitter_long = random.uniform(-0.0005, 0.0005)
    
    new_lat = current_location[0] + (dest_lat - current_location[0]) * progress_ratio + jitter_lat
    new_long = current_location[1] + (dest_long - current_location[1]) * progress_ratio + jitter_long
    
    return (new_lat, new_long)

def get_coordinates_for_stop(stop_name):
    """Get coordinates for a named stop"""
    if stop_name in ROUTE_COORDS:
        return ROUTE_COORDS[stop_name]
    else:
        # Return default NYC coordinates
        return (40.7580, -73.9855)  # Times Square as fallback

def send_udp_beacon(vehicle_id, vehicle_type, status, location, next_stop=None, eta=None):
    message = {
        "type": MessageType.LOCATION_UPDATE,
        "vehicle_id": vehicle_id,
        "vehicle_type": vehicle_type,
        "status": status,
        "location": location,
        "timestamp": get_current_time_string()
    }
    
    if next_stop:
        message["next_stop"] = next_stop
        
    if eta:
        message["eta"] = eta
        
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(json.dumps(message).encode(), (TCP_SERVER_HOST, UDP_SERVER_PORT))
    except Exception as e:
        log_error = f"Error sending UDP beacon: {e}"
        print(log_error)  # Still print errors to console
    finally:
        sock.close()

# Observer pattern
class Observer:
    def update(self, subject, *args, **kwargs):
        pass

class Subject:
    def __init__(self):
        self._observers = []
        
    def register_observer(self, observer):
        if observer not in self._observers:
            self._observers.append(observer)
            
    def remove_observer(self, observer):
        if observer in self._observers:
            self._observers.remove(observer)
            
    def notify_observers(self, *args, **kwargs):
        for observer in self._observers:
            observer.update(self, *args, **kwargs)

# Command pattern
class CommandExecutor:
    def execute(self, command, params=None):
        pass

# Vehicle base class
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
                self.logger.log(f"Server appears to be down. Terminating client after {max_retries} failed reconnection attempts.", also_print=True)
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
