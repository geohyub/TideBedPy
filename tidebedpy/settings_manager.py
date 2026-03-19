"""
settings_manager.py - 세팅 프리셋 저장/불러오기

자주 사용하는 설정을 JSON 프리셋 파일로 관리한다.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 프리셋 저장 디렉토리
PRESETS_DIR_NAME = 'presets'


def _get_presets_dir(base_dir: str = None) -> str:
    """프리셋 디렉토리 경로를 반환하고, 없으면 생성한다."""
    if base_dir is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    presets_dir = os.path.join(base_dir, PRESETS_DIR_NAME)
    os.makedirs(presets_dir, exist_ok=True)
    return presets_dir


def save_preset(name: str, settings: Dict, base_dir: str = None) -> str:
    """
    설정을 프리셋 파일로 저장한다.

    Args:
        name: 프리셋 이름 (파일명으로 사용)
        settings: 설정 딕셔너리
        base_dir: 기준 디렉토리 (기본: tidebedpy/)

    Returns:
        저장된 파일 경로
    """
    presets_dir = _get_presets_dir(base_dir)

    # 파일명 정리 (특수문자 제거)
    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_', '.')).strip()
    if not safe_name:
        safe_name = f'preset_{datetime.now().strftime("%Y%m%d_%H%M%S")}'

    filepath = os.path.join(presets_dir, f'{safe_name}.json')

    preset_data = {
        'name': name,
        'created': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': '2.1.0',
        'settings': settings,
    }

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(preset_data, f, ensure_ascii=False, indent=2)

    logger.info(f"프리셋 저장: {filepath}")
    return filepath


def load_preset(filepath: str) -> Optional[Dict]:
    """
    프리셋 파일에서 설정을 불러온다.

    Args:
        filepath: 프리셋 파일 경로

    Returns:
        설정 딕셔너리 또는 None
    """
    if not os.path.isfile(filepath):
        logger.error(f"프리셋 파일 없음: {filepath}")
        return None

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('settings', {})
    except Exception as e:
        logger.error(f"프리셋 로드 실패: {e}")
        return None


def list_presets(base_dir: str = None) -> List[Dict]:
    """
    사용 가능한 프리셋 목록을 반환한다.

    Returns:
        [{'name': str, 'path': str, 'created': str}, ...]
    """
    presets_dir = _get_presets_dir(base_dir)
    presets = []

    for fname in sorted(os.listdir(presets_dir)):
        if not fname.endswith('.json'):
            continue
        filepath = os.path.join(presets_dir, fname)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            presets.append({
                'name': data.get('name', fname),
                'path': filepath,
                'created': data.get('created', ''),
                'filename': fname,
            })
        except Exception:
            presets.append({
                'name': fname,
                'path': filepath,
                'created': '',
                'filename': fname,
            })

    return presets


def delete_preset(filepath: str) -> bool:
    """프리셋 파일을 삭제한다."""
    try:
        if os.path.isfile(filepath):
            os.remove(filepath)
            logger.info(f"프리셋 삭제: {filepath}")
            return True
    except Exception as e:
        logger.error(f"프리셋 삭제 실패: {e}")
    return False


def settings_to_dict(nav_path='', tide_path='', output_path='',
                     db_path='', station_path='',
                     tide_type='실측', rank_limit=10,
                     time_interval=0, timezone='GMT',
                     utc_offset=0.0,
                     write_detail=True) -> Dict:
    """GUI 변수를 설정 딕셔너리로 변환."""
    return {
        'nav_path': nav_path,
        'tide_path': tide_path,
        'output_path': output_path,
        'db_path': db_path,
        'station_path': station_path,
        'tide_type': tide_type,
        'rank_limit': rank_limit,
        'time_interval': time_interval,
        'timezone': timezone,
        'utc_offset': utc_offset,
        'write_detail': write_detail,
    }
