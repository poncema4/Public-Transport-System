import pytest
from common import config

def test_constants_values():
    assert config.TCP_SERVER_HOST == "localhost"
    assert config.TCP_SERVER_PORT == 5000
    assert config.UDP_SERVER_PORT == 5001
    assert config.BUFFER_SIZE == 1024

def test_bus_route():
    assert isinstance(config.BUS_ROUTE, list)
    assert config.BUS_ROUTE[0] == "Port Authority Terminal"
    assert config.BUS_ROUTE[-1] == "Wall Street"

def test_train_route():
    assert isinstance(config.TRAIN_ROUTE, list)
    assert config.TRAIN_ROUTE[0] == "Queens Plaza"
    assert config.TRAIN_ROUTE[-1] == "Middle Village"

def test_shuttle_route():
    assert isinstance(config.SHUTTLE_ROUTE, list)
    assert config.SHUTTLE_ROUTE == ["Penn Station", "JFK Airport"]

def test_uber_start_and_end():
    assert config.UBER_START == "Washington Square"
    assert config.UBER_END == "Columbia University"

def test_route_coords_structure():
    for stop, coords in config.ROUTE_COORDS.items():
        assert isinstance(stop, str)
        assert isinstance(coords, tuple)
        assert len(coords) == 2
        lat, lon = coords
        assert isinstance(lat, float)
        assert isinstance(lon, float)
        assert -90 <= lat <= 90
        assert -180 <= lon <= 180

def test_message_types_defined():
    assert hasattr(config.MessageType, "STATUS_UPDATE")
    assert hasattr(config.MessageType, "LOCATION_UPDATE")
    assert hasattr(config.MessageType, "COMMAND")
    assert hasattr(config.MessageType, "COMMAND_ACK")
    assert hasattr(config.MessageType, "COMMAND_REJECTED")
    assert hasattr(config.MessageType, "REGISTRATION")

def test_command_types_defined():
    assert hasattr(config.Command, "DELAY")
    assert hasattr(config.Command, "REROUTE")
    assert hasattr(config.Command, "SHUTDOWN")
    assert hasattr(config.Command, "START_ROUTE")

def test_status_types_defined():
    assert hasattr(config.Status, "ON_TIME")
    assert hasattr(config.Status, "DELAYED")
    assert hasattr(config.Status, "ACTIVE")
    assert hasattr(config.Status, "STANDBY")

def test_vehicle_types_defined():
    assert hasattr(config.VehicleType, "BUS")
    assert hasattr(config.VehicleType, "TRAIN")
    assert hasattr(config.VehicleType, "UBER")
    assert hasattr(config.VehicleType, "SHUTTLE")
