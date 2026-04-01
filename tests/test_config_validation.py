"""Test config validation and auto-discovery."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tidebedpy.config import TideBedConfig


def test_default_config():
    """Default config should be creatable without errors."""
    config = TideBedConfig()
    assert config.rank_limit == 10
    assert config.time_interval_sec == 0


def test_validate_empty_config():
    """Empty config should have validation errors."""
    config = TideBedConfig()
    errors = config.validate()
    assert len(errors) > 0  # Missing nav, tide, db, station, output


def test_rank_limit_bounds():
    """Rank limit should accept non-negative values."""
    config = TideBedConfig()
    config.rank_limit = 0
    assert config.rank_limit >= 0

    config.rank_limit = 10
    assert config.rank_limit == 10


def test_utc_offset_kst():
    """UTC offset for KST should be 9.0."""
    config = TideBedConfig()
    config.utc_offset = 9.0
    assert config.utc_offset == 9.0
    config.is_kst = True
    assert config.is_kst is True


def test_validate_with_valid_paths(tmp_path):
    """Config with valid paths should have fewer errors."""
    config = TideBedConfig()

    # Create minimal required directory structure
    nav_dir = tmp_path / "nav"
    nav_dir.mkdir()
    tide_dir = tmp_path / "tide"
    tide_dir.mkdir()
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    station_file = tmp_path / "station.txt"
    station_file.write_text("TRUE\n", encoding='utf-8')
    output_file = tmp_path / "output.tid"

    config.nav_directory = str(nav_dir)
    config.tts_folder = str(tide_dir)
    config.db_root = str(db_dir)
    config.ref_st_info_path = str(station_file)
    config.output_path = str(output_file)

    errors = config.validate()
    assert len(errors) == 0


def test_default_tide_series_type():
    """Default tide series type should be set."""
    config = TideBedConfig()
    assert config.tide_series_type in ('\uc2e4\uce21', '\uc608\uce21')


def test_write_detail_default():
    """Write detail should default to True."""
    config = TideBedConfig()
    assert config.write_detail is True
