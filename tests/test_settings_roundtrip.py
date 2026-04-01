"""Test settings save/load roundtrip."""
import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tidebedpy.settings_manager import (
    save_preset, load_preset, list_presets, delete_preset, PRESET_DEFAULTS,
)


def test_save_load_roundtrip(tmp_path):
    """Save a preset, load it, verify all fields match."""
    settings = dict(PRESET_DEFAULTS)
    settings['nav_path'] = '/test/nav'
    settings['tide_type'] = '\uc608\uce21'
    settings['rank_limit'] = 5

    path = save_preset("RoundTrip", settings, base_dir=str(tmp_path))
    loaded = load_preset(path)

    assert loaded is not None
    assert loaded['nav_path'] == '/test/nav'
    assert loaded['tide_type'] == '\uc608\uce21'
    assert loaded['rank_limit'] == 5


def test_load_missing_fields(tmp_path):
    """Load a preset with missing fields -- should fill defaults."""
    path = tmp_path / "presets" / "partial.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": "2.1.0",
        "name": "Partial",
        "settings": {
            "nav_path": "/some/path",
            "tide_type": "\uc608\uce21",
        },
    }
    path.write_text(json.dumps(data), encoding='utf-8')

    loaded = load_preset(str(path))
    assert loaded is not None
    assert loaded['nav_path'] == '/some/path'
    assert loaded['rank_limit'] == 10  # default
    assert loaded['timezone'] == 'GMT'  # default


def test_load_nonexistent():
    """Loading a non-existent file returns None."""
    result = load_preset("/nonexistent/path.json")
    assert result is None


def test_load_corrupt_json(tmp_path):
    """Loading corrupt JSON returns None."""
    path = tmp_path / "corrupt.json"
    path.write_text("{invalid json!!", encoding='utf-8')
    result = load_preset(str(path))
    assert result is None


def test_api_key_excluded(tmp_path):
    """API key should not be saved in presets."""
    settings = dict(PRESET_DEFAULTS)
    settings['api_key'] = 'secret_key_12345'

    path = save_preset("KeyTest", settings, base_dir=str(tmp_path))
    loaded = load_preset(path)

    assert 'api_key' not in loaded or loaded.get('api_key', '') == ''


def test_delete_preset(tmp_path):
    """Delete a saved preset."""
    settings = dict(PRESET_DEFAULTS)
    path = save_preset("DeleteMe", settings, base_dir=str(tmp_path))

    assert os.path.isfile(path)
    delete_preset(path)
    assert not os.path.isfile(path)


def test_list_presets_returns_saved(tmp_path):
    """list_presets should include freshly saved presets."""
    settings = dict(PRESET_DEFAULTS)
    save_preset("Alpha", settings, base_dir=str(tmp_path))
    save_preset("Beta", settings, base_dir=str(tmp_path))

    presets = list_presets(base_dir=str(tmp_path))
    names = [p['name'] for p in presets]
    assert "Alpha" in names
    assert "Beta" in names
