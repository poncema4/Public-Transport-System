import os
import sys
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

import sqlite3
import threading
from common.patterns import CommandExecutor
from common.utils import *
from vehicles.base_vehicle import *
from vehicles.route_vehicle import RouteVehicle

class ShuttleClient(RouteVehicle, CommandExecutor):
    def __init__(self, vehicle_id=None):
        if not vehicle_id:
            next_number = random.randint(1, 99)
            vehicle_id = f"S{next_number}"
        super().__init__(vehicle_id, VehicleType.SHUTTLE, SHUTTLE_ROUTE.copy(), Status.STANDBY)
        self.start_time = "08:00" # Scheduled start time (8:00 AM) anytime after this will be allowed to run
        self.is_active = False
        self.__passive_counter: int = 0
        self.next_departure_time = self.start_time
        self.location = get_coordinates_for_stop(self._route[self._current_stop_index])

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
            speed = random.uniform(5, 25)  # Realistic speed for a shuttle (5-25 km/h)
            network_status = random.choice(["On Time", "Delayed", "Active", "Unknown"])

            # Send real-time update to the server
            self.send_status_update()

            # Log location update locally
            self.log_location_update(lat, long, speed, network_status)
            time.sleep(pause)
        return last_tcp_timestamp

    #region RouteVehicle Overrides
    def _in_passive_mode(self) -> bool:
        return not self.is_active

    def _simulate_passive(self):
        """Emit occasional TCP + regular UDP in standby."""
        self.__passive_counter += 1
        if self.__passive_counter % 5 == 0:
            self.send_status_update()

        lat, lon = self.location
        send_udp_beacon(
            self.vehicle_id,
            self.vehicle_type,
            self.status,
            {"lat": lat, "long": lon},
            None,
            None
        )
        self.logger.log(f"[UDP] Passive beacon from {self.vehicle_id}")
        self.logger.log(
            f"Shuttle {self.vehicle_id} | Status: {self.status} | "
            f"Next Departure: {self.next_departure_time}"
        )
        time.sleep(10)

    def _progress_generator(self, current_stop, next_stop):
        travel_time = 30
        start: float = time.time()

        while True:
            elapsed: float = time.time() - start
            pct: float = min(100, int(elapsed / travel_time * 100))
            yield pct, 5
            if pct >= 100: break

    def _on_arrival(self, arrived_stop):
        self.notify_observers(
            "ARRIVAL",
            f"Shuttle {self.vehicle_id} arrived at {arrived_stop}"
        )
        # If not at the end of the route, continue route
        if not self._current_stop_index == 0:
            self.logger.log(f"Arrived at {arrived_stop}, next stop {self._next_stop}")
            return
        # Else we are at the end of the route, go to standby
        self.logger.log(
            f"Shuttle {self.vehicle_id} completed route, returning to standby",
            also_print=True
        )
        self.is_active = False
        self.status = Status.STANDBY
        self.next_departure_time = self.calculate_next_departure()
        self.logger.log(f"Next scheduled departure: {self.next_departure_time}")
    #endregion

    #region Vehicle Overrides
    def _pre_step(self):
        """Activate at scheduled start_time."""
        now = datetime.datetime.now().strftime("%H:%M")
        if not self.is_active and now >= self.start_time:
            self.logger.log(
                f"Scheduled start ({self.start_time}) reached; activating {self.vehicle_id}",
                also_print=True
            )
            self.is_active = True
            self.status = Status.ACTIVE
    #endregion

    def calculate_next_departure(self) -> str:
        # schedule next departure in 30m
        now = datetime.datetime.now()
        hh, mm = map(int, self.next_departure_time.split(':'))
        last_dep = now.replace(hour=hh, minute=mm)
        next_dep = last_dep + datetime.timedelta(minutes=30)
        if next_dep <= now:
            next_dep += datetime.timedelta(minutes=30)
        return next_dep.strftime("%H:%M")
    
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
            self._is_delayed = True
            self.status = Status.DELAYED
            self._delay_until = time.time() + duration
            self.logger.log(f"Shuttle delayed for {duration} seconds")
            
if __name__ == "__main__":
    # Check if a vehicle ID was provided
    vehicle_id = None
    if len(sys.argv) > 1:
        vehicle_id = sys.argv[1]
        
    shuttle = ShuttleClient(vehicle_id)
    shuttle.start()
