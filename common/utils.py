import os
import sys
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

import datetime
import json
import random
import socket
from common.config import ROUTE_COORDS, MessageType, UDP_SERVER_PORT, TCP_SERVER_HOST

class Logger:
    def __init__(self, name, is_server=False):
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
                
    def log(self, message, also_print=False):
        timestamp = get_current_time_string()
        log_entry = f"[{timestamp}] {message}\n"
        
        with open(self.log_file, 'a') as f:
            f.write(log_entry)

        if also_print:
            print(f"[{timestamp}] {message}")
            
def get_current_time_string():
    return datetime.datetime.now().strftime("%H:%M:%S")

def get_formatted_coords():
    lat = random.uniform(40.7, 40.8)
    long = random.uniform(-74.0, -73.9)
    return lat, long

def calculate_realistic_movement(current_location, next_stop, progress_percent=None):
    """
    Calculate realistic coordinates between current location and next stop
    
    Args:
        current_location: Tuple (lat, long) of current position
        next_stop: String name of next stop
        progress_percent: Optional percentage of progress towards next stop (0-100)
    
    Returns:
        Tuple (lat, long) of new coordinates
    """
    if progress_percent is None:
        progress_percent = random.uniform(5, 15)
    
    progress_percent = max(0, min(100, progress_percent))
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

def get_coordinates_for_stop(stop_name):
    """Get coordinates for a named stop"""
    if stop_name in ROUTE_COORDS:
        return ROUTE_COORDS[stop_name]
    else:
        return (40.7580, -73.9855)

def send_udp_beacon(vehicle_id, vehicle_type, status, location, next_stop=None, eta=None):
    message = {
        "type": MessageType.LOCATION_UPDATE,
        "vehicle_id": vehicle_id,
        "vehicle_type": vehicle_type,
        "status": status,
        "location": location,
        "timestamp": get_current_time_string()
    }
    
    if next_stop:
        message["next_stop"] = next_stop
        
    if eta:
        message["eta"] = eta
        
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(json.dumps(message).encode(), (TCP_SERVER_HOST, UDP_SERVER_PORT))
    except Exception as e:
        log_error = f"Error sending UDP beacon: {e}"
        print(log_error)
    finally:
        sock.close()

