"""
time_utils.py - 시간 처리 유틸리티

KST/GMT 변환, DOY (Day of Year) 파싱 등.
참조: TideManipulation/GKTime.cs
"""

from datetime import datetime, timedelta


KST_OFFSET_HOURS = 9.0


def parse_doy_datetime(doy_str: str, time_str: str) -> datetime:
    """
    'YYYY-DDD' + 'HH:MM:SS.sss' 형식을 datetime으로 변환.

    C# 원본 (frmMain.cs getTimePosfromNavLine):
        new DateTime(year, 1, 1).AddDays(doy - 1) + time

    Args:
        doy_str: 'YYYY-DDD' (e.g., '2025-014')
        time_str: 'HH:MM:SS.sss' (e.g., '01:30:52.302')

    Returns:
        datetime 객체
    """
    parts = doy_str.split('-')
    year = int(parts[0])
    doy = int(parts[1])

    # 기준일: 1월 1일 + (doy - 1)일
    base_date = datetime(year, 1, 1) + timedelta(days=doy - 1)

    # 시간 파싱
    time_parts = time_str.split(':')
    hour = int(time_parts[0])
    minute = int(time_parts[1])

    sec_parts = time_parts[2].split('.')
    second = int(sec_parts[0])
    microsecond = 0
    if len(sec_parts) > 1:
        # 밀리초를 마이크로초로 변환
        ms_str = sec_parts[1].ljust(6, '0')[:6]
        microsecond = int(ms_str)

    return base_date.replace(
        hour=hour, minute=minute, second=second, microsecond=microsecond
    )


def kst_to_gmt(dt: datetime) -> datetime:
    """KST -> GMT (KST = GMT + 9h)"""
    return dt - timedelta(hours=KST_OFFSET_HOURS)


def gmt_to_kst(dt: datetime) -> datetime:
    """GMT -> KST (KST = GMT + 9h)"""
    return dt + timedelta(hours=KST_OFFSET_HOURS)


def format_tid_time(dt: datetime) -> str:
    """
    .tid 출력용 시간 포맷.
    'YYYY/MM/DD HH:MM:SS'
    """
    return dt.strftime('%Y/%m/%d %H:%M:%S')


def parse_tops_datetime(year: int, month: int, day: int,
                        hour: int, minute: int) -> datetime:
    """
    TOPS 조위 파일의 날짜/시간 파싱.
    'YYYY MM DD HH MM' 형식.
    """
    return datetime(year, month, day, hour, minute)
