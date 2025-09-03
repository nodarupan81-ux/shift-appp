from flask import Flask, render_template, request, redirect, url_for, session, abort, flash
import os, json, calendar
import datetime as dt
import re
from pathlib import Path
from typing import Dict, Any, List

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "CHANGE_ME_TO_A_RANDOM_STRING")

# ====== 店舗設定 ======
SITE_NAME = "若葉2丁目店"
DEFAULT_STORE_ID = os.environ.get("DEFAULT_STORE_ID", "wakaba2")  # ← / はここへ飛ばします

# ====== 管理者/スタッフ ======
ADMIN_USER = "365836"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
STAFF_PASSWORD = os.environ.get("STAFF_PASSWORD", "test123")

# ====== シフト定義 ======
SHIFTS = ["early", "morning", "afternoon", "evening", "night"]
SHIFTS_LABELS = {
    "early": "早朝",
    "morning": "午前",
    "afternoon": "午後",
    "evening": "夕方",
    "night": "深夜",
}
LABEL_TO_KEY = {v: k for k, v in SHIFTS_LABELS.items()}
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

DATA_DIR = Path("data")

# ---------- 共通ユーティリティ ----------
def store_name(store_id: str) -> str:
    return SITE_NAME

def require_store_or_404(store_id: str):
    if not store_exists(store_id):
        abort(404)

def store_exists(store_id: str) -> bool:
    return True

def prev_next_year_month(year: int, month: int):
    prev_y, prev_m = year, month - 1
    next_y, next_m = year, month + 1
    if prev_m == 0:
        prev_m, prev_y = 12, year - 1
    if next_m == 13:
        next_m, next_y = 1, year + 1
    return prev_y, prev_m, next_y, next_m

def load_employees(store_id: str):
    path_primary = DATA_DIR / store_id / "employees.json"
    path_fallback = DATA_DIR / "employees.json"
    p = path_primary if path_primary.exists() else path_fallback
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return []

def schedule_file_path(store_id: str, year: int, month: int) -> Path:
    subdir = DATA_DIR / store_id
    subdir.mkdir(parents=True, exist_ok=True)
    return subdir / f"{year:04d}-{month:02d}.json"

def load_schedule(store_id: str, year: int, month: int):
    p = schedule_file_path(store_id, year, month)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}

def save_schedule(store_id: str, year: int, month: int, payload: dict):
    p = schedule_file_path(store_id, year, month)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def month_bounds(year: int, month: int):
    first = dt.date(year, month, 1)
    _, last_day = calendar.monthrange(year, month)
    last = dt.date(year, month, last_day)
    return first, last

def build_calendar(year: int, month: int):
    cal = calendar.Calendar(firstweekday=0)
    return cal.monthdayscalendar(year, month)

def is_admin(store_id: str):
    return session.get("is_admin")

# ---------- 保存形式の正規化 ----------
def _norm_pair(v: Any) -> List[str]:
    if isinstance(v, list) and len(v) >= 2:
        return [str(v[0] or ""), str(v[1] or "")]
    if isinstance(v, list) and len(v) == 1:
        return [str(v[0] or ""), ""]
    if isinstance(v, str):
        return [v, ""]
    return ["", ""]

def _normalize_schedule_dict(raw: Dict[str, Any]) -> Dict[str, Dict[str, List[str]]]:
    if not isinstance(raw, dict):
        return {}
    if "d" in raw and isinstance(raw["d"], dict):
        raw = raw["d"]
    out: Dict[str, Dict[str, List[str]]] = {}
    for day_key, shifts_dict in raw.items():
        if not isinstance(shifts_dict, dict):
            continue
        day_out: Dict[str, List[str]] = {}
        for k, v in shifts_dict.items():
            if k in SHIFTS:
                day_out[k] = _norm_pair(v)
            elif k in LABEL_TO_KEY:  # 日本語→英語
                day_out[LABEL_TO_KEY[k]] = _norm_pair(v)
        if day_out:
            out[str(day_key)] = day_out
    return out

# ================= 路線 =================

# / はそのまま当月のスケジュールへリダイレクト（テンプレは使わない）
@app.route("/")
def index():
    today = dt.date.today()
    return redirect(url_for("schedule", store_id=DEFAULT_STORE_ID, year=today.year, month=today.month))

@app.route("/<store_id>/login-admin", methods=["GET", "POST"])
def login_admin(store_id):
    if request.method == "POST":
        if request.form.get("userid") == ADMIN_USER and request.form.get("password") == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("管理者ログイン成功", "success")
            next_url = request.args.get("next") or url_for("view", store_id=store_id)
            return redirect(next_url)
        flash("ユーザーIDまたはパスワードが違います", "error")
    return render_template("login_admin.html")

@app.route("/<store_id>/logout")
def logout(store_id):
    session.clear()
    return redirect(url_for("login_admin", store_id=store_id))

@app.route("/<store_id>/staff-login", methods=["GET", "POST"])
def staff_login(store_id):
    if request.method == "POST":
        if request.form.get("password") == STAFF_PASSWORD:
            session["is_staff"] = True
            flash("スタッフログイン成功", "success")
            next_url = request.args.get("next") or url_for("view", store_id=store_id)
            return redirect(next_url)
        flash("パスワードが違います", "error")
    return render_template("staff_login.html")

@app.route("/<store_id>/view")
def view(store_id):
    return render_template("view.html", store_name=store_name(store_id))

# ====== シフト編集 ======
@app.route("/<store_id>/schedule", methods=["GET", "POST"])
def schedule(store_id):
    require_store_or_404(store_id)
    if not is_admin(store_id):
        return redirect(url_for("login_admin", store_id=store_id, next=url_for("schedule", store_id=store_id)))

    today = dt.date.today()

    if request.method == "POST":
        year = int(request.form.get("year") or today.year)
        month = int(request.form.get("month") or today.month)

        data_flat: Dict[str, Dict[str, List[str]]] = {}
        _, last = month_bounds(year, month)

        # 旧方式: name="day_<day>_<shift>_1/2"
        for day in range(1, last.day + 1):
            day_key = str(day)
            for s in SHIFTS:
                a1 = request.form.get(f"day_{day}_{s}_1")
                a2 = request.form.get(f"day_{day}_{s}_2")
                if a1 is not None or a2 is not None:
                    data_flat.setdefault(day_key, {})[s] = [a1 or "", a2 or ""]

        save_schedule(store_id, year, month, data_flat)
        flash("保存しました。", "success")
        return redirect(url_for("schedule", store_id=store_id, year=year, month=month))

    # GET
    year = int(request.args.get("year") or today.year)
    month = int(request.args.get("month") or today.month)
    employees = load_employees(store_id)
    raw = load_schedule(store_id, year, month) or {}
    schedules = _normalize_schedule_dict(raw)

    weeks = build_calendar(year, month)
    prev_y, prev_m, next_y, next_m = prev_next_year_month(year, month)
    year_options = list(range(today.year - 1, today.year + 2))
    month_options = list(range(1, 13))

    return render_template(
        "schedule.html",
        store_name=store_name(store_id),
        store_id=store_id,
        employees=employees,
        prefill=schedules,
        shifts=SHIFTS,
        shifts_labels=SHIFTS_LABELS,
        weekdays=WEEKDAYS,
        weeks=weeks,
        year=year,
        month=month,
        prev_year=prev_y,
        prev_month=prev_m,
        next_year=next_y,
        next_month=next_m,
        year_options=year_options,
        month_options=month_options,
        is_admin=True,
        dt=dt,
        now=dt.date.today(),
    )
