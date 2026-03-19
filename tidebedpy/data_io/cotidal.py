"""
cotidal.py - Co-tidal NetCDF 격자 로드

File_Catalog.txt로 15×16 격자 → NC 파일 매핑.
각 NC에서 SprRange, DL_MSL, MHWI를 읽어 이중선형 보간.

참조: frmMain.cs setSector, find_STBS_SECTOR, getCoTidalValue
"""

import os
import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SectorInfo:
    """Co-tidal 격자 섹터 정보"""
    ii: int = -1               # 격자 행 인덱스
    jj: int = -1               # 격자 열 인덱스
    x_base: float = 0.0        # Longitude 기준점
    y_base: float = 0.0        # Latitude 기준점
    x_size: float = 0.0        # 경도 방향 격자 크기 (degrees)
    y_size: float = 0.0        # 위도 방향 격자 크기 (degrees)
    x_count: int = 0           # 경도 방향 격자 수
    y_count: int = 0           # 위도 방향 격자 수
    is_active: bool = False    # 데이터 존재 여부
    ct_path: str = ''          # NC 파일 경로
    nc_dataset: object = None  # 열린 netCDF4.Dataset


class CoTidalGrid:
    """Co-tidal NetCDF 격자 관리"""

    def __init__(self, db_root: str):
        self.db_root = db_root
        self.sectors: List[List[Optional[SectorInfo]]] = []
        self.num_cols: int = 0   # 격자 열 수
        self.num_rows: int = 0   # 격자 행 수
        self.version: str = ''

    def load_catalog(self) -> bool:
        """
        File_Catalog.txt를 파싱하여 격자 구조를 로드한다.

        참조: frmMain.cs setSector (lines 6824-6891)

        파일 형식:
            Line 0: "15  16  FileName  Generated  1101  2024-07-31"
                     num_cols=15, num_rows=16
            Data: "II  JJ  CT_XX_12250_3000.nc  X|O"

        NC 파일명에서 xBase/yBase 추출:
            CT_XX_12250_3000.nc → xBase=122.50, yBase=30.00
        해상도 (파일명 3-5번째 문자):
            XX → 비활성
            30 → 3" arc-second (1/1200 deg)
            03 → 0.3" arc-second (1/12000 deg)
        """
        catalog_path = os.path.join(self.db_root, 'File_Catalog.txt')
        if not os.path.isfile(catalog_path):
            logger.error(f"File_Catalog.txt를 찾을 수 없음: {catalog_path}")
            return False

        from utils.encoding import read_lines
        lines = read_lines(catalog_path)

        if not lines:
            logger.error(f"File_Catalog.txt가 비어있음")
            return False

        # 헤더 파싱
        header_parts = re.split(r'\s+', lines[0].strip())
        try:
            self.num_cols = int(header_parts[0])
            self.num_rows = int(header_parts[1])
            if len(header_parts) >= 5:
                self.version = header_parts[4]
        except (ValueError, IndexError):
            logger.error(f"File_Catalog.txt 헤더 파싱 실패: {lines[0]}")
            return False

        # 2D 배열 초기화
        self.sectors = [[None] * self.num_rows for _ in range(self.num_cols)]

        # 데이터 파싱
        ct_dir = os.path.join(self.db_root, 'CT')
        loaded = 0

        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue

            parts = re.split(r'\s+', line)
            if len(parts) < 4:
                continue

            try:
                ii = int(parts[0])
                jj = int(parts[1])
                filename = parts[2]
                generated = parts[3]

                if ii >= self.num_cols or jj >= self.num_rows:
                    continue

                sector = SectorInfo(ii=ii, jj=jj)

                # 파일명에서 좌표 추출: CT_XX_12250_3000.nc
                # xBase = filename[6:11] / 100
                # yBase = filename[12:16] / 100
                name_parts = filename.replace('.nc', '').split('_')
                if len(name_parts) >= 4:
                    sector.x_base = int(name_parts[2]) / 100.0
                    sector.y_base = int(name_parts[3]) / 100.0

                # 해상도 결정
                mode = name_parts[1] if len(name_parts) >= 2 else 'XX'
                if mode == 'XX':
                    sector.is_active = False
                elif mode == '30':
                    # 3" arc-second = 1/1200 degree
                    sector.x_size = 1.0 / 1200.0
                    sector.y_size = 1.0 / 1200.0
                    sector.x_count = 601
                    sector.y_count = 601
                    sector.is_active = (generated == 'O')
                elif mode == '03':
                    # 0.3" arc-second = 1/12000 degree
                    sector.x_size = 1.0 / 12000.0
                    sector.y_size = 1.0 / 12000.0
                    sector.x_count = 6001
                    sector.y_count = 6001
                    sector.is_active = (generated == 'O')
                else:
                    sector.is_active = False

                if sector.is_active:
                    sector.ct_path = os.path.join(ct_dir, filename)
                    loaded += 1

                self.sectors[ii][jj] = sector

            except (ValueError, IndexError) as e:
                logger.debug(f"섹터 파싱 오류: {line} - {e}")
                continue

        logger.info(f"Co-tidal 카탈로그 로드: {self.num_cols}×{self.num_rows} 격자, "
                    f"{loaded}개 활성 섹터 (ver.{self.version})")
        return True

    def _safe_open_nc(self, path: str):
        """
        netCDF4로 NC 파일을 안전하게 연다.
        한글 경로 등 비ASCII 경로에서 netCDF4가 실패하면
        임시 디렉토리에 symlink/복사 후 열기를 시도한다.
        """
        import netCDF4
        import tempfile
        import shutil

        # 먼저 직접 열기 시도
        try:
            return netCDF4.Dataset(path, 'r')
        except Exception:
            pass

        # ASCII 경로 문제: 파일명 자체는 ASCII이므로
        # CT 디렉토리에 대한 ASCII symlink/junction 생성
        if not hasattr(self, '_ascii_ct_dir'):
            self._ascii_ct_dir = None
            ct_dir = os.path.dirname(path)
            # 임시 디렉토리에 junction 생성
            tmp_link = os.path.join(tempfile.gettempdir(), 'tidebedpy_ct')
            if os.path.exists(tmp_link):
                # 기존 링크 제거
                try:
                    os.remove(tmp_link)
                except:
                    try:
                        os.rmdir(tmp_link)
                    except:
                        pass
            try:
                os.symlink(ct_dir, tmp_link, target_is_directory=True)
                self._ascii_ct_dir = tmp_link
                logger.info(f"NC 경로 우회 symlink 생성: {tmp_link}")
            except Exception as e:
                logger.warning(f"Symlink 생성 실패, 파일 복사 방식 사용: {e}")
                self._ascii_ct_dir = None

        # symlink된 경로로 시도
        if self._ascii_ct_dir:
            alt_path = os.path.join(self._ascii_ct_dir, os.path.basename(path))
            try:
                return netCDF4.Dataset(alt_path, 'r')
            except Exception as e:
                logger.warning(f"Symlink 경로로도 열기 실패: {alt_path} - {e}")

        # 최후 수단: 파일 복사
        tmp_file = os.path.join(tempfile.gettempdir(), os.path.basename(path))
        shutil.copy2(path, tmp_file)
        try:
            ds = netCDF4.Dataset(tmp_file, 'r')
            if not hasattr(self, '_temp_nc_files'):
                self._temp_nc_files = []
            self._temp_nc_files.append(tmp_file)
            return ds
        except Exception as e:
            os.remove(tmp_file)
            raise

    def open_netcdfs(self) -> int:
        """모든 활성 섹터의 NC 파일을 열고 열린 수를 반환."""
        opened = 0
        for i in range(self.num_cols):
            for j in range(self.num_rows):
                sector = self.sectors[i][j]
                if sector and sector.is_active and sector.ct_path:
                    if os.path.isfile(sector.ct_path):
                        try:
                            sector.nc_dataset = self._safe_open_nc(sector.ct_path)
                            # NC 파일의 실제 좌표에서 그리드 파라미터 갱신
                            self._update_sector_from_nc(sector)
                            opened += 1
                        except Exception as e:
                            logger.warning(f"NC 파일 열기 실패: {sector.ct_path} - {e}")
                            sector.is_active = False
                    else:
                        logger.debug(f"NC 파일 없음: {sector.ct_path}")
                        sector.is_active = False
        logger.info(f"NetCDF 파일 열기: {opened}개")
        return opened

    def _update_sector_from_nc(self, sector: SectorInfo) -> None:
        """
        NC 파일의 실제 좌표 변수에서 그리드 파라미터를 갱신한다.

        File_Catalog.txt의 하드코딩된 값(1/12000, 6001) 대신
        NC 파일의 X/Y 좌표 변수에서 실제 그리드 간격과 크기를 읽는다.
        예: 5401 포인트, 0.5°/5400 = 1/10800° 간격
        """
        nc = sector.nc_dataset
        if nc is None:
            return

        try:
            if 'X' in nc.variables and 'Y' in nc.variables:
                x_coords = nc.variables['X'][:]
                y_coords = nc.variables['Y'][:]

                sector.x_count = len(x_coords)
                sector.y_count = len(y_coords)

                if len(x_coords) >= 2:
                    sector.x_size = float(x_coords[1] - x_coords[0])
                if len(y_coords) >= 2:
                    sector.y_size = float(y_coords[1] - y_coords[0])

                # x_base/y_base도 NC에서 갱신
                sector.x_base = float(x_coords[0])
                sector.y_base = float(y_coords[0])

                logger.debug(f"NC 그리드 갱신: {sector.x_count}×{sector.y_count}, "
                           f"size={sector.x_size:.8f}×{sector.y_size:.8f}, "
                           f"base=({sector.x_base},{sector.y_base})")
            else:
                # 좌표 변수 없으면 SprRange 차원에서 크기만 읽기
                if 'SprRange' in nc.variables:
                    shape = nc.variables['SprRange'].shape
                    if len(shape) == 2:
                        sector.x_count = shape[0]
                        sector.y_count = shape[1]
                        # 0.5도 커버리지 가정
                        if sector.x_count > 1:
                            sector.x_size = 0.5 / (sector.x_count - 1)
                        if sector.y_count > 1:
                            sector.y_size = 0.5 / (sector.y_count - 1)
        except Exception as e:
            logger.debug(f"NC 그리드 갱신 실패: {e}")

    def close_netcdfs(self) -> None:
        """열린 모든 NC 파일을 닫는다."""
        for i in range(self.num_cols):
            for j in range(self.num_rows):
                sector = self.sectors[i][j]
                if sector and sector.nc_dataset:
                    try:
                        sector.nc_dataset.close()
                    except:
                        pass
                    sector.nc_dataset = None

    def find_sector(self, x: float, y: float) -> Optional[SectorInfo]:
        """
        (x, y) 좌표가 속하는 섹터를 찾는다.

        참조: frmMain.cs find_STBS_SECTOR (lines 5931-5950)
        섹터 크기: 0.5° × 0.5°

        Args:
            x: Longitude
            y: Latitude

        Returns:
            SectorInfo 또는 None
        """
        for i in range(self.num_cols):
            if self.sectors[i][0] is None:
                continue
            x_base = self.sectors[i][0].x_base
            if x_base <= x < x_base + 0.5:
                for j in range(self.num_rows):
                    sector = self.sectors[i][j]
                    if sector is None:
                        continue
                    if sector.y_base <= y < sector.y_base + 0.5:
                        return sector
                break
        return None

    def get_cotidal_values(self, x: float, y: float) -> Tuple[float, float, float]:
        """
        (x, y) 위치의 Co-tidal 값을 이중선형 보간하여 반환한다.

        참조: frmMain.cs getCoTidalValue (lines 5753-5778)

        1. 섹터 찾기
        2. 격자 내 위치 계산 (인덱스 + 델타)
        3. NC에서 2×2 블록 읽기
        4. 이중선형 보간

        Args:
            x: Longitude
            y: Latitude

        Returns:
            (spr_range, msl, mhwi) 튜플

        Raises:
            ValueError: 섹터를 찾을 수 없거나 데이터 없음
        """
        sector = self.find_sector(x, y)
        if sector is None or not sector.is_active:
            raise ValueError(f"Co-tidal 섹터를 찾을 수 없음: ({x:.4f}, {y:.4f})")

        if sector.nc_dataset is None:
            raise ValueError(f"NC 데이터셋이 열리지 않음: ({x:.4f}, {y:.4f})")

        # 격자 내 인덱스 계산
        grid_x_float = (x - sector.x_base) / sector.x_size
        grid_y_float = (y - sector.y_base) / sector.y_size
        grid_x = int(grid_x_float)
        grid_y = int(grid_y_float)
        x_delta = grid_x_float - grid_x
        y_delta = grid_y_float - grid_y

        # 경계 체크
        if grid_x < 0 or grid_x >= sector.x_count - 1:
            raise ValueError(f"X 격자 인덱스 범위 초과: {grid_x}")
        if grid_y < 0 or grid_y >= sector.y_count - 1:
            raise ValueError(f"Y 격자 인덱스 범위 초과: {grid_y}")

        nc = sector.nc_dataset

        # 2×2 블록 읽기 및 이중선형 보간
        from core.interpolation import bilinear_interpolate

        results = []
        for var_name in ['SprRange', 'DL_MSL', 'MHWI']:
            try:
                data = nc.variables[var_name]
                block = data[grid_x:grid_x+2, grid_y:grid_y+2]

                v00 = float(block[0, 0])
                v10 = float(block[1, 0])
                v01 = float(block[0, 1])
                v11 = float(block[1, 1])

                val = bilinear_interpolate(x_delta, y_delta, v00, v01, v10, v11)
                results.append(val)
            except Exception as e:
                logger.error(f"NC 변수 '{var_name}' 읽기 실패: {e}")
                raise ValueError(f"Co-tidal 값 읽기 실패: {var_name} at ({x:.4f}, {y:.4f})")

        spr_range, msl, mhwi = results
        return spr_range, msl, mhwi
