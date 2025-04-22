import sys

from .base_vehicle import *
from common.patterns import CommandExecutor
from common.utils import *

class UberClient(Vehicle, CommandExecutor):
    def __init__(self, vehicle_id=None):
        # If no vehicle_id is provided, generate one
        if not vehicle_id:
            next_number = random.randint(900, 999)
            vehicle_id = f"U{next_number}"
            
        super().__init__(vehicle_id, VehicleType.UBER)
        self.start_location = UBER_START
        self.end_location = UBER_END
        self.current_location = "Near NYU"  # Text description of location
        self.status = Status.ACTIVE
        self.eta = random.randint(5, 15)  # minutes to destination
        self.progress = 0  # 0-100% of journey complete
        self.network_dropout_threshold = 50  # Simulate network dropout at 50%
        self.in_network_dropout = False
        
        # Initialize location to approximate NYU coordinates
        self.location = get_coordinates_for_stop("Near NYU")
            
    def simulate_movement(self):
        """Simulate Uber movement from start to destination"""
        # Generate waypoints between start and end
        waypoints = [
            "Near NYU",
            "Greenwich Village",
            "Union Square",
            "Near Flatiron",
            "Near Bryant Park",
            "Midtown",
            "Columbus Circle",
            "Upper West Side",
            "Near Columbia University"
        ]
        
        # Define time between updates
        update_interval = 5  # seconds
        last_tcp_update = 0  # time tracking for TCP updates
        
        while self.running and self.progress < 100:
            # Check if server connection is lost and reconnection failed
            if self.server_shutdown_detected and not self.tcp_socket:
                self.logger.log("Lost connection to server and reconnection failed. Shutting down.", also_print=True)
                break
                
            # Determine current waypoint based on progress
            waypoint_index = min(int(self.progress / 100 * len(waypoints)), len(waypoints) - 1)
            self.current_location = waypoints[waypoint_index]
            
            # Send TCP status update relatively infrequently
            current_time = time.time()
            if current_time - last_tcp_update > 30 or self.progress % 20 == 0:  # Every 30 seconds or 20% progress
                self.send_status_update()
                last_tcp_update = current_time
                
            # Check for network dropout simulation
            if 50 <= self.progress < 60:
                if not self.in_network_dropout:
                    self.in_network_dropout = True
                    self.logger.log(f"Simulating network dropout near Lincoln Tunnel", also_print=True)
                    
                # During dropout, don't send UDP but still try TCP (which will fail)
                if random.random() < 0.8:  # 80% chance of failing to send during dropout
                    self.logger.log(f"Network unstable, retrying...", also_print=True)
                    time.sleep(update_interval)
                    continue
                    
            elif self.progress >= 60 and self.in_network_dropout:
                self.in_network_dropout = False
                self.logger.log(f"Network connection re-established", also_print=True)
                
            # Calculate waypoint-to-waypoint movement
            if waypoint_index < len(waypoints) - 1:
                current_waypoint = waypoints[waypoint_index]
                next_waypoint = waypoints[waypoint_index + 1]
                
                # Calculate progress within current waypoint segment (0-100%)
                segment_progress = (self.progress % (100 / len(waypoints))) * len(waypoints)
                
                # Update location based on movement between waypoints
                self.location = calculate_realistic_movement(
                    get_coordinates_for_stop(current_waypoint),
                    next_waypoint,
                    segment_progress
                )
            else:
                # Almost at destination, fine-tune coordinates
                self.location = calculate_realistic_movement(
                    self.location,
                    self.end_location,
                    min(100, (self.progress - 90) * 10)  # Scale final approach
                )
            
            lat, long = self.location
            
            # Send UDP beacon with current location
            send_udp_beacon(
                self.vehicle_id,
                self.vehicle_type,
                self.status,
                {"lat": lat, "long": long},
                None,
                self.eta
            )
            
            self.logger.log(f"[UDP] At {self.current_location} | Progress: {self.progress}% | Location: ({lat:.4f}, {long:.4f}) | ETA: {self.eta} min")
            
            # Update progress and ETA
            progress_increment = random.randint(2, 5)  # 2-5% progress each update
            self.progress = min(100, self.progress + progress_increment)
            self.eta = max(1, int(15 * (100 - self.progress) / 100))  # Update ETA based on progress
            
            # Wait between updates
            time.sleep(update_interval)
            
        if self.progress >= 100:
            # Reached destination
            self.location = get_coordinates_for_stop(self.end_location)
            self.logger.log(f"Uber {self.vehicle_id} reached destination: {self.end_location}", also_print=True)
            self.status = Status.ON_TIME  # Trip completed
            self.send_status_update()  # Final update
            
            # Send a final UDP beacon
            lat, long = self.location
            send_udp_beacon(
                self.vehicle_id,
                self.vehicle_type,
                self.status,
                {"lat": lat, "long": long},
                None,
                0  # ETA = 0 (arrived)
            )
            
            self.running = False
            
    def handle_command(self, command_message):
        """Handle commands from the server (part of Command pattern)"""
        command_type = command_message["command"]
        
        # Uber has encapsulated business rules - it doesn't accept most commands
        if command_type == Command.SHUTDOWN:
            reason = "Cannot shutdown/cancel private ride - encapsulated rules"
            self.send_command_rejected(command_type, reason)
            
        elif command_type == Command.REROUTE:
            reason = "Cannot reroute private ride - driver autonomy rules"
            self.send_command_rejected(command_type, reason)
            
        elif command_type == Command.DELAY:
            reason = "Cannot artificially delay private ride"
            self.send_command_rejected(command_type, reason)
            
        else:
            self.send_command_rejected(command_type, "Unknown or unsupported command")
            
    def execute(self, command, params=None):
        """Execute a command (implementation of Command pattern)"""
        # Uber client doesn't execute external commands due to encapsulation
        # This method is here for interface compliance but does nothing
        pass
        
if __name__ == "__main__":
    # Check if a vehicle ID was provided
    vehicle_id = None
    if len(sys.argv) > 1:
        vehicle_id = sys.argv[1]
        
    uber = UberClient(vehicle_id)
    uber.start()
