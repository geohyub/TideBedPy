"""
error_codes.py - 조석보정 에러 코드 상수

매직 넘버(-999.0 등)를 명명된 상수로 관리하여 코드 가독성과 유지보수성을 높인다.
"""


class TcError:
    """조석보정(Tc) 에러 코드 상수"""
    FAIL = -999.0           # 보정 실패 (일반)
    NO_TIDE_DATA = -998.0   # 조위 데이터 없음 (시간 범위 밖)
    THRESHOLD = -999.0      # 유효값 판별 임계값 (tc > THRESHOLD → 유효)

    @staticmethod
    def is_valid(tc: float) -> bool:
        """Tc 값이 유효한지 판별."""
        return tc > TcError.THRESHOLD

    @staticmethod
    def is_error(tc: float) -> bool:
        """Tc 값이 에러인지 판별."""
        return tc <= TcError.THRESHOLD


class DistError:
    """측지 거리 에러 코드"""
    FAIL = -9999.9          # Vincenty 거리 계산 실패


class HeightError:
    """조위 높이 에러 코드"""
    NO_DATA = -999.0        # 유효 조위 없음
    NO_TIDE_SERIES = -998.0 # 조위 시계열 자체가 없음
    INVALID_SPR = -999.9    # SprRange 무효
