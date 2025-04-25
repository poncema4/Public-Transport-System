import os
import sys
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

import time
from common.config import VehicleType, TRAIN_ROUTE, Status, Command
from common.patterns import CommandExecutor
from common.utils import *
from vehicles.route_vehicle import RouteVehicle

class TrainClient(RouteVehicle, CommandExecutor):
    def __init__(self, vehicle_id=None):
        if not vehicle_id:
            next_number = random.randint(1, 99)
            vehicle_id = f"T{next_number}"
        super().__init__(vehicle_id, VehicleType.TRAIN, TRAIN_ROUTE.copy(), Status.ON_TIME)
        self.eta: int = random.randint(2, 8)
        self.is_shutdown: bool = False
        self.__standby_reported: bool = False
        self.location: tuple[float, float] = get_coordinates_for_stop(self._route[self._current_stop_index])

    def _movement_step(self, last_tcp_timestamp: float) -> float:
        """Simulate movement and log location updates."""
        for progress, pause in self._progress_generator(self._route[self._current_stop_index], self._next_stop):
            if not self.running:
                break

            # Update location dynamically
            self.location = calculate_realistic_movement(
                get_coordinates_for_stop(self._route[self._current_stop_index]),
                get_coordinates_for_stop(self._next_stop),
                progress
            )
            lat, long = self.location
            speed = random.uniform(40, 120)  # Realistic speed for a train (40-120 km/h)
            network_status = random.choice(["On Time", "Delayed", "Active", "Unknown"])

            # Send real-time update to the server
            self.send_status_update()

            # Log location update locally
            self.log_location_update(lat, long, speed, network_status)
            time.sleep(pause)
        return last_tcp_timestamp

    #region RouteVehicle Overrides
    def _in_passive_mode(self) -> bool:
        return self.is_shutdown

    def _simulate_passive(self):
        # Only send one status at the start of standby
        if not self.__standby_reported:
            self.send_status_update()
            self.__standby_reported = True
        self.logger.log(f"Train is in standby mode", also_print=True)
        time.sleep(5)

    def _progress_generator(self, current_stop, next_stop):
        travel_time: float  = 15.0
        start: float = time.time()
        while True:
            elapsed = time.time() - start
            pct = min(100.0, (elapsed / travel_time) * 100.0)
            # recalc ETA for train
            self.eta = max(1, int(8 * (1 - pct / 100)))
            yield pct, 5
            if pct >= 100.0:
                break

    def _on_arrival(self, arrived_stop):
        # Reset standby flag
        self.__standby_reported = False
        # Notify observers and log
        self.notify_observers(
            "ARRIVAL",
            f"Train {self.vehicle_id} arrived at {arrived_stop}"
        )
        self.logger.log(f"Train {self.vehicle_id} arrived at {arrived_stop}", also_print=True)
        # Advance next stop and reset ETA
        self._current_stop_index = (self._current_stop_index + 1) % len(self._route)
        self._next_stop = self._route[(self._current_stop_index + 1) % len(self._route)]
        self.eta = random.randint(2, 8)
    #endregion

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
            self._is_delayed = True
            self._status = Status.DELAYED
            self._delay_until = time.time() + duration
            self.logger.log(f"Train delayed for {duration} seconds")
            
        elif command == Command.SHUTDOWN:
            self.is_shutdown = True
            self._status = Status.STANDBY
            self.logger.log(f"Train entering standby mode")
            
        elif command == Command.REROUTE:
            # Simulate rerouting by shuffling stops (except first and last)
            if len(self._route) > 3:
                middle_stops = self._route[1:-1]
                random.shuffle(middle_stops)
                self._route = [self._route[0]] + middle_stops + [self._route[-1]]
                self.logger.log(f"Train rerouted: {' -> '.join(self._route)}")
            else:
                self.logger.log(f"Route too short to reroute")
                
        elif command == Command.START_ROUTE:
            # New: Add support for starting the route again
            if self.is_shutdown:
                self.is_shutdown = False
                self._status = Status.ON_TIME
                self.logger.log(f"Train resuming route")

if __name__ == "__main__":
    # Check if a vehicle ID was provided
    vehicle_id = None
    if len(sys.argv) > 1:
        vehicle_id = sys.argv[1]
        
    train = TrainClient(vehicle_id)
    train.start()
