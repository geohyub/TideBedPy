"""
encoding.py - 인코딩 자동감지 유틸리티

EUC-KR / UTF-8 파일을 자동으로 감지하여 올바르게 읽는다.
원본 C#은 Encoding.GetEncoding(949) (EUC-KR)만 사용했으나,
Python 버전은 UTF-8을 먼저 시도하고 실패 시 EUC-KR로 폴백한다.
"""

import logging

logger = logging.getLogger(__name__)


def detect_encoding(file_path: str) -> str:
    """
    파일의 인코딩을 감지한다.
    1. UTF-8 BOM (EF BB BF) 확인
    2. UTF-8로 읽기 시도
    3. 실패 시 EUC-KR (cp949)
    4. 그래도 실패 시 chardet 사용

    Returns:
        'utf-8' 또는 'euc-kr'
    """
    # 1. BOM 확인
    with open(file_path, 'rb') as f:
        raw = f.read(4)
        if raw[:3] == b'\xef\xbb\xbf':
            return 'utf-8-sig'

    # 2. UTF-8 시도
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            f.read()
        return 'utf-8'
    except UnicodeDecodeError:
        pass

    # 3. EUC-KR 시도
    try:
        with open(file_path, 'r', encoding='euc-kr') as f:
            f.read()
        return 'euc-kr'
    except UnicodeDecodeError:
        pass

    # 4. chardet 폴백
    try:
        import chardet
        with open(file_path, 'rb') as f:
            result = chardet.detect(f.read())
        enc = result.get('encoding', 'euc-kr')
        logger.info(f"chardet detected encoding: {enc} (confidence: {result.get('confidence', 0):.2f})")
        return enc
    except ImportError:
        logger.warning("chardet not available, defaulting to euc-kr")
        return 'euc-kr'


def open_text_file(file_path: str, mode: str = 'r'):
    """
    자동 인코딩 감지 후 텍스트 파일을 연다.

    Args:
        file_path: 파일 경로
        mode: 읽기 모드 ('r')

    Returns:
        파일 핸들 (TextIOWrapper)
    """
    encoding = detect_encoding(file_path)
    logger.debug(f"Opening {file_path} with encoding: {encoding}")
    return open(file_path, mode, encoding=encoding, errors='replace')


def read_lines(file_path: str) -> list:
    """
    파일의 모든 줄을 읽어 리스트로 반환한다.
    인코딩 자동 감지.

    Returns:
        줄 리스트 (개행 문자 제거됨)
    """
    encoding = detect_encoding(file_path)
    with open(file_path, 'r', encoding=encoding, errors='replace') as f:
        return [line.rstrip('\n\r') for line in f]
