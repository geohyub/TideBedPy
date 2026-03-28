"""Tests for output visualization briefing helpers."""

import json

from output.graph import _build_compare_contributor_rows, _build_compare_driver_lines
from output.map_view import _build_map_brief_lines, _load_summary_for_output


def test_build_compare_driver_lines_reports_context_differences():
    summary_a = {
        "settings": {
            "tide_model": "KHOA",
            "timezone_offset_hours": 9,
            "rank_limit": 3,
            "time_interval_sec": 60,
            "tolerance_cm": 1.0,
            "preset_summary": "Conservative harbor smoothing",
        },
        "inputs": {
            "nav_name": "nav_a.gps",
            "tide_name": "obs_a",
            "station_name": "station_a.txt",
        },
        "contributors": [
            {"station_name": "Alpha", "coverage_pct": 62.0},
            {"station_name": "Bravo", "coverage_pct": 18.0},
        ],
    }
    summary_b = {
        "settings": {
            "tide_model": "FES2014",
            "timezone_offset_hours": 0,
            "rank_limit": 5,
            "time_interval_sec": 120,
            "tolerance_cm": 2.0,
            "preset_summary": "Wide-area interpolation",
        },
        "inputs": {
            "nav_name": "nav_b.gps",
            "tide_name": "obs_b",
            "station_name": "station_b.txt",
        },
        "contributors": [
            {"station_name": "Charlie", "coverage_pct": 51.0},
            {"station_name": "Bravo", "coverage_pct": 21.0},
        ],
    }

    lines = _build_compare_driver_lines(summary_a, summary_b, 1.0, max_lines=8)

    assert lines[0] == "허용 오차: +/-1.00 cm"
    assert any("모델:" in line for line in lines)
    assert any("시간대:" in line for line in lines)
    assert any("항적:" in line for line in lines)
    assert any("프리셋 의미가" in line for line in lines)
    assert any("주요 기준항:" in line for line in lines)


def test_build_compare_contributor_rows_merges_two_scenarios():
    summary_a = {
        "contributors": [
            {"station_name": "Alpha", "coverage_pct": 48.0},
            {"station_name": "Bravo", "coverage_pct": 30.0},
        ]
    }
    summary_b = {
        "contributors": [
            {"station_name": "Charlie", "coverage_pct": 55.0},
            {"station_name": "Bravo", "coverage_pct": 25.0},
        ]
    }

    rows = _build_compare_contributor_rows(summary_a, summary_b, limit=4)

    assert rows[0] == ("Charlie", 0.0, 55.0)
    assert ("Alpha", 48.0, 0.0) in rows
    assert ("Bravo", 30.0, 25.0) in rows


def test_build_map_brief_lines_includes_guidance_and_contributors():
    summary = {
        "headline": "KHOA correction run produced 120 valid Tc values.",
        "story": {
            "workflow": ["Navigation, station, and tide inputs were aligned before interpolation."],
            "quality": ["95% of points remained within the configured tolerance."],
            "stations": ["Alpha and Bravo supplied most of the interpolation support."],
            "guidance": ["Focus on abrupt Tc color changes and contributor concentration."],
        },
        "contributors": [
            {"station_name": "Alpha", "coverage_pct": 62.4},
            {"station_name": "Bravo", "coverage_pct": 28.1},
        ],
    }

    lines = _build_map_brief_lines(summary, max_lines=5)

    assert lines[0].startswith("KHOA correction run")
    assert any("읽는 방법:" in line for line in lines)
    assert any("주요 기준항:" in line for line in lines)


def test_load_summary_for_output_resolves_map_suffix(tmp_path):
    tid_path = tmp_path / "result.tid"
    summary_path = tmp_path / "result.tid.summary.json"
    summary = {"headline": "Loaded from sidecar", "story": {}, "contributors": []}

    tid_path.write_text("", encoding="utf-8")
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    loaded = _load_summary_for_output(str(tmp_path / "result.tid.map.png"))

    assert loaded is not None
    assert loaded["headline"] == "Loaded from sidecar"
