import socket
import threading
import json
import datetime
import time
import random
from utils import *

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
        self.vehicle_registry = {}  # Maps vehicle_id to client socket
        self.vehicle_types = {}     # Maps vehicle_id to vehicle type
        self.lock = threading.Lock()
        self.running = True
        
        # Set up the logger
        self.logger = Logger("server", is_server=True)
        
        # Register the log observer
        self.log_observer = LogObserver(self.logger)
        self.register_observer(self.log_observer)
        
    def start(self):
        print(f"[{get_current_time_string()}] SERVER STARTED at Bryant Park Control Center")
        print(f"[{get_current_time_string()}] Logs are being saved to the 'logs' directory")
        
        # Start TCP server for reliable communication
        self.tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_server.bind((TCP_SERVER_HOST, TCP_SERVER_PORT))
        self.tcp_server.listen(10)
        
        # Start UDP server for location updates
        self.udp_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_server.bind((TCP_SERVER_HOST, UDP_SERVER_PORT))
        
        # Start threads for handling connections
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
            # Wait for registration message
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
                    
                    # Continue handling messages from this client
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
                            
                    # Client disconnected or error occurred
                    with self.lock:
                        if vehicle_id in self.vehicle_registry:
                            del self.vehicle_registry[vehicle_id]
                        if vehicle_id in self.vehicle_types:
                            del self.vehicle_types[vehicle_id]
                            
                    self.logger.log(f"Vehicle DISCONNECTED: {vehicle_id}")
                    self.notify_observers("VEHICLE_DISCONNECTED", vehicle_id)
                    
        except Exception as e:
            self.logger.log(f"Error handling client: {e}", also_print=True)
        finally:
            client_socket.close()
            
    def process_tcp_message(self, message, vehicle_id):
        message_type = message["type"]
        
        if message_type == MessageType.STATUS_UPDATE:
            lat = message["location"]["lat"]
            long = message["location"]["long"]
            status = message["status"]
            self.logger.log(f"[TCP] {vehicle_id} -> Status Update:")
            self.logger.log(f"Location: ({lat:.4f}, {long:.4f}) | Status: {status}")
            self.notify_observers("STATUS_UPDATE", f"{vehicle_id}: {status} at ({lat:.4f}, {long:.4f})")
            
        elif message_type == MessageType.COMMAND_ACK:
            command = message["command"]
            status = message["status"]
            self.logger.log(f"[ACK] {vehicle_id} -> Acknowledged {command}. Status updated to: {status}")
            self.notify_observers("COMMAND_ACK", f"{vehicle_id} acknowledged {command}")
            
        elif message_type == MessageType.COMMAND_REJECTED:
            command = message["command"]
            reason = message["reason"]
            self.logger.log(f"[REJECTED] {vehicle_id} -> {command} not permitted ({reason})")
            self.notify_observers("COMMAND_REJECTED", f"{vehicle_id} rejected {command}: {reason}")
            
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
                    
                    # Log formatted message based on vehicle type
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
                    return True
                except Exception as e:
                    self.logger.log(f"Error sending command to {vehicle_id}: {e}", also_print=True)
                    return False
            else:
                self.logger.log(f"Vehicle {vehicle_id} not found in registry", also_print=True)
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
