# TideBedPy - TideBedLite Python Rewrite Project

## Background

TideBedLite는 국립해양조사원(KHOA)에서 배포한 .NET 2.0 WinForms 기반 조석보정 프로그램이다.
해양 수로측량 시 선박 항적(Nav)의 각 포인트에 대해, 주변 기준 조위관측소의 실측/예측 조위를 Co-tidal 격자와 IDW 가중평균으로 보간하여 조석보정값(Tc)을 산출한다.

이 프로그램은 ILSpy로 완전히 디컴파일되었으며, 핵심 알고리즘이 모두 파악된 상태이다.
이를 Python CLI 기반으로 재작성하여 더 유연하고 사용 편의성 높은 도구로 만든다.

## 디컴파일된 원본 소스 위치

```
C:\Users\JWONLINETEAM\Desktop\TideBed (2)\TideBedLite_ILSpy\
```

핵심 파일:
- `TideDataGen/frmMain.cs` - 메인 처리 로직 (getTideEstim, Calib4File, GetInfValueInstantly, getCoTidalValue, getTidalCorrections 등)
- `TideDataGen/clsRefSTInfo.cs` - 기준항 정보 로드/매칭
- `TideDataGen/clsRefStation.cs` - 기준항 데이터 구조
- `TideDataGen/Navigation.cs` - 항적 데이터 파싱
- `TideDataGen/StationInfoWithTimeCorrectors.cs` - 보정 구조체
- `TideDataGen/clsTTHeight.cs` - 조위 시계열
- `TideManipulation/TideMan.cs` - 조석 조작
- `TideManipulation/GKTime.cs` - KST/GMT 시간 처리
- `Gavaghan.Geodesy/` - Vincenty 거리 계산

## 데이터 파일 위치

```
C:\Users\JWONLINETEAM\Desktop\TideBed (2)\
├── info\
│   ├── 기준항정보\
│   │   ├── 기준항정보.txt          # 기준항 메타데이터 (EUC-KR, 탭 구분, 17필드)
│   │   ├── BaseControlPoint.txt   # 기준점 좌표
│   │   └── File_Catalog.txt       # 파일 카탈로그
│   ├── 표준개정수DB\
│   │   ├── CT\*.nc                # Co-tidal NetCDF 격자 (133개 섹터)
│   │   ├── File_Catalog.txt       # 섹터 → NC 파일 매핑 (15×16 격자)
│   │   └── 기준항정보.txt
│   ├── 실측조위\                   # 실측 조위 시계열 (TOPS 형식)
│   ├── 예측조위\                   # 예측 조위 시계열 (TOPS 형식, 55개소)
│   └── 해안선\                    # 해안선 shapefile
├── Sample\
│   ├── TideBed\
│   │   ├── Navi\After\            # 항적 파일 샘플 (Format 2)
│   │   └── 실측조위\              # 실측조위 파일 샘플 (EUC-KR)
│   ├── t.tid                      # 출력 검증용 정답 파일
│   ├── t.tid.detail               # 상세 출력
│   └── t.tid.err                  # 에러 로그
└── setting\
    └── TideBedLite.ini            # 설정 파일
```

## 핵심 알고리즘 (원본 C# 기반)

### 1. 데이터 구조

#### 기준항정보.txt (17필드, 탭 구분, EUC-KR)
```
사용여부  번호  이름  경도  위도  M2Amp  M2Phase  S2Amp  S2Phase  K1Amp  K1Phase  O1Amp  O1Phase  sprRange  sprRise  MSL  MHWI
TRUE      1     안흥  125.98  36.11  179.1  87.1     69.5   139.5    32.2   283.4    24.8   245.8    497.2     554.3   305.7  3.005
```

#### 실측/예측조위 파일 (TOPS 형식, EUC-KR)
```
<TOPS - 1시간 간격 실측조위자료>
                    (빈 줄)
대상조위관측소 : 안흥
위도(WGS84) : N  36도 40분 25초
경도(WGS84) : E 126도 07분 56초
관측기간 : 2025-01-14 00:00:00 ~ 2025-01-27 00:00:00
                    (빈 줄)
2025-01-14 00:00    316.3
2025-01-14 01:00    261.8
...
```

#### 항적 Nav 파일 (Format 2 샘플)
```
2025-014 01:30:52.302   36.83484990  126.10979540    0.00    0012F9A0
```
형식: `YYYY-DDD HH:mm:ss.sss  Lat  Lon  Depth  HexID`

#### Co-tidal NetCDF 섹터
- File_Catalog.txt로 격자 인덱스 → NC 파일 매핑
- 각 NC에는 SprRange, DL_MSL, MHWI 변수 (2×2 격자)
- 섹터 크기 0.5° × 0.5°

### 2. 처리 파이프라인

```
Nav 포인트 (X, Y, t)
    │
    ▼
[1] GetInfValueInstantly: 모든 기준항까지 Vincenty 거리 → IDW 가중치 (1/d²)
    │                      거리순 정렬
    ▼
[2] getCoTidalValue: NetCDF 격자에서 (X,Y) 위치의 SprRange, MSL, MHWI 이중선형 보간
    │
    ▼
[3] getTidalCorrections: 각 기준항에 대해
    │   - HRatio = SprRange_point / SprRange_station
    │   - TimeCorrector = MHWI_point - MHWI_station
    │   - correctedTime = obsTime (- 9h if GMT) - TimeCorrector
    │   - orgHeight = 기준항 실측조위에서 correctedTime에 해당하는 값 조회
    │   - EstimHeight = orgHeight × HRatio
    │   - 데이터 없으면 Weight = 0
    ▼
[4] IDW 가중평균: Tc = Σ(EstimHeight × Weight) / Σ(Weight)
    │             상위 RankLimit(=10)개만 사용
    ▼
출력: .tid 파일 (시간, Tc, StdDev)
```

### 3. 핵심 수식

```python
# Vincenty 거리 (WGS84)
distance = vincenty_inverse(lon1, lat1, lon2, lat2)  # meters

# IDW 가중치
weight[i] = (1 / distance[i]²) / sum(1 / distance[j]²)  # 전체 기준항 대상

# Co-tidal 이중선형 보간
V = V00 + (V10 - V00) * xDelta + ((V01 - V00) + (V11 - V01)) * yDelta

# 높이 비율
HRatio = sprRange_point / sprRange_station

# 시간 보정
TimeCorrector = MHWI_point - MHWI_station  # hours
correctedTime = obsTime_KST - TimeCorrector (hours)
# GMT 모드: correctedTime = obsTime_GMT + 9h - TimeCorrector

# 조위 조회: correctedTime에서 ±2분 이내의 실측조위 찾기

# 최종 보정값
EstimHeight = orgHeight × HRatio
Tc = sum(EstimHeight[i] * Weight[i]) / sum(Weight[i])  # 상위 10개
```

### 4. 출력 형식

#### .tid 파일
```
//// TideBed_DB_Generated
//// 임시기준항 지정 : FALSE
//// 시간 : KST (UTC+9)
//// Data Field and Type
//// Time(YYYY/MM/DD HH:MM:SS) : String
//// Tide Correction (meter) : Real
//// Standard Deviation : Real
//// Time Range
//// StartTime : 2025/01/14 01:30:52
//// EndTime   : 2025/01/27 23:57:17
2025/01/14 01:30:52	-0.05	0.0
2025/01/14 01:31:06	-0.05	0.0
...
```

## 개선 목표

### 현재 문제점
1. **인코딩 하드코딩**: EUC-KR만 지원, UTF-8 파일 입력 시 크래시
2. **입력 포맷 제한**: TOPS 헤더 필수, Nav 포맷 2종류만 지원
3. **에러 처리 부재**: -999로 조용히 실패, 원인 파악 불가
4. **GUI 의존**: 배치 처리 불가, 자동화 불가
5. **설정 유연성 부족**: ini 고정, 커맨드라인 파라미터 없음

### Python 버전 개선사항
1. **인코딩 자동 감지**: chardet 또는 패턴 기반 UTF-8/EUC-KR 자동 인식
2. **다양한 입력 포맷**: CSV, Excel, 탭 구분, 헤더 유무 자유, Nav 파일 형식 자동 감지
3. **명확한 에러/경고 메시지**: logging 기반, 어떤 기준항이 왜 빠졌는지 상세 보고
4. **CLI 기반**: argparse로 파라미터 입력, 배치 처리 가능
5. **검증 모드**: 원본 .tid와 비교 검증 기능 내장
6. **모듈화**: 코어 알고리즘, IO, 설정을 분리하여 재사용 가능

### 프로젝트 구조 (제안)
```
tidebedpy/
├── main.py              # CLI 진입점
├── config.py            # 설정 관리 (INI, CLI args)
├── io/
│   ├── station.py       # 기준항정보 로드
│   ├── tide_series.py   # 조위 시계열 로드 (TOPS + CSV + 자동감지)
│   ├── navigation.py    # 항적 파일 로드 (다중 포맷)
│   └── cotidal.py       # Co-tidal NetCDF 격자 로드
├── core/
│   ├── geodesy.py       # Vincenty 거리 계산
│   ├── interpolation.py # IDW + 이중선형 보간
│   └── tide_correction.py  # 핵심 조석보정 알고리즘
├── output/
│   ├── tid_writer.py    # .tid 출력
│   └── report.py        # 상세 보고서
└── utils/
    ├── encoding.py      # 인코딩 자동 감지
    └── time_utils.py    # KST/GMT 변환
```

## 검증 방법

1. Sample 데이터로 원본 프로그램과 동일한 입력 사용
2. 출력 `t.tid`를 원본과 라인별 비교
3. 허용 오차: ±0.01m (반올림 차이)

## 참고사항

- geopy 라이브러리의 vincenty는 deprecated → geographiclib 사용 권장
- NetCDF 읽기: netCDF4 또는 scipy.io.netcdf
- 기준항정보.txt의 sprRange, MSL, MHWI는 조화상수에서 계산된 값이 아닌 별도 필드로 제공됨
- `findLevelValue`는 시계열에서 가장 가까운 시간의 값을 반환 (±2분 이내)
- TimeIntervalSec=0이면 모든 Nav 포인트 사용, >0이면 해당 간격으로 데시메이션
