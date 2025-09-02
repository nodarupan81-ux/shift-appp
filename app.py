# -*- coding: utf-8 -*-
import os
import re
import json
import calendar
import datetime as dt
from pathlib import Path
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, abort
)

app = Flask(__name__)

# ===== 基本設定 =====
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

STAFF_PASSWORD = os.environ.get("STAFF_PASSWORD", "staffpass")   # 従業員ログイン用
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "adminpass")   # 管理者ログイン用

STORES = {
    "wakaba2": "若葉2丁目店",
    "akitsu":  "秋津新町店",
}

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# ===== 便利関数 =====
def store_exists(store_id: str) -> bool:
    return store_id in STORES

def month_bounds(year: int, month: int):
    """対象月の1日と末日を返す"""
    first = dt.date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    last = dt.date(year, month, last_day)
    return first, last

def build_calendar(year: int, month: int):
    """カレンダー配列（週×7日、0=月曜日）"""
    cal = calendar.Calendar(firstweekday=0)
    return cal.monthdayscalendar(year, month)

def prev_next_year_month(year: int, month: int):
    prev_m = month - 1
    prev_y = year
    next_m = month + 1
    next_y = year
    if prev_m == 0:
        prev_m = 12
        prev_y -= 1
    if next_m == 13:
        next_m = 1
        next_y += 1
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

def store_name(store_id: str) -> str:
    return STORES.get(store_id, store_id)

def require_store_or_404(store_id: str):
    if not store_exists(store_id):
        abort(404)

def is_admin(store_id: str) -> bool:
    return session.get(f"is_admin_{store_id}", False)

def is_staff_authed(store_id: str) -> bool:
    return session.get(f"staff_authed_{store_id}", False)

# ===== 表示用定数 =====
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]
SHIFTS = ["socho", "gozen", "gogo", "yugata", "shinya"]
SHIFTS_LABELS = {
    "socho":  "早朝",
    "gozen":  "午前",
    "gogo":   "午後",
    "yugata": "夕方",
    "shinya": "深夜",
}

# ===== 入口 =====
@app.route("/")
def landing():
    return render_template("landing.html", stores=STORES)

# ===== 従業員ログイン =====
@app.route("/<store_id>/staff-login", methods=["GET", "POST"])
def staff_login(store_id):
    """スタッフ用ログイン。成功したら next (なければ /<store_id>/view) へ"""
    require_store_or_404(store_id)

    next_url = request.values.get("next") or url_for("view", store_id=store_id)

    if request.method == "POST":
        pwd = request.form.get("password", "")
        if pwd == STAFF_PASSWORD:
            session[f"staff_authed_{store_id}"] = True
            return redirect(next_url)
        flash("パスワードが違います。", "error")
        # 入力値を保持したい場合は hidden で next を渡す
        return redirect(url_for("staff_login", store_id=store_id, next=next_url))

    # GET はログイン画面を出す（※ここで schedule.html を出していたのが不具合の原因）
    return render_template(
        "staff_login.html",
        store_id=store_id,
        store_name=store_name(store_id),
        next_url=next_url,
    )

@app.route("/<store_id>/staff-logout")
def staff_logout(store_id):
    session.pop(f"staff_authed_{store_id}", None)
    return redirect(url_for("staff_login", store_id=store_id))

# ===== 管理者ログイン =====
@app.route("/<store_id>/login-admin", methods=["GET", "POST"])
def login_admin(store_id):
    require_store_or_404(store_id)
    if request.method == "POST":
        pwd = request.form.get("password", "")
        next_url = request.form.get("next") or url_for("schedule", store_id=store_id)
        if pwd == ADMIN_PASSWORD:
            session[f"is_admin_{store_id}"] = True
            return redirect(next_url)
        flash("パスワードが違います。", "error")
    next_url = request.args.get("next") or url_for("schedule", store_id=store_id)
    return render_template("login_admin.html", store_id=store_id, store_name=store_name(store_id), next_url=next_url)

@app.route("/<store_id>/logout-admin")
def logout_admin(store_id):
    session.pop(f"is_admin_{store_id}", None)
    return redirect(url_for("login_admin", store_id=store_id))

# ===== スタッフ閲覧 =====
@app.route("/<store_id>/view")
def view(store_id):
    require_store_or_404(store_id)
    today = dt.date.today()
    year = int(request.args.get("year") or today.year)
    month = int(request.args.get("month") or today.month)

    employees = load_employees(store_id)
    schedules = load_schedule(store_id, year, month)
    weeks = build_calendar(year, month)
    prev_y, prev_m, next_y, next_m = prev_next_year_month(year, month)

    year_options = list(range(today.year - 1, today.year + 2))
    month_options = list(range(1, 13))

    return render_template(
        "schedule.html",
        title=None,
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
        is_admin=False,
        dt=dt,
        now=today,
    )

# ===== シフト編集（管理者） =====
@app.route("/<store_id>/schedule", methods=["GET", "POST"])
def schedule(store_id):
    require_store_or_404(store_id)
    if not is_admin(store_id):
        return redirect(url_for("login_admin", store_id=store_id, next=url_for("schedule", store_id=store_id)))

    today = dt.date.today()

    if request.method == "POST":
        year = int(request.form.get("year") or today.year)
        month = int(request.form.get("month") or today.month)
        data = load_schedule(store_id, year, month)

        # 1) 新方式: name="shifts[<week>][<day>][<slot>]"
        pat = re.compile(r'^shifts\[(\d+)\]\[(\d+)\]\[(.+)\]$')
        for key, val in request.form.items():
            m = pat.match(key)
            if m:
                w, d, slot = m.groups()
                data.setdefault(w, {}).setdefault(d, {})[slot] = val

        # 2) 旧方式: name="day_<day>_<shift>_1/2"
        _, last = month_bounds(year, month)
        for day in range(1, last.day + 1):
            for s in SHIFTS:
                a1 = request.form.get(f"day_{day}_{s}_1")
                a2 = request.form.get(f"day_{day}_{s}_2")
                if a1 is not None or a2 is not None:
                    data.setdefault("d", {}).setdefault(str(day), {})[s] = [a1 or "", a2 or ""]

        save_schedule(store_id, year, month, data)
        flash("保存しました。", "success")
        return redirect(url_for("schedule", store_id=store_id, year=year, month=month))

    year = int(request.args.get("year") or today.year)
    month = int(request.args.get("month") or today.month)
    employees = load_employees(store_id)
    schedules = load_schedule(store_id, year, month)
    weeks = build_calendar(year, month)
    prev_y, prev_m, next_y, next_m = prev_next_year_month(year, month)

    year_options = list(range(today.year - 1, today.year + 2))
    month_options = list(range(1, 13))

    return render_template(
        "schedule.html",
        title=None,
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
        now=today,
    )

# ===== 従業員名・定休日などの設定（管理） =====
@app.route("/<store_id>/settings", methods=["GET", "POST"])
def settings(store_id):
    require_store_or_404(store_id)
    if not is_admin(store_id):
        return redirect(url_for("login_admin", store_id=store_id, next=url_for("settings", store_id=store_id)))

    employees = load_employees(store_id)

    if request.method == "POST":
        raw = (request.form.get("employees_text") or request.form.get("employees") or "").strip()
        submitted = ("employees_text" in request.form) or ("employees" in request.form)
        if submitted:
            if raw:
                new_list = [line.strip() for line in raw.splitlines() if line.strip()]
                target_path = DATA_DIR / store_id / "employees.json"
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(json.dumps(new_list, ensure_ascii=False, indent=2), encoding="utf-8")
                flash("保存しました。", "success")
            else:
                flash("入力が空です。保存は行われませんでした。", "info")
            return redirect(url_for("settings", store_id=store_id))

    return render_template(
        "settings.html",
        store_id=store_id,
        store_name=store_name(store_id),
        employees=employees,
        employees_text="\n".join(employees),
    )

# ===== /<store_id>/ に来たら view へ =====
@app.route("/<store_id>/")
def go_store_root(store_id):
    require_store_or_404(store_id)
    return redirect(url_for("view", store_id=store_id))
# ---- added global logout ----
@app.route("/logout")
def logout():
    # 全店舗分のセッションフラグをまとめて削除してトップへ戻す
    for sid in STORES.keys():
        session.pop(f"staff_authed_{sid}", None)
        session.pop(f"is_admin_{sid}", None)
    return redirect(url_for("landing"))

if __name__ == "__main__":
    app.run(debug=True)



# ---- alias for old templates (added by helper) ----
@app.route("/index")
def index():
    return redirect(url_for("landing"))

@app.route("/logout")
def logout():
    # すべての店舗コンテキストのログアウト
    for sid in STORES.keys():
        session.pop(f"is_admin_{sid}", None)
        session.pop(f"staff_authed_{sid}", None)
    return redirect(url_for("landing"))
