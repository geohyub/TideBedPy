"""
font_utils.py - 폰트 관리 유틸리티

Pretendard 폰트를 자동으로 등록하고, matplotlib/tkinter에서 사용한다.
번들 폰트를 사용하여 어떤 환경에서도 동일한 글꼴로 표시.
"""

import os
import logging

logger = logging.getLogger(__name__)

# 번들 폰트 디렉토리
_FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fonts')

# 폰트 파일 경로
PRETENDARD_REGULAR = os.path.join(_FONTS_DIR, 'Pretendard-Regular.otf')
PRETENDARD_BOLD = os.path.join(_FONTS_DIR, 'Pretendard-Bold.otf')
PRETENDARD_SEMIBOLD = os.path.join(_FONTS_DIR, 'Pretendard-SemiBold.otf')


def register_pretendard_matplotlib():
    """
    matplotlib에 Pretendard 폰트를 등록한다.
    반환: 등록된 폰트 이름 (없으면 fallback)
    """
    try:
        import matplotlib.font_manager as fm

        registered = False
        for font_path in [PRETENDARD_REGULAR, PRETENDARD_BOLD, PRETENDARD_SEMIBOLD]:
            if os.path.isfile(font_path):
                fm.fontManager.addfont(font_path)
                registered = True

        if registered:
            import matplotlib.pyplot as plt
            plt.rcParams['font.family'] = 'Pretendard'
            plt.rcParams['axes.unicode_minus'] = False
            logger.debug("Pretendard 폰트 matplotlib 등록 완료")
            return 'Pretendard'
        else:
            # Fallback
            plt = __import__('matplotlib.pyplot', fromlist=['pyplot'])
            available = {f.name for f in fm.fontManager.ttflist}
            for fc in ['Malgun Gothic', 'NanumGothic', 'AppleGothic']:
                if fc in available:
                    plt.rcParams['font.family'] = fc
                    plt.rcParams['axes.unicode_minus'] = False
                    return fc
            return 'DejaVu Sans'

    except ImportError:
        return None


def get_tkinter_font_family():
    """
    tkinter에서 사용할 폰트 이름을 반환한다.
    Pretendard가 시스템에 설치되어 있으면 사용, 아니면 맑은 고딕.
    """
    try:
        import tkinter as tk
        root = tk._default_root
        if root is None:
            # 임시 root로 폰트 확인
            return 'Pretendard'  # tkinter에서 OTF 직접 사용은 제한적

        # 시스템 폰트 확인
        from tkinter import font as tkfont
        available = tkfont.families()
        if 'Pretendard' in available:
            return 'Pretendard'
        elif '맑은 고딕' in available or 'Malgun Gothic' in available:
            return '맑은 고딕'
        else:
            return 'Arial'
    except:
        return '맑은 고딕'


def register_pretendard_system():
    """
    시스템에 Pretendard 폰트를 임시 등록한다 (Windows).
    tkinter/exe에서 사용하려면 이 함수를 호출해야 함.
    """
    try:
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes

            # Windows: AddFontResourceEx로 현재 세션에 폰트 추가
            gdi32 = ctypes.windll.gdi32
            FR_PRIVATE = 0x10

            count = 0
            for font_path in [PRETENDARD_REGULAR, PRETENDARD_BOLD, PRETENDARD_SEMIBOLD]:
                if os.path.isfile(font_path):
                    result = gdi32.AddFontResourceExW(font_path, FR_PRIVATE, 0)
                    if result > 0:
                        count += 1

            if count > 0:
                logger.debug(f"Pretendard 폰트 시스템 등록: {count}개")
                return True

    except Exception as e:
        logger.debug(f"폰트 시스템 등록 실패: {e}")

    return False
