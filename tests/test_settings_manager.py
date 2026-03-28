"""Tests for preset metadata handling."""

import json

from settings_manager import list_presets, load_preset, save_preset


def test_save_preset_adds_summary_and_omits_api_key(tmp_path):
    settings = {
        "nav_path": "E:/nav",
        "tide_path": "E:/tide",
        "output_path": "E:/out/result.tid",
        "db_path": "E:/db",
        "station_path": "E:/stations.txt",
        "tide_type": "OBS",
        "rank_limit": 5,
        "time_interval": 60,
        "timezone": "GMT (UTC+0)",
        "utc_offset": 0.0,
        "write_detail": True,
        "generate_graph": True,
        "use_api": True,
        "api_key": "super-secret",
        "tide_model": "KHOA",
    }

    filepath = save_preset("TestPreset", settings, base_dir=str(tmp_path))

    with open(filepath, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    assert payload["summary"]
    assert "KHOA" in payload["summary"]
    assert "api_key" not in payload["settings"]

    loaded = load_preset(filepath)
    assert "api_key" not in loaded
    assert loaded["rank_limit"] == 5

    presets = list_presets(str(tmp_path))
    assert presets[0]["summary"] == payload["summary"]

