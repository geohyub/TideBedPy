"""core/error_codes.py 단위 테스트."""
from core.error_codes import TcError, DistError, HeightError


class TestTcError:
    def test_valid_positive(self):
        assert TcError.is_valid(100.0) is True

    def test_valid_zero(self):
        assert TcError.is_valid(0.0) is True

    def test_valid_small_negative(self):
        assert TcError.is_valid(-5.0) is True

    def test_error_exact(self):
        assert TcError.is_error(-999.0) is True

    def test_error_below(self):
        assert TcError.is_error(-1000.0) is True

    def test_not_error(self):
        assert TcError.is_error(0.0) is False

    def test_constants(self):
        assert TcError.FAIL == -999.0
        assert TcError.NO_TIDE_DATA == -998.0


class TestDistError:
    def test_fail_value(self):
        assert DistError.FAIL == -9999.9
        assert DistError.FAIL < 0


class TestHeightError:
    def test_constants(self):
        assert HeightError.NO_DATA == -999.0
        assert HeightError.NO_TIDE_SERIES == -998.0
        assert HeightError.INVALID_SPR == -999.9
