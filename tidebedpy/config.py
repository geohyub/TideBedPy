"""
config.py - 설정 관리

INI 파일 파싱 + CLI 인자 병합 + 자동 경로 탐색.
참조: setting/TideBedLite.ini, GenOption_T.cs
"""

import os
import configparser
import argparse
import logging
from dataclasses import dataclass, field
from typing import Optional, List

logger = logging.getLogger(__name__)


def _find_project_root(start_path: str = None) -> str:
    """
    TideBed 프로젝트 루트 디렉토리를 탐색한다.

    탐색 기준: info/ 폴더와 setting/ 폴더가 있는 디렉토리.
    tidebedpy/ 폴더 기준으로 상위 디렉토리를 탐색한다.

    Returns:
        프로젝트 루트 경로 또는 빈 문자열
    """
    if start_path is None:
        # tidebedpy 패키지 디렉토리의 상위 = 프로젝트 루트
        start_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # start_path부터 상위 3단계까지 탐색
    candidates = [start_path]
    parent = start_path
    for _ in range(3):
        parent = os.path.dirname(parent)
        if parent == os.path.dirname(parent):  # 루트 도달
            break
        candidates.append(parent)

    for path in candidates:
        has_info = os.path.isdir(os.path.join(path, 'info'))
        has_setting = os.path.isdir(os.path.join(path, 'setting'))
        if has_info and has_setting:
            return path

    return start_path


def _find_db_root(project_root: str) -> str:
    """
    표준개정수DB 디렉토리를 자동 탐색한다.

    탐색 기준: File_Catalog.txt와 CT/ 하위 폴더가 있는 디렉토리.
    info/ 하위를 우선 탐색한다.

    Returns:
        DB 루트 경로 또는 빈 문자열
    """
    info_dir = os.path.join(project_root, 'info')
    if not os.path.isdir(info_dir):
        return ''

    for item in os.listdir(info_dir):
        full = os.path.join(info_dir, item)
        if not os.path.isdir(full):
            continue
        catalog = os.path.join(full, 'File_Catalog.txt')
        ct_dir = os.path.join(full, 'CT')
        if os.path.isfile(catalog) and os.path.isdir(ct_dir):
            return full

    return ''


def _find_station_info(project_root: str) -> str:
    """
    기준항정보.txt 파일을 자동 탐색한다.

    탐색 기준: info/ 하위에서 첫 줄에 TRUE/FALSE가 포함된 .txt 파일.
    '기준항정보' 폴더를 우선 탐색한다.

    Returns:
        기준항정보.txt 경로 또는 빈 문자열
    """
    info_dir = os.path.join(project_root, 'info')
    if not os.path.isdir(info_dir):
        return ''

    # info/ 하위 디렉토리를 순회
    for item in os.listdir(info_dir):
        full = os.path.join(info_dir, item)
        if not os.path.isdir(full):
            continue

        # 디렉토리 내 .txt 파일 검사
        for fname in os.listdir(full):
            if not fname.endswith('.txt'):
                continue
            if fname == 'File_Catalog.txt' or fname == 'BaseControlPoint.txt':
                continue

            fpath = os.path.join(full, fname)
            try:
                # 첫 줄에 TRUE/FALSE 패턴이 있는지 확인
                for enc in ['euc-kr', 'utf-8']:
                    try:
                        with open(fpath, 'r', encoding=enc) as f:
                            first_line = f.readline().strip().upper()
                            if first_line.startswith('TRUE') or first_line.startswith('FALSE'):
                                # File_Catalog.txt가 같은 디렉토리에 없는 것을 확인
                                # (DB 디렉토리의 기준항정보가 아닌 독립 기준항정보 우선)
                                catalog_here = os.path.isfile(os.path.join(full, 'File_Catalog.txt'))
                                if not catalog_here:
                                    return fpath
                                # DB 디렉토리 내 기준항정보는 후순위 후보
                                break
                        break
                    except UnicodeDecodeError:
                        continue
            except Exception:
                continue

    # 후순위: DB 디렉토리 내 기준항정보
    for item in os.listdir(info_dir):
        full = os.path.join(info_dir, item)
        if not os.path.isdir(full):
            continue
        for fname in os.listdir(full):
            if not fname.endswith('.txt'):
                continue
            if fname == 'File_Catalog.txt' or fname == 'BaseControlPoint.txt':
                continue
            fpath = os.path.join(full, fname)
            try:
                for enc in ['euc-kr', 'utf-8']:
                    try:
                        with open(fpath, 'r', encoding=enc) as f:
                            first_line = f.readline().strip().upper()
                            if first_line.startswith('TRUE') or first_line.startswith('FALSE'):
                                return fpath
                        break
                    except UnicodeDecodeError:
                        continue
            except Exception:
                continue

    return ''


@dataclass
class TideBedConfig:
    """TideBedPy 설정"""
    # 경로 설정
    ref_st_info_path: str = ''          # 기준항정보.txt 경로
    db_root: str = ''                   # 표준개정수DB 루트
    tts_folder: str = ''                # 실측조위 폴더
    tts_p_folder: str = ''              # 예측조위 폴더 (선택)
    nav_directory: str = ''             # 항적 데이터 디렉토리
    output_path: str = ''               # 출력 .tid 파일 경로

    # 처리 옵션
    use_search_range: bool = False      # 거리 필터 사용 (C# 원본은 강제 False)
    search_range_km: float = 100.0      # 탐색 범위 (km)
    rank_limit: int = 10                # 최대 사용 기준항 수 (max 10)
    time_interval_sec: int = 0          # 출력 시간 간격 (0=모든 포인트)
    write_detail: bool = True           # 상세 출력 여부
    use_station_restriction: bool = False  # 기준항 제한 사용
    tide_series_type: str = '실측'       # '실측' 또는 '예측'
    is_kst: bool = False                # Nav 시간대 (True=KST, False=GMT) — 하위호환
    utc_offset: float = 0.0            # Nav 시간대 UTC 오프셋 (시간) — 유연한 시간대 설정
                                        # 예: GMT=0, KST=+9, JST=+9, CST=+8 등

    # 검증
    validate_path: str = ''             # 검증용 참조 .tid 파일 경로

    @classmethod
    def from_ini(cls, ini_path: str) -> 'TideBedConfig':
        """INI 파일에서 설정 로드"""
        config = cls()
        ini = configparser.ConfigParser()

        # INI 파일 인코딩 감지하여 읽기
        from utils.encoding import detect_encoding
        encoding = detect_encoding(ini_path)
        ini.read(ini_path, encoding=encoding)

        # [Program] 섹션
        if ini.has_section('Program'):
            prog = ini['Program']
            config.ref_st_info_path = prog.get('RefStInfoFilePath', '')
            config.db_root = prog.get('DB_ROOT', '')
            config.tts_folder = prog.get('TTS_Folder', '')
            config.tts_p_folder = prog.get('TTS_p_Folder', '')

        # [NAVIGATION] 섹션
        if ini.has_section('NAVIGATION'):
            nav = ini['NAVIGATION']
            config.nav_directory = nav.get('Data_Directory', '')

        # [GenOption] 섹션
        if ini.has_section('GenOption'):
            gen = ini['GenOption']
            config.use_search_range = gen.get('UseSearchRange', 'False').lower() == 'true'
            config.search_range_km = float(gen.get('SearchRangeValue', '100'))
            config.rank_limit = min(int(gen.get('RankLimit', '10')), 10)
            config.time_interval_sec = int(gen.get('TimeIntervalSec', '0'))
            config.write_detail = gen.get('WriteDetail', 'True').lower() == 'true'
            config.use_station_restriction = gen.get('UseStationRestriction', 'False').lower() == 'true'
            tts_type = gen.get('TypeOfTideTimeSeries', '실측')
            config.tide_series_type = tts_type

        logger.info(f"INI 설정 로드 완료: {ini_path}")
        return config

    def merge_args(self, args: argparse.Namespace) -> None:
        """CLI 인자로 설정 오버라이드"""
        if hasattr(args, 'nav') and args.nav:
            self.nav_directory = args.nav
        if hasattr(args, 'tide') and args.tide:
            self.tts_folder = args.tide
        if hasattr(args, 'db') and args.db:
            self.db_root = args.db
        if hasattr(args, 'stations') and args.stations:
            self.ref_st_info_path = args.stations
        if hasattr(args, 'output') and args.output:
            self.output_path = args.output
        if hasattr(args, 'type') and args.type:
            self.tide_series_type = args.type
        if hasattr(args, 'rank_limit') and args.rank_limit is not None:
            self.rank_limit = min(args.rank_limit, 10)
        if hasattr(args, 'time_interval') and args.time_interval is not None:
            self.time_interval_sec = args.time_interval
        if hasattr(args, 'detail') and args.detail is not None:
            self.write_detail = args.detail
        if hasattr(args, 'kst') and args.kst:
            self.is_kst = True
        if hasattr(args, 'validate') and args.validate:
            self.validate_path = args.validate

    def auto_discover(self, project_root: str = None) -> List[str]:
        """
        미설정 경로를 자동 탐색으로 채운다.

        프로젝트 루트 기준으로 info/ 하위를 탐색하여
        기준항정보.txt와 표준개정수DB를 자동으로 찾는다.

        Args:
            project_root: 프로젝트 루트 경로 (None이면 자동 탐색)

        Returns:
            자동 탐색으로 발견한 항목 설명 리스트
        """
        if project_root is None:
            project_root = _find_project_root()

        discovered = []

        # 기준항정보.txt 자동 탐색
        if not self.ref_st_info_path or not os.path.isfile(self.ref_st_info_path):
            found = _find_station_info(project_root)
            if found:
                self.ref_st_info_path = found
                discovered.append(f"  [AUTO] Station info: {found}")

        # 표준개정수DB 자동 탐색
        if not self.db_root or not os.path.isdir(self.db_root):
            found = _find_db_root(project_root)
            if found:
                self.db_root = found
                discovered.append(f"  [AUTO] DB root: {found}")

        return discovered

    def validate(self) -> list:
        """설정 유효성 검사. 에러 목록 반환."""
        errors = []
        if not self.ref_st_info_path or not os.path.isfile(self.ref_st_info_path):
            errors.append(f"기준항정보 파일을 찾을 수 없습니다: {self.ref_st_info_path}")
        if not self.db_root or not os.path.isdir(self.db_root):
            errors.append(f"표준개정수DB 디렉토리를 찾을 수 없습니다: {self.db_root}")
        if not self.tts_folder or not os.path.isdir(self.tts_folder):
            errors.append(f"조위 데이터 폴더를 찾을 수 없습니다: {self.tts_folder}")
        if not self.nav_directory or not os.path.isdir(self.nav_directory):
            errors.append(f"항적 데이터 디렉토리를 찾을 수 없습니다: {self.nav_directory}")
        if not self.output_path:
            errors.append("출력 파일 경로가 지정되지 않았습니다")
        return errors
