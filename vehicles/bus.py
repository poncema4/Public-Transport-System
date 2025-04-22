import os
import sys
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

import time
from common.config import VehicleType, BUS_ROUTE, Status, Command
from common.patterns import CommandExecutor
from common.utils import *
from vehicles.route_vehicle import RouteVehicle

class BusClient(RouteVehicle, CommandExecutor):
    def __init__(self, vehicle_id=None):
        # If no vehicle_id is provided, generate one
        if not vehicle_id:
            # Check how many buses are already running to generate a new ID
            # This is a simplification - in a real system you'd query the server
            next_number: int = random.randint(101, 999)
            vehicle_id: str = f"B{next_number}"
            
        super().__init__(vehicle_id, VehicleType.BUS, BUS_ROUTE.copy(), Status.ON_TIME)
        self.eta = random.randint(1, 5)  # ETA in minutes
        
        # Initialize location to the first stop's coordinates
        self.location = get_coordinates_for_stop(self._route[self._current_stop_index])

    #region RouteVehicle Overrides
    def _progress_generator(self, current_stop, next_stop):
        progress: float = 0.0
        iter: int = 0
        while progress < 100.0 and self.running:
            if iter % 3 == 0:
                self.send_status_update()
            iter += 1

            delta = random.uniform(2, 8)
            progress += delta
            yield min(progress, 100.0), 3


    def _on_arrival(self, arrived_stop):
        self.current_stop_index = (self._current_stop_index + 1) % len(self._route)
        self.next_stop = self._route[(self.current_stop_index + 1) % len(self._route)]

        # Congestion at Union Square
        if arrived_stop == "Union Square" and random.random() < 0.5:
            self.status = Status.DELAYED
            self.eta += 2
            self.logger.log("Experiencing congestion at Union Square")

        self.logger.log(f"Arrived at {arrived_stop}, next stop: {self.next_stop}")
        self.notify_observers(
            "ARRIVAL",
            f"Bus {self.vehicle_id} arrived at {arrived_stop}"
        )

        # Reset ETA & location
        self.eta = random.randint(1, 5)
        self.location = get_coordinates_for_stop(arrived_stop)
    #endregion

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
            self._is_delayed = True
            self._status = Status.DELAYED
            self._delay_until = time.time() + duration
            self.logger.log(f"Bus delayed for {duration} seconds")
            
        elif command == Command.REROUTE:
            # Simulate rerouting by shuffling stops (except first and last)
            if len(self._route) > 3:
                middle_stops = self._route[1:-1]
                random.shuffle(middle_stops)
                self._route = [self._route[0]] + middle_stops + [self._route[-1]]
                self.logger.log(f"Bus rerouted: {' -> '.join(self._route)}")
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
