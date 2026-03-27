"""core/geodesy.py 단위 테스트."""
import pytest
from core.geodesy import vincenty_inverse
from core.error_codes import DistError


class TestVincentyInverse:
    def test_known_distance(self):
        """서울↔부산 직선거리 약 325km."""
        dist = vincenty_inverse(126.978, 37.567, 129.076, 35.180)
        assert 320_000 < dist < 330_000

    def test_same_point(self):
        """동일 좌표 → 0m."""
        dist = vincenty_inverse(126.0, 36.0, 126.0, 36.0)
        assert dist == pytest.approx(0.0, abs=0.01)

    def test_short_distance(self):
        """약 1km 거리."""
        dist = vincenty_inverse(126.0, 36.0, 126.01, 36.0)
        assert 800 < dist < 1200

    def test_antipodal_no_crash(self):
        """대척점 계산이 에러 없이 수행되어야 한다."""
        dist = vincenty_inverse(0.0, 0.0, 180.0, 0.0)
        assert dist > 0 or dist == DistError.FAIL
