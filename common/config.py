# Constants
TCP_SERVER_HOST = "localhost" # (If you want to run the server and client on multiple devices, changes this to the local IP address)
TCP_SERVER_PORT = 5000
UDP_SERVER_PORT = 5001
BUFFER_SIZE = 1024

# Vehicle IDs and routes
BUS_ROUTE = ["Port Authority Terminal", "Times Square", "Flatiron", "Union Square", "Wall Street"]
TRAIN_ROUTE = ["Queens Plaza", "Herald Square", "Delancey St", "Middle Village"]
UBER_START = "Washington Square"
UBER_END = "Columbia University"
SHUTTLE_ROUTE = ["Penn Station", "JFK Airport"]

# Route coordinates (approximate NYC coordinates)
ROUTE_COORDS = {
    # Bus route coordinates
    "Port Authority Terminal": (40.7577, -73.9901),
    "Times Square": (40.7580, -73.9855),
    "Flatiron": (40.7411, -73.9897),
    "Union Square": (40.7359, -73.9911),
    "Wall Street": (40.7068, -74.0090),

    # Train route coordinates
    "Queens Plaza": (40.7489, -73.9375),
    "Herald Square": (40.7497, -73.9876),
    "Delancey St": (40.7183, -73.9593),
    "Middle Village": (40.7147, -73.8878),

    # Shuttle route coordinates
    "Penn Station": (40.7506, -73.9939),
    "JFK Airport": (40.6413, -73.7781),

    # Uber route coordinates
    "Washington Square": (40.7308, -73.9973),
    "Greenwich Village": (40.7336, -74.0027),
    "Near NYU": (40.7295, -73.9965),
    "Near Flatiron": (40.7411, -73.9897),
    "Near Bryant Park": (40.7536, -73.9832),
    "Midtown": (40.7549, -73.9840),
    "Columbus Circle": (40.7682, -73.9819),
    "Upper West Side": (40.7870, -73.9754),
    "Near Columbia University": (40.8075, -73.9626),
    "Columbia University": (40.8075, -73.9626)
}

# Message types
class MessageType:
    STATUS_UPDATE = "STATUS_UPDATE"
    LOCATION_UPDATE = "LOCATION_UPDATE"
    COMMAND = "COMMAND"
    COMMAND_ACK = "COMMAND_ACK"
    COMMAND_REJECTED = "COMMAND_REJECTED"
    REGISTRATION = "REGISTRATION"

# Commands
class Command:
    DELAY = "DELAY"
    REROUTE = "REROUTE"
    SHUTDOWN = "SHUTDOWN"
    START_ROUTE = "START_ROUTE"

# Status
class Status:
    ON_TIME = "On Time"
    DELAYED = "Delayed"
    ACTIVE = "Active"
    STANDBY = "Standby"

# Vehicle types
class VehicleType:
    BUS = "Bus"
    TRAIN = "Train"
    UBER = "Uber"
    SHUTTLE = "Shuttle"