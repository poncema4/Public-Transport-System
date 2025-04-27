# Public-Transport-System

## Overview
The Public Transport System simulates a transportation network with real-time location updates, event logging, and admin commands for managing vehicles like buses, trains, shuttles, and private rides (e.g., Uber)

---

## Setup Instructions

## Prerequisites
1. **Python 3.13.2**: Ensure Python is installed.
2. **Sqlite3**: The system uses Sqlite3 for data storage.
3. **Dependencies**: Install required Python libraries using `pip`.

## Steps to Set Up
1. Clone the repository:
   ```bash
   git clone https://github.com/poncema4/Public-Transport-System.git
   cd Public-Transport-System
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Start the server:
   ```bash
    python server/server.py
   ```

6. Start the vehicle client (e.g., Bus):
   ```bash
    python vehicles/bus.py
   ```

8. Repeat step 4 for other vehicle types (e.g. train.py, shuttle.py, uber.py).

9. Use the admin console in the server to issue commands or monitor the system.

10. Use sqlite3.exe in the cloned repository to be able to see your databases and tables

---

## Design Decisions

1. **Modular Architecture**
    - The system is divided into three main modules:
        + Server: Manages vehicle connections, log events, and handle admin commands
        + Vehicles: Simulates different types of vehicles with unique behaviors
        + Common: Contains shared utilities, configurations, and design patterns

2. **Database Design**
    - sqlite3 is used for persistant storage, the tables include:
        + Vehicles: Tracks connected vehicles and their statuses
        + Routes: Stores predefined routes for vehicles
        + Event_logs; Logs significant events (when a vehicle joins or leaves, error in admin commands)
        + Location_updates: Logs real-time location updates for vehicles
        + Admin_commands: Logs admin commands used against clients and any changes with the command panel

3. **Real-Time Communication**
    - TCP: Used for reliable communication between the server and vehicles
    - UDP: Used for lightweight location updates

4. **Dynamic Speed Calculation**
    - Vehicles speed is dynamically calculated based on progress and vehicle type. Speed decreases as the vehicle approaches its destination

---

## Implemented Design Patterns

1. **Observer Pattern**
    - Purpose: Notify observers of signicant events (e.g., vehicle connections, disconnections).
    - Implementation:
        + Subject class manages a list of observers.
        + LogObserver logs events when notified by the server.

2. **Command Pattern**
    - Purpose: Encapsulate admin commands as objects for flexibility and extending it in the future
    - Implementation:
        + CommandHandler encapsulates commnads like DELAY, REROUTE, and SHUTDOWN.
        + Vehicles implement CommandExecutor to handle and execute commands.

3. **Abstract Factory Pattern**
    - Purpose: Provide a way to create families of related objects without specifying their concrete classes.
    - Implementation:
        + Abstract base class like RouteVehicle and PointToPointVehicle define common behavior for specific vehicle types

4. **Singleton Pattern**
    - Purpose: Ensure a single instance of the server is running.
    - Implementation:
        + The TransportServer class is instantiated only once in the main script

---

## Features

1. Real-Time Location Updates:
    - Vehicles send location updates via UDP.
    - The server logs these updates in the location_updates table.

2. Event Logging:
    - Significant events (e.g., vehicle connections, admin commands) are logged in the event_logs table.

3. Admin Commands:
    - Admins can issue commands like DELAY, REROUTE, and SHUTDOWN to manage vehicles.

4. Dynamic Speed Adjustment:
    - Vehicle speed is calculated dynamically based on progress and vehicle type.

---

## Future Enhancements

1. Web Interface:
    - Add a web-based dashboard for monitoring and managing the system, like a GUI.

2. Advanced Routing:
    - Implement dynamic routing based on traffic conditions.

3. Analytics:
    - Provide insights into vehicle performance and system usage.
