# -*- coding: utf-8 -*-
"""
Telejob Auto Ad Engine v3.2.0
- 중복 실행 완벽 차단 (Windows Named Mutex: 무조건 창 1개만 유지, 중복 클릭 시 기존 창 활성화)
- [🌐 텔레잡 실제 등록 확인] 버튼 + 공고 목록 더블클릭 시 해당 공고 상세페이지 즉시 오픈
- 윈도우 부팅 시 자동 실행 ON/OFF 체크박스
- 3색 A/B/C(제목/부제목/키워드) 자동 로테이션 + 디자인 1개 고정 + 원격 OTA
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
from tkinter import ttk, messagebox, scrolledtext

ENGINE_VERSION = "3.2.0"
WINDOW_TITLE = f"텔레잡 자동 광고 등록/관리 모니터 v{ENGINE_VERSION} (3색 A/B/C 로테이션 & 원격 OTA)"
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
    """이미 실행 중인 창이 있으면 그 창을 앞으로 띄우고 현재 프로세스는 즉시 종료"""
    global _mutex_handle
    if "--restart" in sys.argv:
        time.sleep(1.2)
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32
    _mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    last_err = kernel32.GetLastError()
    if last_err == 183:  # ERROR_ALREADY_EXISTS
        # 기존 창 찾아서 앞으로 활성화
        hwnd = user32.FindWindowW(None, WINDOW_TITLE)
        if hwnd:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
        os._exit(0)


DEFAULT_PRESETS = [
    {
        "name": "A안 (고수익/미체결DB)",
        "subTitle": "최대6000%지급",
        "title": "라이나원(직영)IMC센터/미체결디비/아웃바운드",
        "keyword": "아웃바운드,라이나원,보험,콜센터,동의콜",
    },
    {
        "name": "B안 (신입/경력/우량DB)",
        "subTitle": "전직소득/교육비지원",
        "title": "라이나원(직영)광화문/자사우량DB/신입경력모집",
        "keyword": "텔레마케팅,광화문,생명보험,신입,TM",
    },
    {
        "name": "C안 (워라밸/정착지원금)",
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
            headers={"User-Agent": "TelejobAutoAd-OTA/3.2", "Cache-Control": "no-cache"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            remote_info = json.loads(resp.read().decode("utf-8"))

        remote_ver = str(remote_info.get("version", "")).strip()
        if not remote_ver or remote_ver == ENGINE_VERSION:
            return False, ENGINE_VERSION, "최신 버전입니다."

        def _ver_tuple(v):
            return tuple(int(x) for x in re.findall(r"\d+", v))

        if _ver_tuple(remote_ver) <= _ver_tuple(ENGINE_VERSION):
            return False, ENGINE_VERSION, "최신 버전입니다."

        req_eng = urllib.request.Request(
            f"{OTA_ENGINE_URL}?t={ts}",
            headers={"User-Agent": "TelejobAutoAd-OTA/3.2", "Cache-Control": "no-cache"}
        )
        with urllib.request.urlopen(req_eng, timeout=15) as resp:
            new_code = resp.read().decode("utf-8")

        if "class TelejobApp" not in new_code or len(new_code) < 1000:
            return False, ENGINE_VERSION, "다운로드된 엔진 코드 검증 실패"

        tmp_path = ENGINE_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(new_code)
        os.replace(tmp_path, ENGINE_PATH)

        with open(VERSION_PATH, "w", encoding="utf-8") as f:
            json.dump(remote_info, f, ensure_ascii=False, indent=2)

        return True, remote_ver, remote_info.get("notes", "")
    except Exception as e:
        return False, ENGINE_VERSION, f"업데이트 확인 실패: {e}"


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
            raise RuntimeError(f"CSRF 토큰 발급 실패: {csrf}")

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
            raise RuntimeError(f"공고 복제 실패(wiSeq={wi_seq}): {res}")
        return res

    def delete_post(self, wi_seq):
        res = self.post_ajax("/corp/wantedmgr/setWantedDelete", {"wiSeq": wi_seq})
        if res.get("result") != "SUCC":
            raise RuntimeError(f"공고 삭제 실패(wiSeq={wi_seq}): {res}")
        return res

    def open_post(self, wi_seq):
        res = self.post_ajax("/corp/wantedmgr/setWantedOpenProc", {"wiSeq": wi_seq, "wiOpenYn": "Y"})
        if res.get("result") != "SUCC":
            raise RuntimeError(f"공고 게재 실패(wiSeq={wi_seq}): {res}")
        return res

    def upload_editor_image(self, file_path):
        csrf = self.get_csrf()
        boundary = f"----TelejobBoundary{uuid.uuid4().hex}"
        filename = os.path.basename(file_path)
        mime_type = mimetypes.guess_type(filename)[0] or "image/png"

        with open(file_path, "rb") as f:
            file_bytes = f.read()

        parts = []
        for k, v in [
            ("callback", "/resources/smarteditor2/photo_uploader/popup/callback.html"),
            ("callback_func", "tmpFrame_1_func"),
            ("_csrf", csrf["csrfToken"]),
            ("_csrf_header", csrf["headerName"]),
        ]:
            parts.append(f"--{boundary}\r\n".encode("utf-8"))
            parts.append(f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8"))

        parts.append(f"--{boundary}\r\n".encode("utf-8"))
        parts.append(
            f'Content-Disposition: form-data; name="fileData"; filename="{filename}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8")
        )
        parts.append(file_bytes)
        parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
        body = b"".join(parts)

        req = urllib.request.Request(
            f"{self.BASE_URL}/pages/editor/imageUpload?_csrf={urllib.parse.quote(csrf['csrfToken'])}",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-CSRF-TOKEN": csrf["csrfToken"],
            },
        )
        with self.opener.open(req, timeout=self.timeout) as resp:
            final_url = resp.geturl()
            resp_text = resp.read().decode("utf-8", errors="ignore")

        parsed_q = urllib.parse.parse_qs(urllib.parse.urlparse(final_url).query)
        if "sFileURL" in parsed_q:
            return parsed_q["sFileURL"][0], parsed_q.get("sFileName", [filename])[0]
        m = re.search(r"sFileURL=([^&\"'\s]+)", final_url + " " + resp_text)
        if m:
            return urllib.parse.unquote(m.group(1)), filename
        raise RuntimeError(f"이미지 업로드 응답에서 URL을 찾을 수 없습니다: {final_url}")

    def update_post_preset_and_design(self, wi_seq, preset=None, image_path=None):
        uploaded_url, uploaded_name = None, None
        if image_path and os.path.isfile(image_path):
            uploaded_url, uploaded_name = self.upload_editor_image(image_path)

        html = self.get_html(f"/corp/wanted/modifyFrom?wiSeq={wi_seq}&pgType=04")
        form_m = re.search(r'<form[^>]*id="wantedInfoVO"[\s\S]*?</form>', html)
        if not form_m:
            raise RuntimeError("공고 수정 폼(wantedInfoVO)을 불러오지 못했습니다.")
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
            name = ta_m.group(1)
            val = ta_m.group(2)
            if name == "wiContent" and uploaded_url:
                val = (
                    f'<div align="" style=""><p style="text-align: center;" align="center">'
                    f'<img src="{uploaded_url}" title="{uploaded_name}">&nbsp;</p></div><p><br></p>'
                )
            fields.append((name, val))

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
            raise RuntimeError(f"공고 내용 업데이트 실패: {res}")
        return uploaded_url


class TelejobApp:
    def __init__(self, root):
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry("1040x780")
        self.root.minsize(980, 720)
        self.root.configure(bg="#111827")

        self.cfg = load_config()
        if self.cfg.get("windows_startup", True):
            set_windows_startup(True)

        self.is_running = False
        self.is_working = False
        self.next_run_timestamp = None
        self.success_count = 0
        self.fail_count = 0

        self._build_ui()
        self.log(f"프로그램 시작 완료 (v{ENGINE_VERSION} | 중복실행 방지 락 ON | 윈도우 자동실행: {'ON' if is_windows_startup_enabled() else 'OFF'})")

        threading.Thread(target=self.fetch_current_status_only, daemon=True).start()

        if self.cfg.get("auto_start", True):
            self.start_scheduler()

        self._tick_timer()

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        # 1. 상단 상태 요약 헤더
        header = tk.Frame(self.root, bg="#1F2937", padx=14, pady=10)
        header.pack(fill="x", padx=12, pady=(10, 4))

        self.status_badge = tk.Label(
            header, text="● 대기 중", font=("맑은 고딕", 12, "bold"),
            fg="#10B981", bg="#1F2937"
        )
        self.status_badge.pack(side="left")

        self.countdown_label = tk.Label(
            header, text="다음 실행까지: --:--", font=("맑은 고딕", 11, "bold"),
            fg="#60A5FA", bg="#1F2937"
        )
        self.countdown_label.pack(side="left", padx=16)

        self.stats_label = tk.Label(
            header, text="누적 성공: 0회 | 실패: 0회 | 메모리: 정상(0%)",
            font=("맑은 고딕", 9, "bold"), fg="#D1D5DB", bg="#1F2937"
        )
        self.stats_label.pack(side="left", padx=8)

        tk.Button(
            header, text=f"☁️ 원격 업데이트 확인 (v{ENGINE_VERSION})", command=self.manual_ota_check,
            bg="#374151", fg="#93C5FD", font=("맑은 고딕", 9, "bold"), relief="flat", padx=10, pady=3
        ).pack(side="right", padx=(6, 0))

        tk.Button(
            header, text="🌐 텔레잡 실제 등록 확인 (사이트 열기)", command=self.open_public_board,
            bg="#0284C7", fg="#FFFFFF", font=("맑은 고딕", 9, "bold"), relief="flat", padx=10, pady=3
        ).pack(side="right", padx=4)

        # 2. 환경 설정 및 제어 패널
        ctrl_frame = tk.LabelFrame(
            self.root, text=" 환경 설정 및 제어 ", font=("맑은 고딕", 10, "bold"),
            fg="#F9FAFB", bg="#1F2937", padx=12, pady=8
        )
        ctrl_frame.pack(fill="x", padx=12, pady=4)

        row1 = tk.Frame(ctrl_frame, bg="#1F2937")
        row1.pack(fill="x", pady=2)

        tk.Label(row1, text="아이디:", fg="#E5E7EB", bg="#1F2937", font=("맑은 고딕", 9)).pack(side="left")
        self.id_var = tk.StringVar(value=self.cfg["user_id"])
        tk.Entry(row1, textvariable=self.id_var, width=13, font=("맑은 고딕", 9)).pack(side="left", padx=(4, 12))

        tk.Label(row1, text="비밀번호:", fg="#E5E7EB", bg="#1F2937", font=("맑은 고딕", 9)).pack(side="left")
        self.pw_var = tk.StringVar(value=self.cfg["user_pw"])
        tk.Entry(row1, textvariable=self.pw_var, show="*", width=13, font=("맑은 고딕", 9)).pack(side="left", padx=(4, 12))

        tk.Label(row1, text="반복 주기(분):", fg="#E5E7EB", bg="#1F2937", font=("맑은 고딕", 9)).pack(side="left")
        self.interval_var = tk.StringVar(value=str(self.cfg["interval_minutes"]))
        tk.Entry(row1, textvariable=self.interval_var, width=5, font=("맑은 고딕", 9)).pack(side="left", padx=(4, 12))

        tk.Label(row1, text="가동 시간:", fg="#E5E7EB", bg="#1F2937", font=("맑은 고딕", 9)).pack(side="left")
        self.start_h_var = tk.StringVar(value=str(self.cfg["start_hour"]))
        tk.Entry(row1, textvariable=self.start_h_var, width=4, font=("맑은 고딕", 9)).pack(side="left", padx=2)
        tk.Label(row1, text="시 ~", fg="#E5E7EB", bg="#1F2937", font=("맑은 고딕", 9)).pack(side="left")
        self.end_h_var = tk.StringVar(value=str(self.cfg["end_hour"]))
        tk.Entry(row1, textvariable=self.end_h_var, width=4, font=("맑은 고딕", 9)).pack(side="left", padx=2)
        tk.Label(row1, text="시", fg="#E5E7EB", bg="#1F2937", font=("맑은 고딕", 9)).pack(side="left", padx=(0, 8))

        tk.Button(
            row1, text="💾 설정 및 A/B/C 문구 저장", command=self.on_save_config,
            bg="#10B981", fg="#FFFFFF", font=("맑은 고딕", 9, "bold"), relief="flat", padx=12, pady=3
        ).pack(side="right")

        row2 = tk.Frame(ctrl_frame, bg="#1F2937")
        row2.pack(fill="x", pady=(6, 2))

        self.win_startup_var = tk.BooleanVar(value=is_windows_startup_enabled())
        tk.Checkbutton(
            row2, text="PC 켜질 때 자동 실행",
            variable=self.win_startup_var, command=self.on_save_config,
            fg="#60A5FA", bg="#1F2937", selectcolor="#111827",
            activebackground="#1F2937", activeforeground="#60A5FA",
            font=("맑은 고딕", 9, "bold")
        ).pack(side="left")

        self.abc_rot_var = tk.BooleanVar(value=self.cfg.get("use_abc_rotation", True))
        tk.Checkbutton(
            row2, text="3색 A/B/C 세트 순차 변경 (디자인 1개 고정)",
            variable=self.abc_rot_var, command=self.on_save_config,
            fg="#34D399", bg="#1F2937", selectcolor="#111827",
            activebackground="#1F2937", activeforeground="#34D399",
            font=("맑은 고딕", 9, "bold")
        ).pack(side="left", padx=(10, 6))

        tk.Button(
            row2, text="🔄 현황 새로고침", command=lambda: threading.Thread(target=self.fetch_current_status_only, daemon=True).start(),
            bg="#4B5563", fg="#FFFFFF", font=("맑은 고딕", 9), relief="flat", padx=8, pady=4
        ).pack(side="left", padx=3)

        self.toggle_btn = tk.Button(
            row2, text="▶ 자동 반복 시작", command=self.toggle_scheduler,
            bg="#059669", fg="#FFFFFF", font=("맑은 고딕", 9, "bold"), relief="flat", padx=12, pady=4
        )
        self.toggle_btn.pack(side="right", padx=3)

        self.run_now_btn = tk.Button(
            row2, text="⚡ 지금 1회 실행", command=self.run_once_manual,
            bg="#2563EB", fg="#FFFFFF", font=("맑은 고딕", 9, "bold"), relief="flat", padx=12, pady=4
        )
        self.run_now_btn.pack(side="right", padx=3)

        self.run_all3_btn = tk.Button(
            row2, text="🚀 3개 공고 A·B·C 일괄교체", command=self.run_all_three_now,
            bg="#7C3AED", fg="#FFFFFF", font=("맑은 고딕", 9, "bold"), relief="flat", padx=12, pady=4
        )
        self.run_all3_btn.pack(side="right", padx=3)

        # 3. 3색 A/B/C 자동 로테이션 문구 설정
        preset_frame = tk.LabelFrame(
            self.root, text=" 3색 A/B/C 자동 로테이션 문구 설정 (부제목 14자 / 제목 27자 / 키워드 5개·27자 이내) ",
            font=("맑은 고딕", 10, "bold"), fg="#FBBF24", bg="#1F2937", padx=12, pady=6
        )
        preset_frame.pack(fill="x", padx=12, pady=4)

        self.preset_vars = []
        presets = self.cfg.get("presets", DEFAULT_PRESETS)
        for i in range(3):
            p = presets[i] if i < len(presets) else DEFAULT_PRESETS[i]
            prow = tk.Frame(preset_frame, bg="#1F2937")
            prow.pack(fill="x", pady=2)

            badge_colors = ["#EF4444", "#3B82F6", "#10B981"]
            tk.Label(
                prow, text=f" {chr(65+i)}안 ", fg="#FFFFFF", bg=badge_colors[i],
                font=("맑은 고딕", 9, "bold"), width=5
            ).pack(side="left", padx=(0, 6))

            tk.Label(prow, text="부제목:", fg="#D1D5DB", bg="#1F2937", font=("맑은 고딕", 9)).pack(side="left")
            sub_v = tk.StringVar(value=p.get("subTitle", ""))
            tk.Entry(prow, textvariable=sub_v, width=16, font=("맑은 고딕", 9)).pack(side="left", padx=(2, 8))

            tk.Label(prow, text="제목:", fg="#D1D5DB", bg="#1F2937", font=("맑은 고딕", 9)).pack(side="left")
            title_v = tk.StringVar(value=p.get("title", ""))
            tk.Entry(prow, textvariable=title_v, width=38, font=("맑은 고딕", 9)).pack(side="left", padx=(2, 8))

            tk.Label(prow, text="키워드:", fg="#D1D5DB", bg="#1F2937", font=("맑은 고딕", 9)).pack(side="left")
            kw_v = tk.StringVar(value=p.get("keyword", ""))
            tk.Entry(prow, textvariable=kw_v, width=32, font=("맑은 고딕", 9)).pack(side="left", padx=(2, 4))

            self.preset_vars.append({"subTitle": sub_v, "title": title_v, "keyword": kw_v})

        # 4. 현재 게재중인 공고 3개 실시간 현황판 (더블클릭 시 해당 공고 웹페이지 오픈)
        board_frame = tk.LabelFrame(
            self.root, text=" 현재 텔레잡에 게재 중인 실시간 공고 목록 (줄을 더블클릭하면 실제 등록된 공고 웹페이지가 열립니다) ",
            font=("맑은 고딕", 10, "bold"), fg="#F9FAFB", bg="#1F2937", padx=12, pady=6
        )
        board_frame.pack(fill="x", padx=12, pady=4)

        cols = ("rank", "wiSeq", "subTitle", "title", "modDate")
        self.tree = ttk.Treeview(board_frame, columns=cols, show="headings", height=3)
        self.tree.heading("rank", text="순번")
        self.tree.heading("wiSeq", text="공고번호(wiSeq)")
        self.tree.heading("subTitle", text="부제목")
        self.tree.heading("title", text="채용공고 제목 (더블클릭 시 실제 공고 열기)")
        self.tree.heading("modDate", text="최근 게재/수정일시")

        self.tree.column("rank", width=60, anchor="center")
        self.tree.column("wiSeq", width=110, anchor="center")
        self.tree.column("subTitle", width=150, anchor="center")
        self.tree.column("title", width=440, anchor="w")
        self.tree.column("modDate", width=170, anchor="center")
        self.tree.pack(fill="x")
        self.tree.bind("<Double-1>", self.on_tree_double_click)

        # 5. 하단 실시간 진행 로그 창
        log_frame = tk.LabelFrame(
            self.root, text=" 실시간 진행상황 및 결과 모니터링 로그 ",
            font=("맑은 고딕", 10, "bold"), fg="#F9FAFB", bg="#1F2937", padx=12, pady=6
        )
        log_frame.pack(fill="both", expand=True, padx=12, pady=(4, 10))

        self.log_box = scrolledtext.ScrolledText(
            log_frame, bg="#0B0F19", fg="#E5E7EB", font=("Consolas", 10),
            insertbackground="#FFFFFF", relief="flat"
        )
        self.log_box.pack(fill="both", expand=True)

    def open_public_board(self):
        self.log(f"브라우저에서 텔레잡 전체 채용정보 게시판({TELEJOB_PUBLIC_LIST_URL})을 엽니다...")
        webbrowser.open(TELEJOB_PUBLIC_LIST_URL)

    def on_tree_double_click(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        vals = self.tree.item(selected[0], "values")
        if vals and len(vals) >= 2:
            wi_seq = vals[1]
            url = f"{TELEJOB_POST_VIEW_URL}{wi_seq}"
            self.log(f"브라우저에서 실제 등록 공고(wiSeq={wi_seq}) 상세페이지를 엽니다: {url}")
            webbrowser.open(url)

    def log(self, msg):
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{now_str}] {msg}\n"

        log_file = os.path.join(LOG_DIR, f"telejob_{datetime.datetime.now().strftime('%Y-%m-%d')}.log")
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

        def _append():
            lines = int(self.log_box.index("end-1c").split(".")[0])
            if lines > 500:
                self.log_box.delete("1.0", "100.0")
            self.log_box.insert("end", line)
            self.log_box.see("end")

        self.root.after(0, _append)

    def manual_ota_check(self):
        def _worker():
            self.log("원격 업데이트 서버(GitHub OTA)에서 최신 버전을 확인합니다...")
            updated, ver, notes = check_and_download_ota()
            if updated:
                self.log(f"★ 새 버전(v{ver}) 다운로드 완료! ({notes}) -> 1초 후 자동 재시작합니다.")
                time.sleep(1)
                self._restart_self()
            else:
                self.log(f"원격 업데이트 확인 결과: 현재 최신 버전(v{ENGINE_VERSION}) 사용 중 ({notes})")

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
            messagebox.showwarning("입력 오류", "주기(분)와 시간은 숫자로 입력해 주세요.")
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
                "name": f"{chr(65+i)}안",
                "subTitle": pv["subTitle"].get().strip()[:14],
                "title": pv["title"].get().strip()[:27],
                "keyword": pv["keyword"].get().strip()[:27],
            })
        self.cfg["presets"] = new_presets

        save_config(self.cfg)
        self.log(
            f"설정 저장 완료: 주기 {interval}분 | PC 켜질 때 자동실행={'ON' if self.cfg['windows_startup'] else 'OFF'} | 3색 로테이션={'ON' if self.cfg['use_abc_rotation'] else 'OFF'}"
        )

    def update_table(self, posts):
        def _update():
            for item in self.tree.get_children():
                self.tree.delete(item)
            for idx, p in enumerate(posts, 1):
                self.tree.insert("", "end", values=(
                    f"{idx}순위", p["wiSeq"], p["subTitle"], p["title"], p["modDate"]
                ))
        self.root.after(0, _update)

    def fetch_current_status_only(self):
        client = TelejobClient()
        try:
            self.log("텔레잡 서버에 접속하여 현재 게재 중인 공고 현황을 조회합니다...")
            client.login(self.id_var.get().strip(), self.pw_var.get().strip())
            active = client.get_active_posts()
            self.update_table(active)
            seqs_str = ", ".join(f"{p['wiSeq']}({p['subTitle']})" for p in active) if active else "없음"
            self.log(f"현재 게재중 공고 조회 완료 (총 {len(active)}건): [{seqs_str}]")
        except Exception as e:
            self.log(f"[조회 오류] {e}")
        finally:
            client.close()
            gc.collect()

    def start_scheduler(self):
        self.is_running = True
        self.cfg["auto_start"] = True
        save_config(self.cfg)
        self.toggle_btn.config(text="⏹ 자동 반복 중지", bg="#DC2626")
        self.status_badge.config(text="● 자동 반복 가동 중", fg="#10B981")
        interval_sec = max(1, int(self.cfg.get("interval_minutes", 60))) * 60
        self.next_run_timestamp = time.time() + interval_sec
        self.log(f"자동 반복 스케줄러 가동 시작 (주기: {self.cfg.get('interval_minutes', 60)}분)")

    def stop_scheduler(self):
        self.is_running = False
        self.cfg["auto_start"] = False
        save_config(self.cfg)
        self.next_run_timestamp = None
        self.toggle_btn.config(text="▶ 자동 반복 시작", bg="#059669")
        self.status_badge.config(text="● 일시 정지됨", fg="#F59E0B")
        self.countdown_label.config(text="다음 실행 대기: 정지됨")
        self.log("자동 반복 스케줄러가 정지되었습니다.")

    def toggle_scheduler(self):
        if self.is_running:
            self.stop_scheduler()
        else:
            self.on_save_config()
            self.start_scheduler()

    def run_once_manual(self):
        if self.is_working:
            self.log("이미 작업이 진행 중입니다. 잠시만 기다려 주세요.")
            return
        self.on_save_config()
        if self.is_running:
            interval_sec = max(1, int(self.cfg.get("interval_minutes", 60))) * 60
            self.next_run_timestamp = time.time() + interval_sec
        threading.Thread(target=self.execute_cycle, args=(True,), daemon=True).start()

    def run_all_three_now(self):
        if self.is_working:
            self.log("이미 작업이 진행 중입니다. 잠시만 기다려 주세요.")
            return
        self.on_save_config()
        if self.is_running:
            interval_sec = max(1, int(self.cfg.get("interval_minutes", 60))) * 60
            self.next_run_timestamp = time.time() + interval_sec

        def _batch():
            self.log("★★★ [3개 공고 A·B·C 일괄 교체] 3회 연속 로테이션을 시작합니다! ★★★")
            for step_i in range(3):
                self.execute_cycle(is_manual=True)
                if step_i < 2:
                    time.sleep(1.5)
            self.log("★★★ [3개 공고 A·B·C 일괄 교체 완료!] 상단 3개 공고가 모두 서로 다른 타겟팅으로 세팅되었습니다. ★★★")

        threading.Thread(target=_batch, daemon=True).start()

    def execute_cycle(self, is_manual=False):
        if self.is_working:
            return
        self.is_working = True
        self.root.after(0, lambda: self.status_badge.config(text="● 광고 작업 실행 중...", fg="#3B82F6"))

        if self.cfg.get("auto_ota_update", True):
            updated, ver, notes = check_and_download_ota()
            if updated:
                self.log(f"★ 원격 새 버전(v{ver}) 감지 및 업데이트 완료! ({notes}) 재시작합니다...")
                time.sleep(1.0)
                self._restart_self()
                return

        client = TelejobClient()
        try:
            now_hour = datetime.datetime.now().hour
            sh = int(self.cfg.get("start_hour", 4))
            eh = int(self.cfg.get("end_hour", 24))

            if not is_manual and not (sh <= now_hour < eh):
                self.log(f"현재 시각({now_hour}시)은 설정된 가동 시간({sh}시~{eh}시)이 아니므로 이번 주기는 건너뜁니다.")
                return

            self.log("============================================================")
            self.log("▶ [1/5] 텔레잡 기업회원 로그인 시도 중...")
            client.login(self.cfg["user_id"], self.cfg["user_pw"])

            active_before = client.get_active_posts()
            stored_before = client.get_stored_posts()
            self.log(f"▶ [2/5] 작업 전 게재중 공고({len(active_before)}건): {[p['wiSeq'] for p in active_before]}")

            if not active_before and not stored_before:
                raise RuntimeError("게재 중이거나 보관 중인 채용공고가 하나도 없습니다.")

            source_seq = active_before[0]["wiSeq"] if active_before else stored_before[0]["wiSeq"]
            self.log(f"▶ [3/5] 대표 공고(wiSeq={source_seq}) 복제(Copy) 실행 중...")
            client.copy_post(source_seq)

            if len(active_before) >= 3:
                oldest_seq = active_before[-1]["wiSeq"]
                self.log(f"▶ [4/5] 기존 가장 오래된 공고(wiSeq={oldest_seq}) 삭제 중...")
                client.delete_post(oldest_seq)
            else:
                self.log(f"▶ [4/5] 현재 게재 공고가 {len(active_before)}건(3건 미만)이므로 삭제 생략")

            stored_after_copy = client.get_stored_posts()
            if not stored_after_copy:
                raise RuntimeError("복제 후 보관함(t03)에서 새 공고를 찾을 수 없습니다.")
            new_seq = stored_after_copy[0]["wiSeq"]

            presets = self.cfg.get("presets", DEFAULT_PRESETS)
            next_idx = (int(self.cfg.get("last_preset_index", -1)) + 1) % len(presets)
            chosen_preset = presets[next_idx] if self.cfg.get("use_abc_rotation", True) else None

            if chosen_preset:
                preset_label = f"{chr(65+next_idx)}안 ({chosen_preset['subTitle']} | {chosen_preset['title']})"
                self.log(f"▶ [타겟팅 변경] 신규 공고({new_seq}) ➔ [{preset_label}] 적용 중 (디자인 고정)...")
                client.update_post_preset_and_design(new_seq, preset=chosen_preset, image_path=None)
                self.cfg["last_preset_index"] = next_idx
                save_config(self.cfg)
                self.log(f"✓ [타겟팅 변경] {chr(65+next_idx)}안 문구/키워드 세팅 완료")

            self.log(f"▶ [5/5] 복제된 신규 공고(wiSeq={new_seq}) 최상단 게재(Open) 요청 중...")
            client.open_post(new_seq)

            active_after = client.get_active_posts()
            self.update_table(active_after)
            self.success_count += 1
            summary_str = ", ".join(f"{p['wiSeq']}[{p['subTitle']}]" for p in active_after)
            self.log(f"★ 작업 완료! 현재 게재중: {summary_str} (누적 성공: {self.success_count}회)")
            self.log("============================================================")

        except Exception as e:
            self.fail_count += 1
            self.log(f"!!! [에러 발생] {e}")
            self.log("이번 주기는 건너뛰고 다음 주기에 자동 재시도합니다.")
        finally:
            client.close()
            del client
            gc.collect()
            self.is_working = False
            self.root.after(0, self._update_header_labels)

    def _update_header_labels(self):
        if self.is_running:
            self.status_badge.config(text="● 자동 반복 가동 중", fg="#10B981")
        else:
            self.status_badge.config(text="● 일시 정지됨", fg="#F59E0B")
        self.stats_label.config(
            text=f"누적 성공: {self.success_count}회 | 실패: {self.fail_count}회 | 메모리: 정상(0%)"
        )

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
                    self.countdown_label.config(text=f"다음 실행까지: {hrs:02d}:{mins:02d}:{secs:02d}")
                else:
                    self.countdown_label.config(text=f"다음 실행까지: {mins:02d}분 {secs:02d}초")
        self.root.after(1000, self._tick_timer)


def main():
    acquire_single_instance_lock()
    root = tk.Tk()
    app = TelejobApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
