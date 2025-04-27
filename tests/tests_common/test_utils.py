import os
import re

import pytest

from common.config import ROUTE_COORDS
from common.utils import (
    Logger,
    get_current_time_string,
    get_formatted_coords,
    calculate_realistic_movement,
    get_coordinates_for_stop,
    normalize_whitespace
)


def test_get_current_time_string_format():
    time_str = get_current_time_string()
    assert re.match(r"\d{2}:\d{2}:\d{2}", time_str)  # matches HH:MM:SS

def test_get_formatted_coords_in_bounds():
    lat, lon = get_formatted_coords()
    assert 40.7 <= lat <= 40.8
    assert -74.0 <= lon <= -73.9

def test_calculate_realistic_movement_progress_provided():
    current_location = (40.7308, -73.9973)
    next_stop = "Union Square"
    new_location = calculate_realistic_movement(current_location, next_stop, progress_percent=50)

    assert isinstance(new_location, tuple)
    assert len(new_location) == 2
    assert all(isinstance(coord, float) for coord in new_location)

def test_calculate_realistic_movement_no_progress_provided():
    current_location = (40.7308, -73.9973)
    next_stop = "Union Square"
    new_location = calculate_realistic_movement(current_location, next_stop)

    assert isinstance(new_location, tuple)
    assert len(new_location) == 2
    assert all(isinstance(coord, float) for coord in new_location)

def test_get_coordinates_for_known_stop():
    for stop_name in ROUTE_COORDS:
        coords = get_coordinates_for_stop(stop_name)
        assert isinstance(coords, tuple)
        assert len(coords) == 2
        assert all(isinstance(x, float) for x in coords)

def test_get_coordinates_for_unknown_stop():
    coords = get_coordinates_for_stop("Nonexistent Stop")
    assert coords == (40.7580, -73.9855)

def test_normalize_whitespace_various_cases():
    assert normalize_whitespace("   Hello   World ") == "Hello World"
    assert normalize_whitespace("Multiple    spaces") == "Multiple spaces"
    assert normalize_whitespace("\nNewlines\tand tabs") == "Newlines and tabs"

@pytest.fixture
def temp_logger_env(monkeypatch, tmp_path):
    """Fixture to create a temporary log folder."""
    monkeypatch.setattr("common.utils.project_root", str(tmp_path))
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(exist_ok=True)
    return logs_dir

def test_logger_initialization_creates_file(temp_logger_env):
    logger = Logger("test_logger")

    assert os.path.exists(logger.log_file)
    with open(logger.log_file) as f:
        content = f.read()
        assert "client started" in content

def test_logger_server_initialization_creates_file(temp_logger_env):
    logger = Logger("server_logger", is_server=True)

    assert os.path.exists(logger.log_file)
    with open(logger.log_file) as f:
        content = f.read()
        assert "SERVER STARTED" in content

def test_logger_log_writes_message(temp_logger_env, capsys):
    logger = Logger("log_write_test")

    logger.log("Test Message", also_print=True)

    with open(logger.log_file) as f:
        content = f.read()
        assert "Test Message" in content

    captured = capsys.readouterr()
    assert "Test Message" in captured.out
