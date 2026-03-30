"""CorrectionWorker — QThread-based tidal correction pipeline."""

import os
import sys
import time
import threading
import traceback

from PySide6.QtCore import QObject, Signal, Slot

# Ensure tidebedpy package internals can resolve `from core.xxx` imports
_tidebedpy_dir = os.path.join(os.path.dirname(__file__), "..", "..")
if _tidebedpy_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_tidebedpy_dir))


class CorrectionWorker(QObject):
    """
    7-step tidal correction pipeline running in a background QThread.

    Signals:
        progress(current, total) — nav point processing progress
        log(message, tag) — log messages with colored tags
        status(text) — short status label updates
        finished(success, message) — completion signal
        station_select_needed(nearby, nav_points) — request main thread to show dialog
    """

    progress = Signal(int, int)
    log = Signal(str, str)
    status = Signal(str)
    finished = Signal(bool, str)
    result_data = Signal(dict)  # processed navpoints, corrections, stations for visualization
    station_select_needed = Signal(list, list)  # nearby_stations, nav_points

    def __init__(self, config_dict: dict, parent=None):
        super().__init__(parent)
        self._config_dict = config_dict
        self._stop_requested = False
        # C1: Threading event for station selection pause/resume
        self._station_event = threading.Event()
        self._selected_stations = None

    def set_selected_stations(self, stations: list):
        """Called from main thread after StationSelectDialog completes."""
        self._selected_stations = stations
        self._station_event.set()

    def request_stop(self):
        self._stop_requested = True

    @Slot()
    def run(self):
        cotidal = None
        try:
            from datetime import datetime
            from tidebedpy.config import TideBedConfig, _find_project_root

            d = self._config_dict
            start_time = time.time()

            self.log.emit("\u2501" * 56, "dim")
            self.log.emit("  TideBedPy  조석보정  v3.0", "header")
            self.log.emit("\u2501" * 56, "dim")
            self.log.emit(f"  처리 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "detail")
            self.log.emit("", "dim")

            # ── Build config ──
            config = TideBedConfig()
            config.nav_directory = d.get("nav_path", "")
            config.tts_folder = d.get("tide_path", "")
            config.db_root = d.get("db_path", "")
            config.ref_st_info_path = d.get("station_path", "")
            config.output_path = d.get("output_path", "")
            config.tide_series_type = d.get("tide_type", "실측")
            config.rank_limit = min(d.get("rank_limit", 10), 10)
            config.time_interval_sec = d.get("time_interval", 0)
            config.write_detail = d.get("write_detail", True)
            config.model_dir = d.get("model_dir", "")
            config.tolerance_cm = d.get("tolerance_cm", 1.0)

            utc_offset = d.get("utc_offset", 0.0)
            config.utc_offset = utc_offset
            config.is_kst = (utc_offset == 9.0)

            if d.get("do_validate") and d.get("validate_path"):
                config.validate_path = d["validate_path"]

            self.log.emit(
                f"  시간대: UTC{utc_offset:+.1f}h", "detail"
            )

            # Imports
            from tidebedpy.data_io.station import load_stations
            from tidebedpy.data_io.tide_series import load_tide_folder, adjust_tide_year
            from tidebedpy.data_io.navigation import load_nav_directory
            from tidebedpy.data_io.cotidal import CoTidalGrid
            from tidebedpy.core.tide_correction import TideCorrectionEngine
            from tidebedpy.output.tid_writer import write_tid, write_detail, write_error
            from tidebedpy.output.report import validate_output
            from tidebedpy.output.summary import build_run_summary, write_summary_files

            matched = 0
            validation_result = None
            chosen = None  # API 선택 관측소 (스코프 공유)

            # ── [1/7] Station info ──
            self.status.emit("기준항 정보 로드 중...")
            self.log.emit("[1/7]  기준항 정보 로드", "step")
            stations = load_stations(config.ref_st_info_path)
            if not stations:
                self.log.emit("기준항 정보를 불러올 수 없습니다!", "error")
                self.finished.emit(False, "기준항 정보 로드 실패")
                return
            self.log.emit(f"  \u2192 {len(stations)}개 기준항 로드 완료", "info")

            if self._stop_requested:
                self.finished.emit(False, "사용자에 의해 중지됨")
                return

            # ── [2/7] Nav data ──
            self.status.emit("항적 데이터 로드 중...")
            self.log.emit("[2/7]  항적 파일 로드", "step")
            nav_points = load_nav_directory(config.nav_directory)
            if not nav_points:
                self.log.emit("항적 데이터를 불러올 수 없습니다!", "error")
                self.finished.emit(False, "항적 데이터 로드 실패")
                return
            self.log.emit(f"  \u2192 {len(nav_points):,}개 항적 포인트 로드", "info")
            self.log.emit(
                f"  \u2192 시간 범위: {nav_points[0].t} ~ {nav_points[-1].t}", "detail"
            )

            if self._stop_requested:
                self.finished.emit(False, "사용자에 의해 중지됨")
                return

            # ── [2.5/7] API auto-fetch (optional) ──
            api_key = d.get("api_key", "").strip()
            use_api = d.get("use_api", False)
            if use_api and api_key:
                self.status.emit("API 조위 수집 중...")
                self.log.emit("[2.5/7]  API 자동 조위 수집", "step")
                try:
                    from tidebedpy.data_io.khoa_api import (
                        select_nearby_stations, auto_fetch_for_nav,
                    )
                    api_out_dir = os.path.dirname(config.output_path) or "."
                    lats = [p.y for p in nav_points]
                    lons = [p.x for p in nav_points]
                    clat = sum(lats) / len(lats)
                    clon = sum(lons) / len(lons)
                    nearby = select_nearby_stations(
                        clat, clon, stations, max_count=20, max_distance_km=300
                    )
                    self.log.emit(f"  \u2192 {len(nearby)}개 후보 관측소 탐색됨", "detail")

                    # Use pre-selected stations if provided, or ask user
                    chosen = d.get("selected_stations")
                    if not chosen:
                        # C1: Emit signal to main thread for station selection
                        self._station_event.clear()
                        self._selected_stations = None
                        self.log.emit("  관측소 선택 대기 중...", "detail")
                        self.station_select_needed.emit(
                            nearby, list(nav_points)
                        )
                        # Pause worker and wait for main thread response
                        self._station_event.wait(timeout=600)
                        chosen = self._selected_stations
                        if not chosen:
                            self.log.emit("  관측소 선택 취소됨 — API 수집 생략", "warning")
                    if chosen:
                        self.log.emit(f"  \u2192 {len(chosen)}개 관측소 선택됨", "info")

                        def _api_progress(msg):
                            self.log.emit(f"  \u2192 {msg}", "detail")
                            self.status.emit(msg)

                        api_results = auto_fetch_for_nav(
                            api_key, nav_points, api_out_dir,
                            stations=stations, minute=10,
                            progress_callback=_api_progress,
                            selected_stations=chosen,
                        )
                        ok_count = sum(1 for r in api_results if not r.error)
                        self.log.emit(f"  \u2192 {ok_count}개 관측소 수집 완료", "info")

                        if ok_count > 0:
                            if config.tide_series_type == "예측":
                                config.tts_folder = os.path.join(
                                    api_out_dir, "api_예측조위"
                                )
                            else:
                                config.tts_folder = os.path.join(
                                    api_out_dir, "api_실측조위"
                                )
                except Exception as e:
                    self.log.emit(f"  API 수집 실패: {e}", "warning")
                    self.log.emit("  기존 조위 폴더로 진행합니다", "detail")

            # ── C2: Global tidal model branch ──
            tide_model = d.get('tide_model', 'KHOA')
            use_global_model = tide_model in ('FES2014', 'TPXO9')

            if use_global_model:
                # Skip steps 3,4 — direct prediction from pyTMD
                self.status.emit("글로벌 조석 모델 예측 중...")
                self.log.emit(f"[3-4/7]  글로벌 모델 ({tide_model}) 직접 예측", "step")
                try:
                    from tidebedpy.data_io.global_tide import predict_tide_pytmd
                    lons = [p.x for p in nav_points]
                    lats = [p.y for p in nav_points]
                    times = [p.t for p in nav_points]
                    model_dir = d.get('model_dir', None)
                    tide_heights = predict_tide_pytmd(
                        lons, lats, times,
                        model=tide_model,
                        model_dir=model_dir,
                    )
                    # Assign predicted heights directly as Tc (cm)
                    for nav, tc_cm in zip(nav_points, tide_heights):
                        nav.tc = tc_cm
                    processed = list(nav_points)
                    all_corrections = [[] for _ in processed]
                    error_count = sum(1 for nav in processed if nav.tc <= -999.0)
                    valid_count = len(processed) - error_count
                    self.log.emit(
                        f"  \u2192 정상: {valid_count:,}개  /  오류: {error_count:,}개  "
                        f"(총 {len(processed):,}개)",
                        "info",
                    )
                except ImportError as e:
                    self.log.emit(f"  pyTMD 미설치: {e}", "error")
                    self.finished.emit(False, f"pyTMD 미설치: {e}")
                    return
                except Exception as e:
                    self.log.emit(f"  글로벌 모델 오류: {e}", "error")
                    self.finished.emit(False, f"글로벌 모델 오류: {e}")
                    return
            else:
                # ── [3/7] Tide series ──
                self.status.emit("조위 시계열 로드 중...")
                self.log.emit("[3/7]  조위 시계열 로드 + Akima 보간", "step")
                if config.tide_series_type == "예측":
                    folder = config.tts_p_folder if config.tts_p_folder else config.tts_folder
                    matched = load_tide_folder(folder, stations, "PRED")
                    self.log.emit("  \u2192 유형: 예측 시계열", "detail")
                else:
                    matched = load_tide_folder(config.tts_folder, stations, "OBS")
                    self.log.emit("  \u2192 유형: 실측 시계열", "detail")
                self.log.emit(f"  \u2192 {matched}개 기준항 매칭 완료", "info")

                if matched > 0 and config.rank_limit > matched:
                    old_rl = config.rank_limit
                    config.rank_limit = matched
                    self.log.emit(
                        f"  \u2192 기준항 적용 개수 자동 조정: {old_rl} \u2192 {matched}",
                        "info",
                    )

                if matched == 0:
                    self.log.emit(
                        "매칭된 기준항이 없습니다! 조위 폴더를 확인하세요.", "warning"
                    )

                if self._stop_requested:
                    self.finished.emit(False, "사용자에 의해 중지됨")
                    return

                # ── [4/7] Co-tidal grid ──
                self.status.emit("개정수 DB 로드 중...")
                self.log.emit("[4/7]  개정수 DB (Co-tidal 격자) 로드", "step")
                cotidal = CoTidalGrid(config.db_root)
                if not cotidal.load_catalog():
                    self.log.emit("File_Catalog.txt 로드 실패!", "error")
                    self.finished.emit(False, "Co-tidal DB 로드 실패")
                    return
                opened = cotidal.open_netcdfs()
                self.log.emit(f"  \u2192 {opened}개 NetCDF 파일 로드", "info")

                if self._stop_requested:
                    cotidal.close_netcdfs()
                    self.finished.emit(False, "사용자에 의해 중지됨")
                    return

                # Tide year adjustment
                nav_year = nav_points[0].t.year
                adj_count = adjust_tide_year(stations, nav_year)
                if adj_count > 0:
                    self.log.emit(
                        f"  \u2192 조위 연도 \u2192 {nav_year}년 자동 조정 ({adj_count}개)",
                        "warning",
                    )

                # ── [5/7] Correction processing ──
                self.status.emit("조석보정 처리 중...")
                self.log.emit(
                    f"[5/7]  조석보정 처리 (기준항 {config.rank_limit}개, "
                    f"UTC{utc_offset:+.0f})",
                    "step",
                )
                # API 모드: 사용자가 선택한 관측소만 보정에 사용
                # 비-API 모드: 조위 폴더에 있는 관측소 전부 사용 (selected_names=None)
                selected_names = None
                if use_api and api_key:
                    chosen_for_engine = chosen
                    if not chosen_for_engine:
                        chosen_for_engine = d.get("selected_stations")
                    if not chosen_for_engine:
                        chosen_for_engine = getattr(self, '_selected_stations', None)
                    if chosen_for_engine:
                        selected_names = []
                        for s in chosen_for_engine:
                            if isinstance(s, (tuple, list)) and len(s) >= 2:
                                selected_names.append(str(s[1]))  # (code, name, dist)
                            elif isinstance(s, dict):
                                selected_names.append(str(s.get("name", s.get("station_name", ""))))
                            else:
                                selected_names.append(str(s))
                        self.log.emit(
                            f"  → 보정 대상 관측소: {', '.join(selected_names)}",
                            "info",
                        )
                engine = TideCorrectionEngine(
                    config, stations, cotidal,
                    selected_names=selected_names,
                )

                def gui_progress(current, total):
                    if self._stop_requested:
                        raise InterruptedError("중지 요청")
                    self.progress.emit(current, total)

                try:
                    processed, all_corrections = engine.process_all(
                        nav_points, progress_callback=gui_progress
                    )
                except InterruptedError:
                    cotidal.close_netcdfs()
                    self.finished.emit(False, "사용자에 의해 중지됨")
                    return

            if not use_global_model:
                error_count = sum(1 for nav in processed if nav.tc <= -999.0)
                valid_count = len(processed) - error_count
                self.log.emit(
                    f"  \u2192 정상: {valid_count:,}개  /  오류: {error_count:,}개  "
                    f"(총 {len(processed):,}개)",
                    "info",
                )

            # ── [6/7] Output ──
            self.status.emit("출력 파일 생성 중...")
            self.log.emit("[6/7]  출력 파일 생성", "step")

            db_ver = "1101"
            if cotidal and hasattr(cotidal, 'version') and cotidal.version:
                db_ver = cotidal.version

            write_tid(
                config.output_path, processed, config,
                db_version=db_ver,
            )
            self.log.emit(
                f"  \u2192 {os.path.basename(config.output_path)}", "info"
            )

            if config.write_detail:
                write_detail(config.output_path, processed, all_corrections)
                self.log.emit(
                    f"  \u2192 {os.path.basename(config.output_path)}.detail", "info"
                )

            # C3: Additional output format
            output_format = d.get('output_format', 'TID')
            if output_format and output_format != 'TID':
                try:
                    from tidebedpy.output.format_writers import (
                        write_csv, write_kingdom_tide, write_sonarwiz_tide,
                    )
                    base_path = config.output_path
                    if 'CSV' in output_format:
                        csv_path = base_path.rsplit('.', 1)[0] + '.csv'
                        write_csv(csv_path, processed, config)
                        self.log.emit(
                            f"  \u2192 {os.path.basename(csv_path)}", "info"
                        )
                    if 'Kingdom' in output_format:
                        k_path = base_path.rsplit('.', 1)[0] + '.kingdom.txt'
                        write_kingdom_tide(k_path, processed, config)
                        self.log.emit(
                            f"  \u2192 {os.path.basename(k_path)}", "info"
                        )
                    if 'SonarWiz' in output_format:
                        sw_path = base_path.rsplit('.', 1)[0] + '.sonarwiz.txt'
                        write_sonarwiz_tide(sw_path, processed, config)
                        self.log.emit(
                            f"  \u2192 {os.path.basename(sw_path)}", "info"
                        )
                except Exception as e:
                    self.log.emit(f"  추가 포맷 출력 실패: {e}", "warning")

            error_points = []
            for nav in processed:
                if nav.tc <= -999.0:
                    error_points.append({
                        "lon": nav.x,
                        "lat": nav.y,
                        "time": nav.t.strftime("%Y/%m/%d %H:%M:%S"),
                    })
            write_error(config.output_path, error_points)
            self.log.emit(
                f"  \u2192 {os.path.basename(config.output_path)}.err", "info"
            )

            # ── Graphs & maps ──
            generate_graph = d.get("generate_graph", True)
            tolerance_cm = d.get("tolerance_cm", 1.0)
            tolerance_m = tolerance_cm / 100.0

            if generate_graph:
                try:
                    from tidebedpy.output.graph import (
                        generate_tide_graph, generate_comparison_graph,
                    )
                    ref_path = (
                        config.validate_path
                        if config.validate_path
                        and os.path.isfile(config.validate_path)
                        else None
                    )
                    img_path = generate_tide_graph(
                        config.output_path,
                        reference_path=ref_path,
                        tolerance_cm=tolerance_cm,
                    )
                    if img_path:
                        self.log.emit(
                            f"  \u2192 조석 그래프: {os.path.basename(img_path)}",
                            "info",
                        )
                    if ref_path:
                        cmp_path = generate_comparison_graph(
                            config.output_path, ref_path,
                            tolerance_cm=tolerance_cm,
                        )
                        if cmp_path:
                            self.log.emit(
                                f"  \u2192 비교 그래프: {os.path.basename(cmp_path)}",
                                "info",
                            )
                except ImportError:
                    self.log.emit("  matplotlib 미설치 -- 그래프 생략", "warning")
                except Exception as e:
                    self.log.emit(f"  그래프 생성 실패: {e}", "warning")

                try:
                    from tidebedpy.output.map_view import (
                        generate_station_map, generate_correction_map,
                    )
                    map_path = config.output_path + ".map.png"
                    map_img = generate_station_map(
                        stations, nav_points=processed,
                        output_image=map_path,
                        all_corrections=all_corrections,
                    )
                    if map_img:
                        self.log.emit(
                            f"  \u2192 위치 지도: {os.path.basename(map_img)}",
                            "info",
                        )
                    corr_map_path = config.output_path + ".corrmap.png"
                    corr_img = generate_correction_map(
                        stations, processed,
                        output_image=corr_map_path,
                        all_corrections=all_corrections,
                    )
                    if corr_img:
                        self.log.emit(
                            f"  \u2192 보정 결과 지도: {os.path.basename(corr_img)}",
                            "info",
                        )
                except ImportError:
                    pass
                except Exception as e:
                    self.log.emit(f"  지도 생성 실패: {e}", "warning")

            # Close NetCDF (only if opened)
            if cotidal:
                cotidal.close_netcdfs()
                cotidal = None

            # ── [7/7] Validation ──
            if config.validate_path and os.path.isfile(config.validate_path):
                self.log.emit("[7/7]  검증 (참조 TID 비교)", "step")
                result = validate_output(
                    config.output_path,
                    config.validate_path,
                    tolerance=tolerance_m,
                )
                validation_result = dict(result)
                validation_result["tolerance_m"] = tolerance_m
                self.log.emit(
                    f"  \u2192 생성: {result['total_generated']}개  "
                    f"/  참조: {result['total_reference']}개  "
                    f"/  매칭: {result['matched']}개",
                    "detail",
                )
                self.log.emit(
                    f"  \u2192 허용범위 이내: {result['within_tolerance']}개",
                    "detail",
                )
                self.log.emit(
                    f"  \u2192 허용범위 초과: {result['exceeded_tolerance']}개",
                    "detail",
                )
                self.log.emit(
                    f"  \u2192 최대 편차: {result['max_diff']:.4f} m", "detail"
                )

                if result["exceeded_tolerance"] == 0 and result["matched"] > 0:
                    self.log.emit(
                        f"  [합격] 전체 {result['matched']}개 값이 허용범위 이내입니다!",
                        "success",
                    )
                elif result["exceeded_tolerance"] > 0:
                    self.log.emit(
                        f"  [불합격] {result['exceeded_tolerance']}개 값이 허용범위 초과!",
                        "error",
                    )
                    for t, g, r_val, diff in result["mismatches"][:5]:
                        self.log.emit(
                            f"      {t}  결과={g:.2f}  참조={r_val:.2f}  편차={diff:.4f}",
                            "error",
                        )
            else:
                self.log.emit("[7/7]  검증 생략 (참조 파일 없음)", "step")

            # ── Done ──
            elapsed = time.time() - start_time
            base_output = config.output_path.rsplit(".", 1)[0]
            generated_files = [
                path for path in [
                    config.output_path,
                    config.output_path + ".detail",
                    config.output_path + ".err",
                    base_output + ".csv",
                    base_output + ".kingdom.txt",
                    base_output + ".sonarwiz.txt",
                    config.output_path + ".png",
                    config.output_path + ".compare.png",
                    config.output_path + ".map.png",
                    config.output_path + ".corrmap.png",
                ]
                if path and os.path.isfile(path)
            ]
            summary = build_run_summary(
                config,
                nav_points,
                processed,
                stations,
                all_corrections,
                elapsed=elapsed,
                tide_model=tide_model,
                output_format=output_format,
                db_version=db_ver,
                validation=validation_result,
                preset_name=d.get("preset_name", ""),
                preset_summary=d.get("preset_summary", ""),
                generated_files=generated_files,
            )
            summary_paths = write_summary_files(config.output_path, summary)
            for summary_path in summary_paths.values():
                self.log.emit(
                    f"  \u2192 {os.path.basename(summary_path)}",
                    "info",
                )
            generated_files.extend(summary_paths.values())
            self.log.emit("", "dim")
            self.log.emit("\u2501" * 56, "dim")
            self.log.emit(
                f"  보정 완료 -- 소요시간: {elapsed:.1f}초", "success"
            )
            self.log.emit("\u2501" * 56, "dim")

            for fp in generated_files:
                if os.path.isfile(fp):
                    size_kb = os.path.getsize(fp) / 1024
                    self.log.emit(
                        f"  {os.path.basename(fp)}  ({size_kb:.1f} KB)", "detail"
                    )

            # Emit result data for visualization
            try:
                # Identify stations that had tide data loaded (from tide folder)
                tide_loaded_stations = []
                if stations:
                    for s in stations:
                        has_obs = hasattr(s, 'tide_obs') and s.tide_obs and getattr(s.tide_obs, 'records', None)
                        has_pred = hasattr(s, 'tide_pred') and s.tide_pred and getattr(s.tide_pred, 'records', None)
                        if has_obs or has_pred:
                            tide_loaded_stations.append((s.name, s.longitude, s.latitude))

                used_stations = tide_loaded_stations
                used_station_names = {n for n, _, _ in used_stations}

                # ── Confidence / uncertainty metrics ──
                confidence_per_point = []
                distances_to_nearest = []
                extrapolation_count = 0

                if all_corrections:
                    for idx, corr_list in enumerate(all_corrections):
                        if processed[idx].tc <= -999.0:
                            confidence_per_point.append(0.0)
                            distances_to_nearest.append(999.0)
                            if not corr_list:
                                extrapolation_count += 1
                            continue
                        if corr_list:
                            min_dist = min(
                                getattr(c, 'distance_km', 999.0)
                                for c in corr_list
                            )
                            distances_to_nearest.append(min_dist)
                            conf = 1.0 / (1.0 + min_dist / 50.0)
                            confidence_per_point.append(round(conf, 4))
                            if min_dist > 100.0:
                                extrapolation_count += 1
                        else:
                            distances_to_nearest.append(999.0)
                            confidence_per_point.append(0.0)
                            extrapolation_count += 1

                avg_station_distance_km = (
                    sum(distances_to_nearest) / len(distances_to_nearest)
                    if distances_to_nearest else 0.0
                )
                max_station_distance_km = (
                    max(distances_to_nearest) if distances_to_nearest else 0.0
                )

                # Count data gaps (> 1 hour between consecutive nav points)
                data_gap_count = 0
                for i in range(1, len(processed)):
                    dt_sec = abs(
                        (processed[i].t - processed[i - 1].t).total_seconds()
                    )
                    if dt_sec > 3600:
                        data_gap_count += 1

                viz_data = {
                    "processed": [(p.x, p.y, p.t.isoformat(), p.tc) for p in processed],
                    "stations": used_stations,
                    "output_path": config.output_path,
                    "elapsed": elapsed,
                    "rank_limit": d.get("rank_limit", 10),
                    "use_api": bool(use_api and api_key),
                    "summary": summary,
                    "confidence_per_point": confidence_per_point,
                    "avg_station_distance_km": round(avg_station_distance_km, 2),
                    "max_station_distance_km": round(max_station_distance_km, 2),
                    "extrapolation_count": extrapolation_count,
                    "data_gap_count": data_gap_count,
                }

                # Collect per-point station weights (sampled for performance)
                if all_corrections and used_station_names:
                    st_names = sorted(used_station_names)
                    step = max(1, len(all_corrections) // 2000)
                    sampled_times = []
                    sampled_weights = {name: [] for name in st_names}

                    for idx in range(0, len(all_corrections), step):
                        sampled_times.append(processed[idx].t.isoformat())
                        corr_list = all_corrections[idx]
                        # Build weight lookup for this point
                        w_map = {}
                        w_total = 0.0
                        for c in corr_list:
                            if c.station_name in sampled_weights:
                                w_map[c.station_name] = max(0.0, c.weight)
                                w_total += max(0.0, c.weight)
                        # Normalize to sum=1.0
                        for name in st_names:
                            raw_w = w_map.get(name, 0.0)
                            norm_w = raw_w / w_total if w_total > 0 else 0.0
                            sampled_weights[name].append(round(norm_w, 4))

                    viz_data["weight_times"] = sampled_times
                    viz_data["station_weights"] = sampled_weights

                self.result_data.emit(viz_data)
            except Exception as viz_err:
                self.log.emit(f"  시각화 데이터 준비 실패: {viz_err}", "warning")

            self.finished.emit(True, f"보정 완료 ({elapsed:.1f}초)")

        except Exception as e:
            self.log.emit("", "dim")
            self.log.emit(f"오류 발생: {str(e)}", "error")
            self.log.emit(traceback.format_exc(), "error")
            if cotidal:
                try:
                    cotidal.close_netcdfs()
                except Exception:
                    pass
            self.finished.emit(False, f"오류: {str(e)}")
