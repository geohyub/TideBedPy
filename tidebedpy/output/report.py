"""
report.py - 검증 리포트

원본 .tid 파일과 생성된 .tid 파일을 비교하여 검증 리포트를 생성한다.
"""

import logging
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


def parse_tid_data(file_path: str) -> List[Tuple[str, float]]:
    """
    .tid 파일에서 데이터 줄만 추출한다.

    반환값의 Tc는 `.tid` 본문 단위 그대로 metres 이다.

    Returns:
        [(time_str, tc_m), ...] 리스트
    """
    data = []
    in_data = False

    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                if not in_data:
                    continue
                # 헤더 뒤 빈 줄 → 데이터 시작
                in_data = True
                continue

            # 데이터 줄 감지: YYYY/MM/DD HH:MM:SS  값  값
            if line[0].isdigit() and '/' in line:
                parts = line.split()
                if len(parts) >= 3:
                    time_str = parts[0] + ' ' + parts[1]
                    try:
                        tc = float(parts[2])
                        data.append((time_str, tc))
                    except ValueError:
                        continue
    return data


def parse_tid_data_cm(file_path: str) -> List[Tuple[str, float]]:
    """`.tid` 데이터를 읽어 Tc를 centimetres 로 변환한다."""
    return [(time_str, tc_m * 100.0) for time_str, tc_m in parse_tid_data(file_path)]


def validate_output(generated_path: str, reference_path: str,
                    tolerance: float = 0.01) -> dict:
    """
    생성된 .tid와 원본 .tid를 비교 검증한다.

    Args:
        generated_path: 생성된 .tid 파일 경로
        reference_path: 원본 .tid 파일 경로
        tolerance: 허용 오차 (meters, 기본 0.01)

    Returns:
        검증 결과 딕셔너리:
        {
            'total_generated': int,
            'total_reference': int,
            'matched': int,
            'within_tolerance': int,
            'exceeded_tolerance': int,
            'max_diff': float,
            'mean_diff': float,
            'mismatches': [(time_str, gen_val, ref_val, diff), ...]
        }
    """
    gen_data = parse_tid_data(generated_path)
    ref_data = parse_tid_data(reference_path)

    result = {
        'total_generated': len(gen_data),
        'total_reference': len(ref_data),
        'matched': 0,
        'within_tolerance': 0,
        'exceeded_tolerance': 0,
        'within_tolerance_pct': 0.0,
        'max_diff': 0.0,
        'mean_diff': 0.0,
        'mismatches': [],
    }

    # 시간 기반 매칭
    ref_dict = {t: v for t, v in ref_data}

    diffs = []
    for time_str, gen_val in gen_data:
        if time_str in ref_dict:
            ref_val = ref_dict[time_str]
            result['matched'] += 1

            diff = abs(gen_val - ref_val)
            diffs.append(diff)

            if diff <= tolerance:
                result['within_tolerance'] += 1
            else:
                result['exceeded_tolerance'] += 1
                result['mismatches'].append(
                    (time_str, gen_val, ref_val, diff)
                )

    if diffs:
        result['max_diff'] = max(diffs)
        result['mean_diff'] = sum(diffs) / len(diffs)
        result['within_tolerance_pct'] = result['within_tolerance'] / len(diffs) * 100.0
        result['mismatches'].sort(key=lambda item: item[3], reverse=True)

    return result


def print_validation_report(result: dict, tolerance: float = 0.01) -> None:
    """검증 결과를 출력한다."""
    print("\n" + "=" * 60)
    print("  TideBedPy 검증 리포트")
    print("=" * 60)
    print(f"  생성 레코드 수:   {result['total_generated']}")
    print(f"  참조 레코드 수:   {result['total_reference']}")
    print(f"  매칭 레코드 수:   {result['matched']}")
    print(f"  허용 범위 이내:   {result['within_tolerance']}")
    print(f"  허용 범위 초과:   {result['exceeded_tolerance']}")
    print(f"  허용 범위 이내 비율: {result.get('within_tolerance_pct', 0.0):.1f}%")
    print(f"  최대 차이:        {result['max_diff']:.4f} m")
    print(f"  평균 차이:        {result['mean_diff']:.4f} m")
    print(f"  허용 오차:        +/-{tolerance} m")

    if result['exceeded_tolerance'] == 0 and result['matched'] > 0:
        print(f"\n  [PASS] 매칭된 {result['matched']}개 값이 모두 +/-{tolerance}m 허용 오차 안에 있습니다.")
    elif result['exceeded_tolerance'] > 0:
        print(f"\n  [FAIL] {result['exceeded_tolerance']}개 값이 허용 오차를 초과했습니다.")
        print(f"\n  허용 오차 초과 항목 (최대 10개):")
        for time_str, gen_val, ref_val, diff in result['mismatches'][:10]:
            print(f"    {time_str}  생성={gen_val:.2f}  참조={ref_val:.2f}  차이={diff:.4f}")
    else:
        print(f"\n  [WARN] 매칭된 레코드를 찾지 못했습니다.")

    print("=" * 60 + "\n")
