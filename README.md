# Public-Transport-System

## Overview
The Public Transport System simulates a transportation network with real-time location updates, event logging, and admin commands for managing vehicles like buses, trains, shuttles, and private rides (e.g., Uber)

---

## Setup Instructions

### Prerequisites
1. **Python 3.13.2**: Ensure Python is installed.
2. **SQLite**: The system uses SQLite for data storage.
3. **Dependencies**: Install required Python libraries using `pip`.

### Steps to Set Up
1. Clone the repository:
   ```bash
   git clone https://github.com/your-repo/Public-Transport-System.git
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