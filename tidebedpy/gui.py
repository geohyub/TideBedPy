"""
TideBedPy - 조석보정 프로그램

KHOA TideBedLite의 Python 재구현.
tkinter 기반 GUI로 사용자 친화적 조석보정 처리를 제공한다.

v2.3.0: 허용편차 설정 / 사용기준항 정확식별 / 프로그램명 정리

Original: TideBedLite v1.05, Copyright (c) 2014, KHOA / GeoSR Inc.
Python:   Junhyub, 2025
"""

import sys
import os
import time
import threading
import logging
from datetime import datetime
from tkinter import (
    Tk, Frame, Label, Entry, Button, Text, Scrollbar, Canvas, Checkbutton,
    StringVar, IntVar, BooleanVar, DoubleVar,
    filedialog, messagebox, ttk, Toplevel, Listbox,
    END, NORMAL, DISABLED, WORD, BOTH, LEFT, RIGHT, TOP, BOTTOM,
    X, Y, W, E, N, S, NW, NE, SW, SE, HORIZONTAL, VERTICAL,
    PhotoImage
)

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import TideBedConfig, _find_project_root

logger = logging.getLogger(__name__)

# ============================================================
#  디자인 상수
# ============================================================
APP_TITLE = "TideBedPy"
APP_VERSION = "2.3.0"
APP_SUBTITLE = "조석보정 프로그램"
APP_AUTHOR = "Junhyub"
APP_COPYRIGHT = "Original: TideBedLite v1.05 \u00a9 2014 KHOA / GeoSR"
WINDOW_MIN_W = 860
WINDOW_MIN_H = 800

# 색상 팔레트 — 해양/전문 테마
C_PRIMARY     = '#1a5276'
C_PRIMARY_LT  = '#2471a3'
C_PRIMARY_XLT = '#d4e6f1'
C_ACCENT      = '#148f77'
C_ACCENT_HV   = '#117a65'
C_BG          = '#f5f6fa'
C_CARD        = '#ffffff'
C_BORDER      = '#dce1e8'
C_TEXT        = '#2c3e50'
C_TEXT_SEC    = '#7f8c8d'
C_SUCCESS     = '#27ae60'
C_WARNING     = '#f39c12'
C_ERROR       = '#e74c3c'
C_LOG_BG      = '#1b2631'
C_LOG_FG      = '#d5d8dc'

# 폰트 — Pretendard 우선 (번들 OTF 자동 등록)
def _init_font():
    """Pretendard 번들 폰트를 시스템에 등록하고 폰트명 반환."""
    try:
        from utils.font_utils import register_pretendard_system, get_tkinter_font_family
        register_pretendard_system()
        return get_tkinter_font_family()
    except Exception:
        return '맑은 고딕'

_FONT_FAMILY = _init_font()

F_TITLE       = (_FONT_FAMILY, 15, 'bold')
F_SUBTITLE    = (_FONT_FAMILY, 10)
F_SECTION     = (_FONT_FAMILY, 10, 'bold')
F_LABEL       = (_FONT_FAMILY, 9)
F_LABEL_S     = (_FONT_FAMILY, 8)
F_ENTRY       = (_FONT_FAMILY, 9)
F_BTN         = (_FONT_FAMILY, 10, 'bold')
F_BTN_S       = (_FONT_FAMILY, 9)
F_LOG         = (_FONT_FAMILY, 9)
F_STATUS      = (_FONT_FAMILY, 9)
F_HINT        = (_FONT_FAMILY, 8)

PAD = 10

# 시간대 옵션
TIMEZONE_OPTIONS = [
    'GMT (UTC+0)',
    'KST (UTC+9)',
    'JST (UTC+9)',
    'CST (UTC+8)',
    'UTC+1', 'UTC+2', 'UTC+3', 'UTC+4', 'UTC+5',
    'UTC+6', 'UTC+7', 'UTC+8', 'UTC+9', 'UTC+10',
    'UTC+11', 'UTC+12',
    'UTC-1', 'UTC-2', 'UTC-3', 'UTC-4', 'UTC-5',
    'UTC-6', 'UTC-7', 'UTC-8', 'UTC-9', 'UTC-10',
    'UTC-11', 'UTC-12',
]

def _parse_timezone_offset(tz_str: str) -> float:
    """시간대 문자열에서 UTC 오프셋 추출."""
    tz_str = tz_str.strip()
    if tz_str.startswith('GMT') or tz_str == 'UTC+0':
        return 0.0
    if tz_str.startswith('KST') or tz_str.startswith('JST'):
        return 9.0
    if tz_str.startswith('CST'):
        return 8.0
    # UTC+N / UTC-N
    if 'UTC' in tz_str:
        try:
            part = tz_str.split('UTC')[1].strip().rstrip(')')
            if part.startswith('+'):
                return float(part[1:])
            elif part.startswith('-'):
                return -float(part[1:])
            else:
                return float(part)
        except:
            pass
    return 0.0


# ============================================================
#  관측소 선택 미리보기 다이얼로그
# ============================================================
class StationSelectDialog:
    """API 수집 전 관측소를 지도에서 선택하는 모달 다이얼로그."""

    def __init__(self, parent, nearby_stations, nav_points):
        self.result = None
        self._nearby = nearby_stations
        self._nav = nav_points
        self._check_vars = []
        self._scatter_objs = []
        self._label_objs = []
        self._fig = None
        self._ax = None
        self._canvas_tk = None

        self.dlg = Toplevel(parent)
        self.dlg.title('API 관측소 선택')
        self.dlg.geometry('900x600')
        self.dlg.resizable(True, True)
        self.dlg.transient(parent)
        self.dlg.grab_set()

        self.dlg.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 900) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 600) // 2
        self.dlg.geometry(f'+{max(0,x)}+{max(0,y)}')

        main = Frame(self.dlg, bg=C_BG)
        main.pack(fill=BOTH, expand=True, padx=8, pady=8)

        self._map_frame = Frame(main, bg=C_BG)
        self._map_frame.pack(side=LEFT, fill=BOTH, expand=True)

        right = Frame(main, bg=C_BG, width=280)
        right.pack(side=RIGHT, fill=Y, padx=(8, 0))
        right.pack_propagate(False)

        Label(right, text='관측소 선택', font=(_FONT_FAMILY, 11, 'bold'),
              bg=C_BG, fg=C_TEXT).pack(anchor=W, pady=(0, 4))
        Label(right, text='체크된 관측소에서 조위를 수집합니다',
              font=F_HINT, bg=C_BG, fg='#888').pack(anchor=W, pady=(0, 8))

        btn_row = Frame(right, bg=C_BG)
        btn_row.pack(fill=X, pady=(0, 4))
        Button(btn_row, text='전체선택', font=F_LABEL_S, relief='groove',
               command=lambda: self._set_all(True), cursor='hand2',
               padx=8, pady=1).pack(side=LEFT, padx=(0, 4))
        Button(btn_row, text='전체해제', font=F_LABEL_S, relief='groove',
               command=lambda: self._set_all(False), cursor='hand2',
               padx=8, pady=1).pack(side=LEFT)

        list_frame = Frame(right, bg='white', bd=1, relief='sunken')
        list_frame.pack(fill=BOTH, expand=True, pady=(0, 8))

        canvas = Canvas(list_frame, bg='white', highlightthickness=0)
        scrollbar = Scrollbar(list_frame, orient=VERTICAL, command=canvas.yview)
        self._inner = Frame(canvas, bg='white')
        self._inner.bind('<Configure>',
                         lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=self._inner, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        for code, name, dist in self._nearby:
            var = BooleanVar(value=(dist <= 100))
            self._check_vars.append(var)
            cb = Checkbutton(
                self._inner, text=f'{name}  ({dist:.0f}km)',
                variable=var, font=(_FONT_FAMILY, 9),
                bg='white', activebackground='white',
                anchor=W, command=self._update_markers)
            cb.pack(fill=X, padx=4, pady=1)

        bottom = Frame(right, bg=C_BG)
        bottom.pack(fill=X)
        Button(bottom, text='수집 시작', font=(_FONT_FAMILY, 10, 'bold'),
               bg=C_ACCENT, fg='white', relief='flat', cursor='hand2',
               padx=20, pady=4, command=self._on_ok).pack(side=LEFT, padx=(0, 8))
        Button(bottom, text='취소', font=(_FONT_FAMILY, 10),
               relief='groove', cursor='hand2',
               padx=20, pady=4, command=self._on_cancel).pack(side=LEFT)

        self._draw_map_initial()
        self.dlg.protocol('WM_DELETE_WINDOW', self._on_cancel)
        self.dlg.wait_window()

    def _set_all(self, val):
        for v in self._check_vars:
            v.set(val)
        self._update_markers()

    def _on_ok(self):
        selected = [(c, n, d) for i, (c, n, d) in enumerate(self._nearby)
                     if self._check_vars[i].get()]
        if not selected:
            from tkinter import messagebox
            messagebox.showwarning('선택 없음', '최소 1개 관측소를 선택하세요.', parent=self.dlg)
            return
        self.result = selected
        self.dlg.destroy()

    def _on_cancel(self):
        self.result = None
        self.dlg.destroy()

    def _draw_map_initial(self):
        """지도 초기 렌더링 (해안선+Track 1회, 마커는 참조 저장)."""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            import numpy as np
        except ImportError:
            Label(self._map_frame, text='matplotlib 필요', font=F_LABEL, bg=C_BG).pack()
            return

        try:
            from output.map_view import _find_coastline_shp, _read_shp_polygons, _init_fonts
            _init_fonts()
        except ImportError:
            pass

        from data_io.khoa_api import STATION_COORDS

        fig, ax = plt.subplots(figsize=(6, 5), dpi=100)
        fig.patch.set_facecolor('white')
        ax.set_facecolor('#E8F1F8')
        self._fig = fig
        self._ax = ax

        nav_lons = [p.x for p in self._nav]
        nav_lats = [p.y for p in self._nav]
        all_lons, all_lats = list(nav_lons), list(nav_lats)
        for code, name, dist in self._nearby:
            coord = STATION_COORDS.get(code)
            if coord:
                all_lats.append(coord[0])
                all_lons.append(coord[1])

        lon_min, lon_max = min(all_lons), max(all_lons)
        lat_min, lat_max = min(all_lats), max(all_lats)
        lon_pad = max((lon_max - lon_min) * 0.15, 0.2)
        lat_pad = max((lat_max - lat_min) * 0.15, 0.2)
        bbox = (lon_min - lon_pad, lat_min - lat_pad,
                lon_max + lon_pad, lat_max + lat_pad)

        # 해안선 (1회)
        try:
            shp = _find_coastline_shp()
            if shp:
                polys = _read_shp_polygons(shp, clip_bbox=bbox)
                for ring in polys:
                    xs = [p[0] for p in ring]
                    ys = [p[1] for p in ring]
                    ax.fill(xs, ys, color='#F5F0E8', edgecolor='#C8B89A',
                            linewidth=0.6, zorder=1, alpha=0.95)
        except Exception:
            pass

        ax.set_xlim(bbox[0], bbox[2])
        ax.set_ylim(bbox[1], bbox[3])
        mid_lat = (bbox[1] + bbox[3]) / 2
        ax.set_aspect(1.0 / np.cos(np.radians(mid_lat)))

        # Track (1회, 다운샘플링)
        step = max(1, len(nav_lons) // 500)
        ax.plot(nav_lons[::step], nav_lats[::step], color='#1565C0',
                linewidth=0.8, alpha=0.5, zorder=5, linestyle='--')

        # 관측소 마커 (참조 저장 → 빠른 업데이트)
        self._scatter_objs = []
        self._label_objs = []
        for i, (code, name, dist) in enumerate(self._nearby):
            coord = STATION_COORDS.get(code)
            if not coord:
                self._scatter_objs.append(None)
                self._label_objs.append(None)
                continue
            lat, lon = coord
            checked = self._check_vars[i].get()
            color = '#D32F2F' if checked else '#B0BEC5'
            edge = 'white' if checked else '#78909C'
            size = 120 if checked else 50

            sc = ax.scatter(lon, lat, color=color, s=size, marker='^',
                           edgecolors=edge, linewidths=1.0,
                           alpha=1.0 if checked else 0.5, zorder=8)
            self._scatter_objs.append(sc)

            lbl = ax.annotate(f'{name}\n{dist:.0f}km', (lon, lat),
                             fontsize=7.5 if checked else 6.5,
                             fontweight='bold' if checked else 'normal',
                             color='#D32F2F' if checked else '#888',
                             ha='center', va='bottom',
                             xytext=(0, 8), textcoords='offset points', zorder=9)
            self._label_objs.append(lbl)

        ax.grid(True, alpha=0.3, color='#D4E4F0')
        ax.tick_params(labelsize=7, colors='#666')
        fig.tight_layout(pad=1.0)

        self._canvas_tk = FigureCanvasTkAgg(fig, master=self._map_frame)
        self._canvas_tk.draw()
        self._canvas_tk.get_tk_widget().pack(fill=BOTH, expand=True)

    def _update_markers(self):
        """체크 변경 시 마커 색상/크기만 업데이트 (전체 다시 그리지 않음)."""
        if not self._fig or not self._scatter_objs:
            return
        import numpy as np

        for i in range(len(self._nearby)):
            sc = self._scatter_objs[i]
            lbl = self._label_objs[i]
            if sc is None:
                continue

            checked = self._check_vars[i].get()
            sc.set_facecolors('#D32F2F' if checked else '#B0BEC5')
            sc.set_edgecolors('white' if checked else '#78909C')
            sc.set_sizes(np.array([120 if checked else 50]))
            sc.set_alpha(1.0 if checked else 0.5)

            if lbl:
                lbl.set_color('#D32F2F' if checked else '#888')
                lbl.set_fontweight('bold' if checked else 'normal')
                lbl.set_fontsize(7.5 if checked else 6.5)

        self._canvas_tk.draw_idle()


# ============================================================
#  유틸: 카드 프레임
# ============================================================
class CardFrame(Frame):
    """그림자 + 테두리가 있는 카드 스타일 프레임."""
    def __init__(self, parent, title='', **kw):
        super().__init__(parent, bg=C_BG, **kw)

        if title:
            hdr = Frame(self, bg=C_BG)
            hdr.pack(fill=X, padx=2, pady=(0, 3))
            bar = Frame(hdr, bg=C_PRIMARY, width=4, height=16)
            bar.pack(side=LEFT, padx=(0, 6))
            bar.pack_propagate(False)
            Label(hdr, text=title, font=F_SECTION, fg=C_PRIMARY,
                  bg=C_BG).pack(side=LEFT)

        self.body = Frame(self, bg=C_CARD, relief='solid',
                          bd=1, highlightthickness=0)
        self.body.pack(fill=X, expand=False)
        self.inner = Frame(self.body, bg=C_CARD)
        self.inner.pack(fill=X, padx=12, pady=8)


# ============================================================
#  메인 GUI 클래스
# ============================================================
class TideBedGUI:
    """TideBedPy GUI 애플리케이션."""

    def __init__(self, root: Tk):
        self.root = root
        self.root.title(f"{APP_TITLE} - {APP_SUBTITLE}")
        self.root.minsize(WINDOW_MIN_W, WINDOW_MIN_H)
        self.root.configure(bg=C_BG)

        # 화면 중앙 배치
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - WINDOW_MIN_W) // 2
        y = (sh - WINDOW_MIN_H) // 2 - 30
        self.root.geometry(f'{WINDOW_MIN_W}x{WINDOW_MIN_H}+{x}+{y}')

        # ── 변수 ──
        self.nav_path = StringVar()
        self.tide_path = StringVar()
        self.output_path = StringVar()
        self.db_path = StringVar()
        self.station_path = StringVar()
        self.validate_path = StringVar()
        self.tide_type = StringVar(value='실측')
        self.rank_limit = IntVar(value=10)
        self.time_interval = IntVar(value=0)
        self.timezone = StringVar(value='GMT (UTC+0)')
        self.write_detail = BooleanVar(value=True)
        self.do_validate = BooleanVar(value=False)
        self.generate_graph = BooleanVar(value=True)
        self.tolerance_cm = DoubleVar(value=1.0)
        self.use_api = BooleanVar(value=False)
        self.api_key = StringVar()

        # ── 상태 ──
        self.is_running = False
        self._stop_requested = False

        # ── 경로 자동 탐색 ──
        self._auto_discover_paths()

        # ── UI 구성 ──
        self._apply_theme()
        self._build_titlebar()
        self._build_body()

    # ============================================================
    #  테마
    # ============================================================
    def _apply_theme(self):
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except:
            pass

        style.configure('TCombobox', font=F_ENTRY, padding=3)
        style.map('TCombobox',
                  fieldbackground=[('readonly', 'white')],
                  selectbackground=[('readonly', C_PRIMARY_XLT)])
        style.configure('TEntry', font=F_ENTRY, padding=3)
        style.configure('TCheckbutton', font=F_LABEL, background=C_CARD)
        style.configure('Marine.Horizontal.TProgressbar',
                        troughcolor=C_BORDER, background=C_ACCENT,
                        thickness=18)
        style.configure('Card.TSeparator', background=C_BORDER)

    # ============================================================
    #  타이틀바
    # ============================================================
    def _build_titlebar(self):
        bar = Frame(self.root, bg=C_PRIMARY, height=56)
        bar.pack(fill=X)
        bar.pack_propagate(False)

        inner = Frame(bar, bg=C_PRIMARY)
        inner.pack(fill=BOTH, expand=True, padx=16)

        left = Frame(inner, bg=C_PRIMARY)
        left.pack(side=LEFT, fill=Y)

        Label(left, text=f"\u2693  {APP_TITLE}",
              font=F_TITLE, fg='white', bg=C_PRIMARY).pack(side=LEFT)
        Label(left, text=f"  {APP_SUBTITLE}",
              font=F_SUBTITLE, fg='#aed6f1', bg=C_PRIMARY).pack(side=LEFT, pady=(3, 0))

        right = Frame(inner, bg=C_PRIMARY)
        right.pack(side=RIGHT, fill=Y)
        Label(right, text=f"v{APP_VERSION}",
              font=F_LABEL_S, fg='#85c1e9', bg=C_PRIMARY).pack(side=TOP, anchor=E)
        Label(right, text=f"by {APP_AUTHOR}  |  {APP_COPYRIGHT}",
              font=(_FONT_FAMILY, 7), fg='#7fb3d8', bg=C_PRIMARY).pack(side=TOP, anchor=E)

    # ============================================================
    #  메인 바디
    # ============================================================
    def _build_body(self):
        container = Frame(self.root, bg=C_BG)
        container.pack(fill=BOTH, expand=True, padx=14, pady=(10, 8))

        self._build_input_section(container)
        self._build_db_section(container)
        self._build_options_section(container)
        self._build_control_section(container)
        self._build_log_section(container)

        # 처리 중 잠글 위젯 수집 (Entry, Combobox, Checkbutton)
        self._lockable_widgets = []
        for w in container.winfo_children():
            self._collect_lockable(w)

    def _collect_lockable(self, widget):
        """재귀적으로 Entry, Combobox, Checkbutton 위젯을 수집."""
        cls = widget.winfo_class()
        if cls in ('Entry', 'TEntry', 'TCombobox', 'Checkbutton', 'TCheckbutton'):
            self._lockable_widgets.append(widget)
        for child in widget.winfo_children():
            self._collect_lockable(child)

    # ────────────────────────────────────────────
    #  섹션 1: 입력 파일 설정
    # ────────────────────────────────────────────
    def _build_input_section(self, parent):
        card = CardFrame(parent, title='입력 파일 설정')
        card.pack(fill=X, pady=(0, 8))

        self._path_row(card.inner, '항적 파일 폴더', self.nav_path,
                       self._browse_nav, hint='Nav 데이터 폴더 (Before/After 모두 지원)',
                       is_folder=True)
        self._separator(card.inner)
        self._tide_row = self._path_row(card.inner, '조위 시계열 폴더', self.tide_path,
                       self._browse_tide, hint='실측/예측 조위 파일 폴더 (TOPS/CSV 등)',
                       is_folder=True)

        # API 자동 수집 옵션
        api_frame = Frame(card.inner, bg=card.inner['bg'])
        api_frame.pack(fill=X, padx=16, pady=(2, 0))
        self._api_check = Checkbutton(
            api_frame, text='API 자동 수집 (항적 시간/좌표 기반 자동 다운로드)',
            variable=self.use_api, font=F_HINT,
            bg=card.inner['bg'], activebackground=card.inner['bg'],
            command=self._toggle_api_row)
        self._api_check.pack(side=LEFT)

        # API 안내 라벨
        self._api_info = Label(card.inner,
            text='  ℹ  조위 폴더 대신 항적의 시간/좌표에서 자동으로 관측소를 선택하고 API로 수집합니다',
            font=F_HINT, fg=C_PRIMARY, bg='#eaf4fb', pady=3, padx=6, anchor=W)
        # 기본 숨김

        self._api_row = Frame(card.inner, bg=card.inner['bg'])
        Label(self._api_row, text='API 키', font=F_LABEL, width=14,
              anchor='e', bg=self._api_row['bg']).pack(side=LEFT, padx=(0, 4))
        self._api_entry = Entry(self._api_row, textvariable=self.api_key,
                                font=F_ENTRY, show='*')
        self._api_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        # 기본 숨김

        self._separator(card.inner)
        self._path_row(card.inner, '출력 TID 파일', self.output_path,
                       self._browse_output, hint='조석보정 결과 (.tid) 저장 경로',
                       is_save=True)

    # ────────────────────────────────────────────
    #  섹션 2: 데이터베이스 설정
    # ────────────────────────────────────────────
    def _build_db_section(self, parent):
        card = CardFrame(parent, title='개정수 DB 설정')
        card.pack(fill=X, pady=(0, 8))

        if self.db_path.get() or self.station_path.get():
            hint_frame = Frame(card.inner, bg='#eafaf1')
            hint_frame.pack(fill=X, pady=(0, 6))
            Label(hint_frame, text='  \u2713  자동 탐색 완료 \u2014 경로가 올바른지 확인하세요',
                  font=F_HINT, fg=C_SUCCESS, bg='#eafaf1',
                  pady=3, padx=6).pack(fill=X)

        self._path_row(card.inner, '표준개정수 DB', self.db_path,
                       self._browse_db, hint='File_Catalog.txt + CT/ 폴더가 있는 디렉토리',
                       is_folder=True)
        self._separator(card.inner)
        self._path_row(card.inner, '기준항 정보', self.station_path,
                       self._browse_station, hint='기준항정보.txt 파일')

    # ────────────────────────────────────────────
    #  섹션 3: 보정 옵션
    # ────────────────────────────────────────────
    def _build_options_section(self, parent):
        card = CardFrame(parent, title='보정 옵션')
        card.pack(fill=X, pady=(0, 8))

        # ── 행1: 조위 유형, 기준항 적용 개수, 기준 시간 ──
        row1 = Frame(card.inner, bg=C_CARD)
        row1.pack(fill=X, pady=(0, 6))

        grp1 = self._option_group(row1, '조위 시계열 유형')
        grp1.pack(side=LEFT, padx=(0, 20))
        ttk.Combobox(grp1, textvariable=self.tide_type,
                     values=['실측', '예측'], width=8, state='readonly',
                     font=F_ENTRY).pack(side=LEFT)

        self._rank_grp = self._option_group(row1, '기준항 적용 개수')
        self._rank_grp.pack(side=LEFT, padx=(0, 20))
        self._rank_combo = ttk.Combobox(
            self._rank_grp, textvariable=self.rank_limit,
            values=list(range(1, 11)), width=5, state='readonly',
            font=F_ENTRY)
        self._rank_combo.pack(side=LEFT)
        Label(self._rank_grp, text='항', font=F_HINT, fg=C_TEXT_SEC,
              bg=C_CARD).pack(side=LEFT, padx=(3, 0))

        # 시간대 (유연한 UTC 오프셋)
        grp3 = self._option_group(row1, '기준 시간대')
        grp3.pack(side=LEFT, padx=(0, 0))
        cb_tz = ttk.Combobox(grp3, textvariable=self.timezone,
                              values=TIMEZONE_OPTIONS, width=14, state='readonly',
                              font=F_ENTRY)
        cb_tz.pack(side=LEFT)

        # ── 행2: 출력 시간 간격, 상세출력, 그래프, 검증 ──
        row2 = Frame(card.inner, bg=C_CARD)
        row2.pack(fill=X, pady=(0, 2))

        grp4 = self._option_group(row2, '출력 시간 간격')
        grp4.pack(side=LEFT, padx=(0, 10))
        ttk.Entry(grp4, textvariable=self.time_interval,
                  width=7, font=F_ENTRY).pack(side=LEFT)
        Label(grp4, text='초 (0=전체)', font=F_HINT, fg=C_TEXT_SEC,
              bg=C_CARD).pack(side=LEFT, padx=(4, 0))

        ttk.Checkbutton(row2, text='상세출력', variable=self.write_detail,
                        style='TCheckbutton').pack(side=LEFT, padx=(10, 6))

        ttk.Checkbutton(row2, text='그래프', variable=self.generate_graph,
                        style='TCheckbutton').pack(side=LEFT, padx=(0, 6))

        # 허용 편차
        grp_tol = self._option_group(row2, '허용 편차')
        grp_tol.pack(side=LEFT, padx=(6, 10))
        ttk.Entry(grp_tol, textvariable=self.tolerance_cm,
                  width=5, font=F_ENTRY).pack(side=LEFT)
        Label(grp_tol, text='cm', font=F_HINT, fg=C_TEXT_SEC,
              bg=C_CARD).pack(side=LEFT, padx=(3, 0))

        # 검증
        chk_validate = ttk.Checkbutton(row2, text='검증:',
                                        variable=self.do_validate,
                                        command=self._toggle_validate,
                                        style='TCheckbutton')
        chk_validate.pack(side=LEFT, padx=(6, 4))

        self.validate_entry = ttk.Entry(row2, textvariable=self.validate_path,
                                         width=22, font=F_ENTRY, state=DISABLED)
        self.validate_entry.pack(side=LEFT, padx=(0, 3), fill=X, expand=True)

        self.validate_btn = Button(row2, text='...', command=self._browse_validate,
                                    state=DISABLED, font=F_HINT, width=3,
                                    relief='groove', cursor='hand2')
        self.validate_btn.pack(side=LEFT)

    # ────────────────────────────────────────────
    #  섹션 4: 진행률 + 제어 버튼
    # ────────────────────────────────────────────
    def _build_control_section(self, parent):
        ctrl = Frame(parent, bg=C_BG)
        ctrl.pack(fill=X, pady=(0, 6))

        prog_frame = Frame(ctrl, bg=C_BG)
        prog_frame.pack(fill=X, pady=(0, 6))

        self.progress_var = DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            prog_frame, variable=self.progress_var, maximum=100,
            mode='determinate', style='Marine.Horizontal.TProgressbar'
        )
        self.progress_bar.pack(fill=X, ipady=1)

        self.status_var = StringVar(value='대기 중')
        self.status_label = Label(prog_frame, textvariable=self.status_var,
                                   font=F_STATUS, fg=C_TEXT_SEC, bg=C_BG, anchor=W)
        self.status_label.pack(fill=X, pady=(3, 0))

        btn_frame = Frame(ctrl, bg=C_BG)
        btn_frame.pack(fill=X)

        # 보정 수행
        self.run_btn = Button(
            btn_frame, text='  \u25b6  보정 수행  ', command=self._run,
            font=F_BTN, bg=C_ACCENT, fg='white',
            activebackground=C_ACCENT_HV, activeforeground='white',
            relief='flat', padx=24, pady=7, cursor='hand2', bd=0
        )
        self.run_btn.pack(side=LEFT, padx=(0, 8))
        self.run_btn.bind('<Enter>', lambda e: self.run_btn.config(bg=C_ACCENT_HV))
        self.run_btn.bind('<Leave>', lambda e: self.run_btn.config(bg=C_ACCENT))

        # 중지
        self.stop_btn = Button(
            btn_frame, text='  \u25a0  중지  ', command=self._stop,
            font=F_BTN_S, state=DISABLED, padx=14, pady=5,
            relief='groove', cursor='hand2'
        )
        self.stop_btn.pack(side=LEFT, padx=(0, 12))

        Frame(btn_frame, bg=C_BORDER, width=1, height=28).pack(side=LEFT, padx=(0, 12))

        # INI 불러오기
        Button(btn_frame, text='INI 불러오기', command=self._load_ini,
               font=F_BTN_S, padx=8, pady=5, relief='groove',
               cursor='hand2').pack(side=LEFT, padx=(0, 6))

        # 세팅 저장
        Button(btn_frame, text='세팅 저장', command=self._save_preset,
               font=F_BTN_S, padx=8, pady=5, relief='groove',
               cursor='hand2', fg='#1a5276').pack(side=LEFT, padx=(0, 6))

        # 세팅 불러오기
        Button(btn_frame, text='세팅 불러오기', command=self._load_preset,
               font=F_BTN_S, padx=8, pady=5, relief='groove',
               cursor='hand2', fg='#1a5276').pack(side=LEFT, padx=(0, 6))

        # 초기화
        Button(btn_frame, text='초기화', command=self._reset,
               font=F_BTN_S, padx=8, pady=5, relief='groove',
               cursor='hand2').pack(side=LEFT, padx=(0, 0))

        # ── 도구 버튼 (2열) ──
        tool_frame = Frame(ctrl, bg=C_BG)
        tool_frame.pack(fill=X, pady=(6, 0))

        Label(tool_frame, text='도구:', font=F_LABEL_S, fg=C_TEXT_SEC,
              bg=C_BG).pack(side=LEFT, padx=(0, 6))

        Button(tool_frame, text='조위 API 다운로드',
               command=self._download_tide_api,
               font=F_BTN_S, padx=8, pady=4, relief='groove',
               cursor='hand2', fg='#1565C0').pack(side=LEFT, padx=(0, 6))

        Button(tool_frame, text='CSV → TOPS 변환',
               command=self._convert_csv_to_tops,
               font=F_BTN_S, padx=8, pady=4, relief='groove',
               cursor='hand2', fg='#8e44ad').pack(side=LEFT, padx=(0, 6))

        Button(tool_frame, text='매뉴얼 열기',
               command=self._open_manual,
               font=F_BTN_S, padx=8, pady=4, relief='groove',
               cursor='hand2', fg=C_TEXT_SEC).pack(side=LEFT, padx=(0, 0))

    # ────────────────────────────────────────────
    #  섹션 5: 처리 로그
    # ────────────────────────────────────────────
    def _build_log_section(self, parent):
        card = CardFrame(parent, title='처리 로그')
        card.pack(fill=BOTH, expand=True, pady=(0, 0))

        log_container = Frame(card.body, bg=C_LOG_BG)
        log_container.pack(fill=BOTH, expand=True, padx=1, pady=(0, 1))

        self.log_text = Text(
            log_container, wrap=WORD, state=DISABLED,
            font=F_LOG, bg=C_LOG_BG, fg=C_LOG_FG,
            insertbackground='white', selectbackground='#34495e',
            relief='flat', padx=10, pady=8, spacing1=1, spacing3=1
        )
        log_scroll = Scrollbar(log_container, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side=RIGHT, fill=Y)
        self.log_text.pack(fill=BOTH, expand=True)

        self.log_text.tag_configure('info', foreground='#82e0aa')
        self.log_text.tag_configure('step', foreground='#85c1e9',
                                     font=(F_LOG[0], F_LOG[1], 'bold'))
        self.log_text.tag_configure('detail', foreground='#aab7b8')
        self.log_text.tag_configure('warning', foreground='#f9e79f')
        self.log_text.tag_configure('error', foreground='#f1948a')
        self.log_text.tag_configure('success', foreground='#58d68d',
                                     font=(F_LOG[0], F_LOG[1], 'bold'))
        self.log_text.tag_configure('header', foreground='#aed6f1',
                                     font=(F_LOG[0], F_LOG[1], 'bold'))
        self.log_text.tag_configure('dim', foreground='#5d6d7e')

    # ============================================================
    #  UI 유틸
    # ============================================================
    def _path_row(self, parent, label, var, browse_cmd,
                  hint='', is_folder=False, is_save=False):
        row = Frame(parent, bg=C_CARD)
        row.pack(fill=X, pady=2)

        Label(row, text=label, font=F_LABEL, fg=C_TEXT,
              bg=C_CARD, width=14, anchor=E).pack(side=LEFT, padx=(0, 8))

        ttk.Entry(row, textvariable=var, font=F_ENTRY).pack(
            side=LEFT, fill=X, expand=True, padx=(0, 6))

        Button(row, text='  탐색  ', command=browse_cmd,
               font=F_HINT, padx=8, pady=1, relief='groove',
               cursor='hand2', bg='#f8f9fa', fg=C_TEXT).pack(side=LEFT)

        if hint:
            hint_row = Frame(parent, bg=C_CARD)
            hint_row.pack(fill=X)
            Label(hint_row, text='', width=14, bg=C_CARD).pack(side=LEFT)
            Label(hint_row, text=f'  {hint}', font=F_HINT,
                  fg=C_TEXT_SEC, bg=C_CARD, anchor=W).pack(side=LEFT)

        return row

    def _separator(self, parent):
        Frame(parent, bg=C_BORDER, height=1).pack(fill=X, pady=4)

    def _option_group(self, parent, label):
        grp = Frame(parent, bg=C_CARD)
        Label(grp, text=label, font=F_HINT, fg=C_TEXT_SEC,
              bg=C_CARD).pack(side=LEFT, padx=(0, 5))
        return grp

    # ============================================================
    #  경로 자동 탐색
    # ============================================================
    def _auto_discover_paths(self):
        try:
            project_root = _find_project_root()
            temp_config = TideBedConfig()
            temp_config.auto_discover(project_root)
            if temp_config.db_root:
                self.db_path.set(temp_config.db_root)
            if temp_config.ref_st_info_path:
                self.station_path.set(temp_config.ref_st_info_path)
        except:
            pass

    def _toggle_api_row(self):
        """API 체크박스 토글 → API 키 입력 행 + 조위폴더/기준항개수 비활성화."""
        if self.use_api.get():
            self._api_info.pack(fill=X, padx=16, pady=(2, 0))
            self._api_row.pack(fill=X, padx=16, pady=(2, 0))
            # 조위 폴더 비활성화
            for w in self._tide_row.winfo_children():
                try:
                    w.configure(state=DISABLED)
                except:
                    pass
            # 기준항 적용 개수 비활성화
            self._rank_combo.configure(state=DISABLED)
        else:
            self._api_info.pack_forget()
            self._api_row.pack_forget()
            for w in self._tide_row.winfo_children():
                try:
                    w.configure(state=NORMAL)
                except:
                    pass
            self._rank_combo.configure(state='readonly')
        # API 키 저장
        self._save_api_key()

    def _save_api_key(self):
        """API 키를 로컬 파일에 저장."""
        key = self.api_key.get().strip()
        try:
            key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.api_key')
            if key:
                with open(key_path, 'w') as f:
                    f.write(key)
            elif os.path.exists(key_path):
                os.remove(key_path)
        except Exception:
            pass

    def _load_api_key(self):
        """저장된 API 키 로드."""
        try:
            key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.api_key')
            if os.path.exists(key_path):
                with open(key_path, 'r') as f:
                    key = f.read().strip()
                if key:
                    self.api_key.set(key)
                    return True
        except Exception:
            pass
        return False

    # ============================================================
    #  탐색 콜백
    # ============================================================
    def _browse_nav(self):
        path = filedialog.askdirectory(title='항적 파일 폴더 선택')
        if path:
            self.nav_path.set(path)

    def _browse_tide(self):
        path = filedialog.askdirectory(title='조위 시계열 폴더 선택')
        if path:
            self.tide_path.set(path)
            self._auto_detect_rank_limit()

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            title='출력 TID 파일 저장',
            defaultextension='.tid',
            filetypes=[('TID 파일', '*.tid'), ('모든 파일', '*.*')]
        )
        if path:
            self.output_path.set(path)

    def _browse_db(self):
        path = filedialog.askdirectory(title='표준개정수 DB 폴더 선택')
        if path:
            self.db_path.set(path)

    def _browse_station(self):
        path = filedialog.askopenfilename(
            title='기준항정보 파일 선택',
            filetypes=[('텍스트 파일', '*.txt'), ('모든 파일', '*.*')]
        )
        if path:
            self.station_path.set(path)
            self._auto_detect_rank_limit()

    def _auto_detect_rank_limit(self):
        """조위 폴더와 기준항정보를 기반으로 매칭 가능한 기준항 수를 감지하여 spinbox 업데이트."""
        tide_dir = self.tide_path.get().strip()
        station_file = self.station_path.get().strip()
        if not tide_dir or not station_file or not os.path.isdir(tide_dir) or not os.path.isfile(station_file):
            return
        try:
            from data_io.station import load_stations, get_station_by_name
            from data_io.tide_series import _extract_station_name
            stations = load_stations(station_file)
            if not stations:
                return
            matched_names = set()
            for fname in os.listdir(tide_dir):
                if not fname.lower().endswith(('.txt', '.tts', '.csv', '.tsv', '.dat')):
                    continue
                fpath = os.path.join(tide_dir, fname)
                sname = None
                # 파일 헤더 읽기
                lines = None
                for enc in ['utf-8-sig', 'euc-kr', 'cp949']:
                    try:
                        with open(fpath, 'r', encoding=enc) as f:
                            lines = f.readlines()[:20]
                        break
                    except Exception:
                        continue
                if not lines:
                    continue
                # TOPS 형식 관측소명 추출
                sname = _extract_station_name(lines)
                # CSV 형식: 두 번째 데이터 행에서 관측소명 추출
                if not sname and fname.lower().endswith('.csv'):
                    header_line = lines[0] if lines else ''
                    if '관측소명' in header_line and '관측시간' in header_line:
                        for line in lines[1:]:
                            parts = line.strip().split(',')
                            if len(parts) >= 3 and parts[1].strip():
                                sname = parts[1].strip()
                                break
                if sname and sname not in matched_names and get_station_by_name(stations, sname):
                    matched_names.add(sname)
            if matched_names:
                self.rank_limit.set(len(matched_names))
        except Exception:
            pass

    def _browse_validate(self):
        path = filedialog.askopenfilename(
            title='참조 TID 파일 선택',
            filetypes=[('TID 파일', '*.tid'), ('모든 파일', '*.*')]
        )
        if path:
            self.validate_path.set(path)

    def _toggle_validate(self):
        if self.do_validate.get():
            self.validate_entry.configure(state=NORMAL)
            self.validate_btn.configure(state=NORMAL)
        else:
            self.validate_entry.configure(state=DISABLED)
            self.validate_btn.configure(state=DISABLED)

    # ============================================================
    #  세팅 프리셋 저장/불러오기
    # ============================================================
    def _get_current_settings(self) -> dict:
        """현재 GUI 설정을 딕셔너리로."""
        return {
            'nav_path': self.nav_path.get(),
            'tide_path': self.tide_path.get(),
            'output_path': self.output_path.get(),
            'db_path': self.db_path.get(),
            'station_path': self.station_path.get(),
            'tide_type': self.tide_type.get(),
            'rank_limit': self.rank_limit.get(),
            'time_interval': self.time_interval.get(),
            'timezone': self.timezone.get(),
            'write_detail': self.write_detail.get(),
            'generate_graph': self.generate_graph.get(),
            'tolerance_cm': self.tolerance_cm.get(),
            'use_api': self.use_api.get(),
            'api_key': self.api_key.get(),
        }

    def _apply_settings(self, settings: dict):
        """딕셔너리에서 GUI에 설정 적용."""
        if 'nav_path' in settings:
            self.nav_path.set(settings['nav_path'])
        if 'tide_path' in settings:
            self.tide_path.set(settings['tide_path'])
        if 'output_path' in settings:
            self.output_path.set(settings['output_path'])
        if 'db_path' in settings:
            self.db_path.set(settings['db_path'])
        if 'station_path' in settings:
            self.station_path.set(settings['station_path'])
        if 'tide_type' in settings:
            self.tide_type.set(settings['tide_type'])
        if 'rank_limit' in settings:
            self.rank_limit.set(settings['rank_limit'])
        if 'time_interval' in settings:
            self.time_interval.set(settings['time_interval'])
        if 'timezone' in settings:
            self.timezone.set(settings['timezone'])
        if 'write_detail' in settings:
            self.write_detail.set(settings['write_detail'])
        if 'generate_graph' in settings:
            self.generate_graph.set(settings['generate_graph'])
        if 'tolerance_cm' in settings:
            self.tolerance_cm.set(settings['tolerance_cm'])
        if 'use_api' in settings:
            self.use_api.set(settings['use_api'])
        if 'api_key' in settings:
            self.api_key.set(settings['api_key'])
        # API 상태 반영
        self._toggle_api_row()
        # 프리셋 로드 후 기준항 수 자동 감지
        self._auto_detect_rank_limit()

    def _save_preset(self):
        """현재 세팅을 프리셋으로 저장."""
        from settings_manager import save_preset

        # 이름 입력 대화상자
        dialog = Toplevel(self.root)
        dialog.title('세팅 프리셋 저장')
        dialog.geometry('400x140')
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        # 중앙 배치
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 400) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 140) // 2
        dialog.geometry(f'+{x}+{y}')

        Frame(dialog, height=15).pack()
        Label(dialog, text='프리셋 이름을 입력하세요:', font=F_LABEL).pack(padx=20, anchor=W)

        name_var = StringVar(value=f'세팅_{datetime.now().strftime("%Y%m%d")}')
        Entry(dialog, textvariable=name_var, font=F_ENTRY, width=40).pack(padx=20, pady=8)

        def do_save():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning('경고', '이름을 입력하세요', parent=dialog)
                return
            settings = self._get_current_settings()
            filepath = save_preset(name, settings)
            self._log(f'세팅 저장 완료: {os.path.basename(filepath)}', 'info')
            dialog.destroy()

        btn_frame = Frame(dialog)
        btn_frame.pack(pady=5)
        Button(btn_frame, text='저장', command=do_save, font=F_BTN_S,
               bg=C_ACCENT, fg='white', padx=20, pady=3, relief='flat',
               cursor='hand2').pack(side=LEFT, padx=5)
        Button(btn_frame, text='취소', command=dialog.destroy, font=F_BTN_S,
               padx=20, pady=3, relief='groove', cursor='hand2').pack(side=LEFT, padx=5)

    def _load_preset(self):
        """프리셋 목록에서 선택하여 불러오기."""
        from settings_manager import list_presets, load_preset, delete_preset

        presets = list_presets()
        if not presets:
            messagebox.showinfo('알림', '저장된 프리셋이 없습니다.\n세팅 저장 버튼으로 먼저 저장하세요.')
            return

        dialog = Toplevel(self.root)
        dialog.title('세팅 프리셋 불러오기')
        dialog.geometry('450x300')
        dialog.resizable(False, True)
        dialog.transient(self.root)
        dialog.grab_set()

        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 450) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 300) // 2
        dialog.geometry(f'+{x}+{y}')

        Label(dialog, text='프리셋을 선택하세요:', font=F_LABEL).pack(padx=15, pady=(10, 5), anchor=W)

        list_frame = Frame(dialog)
        list_frame.pack(fill=BOTH, expand=True, padx=15, pady=5)

        listbox = Listbox(list_frame, font=F_ENTRY, selectmode='single')
        sb = Scrollbar(list_frame, command=listbox.yview)
        listbox.configure(yscrollcommand=sb.set)
        sb.pack(side=RIGHT, fill=Y)
        listbox.pack(fill=BOTH, expand=True)

        for p in presets:
            listbox.insert(END, f"{p['name']}  ({p['created']})")

        def do_load():
            sel = listbox.curselection()
            if not sel:
                messagebox.showwarning('경고', '프리셋을 선택하세요', parent=dialog)
                return
            idx = sel[0]
            settings = load_preset(presets[idx]['path'])
            if settings:
                self._apply_settings(settings)
                self._log(f'세팅 불러오기: {presets[idx]["name"]}', 'info')
            dialog.destroy()

        def do_delete():
            sel = listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            if messagebox.askyesno('삭제 확인',
                                    f'"{presets[idx]["name"]}" 프리셋을 삭제하시겠습니까?',
                                    parent=dialog):
                delete_preset(presets[idx]['path'])
                listbox.delete(idx)
                presets.pop(idx)
                self._log(f'프리셋 삭제됨', 'detail')

        btn_frame = Frame(dialog)
        btn_frame.pack(pady=8)
        Button(btn_frame, text='불러오기', command=do_load, font=F_BTN_S,
               bg=C_ACCENT, fg='white', padx=20, pady=3, relief='flat',
               cursor='hand2').pack(side=LEFT, padx=5)
        Button(btn_frame, text='삭제', command=do_delete, font=F_BTN_S,
               fg=C_ERROR, padx=14, pady=3, relief='groove',
               cursor='hand2').pack(side=LEFT, padx=5)
        Button(btn_frame, text='취소', command=dialog.destroy, font=F_BTN_S,
               padx=14, pady=3, relief='groove', cursor='hand2').pack(side=LEFT, padx=5)

    # ============================================================
    #  INI 불러오기 / 초기화
    # ============================================================
    def _load_ini(self):
        path = filedialog.askopenfilename(
            title='TideBedLite.ini 선택',
            filetypes=[('INI 파일', '*.ini'), ('모든 파일', '*.*')]
        )
        if not path:
            return

        try:
            config = TideBedConfig.from_ini(path)
            if config.nav_directory:
                self.nav_path.set(config.nav_directory)
            if config.tts_folder:
                self.tide_path.set(config.tts_folder)
            if config.db_root:
                self.db_path.set(config.db_root)
            if config.ref_st_info_path:
                self.station_path.set(config.ref_st_info_path)
            self.tide_type.set(config.tide_series_type)
            self.rank_limit.set(config.rank_limit)
            self.time_interval.set(config.time_interval_sec)
            self.write_detail.set(config.write_detail)
            if config.is_kst:
                self.timezone.set('KST (UTC+9)')
            else:
                self.timezone.set('GMT (UTC+0)')

            config.auto_discover()
            if config.db_root and not self.db_path.get():
                self.db_path.set(config.db_root)
            if config.ref_st_info_path and not self.station_path.get():
                self.station_path.set(config.ref_st_info_path)

            # INI 로드 후 기준항 수 자동 감지
            self._auto_detect_rank_limit()
            self._log('INI 설정 불러오기 완료', 'info')
            self._log(f'  파일: {path}', 'detail')
        except Exception as e:
            self._log(f'INI 불러오기 실패: {e}', 'error')

    def _reset(self):
        self.nav_path.set('')
        self.tide_path.set('')
        self.output_path.set('')
        self.validate_path.set('')
        self.tide_type.set('실측')
        self.rank_limit.set(10)
        self.time_interval.set(0)
        self.timezone.set('GMT (UTC+0)')
        self.write_detail.set(True)
        self.generate_graph.set(True)
        self.tolerance_cm.set(1.0)
        self.do_validate.set(False)
        self.use_api.set(False)
        self.progress_var.set(0)
        self.status_var.set('대기 중')
        self.status_label.configure(fg=C_TEXT_SEC)
        self._toggle_validate()
        self._toggle_api_row()
        self._auto_discover_paths()
        self._log('설정이 초기화되었습니다', 'info')

    # ============================================================
    #  도구: 조위 API 다운로드
    # ============================================================
    def _download_tide_api(self):
        """공공데이터포털 API로 조위 데이터 다운로드 대화상자."""
        try:
            from data_io.khoa_api import (
                STATION_LIST, download_and_export,
                STATION_NAME_TO_CODE)
        except ImportError as e:
            messagebox.showerror('모듈 오류', f'khoa_api 모듈 로드 실패:\n{e}')
            return

        # ── 대화상자 생성 ──
        dlg = Toplevel(self.root)
        dlg.title('조위 API 다운로드 (공공데이터포털)')
        dlg.geometry('520x520')
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        pad = {'padx': 10, 'pady': 4}

        # --- API 키 ---
        Label(dlg, text='API 서비스키:', font=('맑은 고딕', 9, 'bold')).pack(
            anchor=W, **pad)
        api_key_var = StringVar()
        Entry(dlg, textvariable=api_key_var, width=60, show='*').pack(
            anchor=W, padx=10)
        Label(dlg, text='공공데이터포털(data.go.kr) 인증키',
              font=('맑은 고딕', 8), fg='gray').pack(anchor=W, padx=10)

        # --- 기간 ---
        date_frame = Frame(dlg)
        date_frame.pack(anchor=W, **pad)
        Label(date_frame, text='기간:', font=('맑은 고딕', 9, 'bold')).pack(
            side=LEFT)

        today = datetime.now()
        start_var = StringVar(value=(today.replace(day=1)).strftime('%Y%m%d'))
        end_var = StringVar(value=today.strftime('%Y%m%d'))

        Entry(date_frame, textvariable=start_var, width=10).pack(
            side=LEFT, padx=(6, 2))
        Label(date_frame, text='~').pack(side=LEFT)
        Entry(date_frame, textvariable=end_var, width=10).pack(
            side=LEFT, padx=(2, 6))
        Label(date_frame, text='(YYYYMMDD)', font=('맑은 고딕', 8),
              fg='gray').pack(side=LEFT)

        # --- 관측소 선택 ---
        Label(dlg, text='관측소 선택 (Ctrl+클릭 다중선택):',
              font=('맑은 고딕', 9, 'bold')).pack(anchor=W, **pad)

        list_frame = Frame(dlg)
        list_frame.pack(fill=BOTH, expand=True, padx=10, pady=4)

        scrollbar = Scrollbar(list_frame, orient=VERTICAL)
        station_listbox = Listbox(
            list_frame, selectmode='extended', height=15,
            font=('맑은 고딕', 9), yscrollcommand=scrollbar.set)
        scrollbar.config(command=station_listbox.yview)
        station_listbox.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        for code, name in STATION_LIST:
            station_listbox.insert(END, f'{name} ({code})')

        # 전체선택/해제 버튼
        sel_frame = Frame(dlg)
        sel_frame.pack(anchor=W, padx=10)
        Button(sel_frame, text='전체 선택', font=('맑은 고딕', 8),
               command=lambda: station_listbox.select_set(0, END)).pack(
            side=LEFT, padx=(0, 4))
        Button(sel_frame, text='선택 해제', font=('맑은 고딕', 8),
               command=lambda: station_listbox.select_clear(0, END)).pack(
            side=LEFT)

        # --- 진행 상태 ---
        status_var = StringVar(value='대기 중')
        Label(dlg, textvariable=status_var, font=('맑은 고딕', 8),
              fg='#1565C0').pack(anchor=W, padx=10, pady=(6, 2))

        progress = ttk.Progressbar(dlg, mode='indeterminate', length=480)
        progress.pack(padx=10, pady=(0, 6))

        # --- 실행 버튼 ---
        btn_frame = Frame(dlg)
        btn_frame.pack(pady=(4, 10))

        def _do_download():
            api_key = api_key_var.get().strip()
            if not api_key:
                messagebox.showwarning('입력 필요', 'API 서비스키를 입력하세요.',
                                       parent=dlg)
                return

            selected = station_listbox.curselection()
            if not selected:
                messagebox.showwarning('선택 필요', '관측소를 선택하세요.',
                                       parent=dlg)
                return

            start = start_var.get().strip()
            end = end_var.get().strip()
            if len(start) != 8 or len(end) != 8:
                messagebox.showwarning('입력 오류',
                    '날짜를 YYYYMMDD 형식으로 입력하세요.', parent=dlg)
                return

            codes = [STATION_LIST[i][0] for i in selected]
            names = [STATION_LIST[i][1] for i in selected]

            out_dir = filedialog.askdirectory(
                title='CSV 출력 폴더 선택', parent=dlg)
            if not out_dir:
                return

            # 비동기 다운로드
            download_btn.config(state=DISABLED)
            progress.start(10)

            def _run():
                try:
                    def _progress(msg):
                        status_var.set(msg)

                    results = download_and_export(
                        api_key, codes, start, end, out_dir,
                        progress_callback=_progress,
                    )

                    # 결과 메시지 생성
                    ok = [r for r in results if not r.error]
                    err = [r for r in results if r.error]

                    msg_lines = [f'API 다운로드 완료\n']
                    for r in ok:
                        msg_lines.append(
                            f'■ {r.station_name}: '
                            f'실측 {r.obs_count}행, '
                            f'예측 {r.pred_count}행')
                    if err:
                        msg_lines.append('\n--- 오류 ---')
                        for r in err:
                            msg_lines.append(
                                f'✕ {r.station_name}: {r.error}')
                    msg_lines.append(f'\n출력 폴더: {out_dir}')

                    def _done():
                        progress.stop()
                        status_var.set(
                            f'완료: {len(ok)}개 관측소 다운로드')
                        messagebox.showinfo(
                            'API 다운로드 완료',
                            '\n'.join(msg_lines), parent=dlg)
                        download_btn.config(state=NORMAL)
                        self._log(
                            f'API 다운로드: {len(ok)}개 관측소 → {out_dir}',
                            'info')

                        # CSV→TOPS 자동 변환 제안
                        if ok:
                            do_convert = messagebox.askyesno(
                                'TOPS 변환',
                                '다운로드한 CSV를 TOPS로 바로 변환할까요?',
                                parent=dlg)
                            if do_convert:
                                self._auto_convert_to_tops(out_dir)
                                dlg.destroy()

                    dlg.after(0, _done)

                except Exception as e:
                    def _err():
                        progress.stop()
                        status_var.set(f'오류: {e}')
                        messagebox.showerror(
                            'API 오류', str(e), parent=dlg)
                        download_btn.config(state=NORMAL)
                    dlg.after(0, _err)

            threading.Thread(target=_run, daemon=True).start()

        download_btn = Button(
            btn_frame, text='다운로드 시작', font=('맑은 고딕', 10, 'bold'),
            command=_do_download, fg='white', bg='#1565C0',
            padx=20, pady=6, cursor='hand2')
        download_btn.pack(side=LEFT, padx=6)

        Button(btn_frame, text='닫기', font=('맑은 고딕', 10),
               command=dlg.destroy, padx=20, pady=6).pack(side=LEFT)

    def _auto_convert_to_tops(self, csv_dir: str):
        """다운로드된 CSV 폴더를 자동으로 TOPS 변환."""
        csv_files = [os.path.join(csv_dir, f) for f in os.listdir(csv_dir)
                     if f.lower().endswith('.csv')]
        if not csv_files:
            return

        station_coords = self._load_station_coords()

        try:
            from data_io.csv_to_tops import batch_convert
            results = batch_convert(
                csv_files, csv_dir,
                station_coords=station_coords,
                export_observed=True,
                export_predicted=True,
            )
            if results:
                self.tide_path.set(csv_dir)
                self._log(
                    f'API→CSV→TOPS 자동변환: {len(results)}개 관측소',
                    'info')
                messagebox.showinfo(
                    'TOPS 변환 완료',
                    f'{len(results)}개 관측소 TOPS 변환 완료\n'
                    f'조위 경로가 자동 설정되었습니다.')
        except Exception as e:
            messagebox.showerror('TOPS 변환 오류', str(e))

    # ============================================================
    #  도구: CSV → TOPS 변환
    # ============================================================
    def _convert_csv_to_tops(self):
        """KHOA 바다누리 CSV를 TOPS 형식으로 변환하는 대화상자."""
        # 파일 선택 or 폴더 선택
        choice = messagebox.askyesnocancel(
            'CSV → TOPS 변환',
            '폴더 단위로 변환하시겠습니까?\n\n'
            '예 = 폴더 선택 (폴더 내 모든 CSV)\n'
            '아니오 = 개별 파일 선택')
        if choice is None:
            return

        if choice:  # 폴더 선택
            csv_dir = filedialog.askdirectory(title='CSV 파일이 있는 폴더 선택')
            if not csv_dir:
                return
            csv_files = [os.path.join(csv_dir, f) for f in os.listdir(csv_dir)
                         if f.lower().endswith('.csv')]
            if not csv_files:
                messagebox.showwarning('변환', '선택한 폴더에 CSV 파일이 없습니다.')
                return
        else:  # 개별 파일 선택
            csv_files = filedialog.askopenfilenames(
                title='바다누리 CSV 파일 선택',
                filetypes=[('CSV 파일', '*.csv'), ('모든 파일', '*.*')],
            )
            if not csv_files:
                return
            csv_files = list(csv_files)

        out_dir = filedialog.askdirectory(title='TOPS 출력 폴더 선택')
        if not out_dir:
            return

        # 기준항정보에서 좌표 매핑 시도
        station_coords = self._load_station_coords()

        try:
            from data_io.csv_to_tops import batch_convert
            results = batch_convert(
                list(csv_files), out_dir,
                station_coords=station_coords,
                export_observed=True,
                export_predicted=True,
            )

            if not results:
                messagebox.showwarning('변환 결과', '변환된 파일이 없습니다.')
                return

            msg_lines = [f'CSV → TOPS 변환 완료 (입력 {len(csv_files)}개 파일)\n']
            for r in results:
                msg_lines.append(f'■ {r.station_name}')
                if r.obs_path:
                    msg_lines.append(f'  실측: {r.obs_count}행 ({r.obs_start[:16]} ~ {r.obs_end[:16]})')
                if r.pred_path:
                    msg_lines.append(f'  예측: {r.pred_count}행 ({r.pred_start[:16]} ~ {r.pred_end[:16]})')
                msg_lines.append('')
            msg_lines.append(f'출력 폴더: {out_dir}')

            messagebox.showinfo('변환 완료', '\n'.join(msg_lines))
            self._log(f'CSV→TOPS 변환: {len(results)}개 관측소 → {out_dir}', 'info')

            # 변환된 폴더를 조위 경로로 자동 설정
            self.tide_path.set(out_dir)

        except Exception as e:
            messagebox.showerror('변환 오류', f'CSV 변환 중 오류:\n{e}')
            self._log(f'CSV→TOPS 변환 오류: {e}', 'error')

    def _load_station_coords(self):
        """기준항정보.txt에서 관측소명 → (lon, lat) 매핑 로드."""
        coords = {}
        try:
            from data_io.station import load_stations
            # DB 경로에서 기준항정보 탐색
            for base in [self.db_path.get(), self.station_path.get()]:
                if not base:
                    continue
                stn_file = base if base.endswith('.txt') else None
                if stn_file and os.path.isfile(stn_file):
                    stations = load_stations(stn_file)
                    for s in stations:
                        if s.name and s.longitude > -900 and s.latitude > -900:
                            coords[s.name] = (s.longitude, s.latitude)
                    break
        except Exception:
            pass
        return coords if coords else None

    def _open_manual(self):
        """매뉴얼 파일 열기."""
        # EXE 모드에서도 올바른 경로 탐색: 프로젝트 루트 및 __file__ 기준 모두 시도
        search_dirs = [
            os.path.join(_find_project_root(), 'manual'),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'manual'),
        ]
        # EXE의 실행 디렉토리 기준
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            search_dirs.insert(0, os.path.join(exe_dir, 'manual'))

        for manual_dir in search_dirs:
            for fname in ['TideBedPy_Manual.docx', 'TideBedPy_Manual.txt']:
                path = os.path.join(manual_dir, fname)
                if os.path.isfile(path):
                    try:
                        os.startfile(path)
                        return
                    except Exception:
                        import subprocess
                        subprocess.Popen(['start', '', path], shell=True)
                        return

        messagebox.showinfo('매뉴얼',
            f'매뉴얼 파일을 찾을 수 없습니다.\n탐색 경로:\n' +
            '\n'.join(search_dirs))

    # ============================================================
    #  로그
    # ============================================================
    def _log(self, msg: str, tag: str = 'info'):
        ts = datetime.now().strftime('%H:%M:%S')

        def _append():
            self.log_text.configure(state=NORMAL)
            self.log_text.insert(END, f'{ts}  {msg}\n', tag)
            self.log_text.see(END)
            self.log_text.configure(state=DISABLED)

        try:
            self.root.after(0, _append)
        except:
            pass

    def _update_status(self, msg: str, color: str = C_TEXT_SEC):
        def _update():
            self.status_var.set(msg)
            self.status_label.configure(fg=color)
        self.root.after(0, _update)

    def _update_progress(self, current: int, total: int):
        pct = (current / total * 100) if total > 0 else 0
        def _update():
            self.progress_var.set(pct)
            self.status_var.set(f'보정 처리 중: {current:,}/{total:,}  ({pct:.0f}%)')
        self.root.after(0, _update)

    # ============================================================
    #  입력 검증
    # ============================================================
    def _validate_inputs(self) -> bool:
        errors = []

        nav = self.nav_path.get().strip()
        if not nav:
            errors.append('항적 파일 폴더가 지정되지 않았습니다.')
        elif not os.path.isdir(nav):
            errors.append(f'항적 폴더를 찾을 수 없습니다: {nav}')

        # API 모드: 조위 폴더 대신 API 키 검증
        if self.use_api.get():
            api_key = self.api_key.get().strip()
            if not api_key:
                errors.append('API 자동 수집 모드에서는 API 키가 필요합니다.')
        else:
            tide = self.tide_path.get().strip()
            if not tide:
                errors.append('조위 시계열 폴더가 지정되지 않았습니다.')
            elif not os.path.isdir(tide):
                errors.append(f'조위 폴더를 찾을 수 없습니다: {tide}')

        output = self.output_path.get().strip()
        if not output:
            errors.append('출력 파일 경로가 지정되지 않았습니다.')

        db = self.db_path.get().strip()
        if not db:
            errors.append('표준개정수 DB 경로가 지정되지 않았습니다.')
        elif not os.path.isdir(db):
            errors.append(f'DB 폴더를 찾을 수 없습니다: {db}')

        station = self.station_path.get().strip()
        if not station:
            errors.append('기준항정보 파일이 지정되지 않았습니다.')
        elif not os.path.isfile(station):
            errors.append(f'기준항정보 파일을 찾을 수 없습니다: {station}')

        if errors:
            for err in errors:
                self._log(f'\u2717  {err}', 'error')
            messagebox.showerror('입력 오류', '\n'.join(errors))
            return False

        return True

    # ============================================================
    #  보정 수행
    # ============================================================
    def _run(self):
        if self.is_running:
            return
        if not self._validate_inputs():
            return

        self.is_running = True
        self._stop_requested = False
        self.run_btn.configure(state=DISABLED, bg='#95a5a6')
        self.stop_btn.configure(state=NORMAL)
        self.progress_var.set(0)
        self._set_inputs_locked(True)

        self.log_text.configure(state=NORMAL)
        self.log_text.delete('1.0', END)
        self.log_text.configure(state=DISABLED)

        thread = threading.Thread(target=self._process_thread, daemon=True)
        thread.start()

    def _stop(self):
        self._stop_requested = True
        self._update_status('중지 중...', C_WARNING)
        self._log('\u26a0  중지가 요청되었습니다...', 'warning')

    def _process_thread(self):
        cotidal = None
        try:
            self._log('\u2501' * 56, 'dim')
            self._log(f'  {APP_TITLE}  {APP_SUBTITLE}  v{APP_VERSION}', 'header')
            self._log('\u2501' * 56, 'dim')
            self._log(f'  처리 시작: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 'detail')
            self._log('', 'dim')

            start_time = time.time()

            # ── Config 구성 ──
            config = TideBedConfig()
            config.nav_directory = self.nav_path.get().strip()
            config.tts_folder = self.tide_path.get().strip()
            config.db_root = self.db_path.get().strip()
            config.ref_st_info_path = self.station_path.get().strip()
            config.output_path = self.output_path.get().strip()
            config.tide_series_type = self.tide_type.get()
            config.rank_limit = min(self.rank_limit.get(), 10)
            config.time_interval_sec = self.time_interval.get()
            config.write_detail = self.write_detail.get()

            # UTC 오프셋 처리
            utc_offset = _parse_timezone_offset(self.timezone.get())
            config.utc_offset = utc_offset
            config.is_kst = (utc_offset == 9.0)

            if self.do_validate.get():
                config.validate_path = self.validate_path.get().strip()

            self._log(f'  시간대: {self.timezone.get()} (UTC offset: {utc_offset:+.1f}h)', 'detail')

            # 모듈 임포트
            from data_io.station import load_stations
            from data_io.tide_series import load_tide_folder, adjust_tide_year
            from data_io.navigation import load_nav_directory
            from data_io.cotidal import CoTidalGrid
            from core.tide_correction import TideCorrectionEngine
            from output.tid_writer import write_tid, write_detail, write_error
            from output.report import validate_output

            # ── [1/7] 기준항 정보 로드 ──
            self._update_status('기준항 정보 로드 중...', C_PRIMARY)
            self._log('[1/7]  기준항 정보 로드', 'step')
            stations = load_stations(config.ref_st_info_path)
            if not stations:
                self._log('\u2717  기준항 정보를 불러올 수 없습니다!', 'error')
                self._finish(False)
                return
            self._log(f'  \u2192 {len(stations)}개 기준항 로드 완료', 'info')

            if self._stop_requested:
                self._finish(False, '사용자에 의해 중지됨')
                return

            # ── [2/7] 항적 데이터 로드 ──
            self._update_status('항적 데이터 로드 중...', C_PRIMARY)
            self._log('[2/7]  항적 파일 로드', 'step')
            nav_points = load_nav_directory(config.nav_directory)
            if not nav_points:
                self._log('✗  항적 데이터를 불러올 수 없습니다!', 'error')
                self._finish(False)
                return
            self._log(f'  → {len(nav_points):,}개 항적 포인트 로드', 'info')
            self._log(f'  → 시간 범위: {nav_points[0].t} ~ {nav_points[-1].t}', 'detail')

            if self._stop_requested:
                self._finish(False, '사용자에 의해 중지됨')
                return

            # ── [2.5/7] API 자동 수집 (선택) ──
            api_key = self.api_key.get().strip()
            if self.use_api.get() and api_key:
                self._update_status('API 관측소 선택 대기...', C_PRIMARY)
                self._log('[2.5/7]  API 자동 조위 수집', 'step')
                try:
                    from data_io.khoa_api import (select_nearby_stations,
                                                   auto_fetch_for_nav)
                    api_out_dir = os.path.dirname(config.output_path) or '.'

                    # 근처 관측소 후보 계산
                    lats = [p.y for p in nav_points]
                    lons = [p.x for p in nav_points]
                    clat = sum(lats) / len(lats)
                    clon = sum(lons) / len(lons)
                    nearby = select_nearby_stations(
                        clat, clon, stations,
                        max_count=20, max_distance_km=300)

                    self._log(f'  → {len(nearby)}개 후보 관측소 탐색됨', 'detail')

                    # 관측소 선택 다이얼로그 (메인 스레드에서 실행)
                    import threading
                    _dlg_event = threading.Event()
                    _dlg_result = [None]
                    def _show_dialog():
                        dlg = StationSelectDialog(self.root, nearby, nav_points)
                        _dlg_result[0] = dlg.result
                        _dlg_event.set()
                    self.root.after(0, _show_dialog)
                    _dlg_event.wait(timeout=600)  # 최대 10분 대기

                    chosen = _dlg_result[0]
                    if not chosen:
                        self._log('  → API 수집 취소됨, 기존 조위 폴더 사용', 'warning')
                    else:
                        self._log(f'  → {len(chosen)}개 관측소 선택됨', 'info')

                        def _api_progress(msg):
                            self._log(f'  → {msg}', 'detail')
                            self._update_status(msg, C_PRIMARY)

                        api_results = auto_fetch_for_nav(
                            api_key, nav_points, api_out_dir,
                            stations=stations,
                            minute=10,
                            progress_callback=_api_progress,
                            selected_stations=chosen,
                        )

                        ok_count = sum(1 for r in api_results if not r.error)
                        self._log(f'  → {ok_count}개 관측소 수집 완료', 'info')
                        for r in api_results:
                            dist_info = f'({r.distance_km:.0f}km)'
                            if r.error:
                                self._log(f'  ✗ {r.station_name} {dist_info}: {r.error}', 'warning')
                            else:
                                self._log(f'  ✓ {r.station_name} {dist_info}: {r.record_count}행', 'detail')

                        # API 수집된 폴더를 조위 경로로 설정
                        if ok_count > 0:
                            if config.tide_series_type == '예측':
                                config.tts_folder = os.path.join(api_out_dir, 'api_예측조위')
                                if config.tts_p_folder:
                                    config.tts_p_folder = config.tts_folder
                            else:
                                config.tts_folder = os.path.join(api_out_dir, 'api_실측조위')

                except Exception as e:
                    self._log(f'  ⚠ API 수집 실패: {e}', 'warning')
                    self._log(f'  → 기존 조위 폴더로 진행합니다', 'detail')

            # ── [3/7] 조위 시계열 로드 + Akima 보간 ──
            self._update_status('조위 시계열 로드 중...', C_PRIMARY)
            self._log('[3/7]  조위 시계열 로드 + Akima 보간', 'step')
            if config.tide_series_type == '예측':
                folder = config.tts_p_folder if config.tts_p_folder else config.tts_folder
                matched = load_tide_folder(folder, stations, 'PRED')
                self._log(f'  → 유형: 예측 시계열', 'detail')
            else:
                matched = load_tide_folder(config.tts_folder, stations, 'OBS')
                self._log(f'  → 유형: 실측 시계열', 'detail')
            self._log(f'  → {matched}개 기준항 매칭 완료', 'info')

            # rank_limit 자동 조정: 매칭된 기준항 수에 맞춤
            if matched > 0 and config.rank_limit > matched:
                old_rl = config.rank_limit
                config.rank_limit = matched
                self._log(f'  → 기준항 적용 개수 자동 조정: {old_rl} → {matched}', 'info')

            if matched == 0:
                self._log('⚠  매칭된 기준항이 없습니다! 조위 폴더를 확인하세요.', 'warning')

            if self._stop_requested:
                self._finish(False, '사용자에 의해 중지됨')
                return

            # ── [4/7] Co-tidal 격자 로드 ──
            self._update_status('개정수 DB 로드 중...', C_PRIMARY)
            self._log('[4/7]  개정수 DB (Co-tidal 격자) 로드', 'step')
            cotidal = CoTidalGrid(config.db_root)
            if not cotidal.load_catalog():
                self._log('✗  File_Catalog.txt 로드 실패!', 'error')
                self._finish(False)
                return
            opened = cotidal.open_netcdfs()
            self._log(f'  → {opened}개 NetCDF 파일 로드', 'info')

            if self._stop_requested:
                cotidal.close_netcdfs()
                self._finish(False, '사용자에 의해 중지됨')
                return

            # ── 조위 연도 자동 보정 ──
            nav_year = nav_points[0].t.year
            adj_count = adjust_tide_year(stations, nav_year)
            if adj_count > 0:
                self._log(f'  \u2192 조위 연도 \u2192 {nav_year}년 자동 조정 ({adj_count}개)', 'warning')

            # ── [5/7] 조석보정 처리 ──
            self._update_status('조석보정 처리 중...', C_PRIMARY)
            self._log(f'[5/7]  조석보정 처리 (기준항 {config.rank_limit}개, UTC{utc_offset:+.0f})', 'step')
            engine = TideCorrectionEngine(config, stations, cotidal)

            def gui_progress(current, total):
                if self._stop_requested:
                    raise InterruptedError('중지 요청')
                self._update_progress(current, total)

            try:
                processed, all_corrections = engine.process_all(
                    nav_points, progress_callback=gui_progress
                )
            except InterruptedError:
                cotidal.close_netcdfs()
                self._finish(False, '사용자에 의해 중지됨')
                return

            error_count = sum(1 for nav in processed if nav.tc <= -999.0)
            valid_count = len(processed) - error_count
            self._log(f'  \u2192 정상: {valid_count:,}개  /  오류: {error_count:,}개  '
                      f'(총 {len(processed):,}개)', 'info')

            # ── [6/7] 출력 파일 생성 ──
            self._update_status('출력 파일 생성 중...', C_PRIMARY)
            self._log('[6/7]  출력 파일 생성', 'step')

            write_tid(config.output_path, processed, config,
                      db_version=cotidal.version or '1101')
            self._log(f'  \u2192 {os.path.basename(config.output_path)}', 'info')

            if config.write_detail:
                write_detail(config.output_path, processed, all_corrections)
                self._log(f'  \u2192 {os.path.basename(config.output_path)}.detail', 'info')

            error_points = []
            for nav in processed:
                if nav.tc <= -999.0:
                    error_points.append({
                        'lon': nav.x, 'lat': nav.y,
                        'time': nav.t.strftime('%Y/%m/%d %H:%M:%S'),
                    })
            write_error(config.output_path, error_points)
            self._log(f'  \u2192 {os.path.basename(config.output_path)}.err', 'info')

            # ── 조석 그래프 + 지도 생성 ──
            if self.generate_graph.get():
                try:
                    from output.graph import generate_tide_graph, generate_comparison_graph
                    ref_path = config.validate_path if (
                        config.validate_path and os.path.isfile(config.validate_path)
                    ) else None

                    tol_cm = self.tolerance_cm.get()
                    img_path = generate_tide_graph(
                        config.output_path,
                        reference_path=ref_path,
                        tolerance_cm=tol_cm
                    )
                    if img_path:
                        self._log(f'  \u2192 조석 그래프: {os.path.basename(img_path)}', 'info')

                    if ref_path:
                        cmp_path = generate_comparison_graph(
                            config.output_path, ref_path,
                            tolerance_cm=tol_cm
                        )
                        if cmp_path:
                            self._log(f'  \u2192 비교 그래프: {os.path.basename(cmp_path)}', 'info')
                except ImportError:
                    self._log('  \u26a0 matplotlib 미설치 \u2014 그래프 생략', 'warning')
                except Exception as e:
                    self._log(f'  \u26a0 그래프 생성 실패: {e}', 'warning')

                # 지도 시각화
                try:
                    from output.map_view import generate_station_map, generate_correction_map
                    map_path = config.output_path + '.map.png'
                    map_img = generate_station_map(
                        stations, nav_points=processed,
                        output_image=map_path,
                        all_corrections=all_corrections
                    )
                    if map_img:
                        self._log(f'  \u2192 위치 지도: {os.path.basename(map_img)}', 'info')

                    corr_map_path = config.output_path + '.corrmap.png'
                    corr_img = generate_correction_map(
                        stations, processed,
                        output_image=corr_map_path,
                        all_corrections=all_corrections
                    )
                    if corr_img:
                        self._log(f'  \u2192 보정 결과 지도: {os.path.basename(corr_img)}', 'info')
                except ImportError:
                    pass
                except Exception as e:
                    self._log(f'  \u26a0 지도 생성 실패: {e}', 'warning')

            # NetCDF 닫기
            cotidal.close_netcdfs()
            cotidal = None

            # ── [7/7] 검증 ──
            if config.validate_path and os.path.isfile(config.validate_path):
                self._log('[7/7]  검증 (참조 TID 비교)', 'step')
                result = validate_output(config.output_path, config.validate_path)
                self._log(f'  \u2192 생성: {result["total_generated"]}개  '
                          f'/  참조: {result["total_reference"]}개  '
                          f'/  매칭: {result["matched"]}개', 'detail')
                self._log(f'  \u2192 허용범위 이내 (\u00b10.01m): {result["within_tolerance"]}개', 'detail')
                self._log(f'  \u2192 허용범위 초과: {result["exceeded_tolerance"]}개', 'detail')
                self._log(f'  \u2192 최대 편차: {result["max_diff"]:.4f} m', 'detail')

                if result['exceeded_tolerance'] == 0 and result['matched'] > 0:
                    self._log(f'  \u2713  [합격] 전체 {result["matched"]}개 값이 '
                              f'허용범위 이내입니다!', 'success')
                elif result['exceeded_tolerance'] > 0:
                    self._log(f'  \u2717  [불합격] {result["exceeded_tolerance"]}개 값이 '
                              f'허용범위를 초과했습니다!', 'error')
                    for t, g, r, d in result['mismatches'][:5]:
                        self._log(f'      {t}  결과={g:.2f}  참조={r:.2f}  '
                                  f'편차={d:.4f}', 'error')
            else:
                self._log('[7/7]  검증 생략 (참조 파일 없음)', 'step')

            # ── 완료 ──
            elapsed = time.time() - start_time
            self._log('', 'dim')
            self._log('\u2501' * 56, 'dim')
            self._log(f'  \u2713  보정 완료  \u2014  소요시간: {elapsed:.1f}초', 'success')
            self._log('\u2501' * 56, 'dim')

            for fp in [config.output_path,
                       config.output_path + '.detail',
                       config.output_path + '.err',
                       config.output_path + '.png',
                       config.output_path + '.compare.png',
                       config.output_path + '.map.png',
                       config.output_path + '.corrmap.png']:
                if os.path.isfile(fp):
                    size_kb = os.path.getsize(fp) / 1024
                    self._log(f'  \U0001f4c4  {os.path.basename(fp)}  ({size_kb:.1f} KB)', 'detail')

            self._finish(True)

        except Exception as e:
            import traceback
            self._log('', 'dim')
            self._log(f'\u2717  오류 발생: {str(e)}', 'error')
            self._log(traceback.format_exc(), 'error')
            if cotidal:
                try:
                    cotidal.close_netcdfs()
                except:
                    pass
            self._finish(False, f'오류: {str(e)}')

    def _set_inputs_locked(self, locked: bool):
        """처리 중 입력 위젯 활성화/비활성화 (원래 상태 저장/복원)."""
        if locked:
            # 현재 상태 저장 후 비활성화
            self._widget_saved_states = {}
            for widget in getattr(self, '_lockable_widgets', []):
                try:
                    self._widget_saved_states[widget] = str(widget.cget('state'))
                    widget.configure(state=DISABLED)
                except Exception:
                    pass
        else:
            # 저장된 원래 상태로 복원
            for widget, orig_state in getattr(self, '_widget_saved_states', {}).items():
                try:
                    widget.configure(state=orig_state)
                except Exception:
                    pass
            self._widget_saved_states = {}

    def _finish(self, success: bool, msg: str = None):
        def _update():
            self.is_running = False
            self._set_inputs_locked(False)
            self.run_btn.configure(state=NORMAL, bg=C_ACCENT)
            self.stop_btn.configure(state=DISABLED)
            if success:
                self.progress_var.set(100)
                self._update_status(msg or '\u2713  보정이 성공적으로 완료되었습니다!', C_SUCCESS)
            else:
                self._update_status(msg or '\u2717  처리 실패', C_ERROR)
        self.root.after(0, _update)


# ============================================================
#  진입점
# ============================================================
def main():
    root = Tk()

    # DPI 인식 설정 (Windows)
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass

    app = TideBedGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
