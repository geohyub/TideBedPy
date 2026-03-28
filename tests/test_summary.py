"""Tests for TideBedPy run summary generation."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from output.summary import build_run_summary


def _station(name: str, loaded: bool):
    series = SimpleNamespace(records=[1, 2, 3]) if loaded else None
    return SimpleNamespace(
        name=name,
        tide_obs=series,
        tide_pred=None,
    )


def _correction(name: str, weight: float, estim_height: float, h_ratio: float, time_corrector: float):
    return SimpleNamespace(
        station_name=name,
        weight=weight,
        estim_height=estim_height,
        h_ratio=h_ratio,
        time_corrector=time_corrector,
    )


def test_build_run_summary_includes_story_and_contributors():
    start = datetime(2026, 3, 1, 0, 0, 0)
    config = SimpleNamespace(
        nav_directory="E:/nav/input",
        tts_folder="E:/tide/obs",
        db_root="E:/db/root",
        ref_st_info_path="E:/stations/info.txt",
        output_path="E:/out/result.tid",
        tide_series_type="OBS",
        utc_offset=0.0,
        rank_limit=3,
        time_interval_sec=60,
        tolerance_cm=1.5,
        write_detail=True,
        model_dir="",
    )
    raw_nav_points = [
        SimpleNamespace(t=start),
        SimpleNamespace(t=start + timedelta(minutes=1)),
        SimpleNamespace(t=start + timedelta(minutes=2)),
    ]
    processed_nav_points = [
        SimpleNamespace(t=start, tc=12.5),
        SimpleNamespace(t=start + timedelta(minutes=1), tc=-999.0),
        SimpleNamespace(t=start + timedelta(minutes=2), tc=18.0),
    ]
    stations = [_station("Alpha", True), _station("Bravo", True), _station("Charlie", False)]
    all_corrections = [
        [_correction("Alpha", 0.7, 11.0, 1.05, 0.2), _correction("Bravo", 0.3, 9.0, 0.98, -0.1)],
        [],
        [_correction("Alpha", 0.6, 12.0, 1.02, 0.1), _correction("Bravo", 0.4, 10.0, 0.97, -0.2)],
    ]

    summary = build_run_summary(
        config,
        raw_nav_points,
        processed_nav_points,
        stations,
        all_corrections,
        elapsed=3.5,
        tide_model="KHOA",
        output_format="TID",
        db_version="1101",
        generated_files=["E:/out/result.tid"],
    )

    assert summary["counts"]["raw_nav_points"] == 3
    assert summary["counts"]["processed_nav_points"] == 3
    assert summary["counts"]["valid_points"] == 2
    assert summary["counts"]["tide_loaded_stations"] == 2
    assert summary["settings"]["rank_limit"] == 3
    assert summary["settings"]["tolerance_cm"] == 1.5
    assert summary["quality"]["elapsed_seconds"] == 3.5
    assert summary["contributors"][0]["station_name"] == "Alpha"
    assert summary["contributors"][0]["points_used"] == 2
    assert "보정 실행" in summary["headline"]
    assert summary["story"]["workflow"]
    assert "IDW" in summary["story"]["rationale"][1]
    assert summary["story"]["guidance"]
