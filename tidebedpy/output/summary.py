"""Shared run-summary builder for TideBedPy outputs and desktop views."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Iterable


INVALID_TC_THRESHOLD = -999.0


def _safe_name(path: str) -> str:
    if not path:
        return ""
    return os.path.basename(path.rstrip("/\\")) or path


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _fmt_num(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "없음"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:,.{digits}f}"


def _tc_is_valid(value: float | None) -> bool:
    return value is not None and value > INVALID_TC_THRESHOLD


def _series_loaded(station: Any) -> bool:
    for attr in ("tide_obs", "tide_pred"):
        series = getattr(station, attr, None)
        if series is not None and getattr(series, "records", None):
            return True
    return False


def _compute_contributor_stats(
    all_corrections: list[list[Any]],
    valid_point_count: int,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    contributor_map: dict[str, dict[str, float]] = {}
    active_counts: list[int] = []

    for correction_list in all_corrections or []:
        valid_corrs = [
            corr
            for corr in correction_list
            if getattr(corr, "weight", 0.0) > 0
            and getattr(corr, "estim_height", INVALID_TC_THRESHOLD) > INVALID_TC_THRESHOLD
        ]
        active_counts.append(len(valid_corrs))

        weight_total = sum(max(float(getattr(corr, "weight", 0.0)), 0.0) for corr in valid_corrs)
        for corr in valid_corrs:
            name = getattr(corr, "station_name", "") or "미상"
            norm_weight = (
                float(getattr(corr, "weight", 0.0)) / weight_total
                if weight_total > 0
                else 0.0
            )
            item = contributor_map.setdefault(
                name,
                {
                    "station_name": name,
                    "points_used": 0.0,
                    "weight_sum": 0.0,
                    "h_ratio_sum": 0.0,
                    "time_corrector_sum": 0.0,
                },
            )
            item["points_used"] += 1
            item["weight_sum"] += norm_weight
            item["h_ratio_sum"] += float(getattr(corr, "h_ratio", 0.0))
            item["time_corrector_sum"] += float(getattr(corr, "time_corrector", 0.0))

    contributors: list[dict[str, Any]] = []
    for item in contributor_map.values():
        points_used = int(item["points_used"])
        contributors.append(
            {
                "station_name": item["station_name"],
                "points_used": points_used,
                "coverage_pct": round((points_used / valid_point_count) * 100.0, 2)
                if valid_point_count
                else 0.0,
                "avg_weight": round(item["weight_sum"] / points_used, 4) if points_used else 0.0,
                "avg_h_ratio": round(item["h_ratio_sum"] / points_used, 4) if points_used else 0.0,
                "avg_time_corrector_hours": round(
                    item["time_corrector_sum"] / points_used, 4
                )
                if points_used
                else 0.0,
            }
        )

    contributors.sort(
        key=lambda item: (item["points_used"], item["avg_weight"]),
        reverse=True,
    )

    active_metrics = {
        "avg_active_stations": round(
            sum(active_counts) / len(active_counts), 2
        )
        if active_counts
        else 0.0,
        "max_active_stations": max(active_counts) if active_counts else 0,
    }
    return contributors, active_metrics


def _build_workflow_story(
    config: Any,
    raw_nav_points: list[Any],
    processed_nav_points: list[Any],
    total_stations: int,
    tide_loaded_count: int,
    tide_model: str,
    db_version: str | None,
) -> list[str]:
    raw_count = len(raw_nav_points)
    processed_count = len(processed_nav_points)
    skipped_count = max(raw_count - processed_count, 0)
    time_interval = int(getattr(config, "time_interval_sec", 0) or 0)

    lines = [
        (
            f"항적 입력 '{_safe_name(getattr(config, 'nav_directory', ''))}'에서 "
            f"{raw_count:,}개 원시 포인트를 불러왔고, "
            f"시간 범위는 {_fmt_dt(raw_nav_points[0].t if raw_nav_points else None)} "
            f"부터 {_fmt_dt(raw_nav_points[-1].t if raw_nav_points else None)} 까지입니다."
        ),
    ]

    if tide_model == "KHOA":
        lines.append(
            (
                f"조위 입력 '{_safe_name(getattr(config, 'tts_folder', ''))}'은 "
                f"총 {total_stations:,}개 기준항 중 {tide_loaded_count:,}개 시계열과 연결되었고, "
                f"Co-tidal DB 버전 {db_version or '미상'}의 SprRange/MSL/MHWI가 각 포인트 보정에 사용되었습니다."
            )
        )
    else:
        lines.append(
            (
                f"전역 조석 모델 '{tide_model}'을 "
                f"'{_safe_name(getattr(config, 'model_dir', ''))}'에서 직접 사용했기 때문에, "
                "최종 Tc 생성에는 local 기준항 시계열과 Co-tidal DB가 사용되지 않았습니다."
            )
        )

    lines.append(
        (
            f"출력 '{_safe_name(getattr(config, 'output_path', ''))}'에는 {processed_count:,}개 처리 포인트가 기록되었고"
            + (
                f", {time_interval:,}초 간격 필터 적용으로 {skipped_count:,}개 포인트가 제외되었습니다."
                if time_interval > 0
                else "."
            )
        )
    )
    return lines


def _build_rationale_story(config: Any, tide_model: str) -> list[str]:
    if tide_model != "KHOA":
        return [
            (
                f"보정 원리: 각 항적 포인트는 해당 시각과 좌표에서 {tide_model} 전역 조석 예측값을 직접 계산해 "
                "Tc로 기록했습니다."
            ),
            "이 모드에서는 local 기준항 순위 선정, H-ratio 보정, Co-tidal 시차 보정이 적용되지 않습니다.",
        ]

    rank_limit = int(getattr(config, "rank_limit", 0) or 0)
    return [
        (
            "보정 원리: 각 항적 포인트에서 Co-tidal SprRange, MSL, MHWI를 먼저 보간한 뒤, "
            "주변 기준항 조위를 H-ratio와 시차 보정으로 환산했습니다."
        ),
        (
            f"최종 Tc는 최대 {rank_limit:,}개 유효 기준항 추정치를 대상으로, "
            "무효 또는 누락된 기준항을 제외한 뒤 IDW 가중 평균으로 계산했습니다."
        ),
    ]


def _build_quality_story(
    processed_nav_points: list[Any],
    valid_tc_values: list[float],
    active_metrics: dict[str, float],
    validation: dict[str, Any] | None,
) -> list[str]:
    processed_count = len(processed_nav_points)
    valid_count = len(valid_tc_values)
    invalid_count = max(processed_count - valid_count, 0)
    valid_pct = (valid_count / processed_count * 100.0) if processed_count else 0.0

    lines = [
        (
            f"품질 요약: 처리 포인트 {processed_count:,}개 중 {valid_count:,}개가 유효 Tc를 생성했고 "
            f"({valid_pct:.1f}%), {invalid_count:,}개는 무효 또는 누락 상태였습니다."
        )
    ]

    if valid_tc_values:
        mean_tc = sum(valid_tc_values) / len(valid_tc_values)
        variance = sum((value - mean_tc) ** 2 for value in valid_tc_values) / len(valid_tc_values)
        std_tc = variance ** 0.5
        lines.append(
            (
                f"Tc 범위는 {_fmt_num(min(valid_tc_values), 2)} ~ {_fmt_num(max(valid_tc_values), 2)} cm이고, "
                f"평균은 {_fmt_num(mean_tc, 2)} cm, 표준편차는 {_fmt_num(std_tc, 2)} cm였습니다."
            )
        )

    if active_metrics["max_active_stations"] > 0:
        lines.append(
            (
                f"포인트당 활성 기준항 수는 평균 {_fmt_num(active_metrics['avg_active_stations'], 2)}개였고, "
                f"최대 {int(active_metrics['max_active_stations'])}개까지 사용되었습니다."
            )
        )

    if validation:
        within = int(validation.get("within_tolerance", 0))
        exceeded = int(validation.get("exceeded_tolerance", 0))
        tolerance = validation.get("tolerance_m", 0.01)
        lines.append(
            (
                f"참조 TID 검증 결과, +/-{tolerance:.3f} m 허용 범위 안에 {within:,}개가 있었고 "
                f"{exceeded:,}개는 허용 범위를 벗어났습니다."
            )
        )

    return lines


def _build_station_story(contributors: list[dict[str, Any]]) -> list[str]:
    if not contributors:
        return ["이번 실행에서는 기준항 기여 요약을 계산할 수 없었습니다."]

    top_items = contributors[:3]
    fragments = []
    for item in top_items:
        fragments.append(
            (
                f"{item['station_name']} ({item['coverage_pct']:.1f}% coverage, "
                f"avg weight {item['avg_weight']:.3f})"
            )
        )

    return [
        "주요 기여 기준항: " + ", ".join(fragments) + ".",
    ]


def _build_guidance_story(
    tide_model: str,
    contributors: list[dict[str, Any]],
    validation: dict[str, Any] | None,
) -> list[str]:
    """Explain how users should read the main charts and outputs."""
    lines = [
        "먼저 조석 보정 차트에서 결측, 급격한 점프, 비정상적으로 평평한 구간이 있는지 확인한 뒤 고점/저점을 해석하세요."
    ]

    if tide_model == "KHOA":
        if contributors:
            lead = contributors[0]
            lines.append(
                f"다음으로 가중치 차트를 보세요. 대부분 시점에서 {lead['station_name']} 비중이 높다면 최종 Tc는 해당 기준항 영향이 크다는 뜻입니다."
            )
        else:
            lines.append(
                "다음으로 가중치 차트를 보세요. 한 기준항이 전체 구간을 지배하는 경우보다 여러 기준항이 균형 있게 섞이는 경우가 더 자연스러운 경우가 많습니다."
            )
        lines.append(
            "지도에서는 사용 기준항이 항적을 한쪽으로 치우치지 않고 감싸는지 확인하세요. 편향된 배치는 불안정한 보정 구간의 원인이 될 수 있습니다."
        )
    else:
        lines.append(
            f"이번 실행은 {tide_model} 전역 모델 기반이므로, local 기준항 조합보다 시간/공간 커버리지를 중심으로 해석하는 편이 적절합니다."
        )

    if validation:
        lines.append(
            "참조 TID가 있다면 마지막으로 비교 그래프를 보고, residual 패턴이 선택한 허용 범위 안에 머무르는지 확인하세요."
        )

    return lines


def build_run_summary(
    config: Any,
    raw_nav_points: list[Any],
    processed_nav_points: list[Any],
    stations: list[Any],
    all_corrections: list[list[Any]],
    *,
    elapsed: float = 0.0,
    tide_model: str = "KHOA",
    output_format: str = "TID",
    db_version: str | None = None,
    validation: dict[str, Any] | None = None,
    preset_name: str = "",
    preset_summary: str = "",
    generated_files: list[str] | None = None,
) -> dict[str, Any]:
    """Build a structured run summary from one TideBedPy correction run."""

    valid_tc_values = [
        float(point.tc) for point in processed_nav_points if _tc_is_valid(getattr(point, "tc", None))
    ]
    total_stations = len(stations or [])
    tide_loaded_count = sum(1 for station in stations or [] if _series_loaded(station))
    contributors, active_metrics = _compute_contributor_stats(all_corrections, len(valid_tc_values))

    summary = {
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "headline": (
            f"{tide_model} 보정 실행에서 처리 포인트 {len(processed_nav_points):,}개 중 "
            f"유효 Tc {len(valid_tc_values):,}개를 생성했습니다."
        ),
        "settings": {
            "tide_model": tide_model,
            "tide_type": getattr(config, "tide_series_type", ""),
            "timezone_offset_hours": getattr(config, "utc_offset", 0.0),
            "rank_limit": int(getattr(config, "rank_limit", 0) or 0),
            "time_interval_sec": int(getattr(config, "time_interval_sec", 0) or 0),
            "tolerance_cm": round(float(getattr(config, "tolerance_cm", 0.0)), 2)
            if getattr(config, "tolerance_cm", None) is not None
            else None,
            "write_detail": bool(getattr(config, "write_detail", False)),
            "output_format": output_format,
            "preset_name": preset_name or "",
            "preset_summary": preset_summary or "",
        },
        "inputs": {
            "nav_path": getattr(config, "nav_directory", ""),
            "nav_name": _safe_name(getattr(config, "nav_directory", "")),
            "tide_path": getattr(config, "tts_folder", ""),
            "tide_name": _safe_name(getattr(config, "tts_folder", "")),
            "db_path": getattr(config, "db_root", ""),
            "db_name": _safe_name(getattr(config, "db_root", "")),
            "station_path": getattr(config, "ref_st_info_path", ""),
            "station_name": _safe_name(getattr(config, "ref_st_info_path", "")),
            "output_path": getattr(config, "output_path", ""),
            "output_name": _safe_name(getattr(config, "output_path", "")),
        },
        "counts": {
            "raw_nav_points": len(raw_nav_points or []),
            "processed_nav_points": len(processed_nav_points or []),
            "valid_points": len(valid_tc_values),
            "invalid_points": max(len(processed_nav_points or []) - len(valid_tc_values), 0),
            "total_stations": total_stations,
            "tide_loaded_stations": tide_loaded_count,
        },
        "time_range": {
            "raw_start": _fmt_dt(raw_nav_points[0].t if raw_nav_points else None),
            "raw_end": _fmt_dt(raw_nav_points[-1].t if raw_nav_points else None),
            "processed_start": _fmt_dt(processed_nav_points[0].t if processed_nav_points else None),
            "processed_end": _fmt_dt(processed_nav_points[-1].t if processed_nav_points else None),
        },
        "quality": {
            "elapsed_seconds": round(float(elapsed), 2),
            "min_tc_cm": round(min(valid_tc_values), 2) if valid_tc_values else None,
            "max_tc_cm": round(max(valid_tc_values), 2) if valid_tc_values else None,
            "mean_tc_cm": round(sum(valid_tc_values) / len(valid_tc_values), 2)
            if valid_tc_values
            else None,
            "avg_active_stations": active_metrics["avg_active_stations"],
            "max_active_stations": active_metrics["max_active_stations"],
        },
        "contributors": contributors,
        "generated_files": list(generated_files or []),
        "story": {
            "workflow": _build_workflow_story(
                config,
                raw_nav_points,
                processed_nav_points,
                total_stations,
                tide_loaded_count,
                tide_model,
                db_version,
            ),
            "rationale": _build_rationale_story(config, tide_model),
            "quality": _build_quality_story(
                processed_nav_points,
                valid_tc_values,
                active_metrics,
                validation,
            ),
            "stations": _build_station_story(contributors),
            "guidance": _build_guidance_story(tide_model, contributors, validation),
        },
        "validation": validation or None,
    }

    return summary


def _summary_text_lines(summary: dict[str, Any]) -> list[str]:
    inputs = summary.get("inputs", {})
    counts = summary.get("counts", {})
    settings = summary.get("settings", {})
    quality = summary.get("quality", {})
    story = summary.get("story", {})

    lines = [
        "TideBedPy 보정 요약",
        "=" * 20,
        "",
        summary.get("headline", ""),
        "",
        "실행 정보",
        "-" * 8,
        f"출력: {inputs.get('output_path', '')}",
        f"모델: {settings.get('tide_model', '')}",
        f"시간대 오프셋: {settings.get('timezone_offset_hours', 0.0):+.1f} h",
        f"선정 기준항 수: {settings.get('rank_limit', 0)}",
        f"간격: {settings.get('time_interval_sec', 0)} sec",
        f"허용 오차: {settings.get('tolerance_cm', '없음')} cm",
        f"프리셋: {settings.get('preset_name', '') or '없음'}",
        "",
        "입력 데이터",
        "-" * 10,
        f"항적: {inputs.get('nav_path', '')}",
        f"조위: {inputs.get('tide_path', '')}",
        f"Co-tidal DB: {inputs.get('db_path', '')}",
        f"기준항 파일: {inputs.get('station_path', '')}",
        "",
        "집계",
        "-" * 4,
        f"원시 항적 포인트: {counts.get('raw_nav_points', 0):,}",
        f"처리 항적 포인트: {counts.get('processed_nav_points', 0):,}",
        f"유효 Tc 개수: {counts.get('valid_points', 0):,}",
        f"무효 Tc 개수: {counts.get('invalid_points', 0):,}",
        f"전체 기준항 수: {counts.get('total_stations', 0):,}",
        f"조위 시계열 연결 기준항 수: {counts.get('tide_loaded_stations', 0):,}",
        "",
        "보정 스토리",
        "-" * 10,
    ]

    for section_name in ("workflow", "rationale", "quality", "stations"):
        for line in story.get(section_name, []):
            lines.append(f"- {line}")

    guidance = story.get("guidance", [])
    if guidance:
        lines.extend(["", "읽는 방법", "-" * 8])
        for line in guidance:
            lines.append(f"- {line}")

    contributors = summary.get("contributors", [])[:5]
    if contributors:
        lines.extend(["", "주요 기준항", "-" * 10])
        for item in contributors:
            lines.append(
                "- "
                f"{item['station_name']}: "
                f"커버리지 {item['coverage_pct']:.1f}%, "
                f"평균 가중치 {item['avg_weight']:.3f}, "
                f"평균 H-ratio {item['avg_h_ratio']:.3f}, "
                f"평균 시차 보정 {item['avg_time_corrector_hours']:.3f} h"
            )

    lines.extend(
        [
            "",
            "품질 스냅샷",
            "-" * 11,
            f"소요 시간: {quality.get('elapsed_seconds', 0.0):,.2f} s",
            f"Tc 최소/최대: {_fmt_num(quality.get('min_tc_cm'))} / {_fmt_num(quality.get('max_tc_cm'))} cm",
            f"Tc 평균: {_fmt_num(quality.get('mean_tc_cm'))} cm",
            f"평균 활성 기준항 수: {_fmt_num(quality.get('avg_active_stations'))}",
            f"최대 활성 기준항 수: {quality.get('max_active_stations', 0)}",
        ]
    )

    generated_files = summary.get("generated_files", [])
    if generated_files:
        lines.extend(["", "생성 파일", "-" * 9])
        for path in generated_files:
            lines.append(f"- {path}")

    return lines


def write_summary_files(output_path: str, summary: dict[str, Any]) -> dict[str, str]:
    """Write JSON and TXT summary files next to a TID output."""

    json_path = output_path + ".summary.json"
    text_path = output_path + ".summary.txt"

    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)

    with open(text_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(_summary_text_lines(summary)).rstrip() + "\n")

    return {"json": json_path, "text": text_path}


def load_summary_file(tid_path: str) -> dict[str, Any] | None:
    """Load a sidecar summary JSON for a TID file if one exists."""

    summary_path = tid_path + ".summary.json"
    if not os.path.isfile(summary_path):
        return None

    with open(summary_path, "r", encoding="utf-8") as handle:
        return json.load(handle)
