import time

from base_vehicle import Vehicle
from abc import ABC, abstractmethod

from common.utils import calculate_realistic_movement, get_coordinates_for_stop, send_udp_beacon


class RouteVehicle(Vehicle, ABC):
    def __init__(self, vehicle_id: str, vehicle_type: str, route: list[str], status: str):
        super().__init__(vehicle_id, vehicle_type)
        self._route: list[str] = route
        self._current_stop_index: int = 0
        self._next_stop: str | None = self._route[1] if len(self._route) > 1 else None
        self._status: str = status
        self._delay_until: float = 0.0
        self._is_delayed: bool = False

    def _movement_step(self, last_tcp_timestamp: float) -> float:
        # Passive standby?
        if self._in_passive_mode():
            self._simulate_passive()
            return last_tcp_timestamp

        # Active: send a TCP status update at start of each leg
        self.send_status_update()

        # Identify points
        current = self._route[self._current_stop_index]
        next_idx = (self._current_stop_index + 1) % len(self._route)
        next_stop = self._route[next_idx]
        self.next_stop = next_stop

        self.logger.log(f"Shuttle at {current}, heading to {next_stop}")

        # Step through progress until arrival
        for progress, pause in self._progress_generator(current, next_stop):
            if not self.running:
                break

            if progress >= 100:
                # Arrived
                self._current_stop_index = next_idx
                self.location = get_coordinates_for_stop(next_stop)
                self._on_arrival(next_stop)
                return last_tcp_timestamp

            # In‑flight update
            self.location = calculate_realistic_movement(
                get_coordinates_for_stop(current),
                next_stop,
                progress
            )
            lat, long = self.location
            send_udp_beacon(
                self.vehicle_id,
                self.vehicle_type,
                self.status,
                {"lat": lat, "long": long},
                self.next_stop,
                getattr(self, "eta", None)
            )
            self.logger.log(f"[UDP] Progress: {progress:.1f}% to {next_stop} | Location: ({lat:.4f}, {long:.4f})")

            time.sleep(pause)

        return last_tcp_timestamp

    def _in_passive_mode(self) -> bool:
        return False

    def _simulate_passive(self):
        pass

    @abstractmethod
    def _progress_generator(self, current_stop, next_stop):
        pass

    @abstractmethod
    def _on_arrival(self, arrived_stop):
        pass