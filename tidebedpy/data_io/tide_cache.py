"""KHOA API 조위 데이터 오프라인 캐시 (SQLite)."""

import os
import json
import sqlite3
import logging
from datetime import datetime
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".tidebedpy")
DEFAULT_CACHE_DB = os.path.join(DEFAULT_CACHE_DIR, "tide_cache.db")


class TideCache:
    """SQLite cache for KHOA API tide observation data."""

    def __init__(self, db_path: str = DEFAULT_CACHE_DB):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._create_tables()

    def _create_tables(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS tide_data (
                station_code TEXT NOT NULL,
                date TEXT NOT NULL,
                interval_min INTEGER NOT NULL DEFAULT 10,
                data TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (station_code, date, interval_min)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS cache_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        self._conn.commit()

    def get(self, station_code: str, date: str,
            interval_min: int = 10) -> Optional[List[Dict]]:
        """Get cached tide data for station+date. Returns None if not cached."""
        row = self._conn.execute(
            "SELECT data FROM tide_data "
            "WHERE station_code=? AND date=? AND interval_min=?",
            (station_code, date, interval_min)
        ).fetchone()
        if row:
            return json.loads(row[0])
        return None

    def put(self, station_code: str, date: str, records: List[Dict],
            interval_min: int = 10):
        """Store tide data in cache."""
        self._conn.execute(
            "INSERT OR REPLACE INTO tide_data "
            "(station_code, date, interval_min, data, fetched_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (station_code, date, interval_min,
             json.dumps(records, ensure_ascii=False),
             datetime.now().isoformat())
        )
        self._conn.commit()

    def has(self, station_code: str, date: str,
            interval_min: int = 10) -> bool:
        """Check if data exists in cache."""
        row = self._conn.execute(
            "SELECT 1 FROM tide_data "
            "WHERE station_code=? AND date=? AND interval_min=?",
            (station_code, date, interval_min)
        ).fetchone()
        return row is not None

    def get_date_range(self, station_code: str, start: str, end: str,
                       interval_min: int = 10) -> Dict[str, List[Dict]]:
        """Get all cached dates in range.

        Returns {date: records} for cached dates only.
        """
        rows = self._conn.execute(
            "SELECT date, data FROM tide_data "
            "WHERE station_code=? AND date>=? AND date<=? AND interval_min=?",
            (station_code, start, end, interval_min)
        ).fetchall()
        return {row[0]: json.loads(row[1]) for row in rows}

    def stats(self) -> Dict:
        """Return cache statistics."""
        row = self._conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT station_code) FROM tide_data"
        ).fetchone()
        return {"total_records": row[0], "stations": row[1]}

    def clear(self, station_code: str = None):
        """Clear cache. If station_code given, clear only that station."""
        if station_code:
            self._conn.execute(
                "DELETE FROM tide_data WHERE station_code=?",
                (station_code,))
        else:
            self._conn.execute("DELETE FROM tide_data")
        self._conn.commit()

    def close(self):
        """Close database connection."""
        self._conn.close()
