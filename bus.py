import socket
import threading
import json
import time
import random
import sys
from utils import *

class BusClient(Vehicle, CommandExecutor):
    def __init__(self, vehicle_id=None):
        # If no vehicle_id is provided, generate one
        if not vehicle_id:
            # Check how many buses are already running to generate a new ID
            # This is a simplification - in a real system you'd query the server
            next_number = random.randint(101, 999)
            vehicle_id = f"B{next_number}"
            
        super().__init__(vehicle_id, VehicleType.BUS)
        self.route = BUS_ROUTE.copy()
        self.current_stop_index = 0
        self.next_stop = self.route[1] if len(self.route) > 1 else None
        self.status = Status.ON_TIME
        self.eta = random.randint(1, 5)  # ETA in minutes
        self.is_delayed = False
        self.delay_until = 0
        
        # Initialize location to the first stop's coordinates
        self.location = get_coordinates_for_stop(self.route[self.current_stop_index])
        
    def start(self):
        print(f"Starting bus client {self.vehicle_id}. Logs will be saved to logs/{self.vehicle_id}.txt")
        
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
            self.logger.log("Shutting down bus client...", also_print=True)
        finally:
            self.close()
            
    def simulate_movement(self):
        """Simulate bus movement along its route"""
        # Track progress between stops (0-100%)
        progress_to_next_stop = 0
        
        while self.running:
            # Check if server connection is lost and reconnection failed
            if self.server_shutdown_detected and not self.tcp_socket:
                self.logger.log("Lost connection to server and reconnection failed. Shutting down.", also_print=True)
                break
                
            # Check if delayed
            current_time = time.time()
            if self.is_delayed and current_time < self.delay_until:
                # Bus is delayed, just wait without constant updates
                time.sleep(1)
                continue
                
            if self.is_delayed and current_time >= self.delay_until:
                # Delay period is over
                self.is_delayed = False
                self.logger.log("Delay period over, resuming normal operation")
                
            # Send TCP status update every minute (we use 60 seconds here)
            # For demo purposes, we'll use 10 seconds instead of 60
            self.send_status_update()
            
            # Get current and next stop coordinates
            current_stop = self.route[self.current_stop_index]
            next_stop_index = (self.current_stop_index + 1) % len(self.route)
            next_stop = self.route[next_stop_index]
            
            # Send UDP beacon every 10 seconds
            # For demo purposes, we'll use 3 seconds
            for _ in range(3):  # 3 beacons between status updates
                if not self.running:
                    break
                    
                # Update simulated location based on progress to next stop
                progress_to_next_stop += random.uniform(2, 8)  # Progress 2-8% at a time
                
                if progress_to_next_stop >= 100:
                    # Arrived at next stop, reset progress
                    progress_to_next_stop = 0
                    self.current_stop_index = next_stop_index
                    current_stop = self.route[self.current_stop_index]
                    next_stop_index = (self.current_stop_index + 1) % len(self.route)
                    next_stop = self.route[next_stop_index]
                    self.next_stop = next_stop
                    
                    # Check for simulated congestion at Union Square
                    if current_stop == "Union Square":
                        # 50% chance of congestion at Union Square
                        if random.random() < 0.5:
                            self.status = Status.DELAYED
                            self.eta += 2  # Add 2 minutes to ETA
                            self.logger.log(f"Experiencing congestion at Union Square")
                            
                    self.logger.log(f"Arrived at {current_stop}, next stop: {self.next_stop}")
                    
                    # Notify observers of arrival (part of Observer pattern)
                    self.notify_observers("ARRIVAL", f"Bus {self.vehicle_id} arrived at {current_stop}")
                    
                    # Reset ETA for next stop
                    self.eta = random.randint(1, 5)
                    
                    # Set location to current stop coordinates
                    self.location = get_coordinates_for_stop(current_stop)
                    
                else:
                    # Update location based on progress between stops
                    current_coords = get_coordinates_for_stop(current_stop)
                    self.location = calculate_realistic_movement(
                        current_coords, 
                        next_stop, 
                        progress_to_next_stop
                    )
                
                # Send UDP beacon with current location
                lat, long = self.location
                send_udp_beacon(
                    self.vehicle_id,
                    self.vehicle_type,
                    self.status,
                    {"lat": lat, "long": long},
                    self.next_stop,
                    self.eta
                )
                
                # Log beacon emission
                self.logger.log(f"[UDP] Sending location beacon: ({lat:.4f}, {long:.4f}) | Next stop: {self.next_stop} | ETA: {self.eta} min")
                
                # Simulate movement - wait a bit
                time.sleep(3)  # 3 seconds between UDP beacons
                
                # Update ETA based on progress
                if progress_to_next_stop > 0:
                    # Gradually decrease ETA as we get closer to destination
                    progress_ratio = progress_to_next_stop / 100.0
                    self.eta = max(1, int(5 * (1 - progress_ratio)))
                    
    def handle_command(self, command_message):
        """Handle commands from the server (part of Command pattern)"""
        command_type = command_message["command"]
        params = command_message.get("params", {})
        
        if command_type == Command.DELAY:
            duration = params.get("duration", 30)  # Default 30 seconds
            self.execute(Command.DELAY, {"duration": duration})
            self.send_command_ack(command_type, f"Delayed for {duration} seconds")
            
        elif command_type == Command.REROUTE:
            self.execute(Command.REROUTE)
            self.send_command_ack(command_type, "Route changed")
            
        elif command_type == Command.SHUTDOWN:
            self.execute(Command.SHUTDOWN)
            self.send_command_ack(command_type, "Shutting down")
            self.running = False
            
        else:
            self.send_command_rejected(command_type, "Unknown command")
            
    def execute(self, command, params=None):
        """Execute a command (implementation of Command pattern)"""
        if command == Command.DELAY:
            duration = params.get("duration", 30)
            self.is_delayed = True
            self.status = Status.DELAYED
            self.delay_until = time.time() + duration
            self.logger.log(f"Bus delayed for {duration} seconds")
            
        elif command == Command.REROUTE:
            # Simulate rerouting by shuffling stops (except first and last)
            if len(self.route) > 3:
                middle_stops = self.route[1:-1]
                random.shuffle(middle_stops)
                self.route = [self.route[0]] + middle_stops + [self.route[-1]]
                self.logger.log(f"Bus rerouted: {' -> '.join(self.route)}")
            else:
                self.logger.log(f"Route too short to reroute")
                
        elif command == Command.SHUTDOWN:
            self.logger.log(f"Received shutdown command")
            
if __name__ == "__main__":
    # Check if a vehicle ID was provided
    vehicle_id = None
    if len(sys.argv) > 1:
        vehicle_id = sys.argv[1]
        
    bus = BusClient(vehicle_id)
    bus.start()
