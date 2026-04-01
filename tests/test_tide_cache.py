"""Test tide data caching."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_cache_roundtrip(tmp_path):
    """Store and retrieve tide data."""
    try:
        from tidebedpy.data_io.tide_cache import TideCache
    except ImportError:
        pytest.skip("tide_cache not yet created")

    cache = TideCache(str(tmp_path / "test_cache.db"))

    records = [{"time": "2025-01-14 01:00", "value": 3.14}]
    cache.put("DT_0001", "20250114", records)

    result = cache.get("DT_0001", "20250114")
    assert result is not None
    assert len(result) == 1
    assert result[0]["value"] == 3.14

    cache.close()


def test_cache_miss(tmp_path):
    """Cache miss returns None."""
    try:
        from tidebedpy.data_io.tide_cache import TideCache
    except ImportError:
        pytest.skip("tide_cache not yet created")

    cache = TideCache(str(tmp_path / "test_cache.db"))
    result = cache.get("DT_9999", "20250114")
    assert result is None
    cache.close()


def test_cache_stats(tmp_path):
    """Cache stats should reflect stored data."""
    try:
        from tidebedpy.data_io.tide_cache import TideCache
    except ImportError:
        pytest.skip("tide_cache not yet created")

    cache = TideCache(str(tmp_path / "test_cache.db"))
    cache.put("DT_0001", "20250114", [{"time": "01:00", "value": 1.0}])
    cache.put("DT_0002", "20250114", [{"time": "01:00", "value": 2.0}])

    stats = cache.stats()
    assert stats["total_records"] == 2
    assert stats["stations"] == 2
    cache.close()


def test_cache_overwrite(tmp_path):
    """Overwriting same key should update data."""
    try:
        from tidebedpy.data_io.tide_cache import TideCache
    except ImportError:
        pytest.skip("tide_cache not yet created")

    cache = TideCache(str(tmp_path / "test_cache.db"))
    cache.put("DT_0001", "20250114", [{"time": "01:00", "value": 1.0}])
    cache.put("DT_0001", "20250114", [{"time": "01:00", "value": 9.99}])

    result = cache.get("DT_0001", "20250114")
    assert result[0]["value"] == 9.99

    stats = cache.stats()
    assert stats["total_records"] == 1  # replaced, not duplicated
    cache.close()


def test_cache_clear(tmp_path):
    """Clear should remove all data."""
    try:
        from tidebedpy.data_io.tide_cache import TideCache
    except ImportError:
        pytest.skip("tide_cache not yet created")

    cache = TideCache(str(tmp_path / "test_cache.db"))
    cache.put("DT_0001", "20250114", [{"time": "01:00", "value": 1.0}])
    cache.put("DT_0002", "20250115", [{"time": "02:00", "value": 2.0}])

    cache.clear()
    stats = cache.stats()
    assert stats["total_records"] == 0
    cache.close()


def test_cache_has(tmp_path):
    """has() should return True for cached, False for missing."""
    try:
        from tidebedpy.data_io.tide_cache import TideCache
    except ImportError:
        pytest.skip("tide_cache not yet created")

    cache = TideCache(str(tmp_path / "test_cache.db"))
    assert cache.has("DT_0001", "20250114") is False

    cache.put("DT_0001", "20250114", [{"time": "01:00", "value": 1.0}])
    assert cache.has("DT_0001", "20250114") is True
    cache.close()
