# TideBedPy

> 조석보정 프로그램 - KHOA TideBedLite의 Python 재구현

해양 수로측량 Nav 데이터에 대해 Co-tidal 격자 기반 IDW 가중평균으로 조석보정값(Tc)을 산출하는 프로그램.
GUI(Tkinter)와 CLI 두 가지 모드를 지원한다.

**원본**: TideBedLite v1.05, Copyright (c) 2014, KHOA / GeoSR Inc.
**버전**: v2.3.0

## 기술 스택

| 구분 | 기술 |
|------|------|
| 언어 | Python 3.10+ |
| GUI | Tkinter (Pretendard 폰트 번들) |
| 핵심 연산 | NumPy, SciPy (IDW 보간, 측지 계산) |
| 조위 데이터 | KHOA API (data.go.kr), 바다누리 CSV, TOPS 형식 |
| 글로벌 조석 | pyTMD (FES2014, TPXO9 - 해외 해역용) |
| 좌표 변환 | geographiclib |
| NetCDF | netCDF4 (Co-tidal 격자 데이터) |
| 빌드 | PyInstaller |

## 설치

```bash
cd tidebedpy
pip install -r requirements.txt
```

### requirements.txt
```
geographiclib>=2.0
netCDF4>=1.6.0
numpy>=1.24.0
scipy>=1.10.0
chardet>=5.0.0
```

## 실행

### GUI 모드
```bash
cd tidebedpy
python gui.py
```
또는 배치 파일 실행:
```bash
run_gui.bat
```

### CLI 모드
```bash
# 최소 인자 (DB/기준항정보는 자동 탐색)
python tidebedpy/main.py --nav Navi/After --tide 실측조위 -o result.tid

# INI 파일로 실행
python tidebedpy/main.py --ini setting/TideBedLite.ini -o result.tid

# 검증 모드 (기존 결과와 비교)
python tidebedpy/main.py --nav Navi/After --tide 실측조위 -o result.tid --validate ref.tid
```

## 주요 기능

### 조석보정 엔진
- **Co-tidal IDW 보간**: 표준개정수 DB 기반 조석 매개변수 보간
- **다중 기준항 가중평균**: Nav 포인트별 인근 조위관측소 자동 선택
- **UTC 오프셋 지원**: 시간대 보정 자동 처리
- **배치 처리 최적화**: 벡터화 연산, LRU 캐싱

### 데이터 입출력
- **항적 데이터**: Nav 디렉토리 자동 로딩
- **조위 시계열**: 실측/예측 조위 폴더 로딩, 연도 자동 보정
- **KHOA API**: 공공데이터포털 실측/예측 조위 자동 다운로드 (37개 관측소)
- **바다누리 CSV**: CSV → TOPS 형식 자동 변환
- **글로벌 모델**: pyTMD 연동 (FES2014/TPXO9, 해외 해역)

### 출력
- `.tid` 파일: 조석보정 결과
- 상세 로그: 기준항별 보정값, 에러 코드
- 검증 리포트: 기존 결과 파일과 비교 분석

### GUI (v2.3.0)
- 해양 테마 UI (Pretendard 폰트)
- 프로젝트 경로 자동 탐색
- 허용편차 설정
- 사용 기준항 정확 식별
- 실시간 처리 로그

## 디렉토리 구조

```
TideBedPy/
├── tidebedpy/               ← 메인 패키지
│   ├── main.py              CLI 엔트리
│   ├── gui.py               GUI 엔트리 (Tkinter)
│   ├── config.py            설정 관리 (INI 파싱 + 자동 경로 탐색)
│   ├── settings_manager.py  설정 저장/로드
│   ├── core/                ← 핵심 알고리즘
│   │   ├── tide_correction.py  조석보정 엔진
│   │   ├── interpolation.py    IDW 가중평균 (벡터화)
│   │   ├── geodesy.py          측지 계산
│   │   └── error_codes.py      에러 코드 정의
│   ├── data_io/             ← 데이터 입출력
│   │   ├── navigation.py       Nav 데이터 로더
│   │   ├── tide_series.py      조위 시계열 로더
│   │   ├── station.py          기준항 정보 로더
│   │   ├── cotidal.py          Co-tidal 격자 로더
│   │   ├── khoa_api.py         KHOA API 다운로더
│   │   ├── csv_to_tops.py      바다누리 CSV 변환
│   │   └── global_tide.py      pyTMD 글로벌 조석 모델
│   ├── utils/               ← 유틸리티
│   ├── fonts/               ← Pretendard 폰트 번들
│   └── requirements.txt
├── tests/                   ← 테스트
└── dist/                    ← PyInstaller 빌드 결과
```

## 라이선스

Proprietary - Geoview Co., Ltd.
