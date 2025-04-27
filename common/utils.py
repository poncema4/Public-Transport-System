import os
import sys
import datetime
import random
import re
from typing import Tuple

from common.config import ROUTE_COORDS

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)


class Logger:
    """
    Logger for server or client events, writing to text files and optionally printing to console.
    """

    def __init__(self, name: str, is_server: bool = False) -> None:
        logs_dir = os.path.join(project_root, "logs")
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir)

        self.name = name
        self.is_server = is_server
        self.log_file = os.path.join(logs_dir, f"{name}.txt")

        with open(self.log_file, 'w') as f:
            timestamp = get_current_time_string()
            if is_server:
                f.write(f"[{timestamp}] SERVER STARTED at Bryant Park Control Center\n")
            else:
                f.write(f"[{timestamp}] {name} client started\n")

    def log(self, message: str, also_print: bool = False) -> None:
        """
        Log a message to the log file (and optionally print it to the console).
        :param message: Message to log.
        :param also_print: Whether to print the message to console as well.
        """
        timestamp = get_current_time_string()
        log_entry = f"[{timestamp}] {message}\n"

        with open(self.log_file, 'a') as f:
            f.write(log_entry)

        if also_print:
            print(f"[{timestamp}] {message}")


def get_current_time_string() -> str:
    """
    Get the current time as a string formatted HH:MM:SS.
    :return: Current time string.
    """
    return datetime.datetime.now().strftime("%H:%M:%S")


def get_formatted_coords() -> Tuple[float, float]:
    """
    Generate random (latitude, longitude) coordinates within a specified NYC area.
    :return: Tuple of (latitude, longitude).
    """
    lat = random.uniform(40.7, 40.8)
    long = random.uniform(-74.0, -73.9)
    return lat, long


def calculate_realistic_movement(
        current_location: Tuple[float, float],
        next_stop: str,
        progress_percent: float = None
) -> Tuple[float, float]:
    """
    Calculate realistic interpolated coordinates between the current location and next stop.
    :param current_location: Tuple of (latitude, longitude) representing the current position.
    :param next_stop: Name of the next stop (looked up in ROUTE_COORDS).
    :param progress_percent: Progress towards next stop (0–100). If None, random small progress is used.
    :return: New (latitude, longitude) coordinates.
    """
    if progress_percent is None:
        progress_percent = random.uniform(5, 15)

    progress_percent = max(0, min(100, int(progress_percent)))
    progress_ratio = progress_percent / 100.0

    if next_stop in ROUTE_COORDS:
        dest_lat, dest_long = ROUTE_COORDS[next_stop]
    else:
        dest_lat = current_location[0] + random.uniform(0.001, 0.003)
        dest_long = current_location[1] + random.uniform(0.001, 0.003)

    jitter_lat = random.uniform(-0.0005, 0.0005)
    jitter_long = random.uniform(-0.0005, 0.0005)

    new_lat = current_location[0] + (dest_lat - current_location[0]) * progress_ratio + jitter_lat
    new_long = current_location[1] + (dest_long - current_location[1]) * progress_ratio + jitter_long

    return (new_lat, new_long)


def get_coordinates_for_stop(stop_name: str) -> Tuple[float, float]:
    """
    Get the (latitude, longitude) coordinates for a given stop name.
    :param stop_name: Name of the stop to look up.
    :return: (latitude, longitude) coordinates, or default coordinates if unknown.
    """
    if stop_name in ROUTE_COORDS:
        return ROUTE_COORDS[stop_name]
    else:
        return (40.7580, -73.9855)  # Default to Times Square if unknown


def normalize_whitespace(s: str) -> str:
    """
    Normalize whitespace in a string: collapse multiple spaces into a single space and trim.

    :param s: Input string.
    :return: Cleaned-up string.
    """
    return re.sub(r'\s+', ' ', s.strip())
