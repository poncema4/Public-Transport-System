import socket
import threading
import json
import time
import random
import sys
from utils import *

class TrainClient(Vehicle, CommandExecutor):
    def __init__(self, vehicle_id=None):
        # If no vehicle_id is provided, generate one
        if not vehicle_id:
            next_number = random.randint(1, 99)
            vehicle_id = f"T{next_number}"
            
        super().__init__(vehicle_id, VehicleType.TRAIN)
        self.route = TRAIN_ROUTE.copy()
        self.current_stop_index = 0
        self.next_stop = self.route[1] if len(self.route) > 1 else None
        self.status = Status.ON_TIME
        self.eta = random.randint(2, 8)  # ETA in minutes
        self.is_delayed = False
        self.delay_until = 0
        self.is_shutdown = False
        
        # Initialize location to the first stop's coordinates
        self.location = get_coordinates_for_stop(self.route[self.current_stop_index])
        
    def start(self):
        self.logger.log(f"Starting train client {self.vehicle_id}. Logs will be saved to logs/{self.vehicle_id}.txt", also_print=True)
        
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
            self.logger.log("Shutting down train client...", also_print=True)
        finally:
            self.close()
            
    def simulate_movement(self):
        """Simulate train movement between stations"""
        # Track progress between stops (0-100%)
        progress_to_next_stop = 0
        
        while self.running:
            # Check if server connection is lost and reconnection failed
            if self.server_shutdown_detected and not self.tcp_socket:
                self.logger.log("Lost connection to server and reconnection failed. Shutting down.", also_print=True)
                break
                
            # Check if train is shut down
            if self.is_shutdown:
                # When shut down, send a status update to show we're in standby
                if progress_to_next_stop == 0:
                    self.send_status_update()
                self.logger.log(f"Train is in standby mode", also_print=True)
                time.sleep(5)  # Check every 5 seconds if shutdown has been lifted
                continue
                
            # Check if train is delayed
            current_time = time.time()
            if self.is_delayed and current_time < self.delay_until:
                # Train is delayed, just wait without sending constant updates
                time.sleep(1)
                continue
                
            if self.is_delayed and current_time >= self.delay_until:
                # Delay period is over
                self.is_delayed = False
                self.logger.log(f"Delay period over, resuming normal operation")
                
            # Send TCP status update
            if progress_to_next_stop == 0:
                self.send_status_update()
                
                # Notify observers of arrival (part of Observer pattern)
                self.notify_observers("ARRIVAL", f"Train {self.vehicle_id} arrived at {self.route[self.current_stop_index]}")
                
                self.logger.log(f"Train arrived at {self.route[self.current_stop_index]}", also_print=True)
            
            # Get current and next stop coordinates
            current_stop = self.route[self.current_stop_index]
            next_stop_index = (self.current_stop_index + 1) % len(self.route)
            next_stop = self.route[next_stop_index]
            
            # Simulate travel time between stations
            # For demo purposes, we'll use 15 seconds instead of several minutes
            travel_time = 15  # seconds
            travel_start = time.time()
            
            # During travel, send UDP updates at intervals
            while time.time() - travel_start < travel_time and self.running and not self.is_shutdown:
                # Update progress towards next stop
                elapsed_ratio = (time.time() - travel_start) / travel_time
                progress_to_next_stop = min(100, elapsed_ratio * 100)
                
                # Update simulated location based on progress between stops
                current_coords = get_coordinates_for_stop(current_stop)
                self.location = calculate_realistic_movement(
                    current_coords, 
                    next_stop, 
                    progress_to_next_stop
                )
                
                lat, long = self.location
                
                # Send UDP beacon with current location
                send_udp_beacon(
                    self.vehicle_id,
                    self.vehicle_type,
                    self.status,
                    {"lat": lat, "long": long},
                    next_stop,
                    self.eta
                )
                
                # Wait a bit between updates
                time.sleep(5)
                
                # Update ETA
                remaining_ratio = 1 - (progress_to_next_stop / 100)
                self.eta = max(1, int(8 * remaining_ratio))
                
            # Move to next stop if not delayed or shutdown
            if not self.is_delayed and not self.is_shutdown:
                # Update position in route
                self.current_stop_index = next_stop_index
                self.next_stop = self.route[(next_stop_index + 1) % len(self.route)]
                
                # Reset progress for the next leg
                progress_to_next_stop = 0
                
                # Reset ETA for next stop
                self.eta = random.randint(2, 8)
                
    def handle_command(self, command_message):
        """Handle commands from the server (part of Command pattern)"""
        command_type = command_message["command"]
        params = command_message.get("params", {})
        
        if command_type == Command.DELAY:
            duration = params.get("duration", 30)  # Default 30 seconds
            self.execute(Command.DELAY, {"duration": duration})
            self.send_command_ack(command_type, f"Delayed for {duration} seconds")
            
        elif command_type == Command.SHUTDOWN:
            self.execute(Command.SHUTDOWN)
            self.send_command_ack(command_type, "Entering standby mode")
            
        elif command_type == Command.REROUTE:
            self.execute(Command.REROUTE)
            self.send_command_ack(command_type, "Route changed")
            
        elif command_type == Command.START_ROUTE:
            # New: Add support for START_ROUTE command
            if self.is_shutdown:
                self.execute(Command.START_ROUTE)
                self.send_command_ack(command_type, "Resuming route")
            else:
                self.send_command_ack(command_type, "Already active")
        else:
            self.send_command_rejected(command_type, "Unknown command")
            
    def execute(self, command, params=None):
        """Execute a command (implementation of Command pattern)"""
        if command == Command.DELAY:
            duration = params.get("duration", 30)
            self.is_delayed = True
            self.status = Status.DELAYED
            self.delay_until = time.time() + duration
            self.logger.log(f"Train delayed for {duration} seconds")
            
        elif command == Command.SHUTDOWN:
            self.is_shutdown = True
            self.status = Status.STANDBY
            self.logger.log(f"Train entering standby mode")
            
        elif command == Command.REROUTE:
            # Simulate rerouting by shuffling stops (except first and last)
            if len(self.route) > 3:
                middle_stops = self.route[1:-1]
                random.shuffle(middle_stops)
                self.route = [self.route[0]] + middle_stops + [self.route[-1]]
                self.logger.log(f"Train rerouted: {' -> '.join(self.route)}")
            else:
                self.logger.log(f"Route too short to reroute")
                
        elif command == Command.START_ROUTE:
            # New: Add support for starting the route again
            if self.is_shutdown:
                self.is_shutdown = False
                self.status = Status.ON_TIME
                self.logger.log(f"Train resuming route")

if __name__ == "__main__":
    # Check if a vehicle ID was provided
    vehicle_id = None
    if len(sys.argv) > 1:
        vehicle_id = sys.argv[1]
        
    train = TrainClient(vehicle_id)
    train.start()
