import os
import random
import sys

from vehicles.point_to_point_vehicle import PointToPointVehicle

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

import sqlite3
from vehicles.base_vehicle import *
from common.patterns import CommandExecutor
from common.utils import *

class UberClient(PointToPointVehicle, CommandExecutor):
    def __init__(self, vehicle_id=None):
        if not vehicle_id:
            next_number = random.randint(900, 999)
            vehicle_id = f"U{next_number}"
        super().__init__(vehicle_id, VehicleType.UBER, UBER_START, UBER_END, "Near NYU",
                         random.randint(5, 15), 50)

        # Initialize SQLite database
        self.db_lock = threading.Lock()
        self.init_database()

    def init_database(self):
        """Initialize the SQLite database for this vehicle."""
        with self.db_lock:
            conn = sqlite3.connect(f"{self.vehicle_id}.db")
            cursor = conn.cursor()

            # Create tables
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS location_updates (
                    update_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehicle_id TEXT,
                    lat REAL,
                    long REAL,
                    speed REAL,
                    timestamp TEXT,
                    network_status TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admin_commands (
                    command_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    command_type TEXT,
                    parameters TEXT,
                    sent_time TEXT,
                    response_time TEXT,
                    status TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_logs (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT,
                    details TEXT,
                    timestamp TEXT
                )
            """)
            conn.commit()
            conn.close()

    def log_location_update(self, lat, long, speed, network_status):
        """Log a location update to the database."""
        with self.db_lock:
            conn = sqlite3.connect(f"{self.vehicle_id}.db")
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO location_updates (vehicle_id, lat, long, speed, timestamp, network_status)
                VALUES (?, ?, ?, ?, datetime('now'), ?)
            """, (self.vehicle_id, lat, long, speed, network_status))
            conn.commit()
            conn.close()

    def log_event(self, event_type, details):
        """Log an event to the database."""
        with self.db_lock:
            conn = sqlite3.connect(f"{self.vehicle_id}.db")
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO event_logs (event_type, details, timestamp)
                VALUES (?, ?, datetime('now'))
            """, (event_type, details))
            conn.commit()
            conn.close()

    #region PointToPointVehicle Overrides
    def _progress_generator(self) -> float:
        # simulate one step, update progress, dropout logic, location, eta
        # network dropout
        if (self._progress >= self._network_dropout_threshold
                and self._progress < self._network_dropout_threshold + 10):
            if not self._in_network_dropout:
                self._in_network_dropout = True
                self.logger.log(
                    "Simulating network dropout near Lincoln Tunnel",
                    also_print=True
                )
            if random.random() < 0.8:
                self.logger.log("Network unstable, retrying...", also_print=True)
                return 5
        elif self._in_network_dropout:
            self._in_network_dropout = False
            self.logger.log("Network connection re-established", also_print=True)

        # advance progress and ETA
        inc = random.randint(2, 5)
        self._progress = min(100, int(self._progress + inc))
        self.eta = max(1, int(15 * (100 - self._progress) / 100))

        # waypoint-driven location
        waypoints = [
            "Near NYU", "Greenwich Village", "Union Square",
            "Near Flatiron", "Near Bryant Park", "Midtown",
            "Columbus Circle", "Upper West Side", "Near Columbia University"
        ]
        idx = min(int(self._progress / 100 * len(waypoints)), len(waypoints) - 1)
        self.current_location = waypoints[idx]
        if idx < len(waypoints) - 1:
            segment_pct = (self._progress % (100 / len(waypoints))) * len(waypoints)
            self.location = calculate_realistic_movement(
                get_coordinates_for_stop(waypoints[idx]),
                waypoints[idx + 1],
                segment_pct
            )
        else:
            self.location = calculate_realistic_movement(
                self.location,
                self._end_location,
                min(100, (self._progress - 90) * 10)
            )

        return 5

    def _on_completion(self):
        self.location = get_coordinates_for_stop(self._end_location)
        self.logger.log(
            f"Uber {self.vehicle_id} reached destination: {self._end_location}",
            also_print=True
        )
        self.status = Status.ON_TIME
        self.send_status_update()
        lat, lon = self.location
        send_udp_beacon(
            self.vehicle_id,
            self.vehicle_type,
            self.status,
            {"lat": lat, "long": lon},
            None,
            0
        )
        self.running = False
    #endregion
            
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
