import socket
import threading
import json
import time
import datetime
import random
import sys
from utils import *

class ShuttleClient(Vehicle, CommandExecutor):
    def __init__(self, vehicle_id=None):
        # If no vehicle_id is provided, generate one
        if not vehicle_id:
            next_number = random.randint(1, 99)
            vehicle_id = f"S{next_number:02d}"
            
        super().__init__(vehicle_id, VehicleType.SHUTTLE)
        self.route = SHUTTLE_ROUTE.copy()
        self.current_stop_index = 0
        self.next_stop = self.route[1] if len(self.route) > 1 else None
        self.status = Status.STANDBY
        self.start_time = "08:00"  # Scheduled start time (8:00 AM) anytime after this will be allowed to run 
        self.is_active = False
        self.is_delayed = False
        self.delay_until = 0
        
        # Initialize next departure time to 8:00 AM
        self.next_departure_time = self.start_time
        
        # Initialize location to the first stop's coordinates
        self.location = get_coordinates_for_stop(self.route[self.current_stop_index])
        
    def start(self):
        self.logger.log(f"Starting shuttle client {self.vehicle_id}. Logs will be saved to logs/{self.vehicle_id}.txt", also_print=True)
        
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
            self.logger.log("Shutting down shuttle client...", also_print=True)
        finally:
            self.close()
            
    def simulate_movement(self):
        """Simulate shuttle movement along route"""
        passive_update_count = 0
        
        while self.running:
            # Check if server connection is lost and reconnection failed
            if self.server_shutdown_detected and not self.tcp_socket:
                self.logger.log("Lost connection to server and reconnection failed. Shutting down.", also_print=True)
                break
                
            # Check if delayed
            current_time = time.time()
            if self.is_delayed and current_time < self.delay_until:
                # Shuttle is delayed, just wait
                time.sleep(1)
                continue
                
            if self.is_delayed and current_time >= self.delay_until:
                # Delay period is over
                self.is_delayed = False
                self.status = Status.ACTIVE if self.is_active else Status.STANDBY
                self.logger.log("Delay period over, resuming normal operation")
                
            current_hour = datetime.datetime.now().strftime("%H:%M")
            
            # Check if it's time to start automatically (if not already active)
            if not self.is_active and current_hour >= self.start_time:
                self.logger.log(f"Scheduled start time reached ({self.start_time}). Shuttle {self.vehicle_id} activating automatically.")
                self.is_active = True
                self.status = Status.ACTIVE
                
            # If in standby mode, send only passive updates
            if not self.is_active:
                passive_update_count += 1
                
                if passive_update_count % 5 == 0:  # Only do TCP updates occasionally in standby
                    self.send_status_update()
                    
                # Send UDP passive beacon
                lat, long = self.location
                send_udp_beacon(
                    self.vehicle_id,
                    self.vehicle_type,
                    self.status,
                    {"lat": lat, "long": long},
                    None,
                    None
                )
                
                self.logger.log(f"[UDP] {self.vehicle_id} -> Broadcasted passive status:")
                self.logger.log(f"Shuttle {self.vehicle_id} | Status: {self.status} | Next Departure: {self.next_departure_time}")
                
                time.sleep(10)  # Wait 10 seconds between passive updates
                continue
                
            # Active shuttles behave differently
            # Send TCP status update
            self.send_status_update()
            
            # For active shuttles, simulate movement
            current_stop = self.route[self.current_stop_index]
            next_stop_index = (self.current_stop_index + 1) % len(self.route)
            next_stop = self.route[next_stop_index]
            self.next_stop = next_stop
            
            self.logger.log(f"Shuttle at {current_stop}, heading to {next_stop}")
            
            # Travel to next stop - initialize progress tracking
            travel_time = 30  # seconds for demo
            travel_start = time.time()
            
            # During travel, send UDP updates at intervals
            while time.time() - travel_start < travel_time and self.running:
                # Calculate progress percentage
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
                
                # Send UDP location update
                send_udp_beacon(
                    self.vehicle_id,
                    self.vehicle_type,
                    self.status,
                    {"lat": lat, "long": long},
                    self.next_stop,
                    None
                )
                
                self.logger.log(f"[UDP] Progress: {progress_to_next_stop:.1f}% to {next_stop} | Location: ({lat:.4f}, {long:.4f})")

                time.sleep(5)  # 5 seconds between updates
                
            # Move to next stop
            self.current_stop_index = next_stop_index
            next_stop_index = (self.current_stop_index + 1) % len(self.route)
            self.next_stop = self.route[next_stop_index]
            
            # Notify observers of arrival (part of Observer pattern)
            self.notify_observers("ARRIVAL", f"Shuttle {self.vehicle_id} arrived at {current_stop}")
            
            # If we've completed the route (back to Penn Station), go to standby
            if self.current_stop_index == 0:
                self.logger.log(f"Shuttle {self.vehicle_id} completed route, returning to standby", also_print=True)
                self.is_active = False
                self.status = Status.STANDBY
                
                # Calculate next scheduled departure time (exactly 30 minutes from the previous scheduled departure)
                now = datetime.datetime.now()
                
                # Parse the previous departure time
                departure_hour, departure_minute = map(int, self.next_departure_time.split(':'))
                last_departure = now.replace(hour=departure_hour, minute=departure_minute)
                
                # Calculate the next 30-minute slot after the previous departure
                next_departure = last_departure + datetime.timedelta(minutes=30)
                self.next_departure_time = next_departure.strftime("%H:%M")
                
                # If we've somehow calculated a time in the past, add another 30 minutes
                current_time_str = now.strftime("%H:%M")
                if self.next_departure_time <= current_time_str:
                    next_departure = next_departure + datetime.timedelta(minutes=30)
                    self.next_departure_time = next_departure.strftime("%H:%M")
                
                self.logger.log(f"Next scheduled departure: {self.next_departure_time}")
    
    def handle_command(self, command_message):
        """Handle commands from the server (part of Command pattern)"""
        command_type = command_message["command"]
        params = command_message.get("params", {})
        
        if command_type == Command.START_ROUTE:
            # Check if we're allowed to start (time-based validation)
            current_time = datetime.datetime.now().strftime("%H:%M")
            
            if current_time >= self.start_time:
                # It's past the start time, we can start
                self.execute(Command.START_ROUTE)
                self.send_command_ack(command_type, "Starting route")
            else:
                # It's too early, reject command
                reason = f"Cannot start before scheduled time ({self.start_time})"
                self.send_command_rejected(command_type, reason)
                self.logger.log(f"Rejected START_ROUTE command: {reason}")
                
        elif command_type == Command.SHUTDOWN:
            self.execute(Command.SHUTDOWN)
            self.send_command_ack(command_type, "Shutting down")
            self.running = False
            
        elif command_type == Command.DELAY:
            duration = params.get("duration", 30)  # Default 30 seconds
            self.execute(Command.DELAY, {"duration": duration})
            self.send_command_ack(command_type, f"Delayed for {duration} seconds")
            
        else:
            self.send_command_rejected(command_type, "Unknown command")
            
    def execute(self, command, params=None):
        """Execute a command (implementation of Command pattern)"""
        if command == Command.START_ROUTE:
            self.is_active = True
            self.status = Status.ACTIVE
            self.logger.log(f"Shuttle activated")
            
        elif command == Command.SHUTDOWN:
            self.logger.log(f"Shuttle shutting down")
            self.running = False
            
        elif command == Command.DELAY:
            duration = params.get("duration", 30)
            self.is_delayed = True
            self.status = Status.DELAYED
            self.delay_until = time.time() + duration
            self.logger.log(f"Shuttle delayed for {duration} seconds")
            
if __name__ == "__main__":
    # Check if a vehicle ID was provided
    vehicle_id = None
    if len(sys.argv) > 1:
        vehicle_id = sys.argv[1]
        
    shuttle = ShuttleClient(vehicle_id)
    shuttle.start()
