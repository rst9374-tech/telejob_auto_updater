# -*- coding: utf-8 -*-
"""
Telejob Auto Ad Engine v3.3.0
- 모던 블랙 & 모노톤 미니멀 UI (단색 아이콘, 다크 테이블, 요약형 레이아웃)
- 중복 실행 완벽 차단 (Single-Instance Mutex)
- 윈도우 부팅 시 자동 실행 + 3색 A/B/C 로테이션 + 원격 OTA 핫스왑
- 크롬 미사용 순수 HTTP Direct 엔진 (메모리 누수 0%)
"""

import os
import sys
import gc
import re
import json
import time
import uuid
import ctypes
import winreg
import mimetypes
import datetime
import threading
import subprocess
import webbrowser
import urllib.request
import urllib.parse
import http.cookiejar
import tkinter as tk
from tkinter import ttk, messagebox

ENGINE_VERSION = "3.3.0"
WINDOW_TITLE = f"TELEJOB AUTO AD  v{ENGINE_VERSION}"
MUTEX_NAME = "Global\\TelejobAutoAd_SingleInstance_Mutex_v3"
OTA_VERSION_URL = "https://raw.githubusercontent.com/rst9374-tech/telejob_auto_updater/main/version.json"
OTA_ENGINE_URL = "https://raw.githubusercontent.com/rst9374-tech/telejob_auto_updater/main/telejob_engine.py"
TELEJOB_PUBLIC_LIST_URL = "https://www.telejob.co.kr/pages/job/list"
TELEJOB_POST_VIEW_URL = "https://www.telejob.co.kr/pages/job/view?wiSeq="
RUN_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_REG_NAME = "TelejobAutoAd"

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
VERSION_PATH = os.path.join(BASE_DIR, "version.json")
ENGINE_PATH = os.path.join(BASE_DIR, "telejob_engine.py")
EXE_PATH = os.path.join(BASE_DIR, "TelejobAutoAd.exe")
LOG_DIR = os.path.join(BASE_DIR, "logs")
DESIGN_DIR = os.path.join(BASE_DIR, "designs")

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DESIGN_DIR, exist_ok=True)

_mutex_handle = None


def acquire_single_instance_lock():
    global _mutex_handle
    if "--restart" in sys.argv:
        time.sleep(1.2)
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32
    _mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() == 183:
        hwnd = user32.FindWindowW(None, WINDOW_TITLE)
        if hwnd:
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
        os._exit(0)


DEFAULT_PRESETS = [
    {
        "name": "A",
        "subTitle": "최대6000%지급",
        "title": "라이나원(직영)IMC센터/미체결디비/아웃바운드",
        "keyword": "아웃바운드,라이나원,보험,콜센터,동의콜",
    },
    {
        "name": "B",
        "subTitle": "전직소득/교육비지원",
        "title": "라이나원(직영)광화문/자사우량DB/신입경력모집",
        "keyword": "텔레마케팅,광화문,생명보험,신입,TM",
    },
    {
        "name": "C",
        "subTitle": "주5일/정착지원금",
        "title": "라이나원(직영)IMC센터/동의콜/고수익상담원채용",
        "keyword": "보험TM,종로구,인센티브,주부알바,상담원",
    }
]

DEFAULT_CONFIG = {
    "user_id": "fkdlsk0301",
    "user_pw": "tjdrb!!1",
    "interval_minutes": 60,
    "start_hour": 4,
    "end_hour": 24,
    "auto_start": True,
    "windows_startup": True,
    "use_abc_rotation": True,
    "use_design_rotation": False,
    "auto_ota_update": True,
    "last_preset_index": 0,
    "presets": DEFAULT_PRESETS
}


def is_windows_startup_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REG_PATH, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, RUN_REG_NAME)
            return bool(val)
    except Exception:
        return False


def set_windows_startup(enable=True):
    try:
        target = f'"{EXE_PATH}"' if os.path.exists(EXE_PATH) else f'"{sys.executable}" "{os.path.join(BASE_DIR, "telejob_auto_ad.py")}"'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                winreg.SetValueEx(key, RUN_REG_NAME, 0, winreg.REG_SZ, target)
            else:
                try:
                    winreg.DeleteValue(key, RUN_REG_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = dict(DEFAULT_CONFIG)
                merged.update(data)
                if not merged.get("presets") or len(merged["presets"]) < 3:
                    merged["presets"] = DEFAULT_PRESETS
                return merged
        except Exception:
            pass
    save_config(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def check_and_download_ota():
    try:
        ts = int(time.time())
        req = urllib.request.Request(
            f"{OTA_VERSION_URL}?t={ts}",
            headers={"User-Agent": "TelejobAutoAd-OTA/3.3", "Cache-Control": "no-cache"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            remote_info = json.loads(resp.read().decode("utf-8"))

        remote_ver = str(remote_info.get("version", "")).strip()
        if not remote_ver or remote_ver == ENGINE_VERSION:
            return False, ENGINE_VERSION, "최신 버전 유지 중"

        def _ver_tuple(v):
            return tuple(int(x) for x in re.findall(r"\d+", v))

        if _ver_tuple(remote_ver) <= _ver_tuple(ENGINE_VERSION):
            return False, ENGINE_VERSION, "최신 버전 유지 중"

        req_eng = urllib.request.Request(
            f"{OTA_ENGINE_URL}?t={ts}",
            headers={"User-Agent": "TelejobAutoAd-OTA/3.3", "Cache-Control": "no-cache"}
        )
        with urllib.request.urlopen(req_eng, timeout=15) as resp:
            new_code = resp.read().decode("utf-8")

        if "class TelejobApp" not in new_code or len(new_code) < 1000:
            return False, ENGINE_VERSION, "엔진 무결성 검증 실패"

        tmp_path = ENGINE_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(new_code)
        os.replace(tmp_path, ENGINE_PATH)

        with open(VERSION_PATH, "w", encoding="utf-8") as f:
            json.dump(remote_info, f, ensure_ascii=False, indent=2)

        return True, remote_ver, remote_info.get("notes", "")
    except Exception as e:
        return False, ENGINE_VERSION, f"연결 실패: {e}"


class TelejobClient:
    BASE_URL = "https://www.telejob.co.kr"

    def __init__(self, timeout=30):
        self.timeout = timeout
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.opener.addheaders = [
            ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
            ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"),
            ("Accept-Language", "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"),
            ("Connection", "close"),
        ]

    def close(self):
        try:
            self.cj.clear()
        except Exception:
            pass
        self.opener = None
        self.cj = None

    def get_html(self, path):
        req = urllib.request.Request(f"{self.BASE_URL}{path}")
        with self.opener.open(req, timeout=self.timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")

    def get_csrf(self):
        req = urllib.request.Request(
            f"{self.BASE_URL}/pages/refresh-csrf",
            data=b"isajax=Y",
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        with self.opener.open(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def post_ajax(self, path, params):
        csrf = self.get_csrf()
        if csrf.get("result") != "SUCC":
            raise RuntimeError(f"CSRF 오류: {csrf}")

        payload = dict(params)
        payload["isajax"] = "Y"
        payload["_csrf"] = csrf["csrfToken"]
        payload["_csrf_header"] = csrf["headerName"]

        encoded = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.BASE_URL}{path}",
            data=encoded,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        with self.opener.open(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def login(self, user_id, user_pw):
        self.get_html("/pages/login?showTab=ROLE_CORP")
        res = self.post_ajax("/telejob_sec_login", {
            "userId": user_id,
            "userPw": user_pw,
            "userLoginType": "NORMAL",
            "userType": "ROLE_CORP",
            "target": "/corp/main",
            "failUrl": "/pages/login",
        })
        if res.get("status") != "success":
            raise RuntimeError(f"로그인 실패: {res.get('message', res)}")
        return res

    @staticmethod
    def parse_posts(html):
        posts = []
        seen = set()
        for tr_m in re.finditer(r"<tr>([\s\S]*?)</tr>", html):
            tr = tr_m.group(1)
            seq_m = re.search(r"fnCorpWantedView\('(\d+)'\)", tr)
            if not seq_m:
                seq_m = re.search(r"fnWanted(?:Modify|Open|Delete|Copy)\('(\d+)'", tr)
            if not seq_m:
                continue
            wi_seq = seq_m.group(1)
            if wi_seq in seen:
                continue
            seen.add(wi_seq)

            sub_m = re.search(r'<p class="preview_sub_copy">([\s\S]*?)</p>', tr)
            main_m = re.search(r'<p class="preview_main_copy[^"]*"[^>]*>([\s\S]*?)</p>', tr)
            dates = re.findall(r'<p class="respond_tdtext(?: sub)? spoca font14">([^<]+)</p>', tr)

            posts.append({
                "wiSeq": wi_seq,
                "subTitle": sub_m.group(1).strip() if sub_m else "",
                "title": main_m.group(1).strip() if main_m else "",
                "modDate": " ".join(d.strip() for d in dates) if dates else "",
            })
        return posts

    def get_active_posts(self):
        html = self.get_html("/corp/wantedmgr/main?currTab=t02")
        return self.parse_posts(html)

    def get_stored_posts(self):
        html = self.get_html("/corp/wantedmgr/main?currTab=t03")
        return self.parse_posts(html)

    def copy_post(self, wi_seq):
        res = self.post_ajax("/corp/wantedmgr/setWantedCopy", {"wiSeq": wi_seq})
        if res.get("result") != "SUCC":
            raise RuntimeError(f"복제 실패({wi_seq}): {res}")
        return res

    def delete_post(self, wi_seq):
        res = self.post_ajax("/corp/wantedmgr/setWantedDelete", {"wiSeq": wi_seq})
        if res.get("result") != "SUCC":
            raise RuntimeError(f"삭제 실패({wi_seq}): {res}")
        return res

    def open_post(self, wi_seq):
        res = self.post_ajax("/corp/wantedmgr/setWantedOpenProc", {"wiSeq": wi_seq, "wiOpenYn": "Y"})
        if res.get("result") != "SUCC":
            raise RuntimeError(f"게재 실패({wi_seq}): {res}")
        return res

    def update_post_preset_and_design(self, wi_seq, preset=None, image_path=None):
        html = self.get_html(f"/corp/wanted/modifyFrom?wiSeq={wi_seq}&pgType=04")
        form_m = re.search(r'<form[^>]*id="wantedInfoVO"[\s\S]*?</form>', html)
        if not form_m:
            raise RuntimeError("수정 폼 로드 실패")
        form_html = form_m.group(0)

        fields = []
        for inp_m in re.finditer(r"<input([^>]*)>", form_html):
            attrs = inp_m.group(1)
            name_m = re.search(r'name="([^"]+)"', attrs)
            if not name_m:
                continue
            name = name_m.group(1)
            type_m = re.search(r'type="([^"]+)"', attrs)
            inp_type = (type_m.group(1) if type_m else "text").lower()
            if inp_type == "file":
                continue
            if inp_type in ("radio", "checkbox") and "checked" not in attrs:
                continue
            val_m = re.search(r'value="([^"]*)"', attrs)
            val = val_m.group(1) if val_m else ""

            if preset:
                if name == "wiSubject" and preset.get("title"):
                    val = preset["title"][:27]
                elif name == "wiRp" and preset.get("subTitle"):
                    val = preset["subTitle"][:14]
                elif name == "wiKeyword" and preset.get("keyword"):
                    val = preset["keyword"][:27]

            fields.append((name, val))

        for sel_m in re.finditer(r'<select[^>]*name="([^"]+)"[^>]*>([\s\S]*?)</select>', form_html):
            name = sel_m.group(1)
            options_html = sel_m.group(2)
            opt_m = re.search(r'<option[^>]*value="([^"]*)"[^>]*selected', options_html)
            if not opt_m:
                opt_m = re.search(r'<option[^>]*selected[^>]*value="([^"]*)"', options_html)
            if opt_m:
                fields.append((name, opt_m.group(1)))

        for ta_m in re.finditer(r'<textarea[^>]*name="([^"]+)"[^>]*>([\s\S]*?)</textarea>', form_html):
            fields.append((ta_m.group(1), ta_m.group(2)))

        csrf = self.get_csrf()
        fields.append(("isajax", "Y"))
        fields.append(("_csrf", csrf["csrfToken"]))
        fields.append(("_csrf_header", csrf["headerName"]))

        boundary = f"----TelejobUpdateBoundary{uuid.uuid4().hex}"
        parts = []
        for k, v in fields:
            parts.append(f"--{boundary}\r\n".encode("utf-8"))
            parts.append(f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8"))
        for file_field in ("wiDocFile", "wiHwpFile", "wiExcelFile"):
            parts.append(f"--{boundary}\r\n".encode("utf-8"))
            parts.append(
                f'Content-Disposition: form-data; name="{file_field}"; filename=""\r\n'
                f"Content-Type: application/octet-stream\r\n\r\n\r\n".encode("utf-8")
            )
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        body = b"".join(parts)

        req = urllib.request.Request(
            f"{self.BASE_URL}/corp/wanted/updateWanted",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRF-TOKEN": csrf["csrfToken"],
            },
        )
        with self.opener.open(req, timeout=self.timeout) as resp:
            res = json.loads(resp.read().decode("utf-8"))
        if res.get("result") != "SUCC":
            raise RuntimeError(f"공고 수정 실패: {res}")
        return True


class TelejobApp:
    # HASTE Monotone Dark Palette
    BG_MAIN = "#09090B"
    BG_CARD = "#121215"
    BG_INPUT = "#18181B"
    BORDER = "#27272A"
    FG_PRIMARY = "#FAFAFA"
    FG_SECONDARY = "#A1A1AA"
    FG_MUTED = "#71717A"
    ACCENT_WHITE = "#F4F4F5"
    ACCENT_GREEN = "#10B981"

    def __init__(self, root):
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry("920x680")
        self.root.minsize(880, 640)
        self.root.configure(bg=self.BG_MAIN)

        self.cfg = load_config()
        if self.cfg.get("windows_startup", True):
            set_windows_startup(True)

        self.is_running = False
        self.is_working = False
        self.next_run_timestamp = None
        self.success_count = 0
        self.fail_count = 0

        self._setup_styles()
        self._build_ui()
        self.log(f"SYSTEM READY  |  v{ENGINE_VERSION}  |  DIRECT ENGINE (0% LEAK)")

        threading.Thread(target=self.fetch_current_status_only, daemon=True).start()

        if self.cfg.get("auto_start", True):
            self.start_scheduler()

        self._tick_timer()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Dark.Treeview",
            background=self.BG_CARD,
            foreground=self.FG_PRIMARY,
            fieldbackground=self.BG_CARD,
            borderwidth=0,
            rowheight=28,
            font=("맑은 고딕", 9)
        )
        style.configure(
            "Dark.Treeview.Heading",
            background="#18181B",
            foreground=self.FG_SECONDARY,
            borderwidth=0,
            relief="flat",
            font=("맑은 고딕", 9, "bold")
        )
        style.map(
            "Dark.Treeview",
            background=[("selected", "#27272A")],
            foreground=[("selected", "#FFFFFF")]
        )
        style.map(
            "Dark.Treeview.Heading",
            background=[("active", "#27272A")]
        )

    def _card(self, parent, pady=(0, 8)):
        outer = tk.Frame(parent, bg=self.BORDER, padx=1, pady=1)
        outer.pack(fill="x", padx=16, pady=pady)
        inner = tk.Frame(outer, bg=self.BG_CARD, padx=14, pady=10)
        inner.pack(fill="both", expand=True)
        return inner

    def _btn(self, parent, text, command, primary=False, width=None):
        bg = self.ACCENT_WHITE if primary else "#18181B"
        fg = "#09090B" if primary else self.FG_PRIMARY
        abg = "#D4D4D8" if primary else "#27272A"
        border_wrap = tk.Frame(parent, bg=self.BORDER if not primary else self.ACCENT_WHITE, padx=1, pady=1)
        btn = tk.Button(
            border_wrap, text=text, command=command,
            bg=bg, fg=fg, activebackground=abg, activeforeground=fg,
            font=("맑은 고딕", 9, "bold"), relief="flat", bd=0,
            padx=12, pady=4, cursor="hand2", width=width
        )
        btn.pack(fill="both")
        return border_wrap, btn

    def _entry(self, parent, var, width=12, show=None):
        wrap = tk.Frame(parent, bg=self.BORDER, padx=1, pady=1)
        ent = tk.Entry(
            wrap, textvariable=var, width=width, show=show,
            bg=self.BG_INPUT, fg=self.FG_PRIMARY, insertbackground=self.FG_PRIMARY,
            relief="flat", bd=3, font=("맑은 고딕", 9)
        )
        ent.pack()
        return wrap

    def _build_ui(self):
        # 1. 상단 미니멀 헤더 + 우측 단색 액션바
        top = tk.Frame(self.root, bg=self.BG_MAIN, padx=16, pady=12)
        top.pack(fill="x")

        title_lbl = tk.Label(
            top, text="TELEJOB AUTO AD", font=("Segoe UI", 13, "bold"),
            fg=self.FG_PRIMARY, bg=self.BG_MAIN
        )
        title_lbl.pack(side="left")

        ver_lbl = tk.Label(
            top, text=f"v{ENGINE_VERSION}", font=("Segoe UI", 9),
            fg=self.FG_MUTED, bg=self.BG_MAIN
        )
        ver_lbl.pack(side="left", padx=(6, 18))

        self.status_dot = tk.Label(
            top, text="●", font=("Segoe UI", 10), fg=self.ACCENT_GREEN, bg=self.BG_MAIN
        )
        self.status_dot.pack(side="left")

        self.status_text = tk.Label(
            top, text="가동 중", font=("맑은 고딕", 9, "bold"),
            fg=self.FG_PRIMARY, bg=self.BG_MAIN
        )
        self.status_text.pack(side="left", padx=(4, 14))

        self.countdown_label = tk.Label(
            top, text="다음 실행  --:--", font=("맑은 고딕", 9),
            fg=self.FG_SECONDARY, bg=self.BG_MAIN
        )
        self.countdown_label.pack(side="left")

        self.stats_label = tk.Label(
            top, text="성공 0  ·  실패 0", font=("맑은 고딕", 9),
            fg=self.FG_MUTED, bg=self.BG_MAIN
        )
        self.stats_label.pack(side="left", padx=16)

        w_ota, _ = self._btn(top, "업데이트 확인", self.manual_ota_check)
        w_ota.pack(side="right", padx=(6, 0))

        w_site, _ = self._btn(top, "실제 등록 사이트 열기 ↗", self.open_public_board)
        w_site.pack(side="right")

        # 2. 설정 & 실행 컨트롤 통합 바
        ctrl = self._card(self.root)

        r1 = tk.Frame(ctrl, bg=self.BG_CARD)
        r1.pack(fill="x", pady=(0, 8))

        tk.Label(r1, text="계정", fg=self.FG_SECONDARY, bg=self.BG_CARD, font=("맑은 고딕", 9)).pack(side="left")
        self.id_var = tk.StringVar(value=self.cfg["user_id"])
        self._entry(r1, self.id_var, width=12).pack(side="left", padx=(6, 6))

        self.pw_var = tk.StringVar(value=self.cfg["user_pw"])
        self._entry(r1, self.pw_var, width=11, show="*").pack(side="left", padx=(0, 16))

        tk.Label(r1, text="주기(분)", fg=self.FG_SECONDARY, bg=self.BG_CARD, font=("맑은 고딕", 9)).pack(side="left")
        self.interval_var = tk.StringVar(value=str(self.cfg["interval_minutes"]))
        self._entry(r1, self.interval_var, width=5).pack(side="left", padx=(6, 16))

        tk.Label(r1, text="가동 시간", fg=self.FG_SECONDARY, bg=self.BG_CARD, font=("맑은 고딕", 9)).pack(side="left")
        self.start_h_var = tk.StringVar(value=str(self.cfg["start_hour"]))
        self._entry(r1, self.start_h_var, width=3).pack(side="left", padx=(6, 2))
        tk.Label(r1, text="~", fg=self.FG_MUTED, bg=self.BG_CARD).pack(side="left", padx=2)
        self.end_h_var = tk.StringVar(value=str(self.cfg["end_hour"]))
        self._entry(r1, self.end_h_var, width=3).pack(side="left", padx=2)
        tk.Label(r1, text="시", fg=self.FG_MUTED, bg=self.BG_CARD, font=("맑은 고딕", 9)).pack(side="left", padx=(2, 14))

        w_save, _ = self._btn(r1, "설정 저장", self.on_save_config)
        w_save.pack(side="right")

        # 구분선
        tk.Frame(ctrl, bg=self.BORDER, height=1).pack(fill="x", pady=4)

        r2 = tk.Frame(ctrl, bg=self.BG_CARD)
        r2.pack(fill="x", pady=(4, 0))

        self.win_startup_var = tk.BooleanVar(value=is_windows_startup_enabled())
        tk.Checkbutton(
            r2, text="PC 부팅 시 자동 실행",
            variable=self.win_startup_var, command=self.on_save_config,
            fg=self.FG_SECONDARY, bg=self.BG_CARD, selectcolor=self.BG_MAIN,
            activebackground=self.BG_CARD, activeforeground=self.FG_PRIMARY,
            font=("맑은 고딕", 9)
        ).pack(side="left")

        self.abc_rot_var = tk.BooleanVar(value=self.cfg.get("use_abc_rotation", True))
        tk.Checkbutton(
            r2, text="A · B · C 문구 순차 로테이션 (디자인 고정)",
            variable=self.abc_rot_var, command=self.on_save_config,
            fg=self.FG_SECONDARY, bg=self.BG_CARD, selectcolor=self.BG_MAIN,
            activebackground=self.BG_CARD, activeforeground=self.FG_PRIMARY,
            font=("맑은 고딕", 9)
        ).pack(side="left", padx=(14, 0))

        w_toggle, self.toggle_btn = self._btn(r2, "일시 정지", self.toggle_scheduler)
        w_toggle.pack(side="right", padx=(6, 0))

        w_run1, _ = self._btn(r2, "즉시 1회 실행", self.run_once_manual, primary=True)
        w_run1.pack(side="right", padx=(6, 0))

        w_run3, _ = self._btn(r2, "3건 일괄 갱신", self.run_all_three_now)
        w_run3.pack(side="right", padx=(6, 0))

        w_ref, _ = self._btn(r2, "새로고침", lambda: threading.Thread(target=self.fetch_current_status_only, daemon=True).start())
        w_ref.pack(side="right")

        # 3. A/B/C 로테이션 프리셋 카드
        preset_card = self._card(self.root)
        hdr_p = tk.Frame(preset_card, bg=self.BG_CARD)
        hdr_p.pack(fill="x", pady=(0, 6))
        tk.Label(
            hdr_p, text="ROTATION PRESETS", font=("Segoe UI", 8, "bold"),
            fg=self.FG_MUTED, bg=self.BG_CARD
        ).pack(side="left")
        tk.Label(
            hdr_p, text="부제목(14자) · 제목(27자) · 키워드(5개/27자)", font=("맑은 고딕", 8),
            fg=self.FG_MUTED, bg=self.BG_CARD
        ).pack(side="right")

        self.preset_vars = []
        presets = self.cfg.get("presets", DEFAULT_PRESETS)
        for i in range(3):
            p = presets[i] if i < len(presets) else DEFAULT_PRESETS[i]
            prow = tk.Frame(preset_card, bg=self.BG_CARD)
            prow.pack(fill="x", pady=2)

            tk.Label(
                prow, text=f"{chr(65+i)}", fg=self.FG_PRIMARY, bg="#27272A",
                font=("Segoe UI", 9, "bold"), width=3, pady=2
            ).pack(side="left", padx=(0, 8))

            sub_v = tk.StringVar(value=p.get("subTitle", ""))
            self._entry(prow, sub_v, width=16).pack(side="left", padx=(0, 6))

            title_v = tk.StringVar(value=p.get("title", ""))
            self._entry(prow, title_v, width=38).pack(side="left", padx=(0, 6))

            kw_v = tk.StringVar(value=p.get("keyword", ""))
            self._entry(prow, kw_v, width=34).pack(side="left")

            self.preset_vars.append({"subTitle": sub_v, "title": title_v, "keyword": kw_v})

        # 4. 실시간 게재 공고 목록 카드
        board_card = self._card(self.root)
        hdr_b = tk.Frame(board_card, bg=self.BG_CARD)
        hdr_b.pack(fill="x", pady=(0, 6))
        tk.Label(
            hdr_b, text="ACTIVE LISTINGS (3)", font=("Segoe UI", 8, "bold"),
            fg=self.FG_MUTED, bg=self.BG_CARD
        ).pack(side="left")
        tk.Label(
            hdr_b, text="항목 더블클릭 시 해당 공고 웹페이지 열기", font=("맑은 고딕", 8),
            fg=self.FG_MUTED, bg=self.BG_CARD
        ).pack(side="right")

        cols = ("rank", "wiSeq", "subTitle", "title", "modDate")
        self.tree = ttk.Treeview(board_card, columns=cols, show="headings", height=3, style="Dark.Treeview")
        self.tree.heading("rank", text="순위")
        self.tree.heading("wiSeq", text="공고번호")
        self.tree.heading("subTitle", text="부제목")
        self.tree.heading("title", text="채용공고 제목")
        self.tree.heading("modDate", text="최근 등록일시")

        self.tree.column("rank", width=55, anchor="center")
        self.tree.column("wiSeq", width=95, anchor="center")
        self.tree.column("subTitle", width=140, anchor="center")
        self.tree.column("title", width=410, anchor="w")
        self.tree.column("modDate", width=155, anchor="center")
        self.tree.pack(fill="x")
        self.tree.bind("<Double-1>", self.on_tree_double_click)

        # 5. 하단 미니멀 콘솔 로그
        log_outer = tk.Frame(self.root, bg=self.BORDER, padx=1, pady=1)
        log_outer.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        log_inner = tk.Frame(log_outer, bg=self.BG_CARD, padx=12, pady=8)
        log_inner.pack(fill="both", expand=True)

        hdr_l = tk.Frame(log_inner, bg=self.BG_CARD)
        hdr_l.pack(fill="x", pady=(0, 4))
        tk.Label(
            hdr_l, text="SYSTEM LOG", font=("Segoe UI", 8, "bold"),
            fg=self.FG_MUTED, bg=self.BG_CARD
        ).pack(side="left")

        self.log_box = tk.Text(
            log_inner, bg="#09090B", fg="#A1A1AA", font=("Consolas", 9),
            insertbackground=self.FG_PRIMARY, relief="flat", bd=6, wrap="word"
        )
        self.log_box.pack(fill="both", expand=True)

    def open_public_board(self):
        self.log(f"웹 브라우저 열기 -> {TELEJOB_PUBLIC_LIST_URL}")
        webbrowser.open(TELEJOB_PUBLIC_LIST_URL)

    def on_tree_double_click(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        vals = self.tree.item(selected[0], "values")
        if vals and len(vals) >= 2:
            wi_seq = vals[1]
            url = f"{TELEJOB_POST_VIEW_URL}{wi_seq}"
            self.log(f"공고 상세페이지 열기 (#{wi_seq}) -> {url}")
            webbrowser.open(url)

    def log(self, msg):
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        full_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ui_line = f"[{now_str}]  {msg}\n"
        file_line = f"[{full_str}] {msg}\n"

        log_file = os.path.join(LOG_DIR, f"telejob_{datetime.datetime.now().strftime('%Y-%m-%d')}.log")
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(file_line)
        except Exception:
            pass

        def _append():
            lines = int(self.log_box.index("end-1c").split(".")[0])
            if lines > 400:
                self.log_box.delete("1.0", "80.0")
            self.log_box.insert("end", ui_line)
            self.log_box.see("end")

        self.root.after(0, _append)

    def manual_ota_check(self):
        def _worker():
            self.log("원격 업데이트 확인 중...")
            updated, ver, notes = check_and_download_ota()
            if updated:
                self.log(f"신규 버전(v{ver}) 적용 완료 ({notes}) -> 재시작합니다.")
                time.sleep(1)
                self._restart_self()
            else:
                self.log(f"현재 최신 버전(v{ENGINE_VERSION})입니다. ({notes})")

        threading.Thread(target=_worker, daemon=True).start()

    def _restart_self(self):
        def _do():
            global _mutex_handle
            if _mutex_handle:
                ctypes.windll.kernel32.CloseHandle(_mutex_handle)
                _mutex_handle = None
            self.root.destroy()
            subprocess.Popen([sys.executable] + sys.argv + ["--restart"], cwd=BASE_DIR)
            os._exit(0)
        self.root.after(0, _do)

    def on_save_config(self):
        try:
            interval = max(1, int(self.interval_var.get().strip()))
            sh = max(0, min(23, int(self.start_h_var.get().strip())))
            eh = max(1, min(24, int(self.end_h_var.get().strip())))
        except ValueError:
            messagebox.showwarning("입력 확인", "주기와 시간은 숫자로 입력해 주세요.")
            return

        self.cfg["user_id"] = self.id_var.get().strip()
        self.cfg["user_pw"] = self.pw_var.get().strip()
        self.cfg["interval_minutes"] = interval
        self.cfg["start_hour"] = sh
        self.cfg["end_hour"] = eh
        self.cfg["use_abc_rotation"] = bool(self.abc_rot_var.get())
        self.cfg["windows_startup"] = bool(self.win_startup_var.get())
        set_windows_startup(self.cfg["windows_startup"])

        new_presets = []
        for i, pv in enumerate(self.preset_vars):
            new_presets.append({
                "name": f"{chr(65+i)}",
                "subTitle": pv["subTitle"].get().strip()[:14],
                "title": pv["title"].get().strip()[:27],
                "keyword": pv["keyword"].get().strip()[:27],
            })
        self.cfg["presets"] = new_presets

        save_config(self.cfg)
        self.log(
            f"설정 저장 완료 (주기 {interval}분 · 부팅 자동실행 {'ON' if self.cfg['windows_startup'] else 'OFF'} · A/B/C 로테이션 {'ON' if self.cfg['use_abc_rotation'] else 'OFF'})"
        )

    def update_table(self, posts):
        def _update():
            for item in self.tree.get_children():
                self.tree.delete(item)
            for idx, p in enumerate(posts, 1):
                self.tree.insert("", "end", values=(
                    f"#{idx}", p["wiSeq"], p["subTitle"], p["title"], p["modDate"]
                ))
        self.root.after(0, _update)

    def fetch_current_status_only(self):
        client = TelejobClient()
        try:
            client.login(self.id_var.get().strip(), self.pw_var.get().strip())
            active = client.get_active_posts()
            self.update_table(active)
            seqs_str = " / ".join(f"#{p['wiSeq']} ({p['subTitle']})" for p in active) if active else "없음"
            self.log(f"게재 현황 동기화 완료: {seqs_str}")
        except Exception as e:
            self.log(f"조회 오류: {e}")
        finally:
            client.close()
            gc.collect()

    def start_scheduler(self):
        self.is_running = True
        self.cfg["auto_start"] = True
        save_config(self.cfg)
        self.toggle_btn.config(text="일시 정지")
        self.status_dot.config(fg=self.ACCENT_GREEN)
        self.status_text.config(text="가동 중")
        interval_sec = max(1, int(self.cfg.get("interval_minutes", 60))) * 60
        self.next_run_timestamp = time.time() + interval_sec

    def stop_scheduler(self):
        self.is_running = False
        self.cfg["auto_start"] = False
        save_config(self.cfg)
        self.next_run_timestamp = None
        self.toggle_btn.config(text="자동 시작")
        self.status_dot.config(fg="#71717A")
        self.status_text.config(text="일시 정지")
        self.countdown_label.config(text="다음 실행  정지됨")
        self.log("스케줄러 일시 정지됨")

    def toggle_scheduler(self):
        if self.is_running:
            self.stop_scheduler()
        else:
            self.on_save_config()
            self.start_scheduler()
            self.log(f"스케줄러 재가동 (주기 {self.cfg.get('interval_minutes', 60)}분)")

    def run_once_manual(self):
        if self.is_working:
            self.log("작업이 이미 진행 중입니다.")
            return
        self.on_save_config()
        if self.is_running:
            interval_sec = max(1, int(self.cfg.get("interval_minutes", 60))) * 60
            self.next_run_timestamp = time.time() + interval_sec
        threading.Thread(target=self.execute_cycle, args=(True,), daemon=True).start()

    def run_all_three_now(self):
        if self.is_working:
            self.log("작업이 이미 진행 중입니다.")
            return
        self.on_save_config()
        if self.is_running:
            interval_sec = max(1, int(self.cfg.get("interval_minutes", 60))) * 60
            self.next_run_timestamp = time.time() + interval_sec

        def _batch():
            self.log("3건 일괄 갱신 시작 (A · B · C 연속 적용)")
            for step_i in range(3):
                self.execute_cycle(is_manual=True)
                if step_i < 2:
                    time.sleep(1.2)
            self.log("3건 일괄 갱신 완료")

        threading.Thread(target=_batch, daemon=True).start()

    def execute_cycle(self, is_manual=False):
        if self.is_working:
            return
        self.is_working = True
        self.root.after(0, lambda: self.status_text.config(text="실행 중..."))

        if self.cfg.get("auto_ota_update", True):
            updated, ver, notes = check_and_download_ota()
            if updated:
                self.log(f"원격 업데이트(v{ver}) 적용 -> 재시작")
                time.sleep(1.0)
                self._restart_self()
                return

        client = TelejobClient()
        try:
            now_hour = datetime.datetime.now().hour
            sh = int(self.cfg.get("start_hour", 4))
            eh = int(self.cfg.get("end_hour", 24))

            if not is_manual and not (sh <= now_hour < eh):
                self.log(f"비작업 시간대({now_hour}시) 대기")
                return

            client.login(self.cfg["user_id"], self.cfg["user_pw"])
            active_before = client.get_active_posts()
            stored_before = client.get_stored_posts()

            if not active_before and not stored_before:
                raise RuntimeError("등록된 원본 공고가 없습니다.")

            source_seq = active_before[0]["wiSeq"] if active_before else stored_before[0]["wiSeq"]
            client.copy_post(source_seq)

            deleted_seq = "-"
            if len(active_before) >= 3:
                deleted_seq = active_before[-1]["wiSeq"]
                client.delete_post(deleted_seq)

            stored_after_copy = client.get_stored_posts()
            if not stored_after_copy:
                raise RuntimeError("복제 공고 조회 실패")
            new_seq = stored_after_copy[0]["wiSeq"]

            presets = self.cfg.get("presets", DEFAULT_PRESETS)
            next_idx = (int(self.cfg.get("last_preset_index", -1)) + 1) % len(presets)
            chosen_preset = presets[next_idx] if self.cfg.get("use_abc_rotation", True) else None

            tag_name = "기본"
            if chosen_preset:
                tag_name = f"{chr(65+next_idx)}안({chosen_preset['subTitle']})"
                client.update_post_preset_and_design(new_seq, preset=chosen_preset, image_path=None)
                self.cfg["last_preset_index"] = next_idx
                save_config(self.cfg)

            client.open_post(new_seq)

            active_after = client.get_active_posts()
            self.update_table(active_after)
            self.success_count += 1
            self.log(f"갱신 완료  |  복제 #{source_seq} -> 삭제 #{deleted_seq} -> 신규 #{new_seq} [{tag_name}] 게재")

        except Exception as e:
            self.fail_count += 1
            self.log(f"오류 발생: {e}")
        finally:
            client.close()
            del client
            gc.collect()
            self.is_working = False
            self.root.after(0, self._update_header_labels)

    def _update_header_labels(self):
        if self.is_running:
            self.status_dot.config(fg=self.ACCENT_GREEN)
            self.status_text.config(text="가동 중")
        else:
            self.status_dot.config(fg="#71717A")
            self.status_text.config(text="일시 정지")
        self.stats_label.config(text=f"성공 {self.success_count}  ·  실패 {self.fail_count}")

    def _tick_timer(self):
        if self.is_running and self.next_run_timestamp is not None:
            rem = int(self.next_run_timestamp - time.time())
            if rem <= 0:
                interval_sec = max(1, int(self.cfg.get("interval_minutes", 60))) * 60
                self.next_run_timestamp = time.time() + interval_sec
                if not self.is_working:
                    threading.Thread(target=self.execute_cycle, args=(False,), daemon=True).start()
            else:
                mins, secs = divmod(rem, 60)
                hrs, mins = divmod(mins, 60)
                if hrs > 0:
                    self.countdown_label.config(text=f"다음 실행  {hrs:02d}:{mins:02d}:{secs:02d}")
                else:
                    self.countdown_label.config(text=f"다음 실행  {mins:02d}분 {secs:02d}초")
        self.root.after(1000, self._tick_timer)


def main():
    acquire_single_instance_lock()
    root = tk.Tk()
    app = TelejobApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
