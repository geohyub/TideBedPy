"""core/interpolation.py 단위 테스트."""
import math
import pytest
from core.interpolation import bilinear_interpolate, compute_idw_weights


# ── bilinear_interpolate ──

class TestBilinearInterpolate:
    def test_center(self):
        """중심점 (0.5, 0.5) → 4꼭짓점의 평균."""
        result = bilinear_interpolate(0.5, 0.5, 100.0, 200.0, 300.0, 400.0)
        assert result == pytest.approx(250.0)

    def test_corner_v00(self):
        """꼭짓점 (0,0) → v00."""
        assert bilinear_interpolate(0.0, 0.0, 10.0, 20.0, 30.0, 40.0) == pytest.approx(10.0)

    def test_corner_v11(self):
        """꼭짓점 (1,1) → v11."""
        assert bilinear_interpolate(1.0, 1.0, 10.0, 20.0, 30.0, 40.0) == pytest.approx(40.0)

    def test_edge_x(self):
        """X 엣지 (0.5, 0) → v00과 v10의 중간 (a = v00+(v10-v00)*0.5)."""
        # a = 100 + (300-100)*0.5 = 200, b = 200 + (400-200)*0.5 = 300
        # result = 200 + (300-200)*0 = 200
        assert bilinear_interpolate(0.5, 0.0, 100.0, 200.0, 300.0, 400.0) == pytest.approx(200.0)

    def test_edge_y(self):
        """Y 엣지 (0, 0.5) → v00과 v01의 중간."""
        # a = 100 + (300-100)*0 = 100, b = 200 + (400-200)*0 = 200
        # result = 100 + (200-100)*0.5 = 150
        assert bilinear_interpolate(0.0, 0.5, 100.0, 200.0, 300.0, 400.0) == pytest.approx(150.0)

    def test_uniform(self):
        """모든 값 동일 → 결과도 동일."""
        assert bilinear_interpolate(0.3, 0.7, 42.0, 42.0, 42.0, 42.0) == pytest.approx(42.0)

    # ── NaN 방어 ──

    def test_one_nan(self):
        """1개 NaN → 나머지 3개로 IDW 보간."""
        result = bilinear_interpolate(0.5, 0.5, 100.0, float('nan'), 200.0, 300.0)
        assert not math.isnan(result)
        assert 100.0 < result < 300.0

    def test_two_nan(self):
        """2개 NaN → 나머지 2개로 IDW 보간."""
        result = bilinear_interpolate(0.0, 0.0, 100.0, float('nan'), float('nan'), 300.0)
        assert not math.isnan(result)
        # (0,0)에서 v00=100 거리 0, v11=300 거리 sqrt(2) → 100에 가까운 값
        assert result == pytest.approx(100.0, abs=1.0)

    def test_three_nan(self):
        """3개 NaN → 유일한 유효값 반환."""
        result = bilinear_interpolate(0.5, 0.5, float('nan'), float('nan'), float('nan'), 42.0)
        assert result == pytest.approx(42.0)

    def test_all_nan(self):
        """모든 NaN → NaN 반환."""
        result = bilinear_interpolate(0.5, 0.5, float('nan'), float('nan'), float('nan'), float('nan'))
        assert math.isnan(result)

    def test_inf_treated_as_nan(self):
        """inf도 NaN과 같이 제외."""
        result = bilinear_interpolate(0.5, 0.5, 100.0, float('inf'), 200.0, 300.0)
        assert not math.isinf(result)
        assert not math.isnan(result)


# ── compute_idw_weights ──

class TestComputeIDW:
    @pytest.fixture
    def mock_stations(self):
        """테스트용 간이 기준항."""
        class St:
            def __init__(self, name, lon, lat):
                self.name = name
                self.longitude = lon
                self.latitude = lat
        return [
            St('A', 126.0, 36.0),
            St('B', 127.0, 36.0),
            St('C', 126.5, 37.0),
        ]

    def test_weights_sum_to_one(self, mock_stations):
        """모든 가중치의 합 = 1.0."""
        weights = compute_idw_weights(126.5, 36.5, mock_stations)
        total = sum(w.weight for w in weights)
        assert total == pytest.approx(1.0, abs=1e-10)

    def test_sorted_by_distance(self, mock_stations):
        """결과가 거리순 정렬."""
        weights = compute_idw_weights(126.5, 36.5, mock_stations)
        distances = [w.distance_m for w in weights]
        assert distances == sorted(distances)

    def test_nearest_has_highest_weight(self, mock_stations):
        """가장 가까운 관측소가 가장 큰 가중치."""
        weights = compute_idw_weights(126.0, 36.0, mock_stations)
        assert weights[0].station_name == 'A'
        assert weights[0].weight > weights[1].weight

    def test_empty_stations(self):
        """관측소 없으면 빈 리스트."""
        weights = compute_idw_weights(126.0, 36.0, [])
        assert weights == []

    def test_same_location(self, mock_stations):
        """동일 위치 관측소 → 0.001m floor, weight 정상."""
        weights = compute_idw_weights(126.0, 36.0, mock_stations)
        assert weights[0].distance_m == pytest.approx(0.001, abs=0.01)
        assert weights[0].weight > 0.99  # 거의 1
