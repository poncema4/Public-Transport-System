# Public-Transport-System

## Overview
The Public Transport System simulates a transportation network with real-time location updates, event logging, and admin commands for managing vehicles like buses, trains, shuttles, and private rides (e.g., Uber)

---

## Setup Instructions

### Prerequisites
1. **Python 3.13.2**: Ensure Python is installed.
2. **Sqlite3**: The system uses Sqlite3 for data storage.
3. **Dependencies**: Install required Python libraries using `pip`.

### Steps to Set Up
1. Clone the repository:
   ```bash
   git clone https://github.com/poncema4/Public-Transport-System.git
   cd Public-Transport-System
   ```

2. Install dependencies:
    pip install -r requirements.txt

3. Start the server:
    python server/server.py

4. Start the vehicle client (e.g., Bus):
    python vehicles/bus.py

5. Repeat step 4 for other vehicle types (e.g. train.py, shuttle.py, uber.py).

6. Use the admin console in the server to issue commands or monitor the system.

---

## Design Decisions

1. **Modular Architecture**
    - The system is divided into three main modules:
        Server: Manages vehicle connections, log events, and handle admin commands
        Vehicles: Simulates different types of vehicles with unique behaviors
        Common: Contains shared utilities, configurations, and design patterns

2. **Database Design**
    - sqlite3 is used for persistant storage, the tables include:
        Vehicles: Tracks connected vehicles and their statuses
        Routes: Stores predefined routes for vehicles
        Event_logs; Logs significant events (when a vehicle joins or leaves, error in admin commands)
        Location_updates: Logs real-time location updates for vehicles
        Admin_commands: Logs admin commands used against clients and any changes with the command panel

3. **Real-Time Communication**
    - TCP: Used for reliable communication between the server and vehicles
    - UDP: Used for lightweight location updates

4. **Dynamic Speed Calculation**
    - Vehicles speed is dynamically calculated based on progress and vehicle type. Speed decreases as the vehicle approaches its destination

---

# Implemented Design Patterns

1. **Observer Pattern**
    - Purpose: Notify observers of signicant events (e.g., vehicle connections, disconnections).
    - Implementation:
        + Subject class manages a list of observers.
        + LogObserver logs events when notified by the server.