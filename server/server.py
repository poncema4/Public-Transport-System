import os
import sys
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

import sqlite3
import threading
import time
from common.config import TCP_SERVER_PORT, BUFFER_SIZE, Command
from common.patterns import Observer, Subject
from common.utils import *

class CommandHandler:
    """Command Pattern: Encapsulates a command request as an object"""
    def __init__(self, command_type, params=None):
        self.command_type = command_type
        self.params = params or {}
        
    def to_dict(self):
        return {
            "type": MessageType.COMMAND,
            "command": self.command_type,
            "params": self.params,
            "timestamp": get_current_time_string()
        }

class LogObserver(Observer):
    """Observer Pattern: Gets notified of important events"""
    def __init__(self, logger):
        self.logger = logger
        
    def update(self, subject, event, data):
        self.logger.log(f"[LOG] {event}: {data}")

class TransportServer(Subject):
    def __init__(self):
        super().__init__()
        self.vehicle_registry = {}
        self.vehicle_types = {}
        self.lock = threading.Lock()
        self.running = True
        self.logger = Logger("server", is_server=True)
        self.log_observer = LogObserver(self.logger)
        self.register_observer(self.log_observer)

        self.db_lock = threading.Lock()
        self.init_database()
        self.init_routes()

    def init_database(self):
        with self.db_lock:
            conn = sqlite3.connect("transport_system.db")
            cursor = conn.cursor()

            # Create vehicles table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vehicles (
                    vehicle_id TEXT PRIMARY KEY,      
                    vehicle_type TEXT,                 
                    route_id TEXT,
                    status TEXT,
                    last_seen TEXT
                )
            """)

            # Create routes table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS routes (
                    route_id TEXT PRIMARY KEY,
                    origin TEXT,
                    destination TEXT,
                    stop_sequence TEXT
                )
            """)

            # Create admin_commands table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admin_commands (
                    command_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehicle_id TEXT,
                    command_type TEXT,
                    parameters TEXT,
                    sent_time TEXT,
                    response_time TEXT,
                    status TEXT
                )
            """)

            # Create event_logs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_logs (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehicle_id TEXT,
                    event_type TEXT,
                    details TEXT,
                    event_time TEXT
                )
            """)

            # Create location_updates table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS location_updates (
                    update_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehicle_id TEXT,
                    latitude REAL,
                    longitude REAL,
                    speed REAL,
                    timestamp TEXT,
                    network_status TEXT
                )
            """)

            conn.commit()
            conn.close()

    def init_routes(self):
        """Initialize predefined routes in the database."""
        with self.db_lock:
            conn = sqlite3.connect("transport_system.db")
            cursor = conn.cursor()

            routes = [
                ("BUS_ROUTE", "Port Authority Terminal", "Wall Street", "Port Authority Terminal,Times Square,Flatiron,Union Square,Wall Street"),
                ("TRAIN_ROUTE", "Queens Plaza", "Middle Village", "Queens Plaza,Herald Square,Delancey St,Middle Village"),
                ("SHUTTLE_ROUTE", "Penn Station", "JFK Airport", "Penn Station,JFK Airport"),
                ("UBER_ROUTE", "Washington Square", "Columbia University", "Washington Square,Greenwich Village,Union Square,Near Flatiron,Near Bryant Park,Midtown,Columbus Circle,Upper West Side,Near Columbia University")
            ]

            cursor.executemany("""
                INSERT OR IGNORE INTO routes (route_id, origin, destination, stop_sequence)
                VALUES (?, ?, ?, ?)
            """, routes)

            conn.commit()
            conn.close()

    def log_admin_command(self, vehicle_id, command_type, parameters, status):
        """Log an admin command to the database"""
        with self.db_lock:
            conn = sqlite3.connect("transport_system.db")
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO admin_commands (vehicle_id, command_type, parameters, sent_time, status)
                VALUES (?, ?, ?, datetime('now'), ?)
            """, (vehicle_id, command_type, json.dumps(parameters), status))
            conn.commit()
            conn.close()

    def log_location_update(self, vehicle_id, latitude, longitude, speed, network_status):
        """Log a location update to the database"""
        with self.db_lock:
            conn = sqlite3.connect("transport_system.db")
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO location_updates (vehicle_id, latitude, longitude, speed, timestamp, network_status)
                VALUES (?, ?, ?, ?, datetime('now'), ?)
            """, (vehicle_id, latitude, longitude, speed, network_status))
            conn.commit()
            conn.close()

    def log_event(self, vehicle_id, event_type, details):
        """Log specific events to the database"""
        with self.db_lock:
            conn = sqlite3.connect("transport_system.db")
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO event_logs (vehicle_id, event_type, details, event_time)
                VALUES (?, ?, ?, datetime('now'))
            """, (vehicle_id, event_type, details))
            conn.commit()
            conn.close()

    def update_vehicle_status(self, vehicle_id, status, last_seen):
        """Update vehicle status in the database"""
        with self.db_lock:
            conn = sqlite3.connect("transport_system.db")
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO vehicles (vehicle_id, vehicle_type, route_id, status, last_seen)
                VALUES (?, ?, ?, ?, ?)
            """, (vehicle_id, self.vehicle_types.get(vehicle_id, "Unknown"), None, status, last_seen))
            conn.commit()
            conn.close()
        
    def start(self):
        print(f"[{get_current_time_string()}] SERVER STARTED at Bryant Park Control Center")
        print(f"[{get_current_time_string()}] Admin Logs are being saved to transport_system.db")
        
        self.tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_server.bind((TCP_SERVER_HOST, TCP_SERVER_PORT))
        self.tcp_server.listen(10)

        self.udp_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_server.bind((TCP_SERVER_HOST, UDP_SERVER_PORT))

        tcp_thread = threading.Thread(target=self.handle_tcp_connections)
        udp_thread = threading.Thread(target=self.handle_udp_messages)
        command_thread = threading.Thread(target=self.handle_admin_commands)
        tcp_thread.daemon = True
        udp_thread.daemon = True
        command_thread.daemon = True
        
        tcp_thread.start()
        udp_thread.start()
        command_thread.start()
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down server...")
            self.running = False
            self.tcp_server.close()
            self.udp_server.close()
            
    def handle_tcp_connections(self):
        while self.running:
            try:
                client_socket, addr = self.tcp_server.accept()
                client_thread = threading.Thread(target=self.handle_client, args=(client_socket, addr))
                client_thread.daemon = True
                client_thread.start()
            except Exception as e:
                if self.running:
                    self.logger.log(f"Error accepting connection: {e}", also_print=True)
                
    def handle_client(self, client_socket, addr):
        try:
            data = client_socket.recv(BUFFER_SIZE)
            if data:
                message = json.loads(data.decode())
                if message["type"] == MessageType.REGISTRATION:
                    vehicle_id = message["vehicle_id"]
                    vehicle_type = message["vehicle_type"]

                    with self.lock:
                        self.vehicle_registry[vehicle_id] = client_socket
                        self.vehicle_types[vehicle_id] = vehicle_type

                    self.logger.log(f"Vehicle CONNECTED: {vehicle_id} ({vehicle_type}) via TCP")
                    self.notify_observers("VEHICLE_CONNECTED", f"{vehicle_id} ({vehicle_type})")
                    self.log_event(vehicle_id, "VEHICLE_CONNECTED", f"{vehicle_id} ({vehicle_type}) connected")

                    while self.running:
                        try:
                            data = client_socket.recv(BUFFER_SIZE)
                            if not data:
                                break

                            message = json.loads(data.decode())
                            self.process_tcp_message(message, vehicle_id)
                        except Exception as e:
                            self.logger.log(f"Error receiving message from {vehicle_id}: {e}")
                            break

                    with self.lock:
                        if vehicle_id in self.vehicle_registry:
                            del self.vehicle_registry[vehicle_id]
                        if vehicle_id in self.vehicle_types:
                            del self.vehicle_types[vehicle_id]

                    self.logger.log(f"Vehicle DISCONNECTED: {vehicle_id}")
                    self.notify_observers("VEHICLE_DISCONNECTED", vehicle_id)

                    self.log_event(vehicle_id, "VEHICLE_DISCONNECTED", f"{vehicle_id} disconnected")

        except Exception as e:
            self.logger.log(f"Error handling client: {e}", also_print=True)
        finally:
            client_socket.close()
                
    def process_tcp_message(self, message, vehicle_id):
        message_type = message["type"]
        if message_type == MessageType.STATUS_UPDATE:
            lat = message["location"]["lat"]
            long = message["location"]["long"]
            network_status = message.get("network_status", "Unknown")
            status = message["status"]

            self.log_location_update(vehicle_id, lat, long, 0.0, network_status)

            self.update_vehicle_status(vehicle_id, status, get_current_time_string())

        elif message_type == MessageType.COMMAND_REJECTED:
            reason = message.get("reason", "Unknown reason")
            self.log_event(vehicle_id, "COMMAND_FAILURE", reason)

        elif message_type == MessageType.COMMAND_ACK:
            pass
            
    def calculate_speed(self, vehicle_type, progress):
        """
        Calculate the speed of the vehicle based on its type and progress.
        Vehicles slow down as they approach their destination.
        """
        if vehicle_type == "Bus":
            max_speed = 30
            min_speed = 10
        elif vehicle_type == "Train":
            max_speed = 80
            min_speed = 40
        elif vehicle_type == "Shuttle":
            max_speed = 50
            min_speed = 20
        elif vehicle_type == "Uber":
            max_speed = 25
            min_speed = 5
        else:
            max_speed = 20
            min_speed = 5

        speed = max_speed - ((max_speed - min_speed) * (progress / 100))
        return round(speed, 2)

    def handle_udp_messages(self):
        while self.running:
            try:
                data, addr = self.udp_server.recvfrom(BUFFER_SIZE)
                message = json.loads(data.decode())
                
                if message["type"] == MessageType.LOCATION_UPDATE:
                    vehicle_id = message["vehicle_id"]
                    vehicle_type = message["vehicle_type"]
                    location = message["location"]
                    status = message["status"]

                    log_entry = f"[UDP] {vehicle_id} -> Real-Time Location Update:"
                    log_details = f"Lat: {location['lat']:.4f} | Long: {location['long']:.4f}"
                    
                    if "next_stop" in message:
                        log_details += f" | Next stop: {message['next_stop']}"
                        
                    if "eta" in message:
                        log_details += f" | ETA: {message['eta']} mins"
                        
                    if status:
                        log_details += f" | Status: {status}"
                    
                    self.logger.log(log_entry)
                    self.logger.log(log_details)
                    self.notify_observers("LOCATION_UPDATE", f"{vehicle_id} at ({location['lat']:.4f}, {location['long']:.4f})")
            except Exception as e:
                if self.running:
                    self.logger.log(f"Error receiving UDP message: {e}", also_print=True)
                    
    def send_command(self, vehicle_id, command_type, params=None):
        with self.lock:
            if vehicle_id in self.vehicle_registry:
                client_socket = self.vehicle_registry[vehicle_id]
                command = CommandHandler(command_type, params)
                command_dict = command.to_dict()

                try:
                    client_socket.send(json.dumps(command_dict).encode())
                    self.logger.log(f"[COMMAND] {command_type} issued to {vehicle_id}")
                    if params:
                        self.logger.log(f"Parameters: {params}")
                    self.notify_observers("COMMAND_SENT", f"{command_type} to {vehicle_id}")

                    self.log_admin_command(vehicle_id, command_type, params, "SENT")
                    return True
                except Exception as e:
                    self.logger.log(f"Error sending command to {vehicle_id}: {e}", also_print=True)
                    self.log_admin_command(vehicle_id, command_type, params, "FAILED")
                    return False
            else:
                self.logger.log(f"Vehicle {vehicle_id} not found in registry", also_print=True)
                self.log_admin_command(vehicle_id, command_type, params, "NOT_FOUND")
                return False
                
    def handle_admin_commands(self):
        while self.running:
            print("\nAvailable commands:")
            print("1. DELAY <vehicle_id> <seconds>")
            print("2. REROUTE <vehicle_id>")
            print("3. SHUTDOWN <vehicle_id>")
            print("4. START_ROUTE <vehicle_id>")
            print("5. REGISTRY - Show connected vehicles")
            print("6. EXIT - Shutdown server")
            
            try:
                command_input = input("\nEnter command: ")
                parts = command_input.strip().split()
                
                if not parts:
                    continue
                 
                if parts[0].upper() == "EXIT":
                    print("Shutting down server...")
                    self.logger.log("Server shutdown initiated by admin", also_print=True)
                    self.running = False
                    break
                    
                if parts[0].upper() == "REGISTRY":
                    self.print_registry()
                    continue
                    
                if len(parts) < 2:
                    print("Invalid command format. Please provide vehicle ID.")
                    continue
                    
                command_type = parts[0].upper()
                vehicle_id = parts[1]
                
                if command_type == Command.DELAY and len(parts) >= 3:
                    try:
                        delay_seconds = int(parts[2])
                        success = self.send_command(vehicle_id, Command.DELAY, {"duration": delay_seconds})
                        if success:
                            print(f"Command {Command.DELAY} sent to {vehicle_id}")
                    except ValueError:
                        print("Invalid delay duration. Please provide a number in seconds.")
                elif command_type in [Command.REROUTE, Command.SHUTDOWN, Command.START_ROUTE]:
                    success = self.send_command(vehicle_id, command_type)
                    if success:
                        print(f"Command {command_type} sent to {vehicle_id}")
                else:
                    print("Invalid command or format.")
                    
            except Exception as e:
                self.logger.log(f"Error processing command: {e}", also_print=True)
                
    def print_registry(self):
        print(f"\nServer registry summary:")
        self.logger.log("Admin requested registry summary")
        with self.lock:
            if not self.vehicle_registry:
                print("No vehicles connected.")
                self.logger.log("No vehicles connected.")
            else:
                for vehicle_id, _ in self.vehicle_registry.items():
                    vehicle_type = self.vehicle_types.get(vehicle_id, "Unknown")
                    print(f"- {vehicle_id}: Connected | Type: {vehicle_type}")
                    self.logger.log(f"- {vehicle_id}: Connected | Type: {vehicle_type}")

if __name__ == "__main__":
    server = TransportServer()
    server.start()