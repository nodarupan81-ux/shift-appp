# -*- coding: utf-8 -*-
# Shift アプリ - 完全版 app.py
#
# ポイント
# - ログイン：フォーム名を username / password に統一。next パラメータで遷移。
# - シフト保存：POST フィールド day_<日>_<shift>_<1|2> を正規表現で総なめにして保存（堅牢）。
# - 読み込み：旧データ {"d": {...}} でも自動で正規化して表示。
# - テンプレートと整合：login_admin.html / staff_login.html / schedule.html と噛み合う。

from flask import Flask, render_template, request, redirect, url_for, session, abort, flash
import os
import json
import calendar
import datetime as dt
import re
from pathlib import Path

# ==========================================================
# Flask 基本設定
# ==========================================================
app = Flask(__name__)

# セッション用シークレット
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "CHANGE_ME_TO_A_RANDOM_STRING")

# ==========================================================
# アプリ固有設定
# ==========================================================
SITE_NAME = "若葉2丁目店"

# 管理者アカウント
ADMIN_USER = "365836"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")

# スタッフ用パスワード
STAFF_PASSWORD = os.environ.get("STAFF_PASSWORD", "test123")

# シフト定義
SHIFTS = ["early", "morning", "afternoon", "evening", "night"]
SHIFTS_LABELS = {
    "early": "早朝",
    "morning": "午前",
    "afternoon": "午後",
    "evening": "夕方",
    "night": "深夜",
}
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

# データ格納先
DATA_DIR = Path("data")

# ==========================================================
# ユーティリティ
# ==========================================================
def store_name(store_id: str) -> str:
    return SITE_NAME

def store_exists(store_id: str) -> bool:
    # 店舗IDの妥当性チェックを入れる場合はここを実装
    return True

def require_store_or_404(store_id: str):
    if not store_exists(store_id):
        abort(404)

def is_admin(store_id: str) -> bool:
    return bool(session.get("is_admin"))

def prev_next_year_month(year: int, month: int):
    prev_y, prev_m = year, month - 1
    next_y, next_m = year, month + 1
    if prev_m == 0:
        prev_m = 12
        prev_y -= 1
    if next_m == 13:
        next_m = 1
        next_y += 1
    return prev_y, prev_m, next_y, next_m

def load_employees(store_id: str):
    # 優先：data/<store_id>/employees.json、なければ data/employees.json
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
    # monthdayscalendar: 各週が 7 要素（0=月外、1..=日付）を持つ配列
    cal = calendar.Calendar(firstweekday=0)
    return cal.monthdayscalendar(year, month)

# ==========================================================
# ルート
# ==========================================================
@app.route("/")
def index():
    return render_template("index.html", site_name=SITE_NAME)

# ---- 管理者ログイン ----
@app.route("/<store_id>/login-admin", methods=["GET", "POST"])
def login_admin(store_id):
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        # next は form 優先 → query → 既定
        next_url = request.form.get("next") or request.args.get("next") or url_for("view", store_id=store_id)

        if username == ADMIN_USER and password == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("管理者ログイン成功", "success")
            return redirect(next_url)

        flash("ユーザー名またはパスワードが違います", "error")

    return render_template("login_admin.html", store_id=store_id, store_name=store_name(store_id))

# ---- ログアウト ----
@app.route("/<store_id>/logout")
def logout(store_id):
    session.clear()
    return redirect(url_for("login_admin", store_id=store_id))

# ---- スタッフログイン ----
@app.route("/<store_id>/staff-login", methods=["GET", "POST"])
def staff_login(store_id):
    if request.method == "POST":
        pwd = request.form.get("password", "")
        next_url = request.form.get("next") or request.args.get("next") or url_for("view", store_id=store_id)
        if pwd == STAFF_PASSWORD:
            session["is_staff"] = True
            flash("スタッフログイン成功", "success")
            return redirect(next_url)
        flash("パスワードが違います", "error")

    return render_template("staff_login.html", store_id=store_id, store_name=store_name(store_id))

# ---- 閲覧（ダミー画面）----
@app.route("/<store_id>/view")
def view(store_id):
    return render_template("view.html", store_name=store_name(store_id))

# ---- シフト編集 ----
@app.route("/<store_id>/schedule", methods=["GET", "POST"])
def schedule(store_id):
    require_store_or_404(store_id)
    if not is_admin(store_id):
        # 未ログインならログインへ
        return redirect(url_for("login_admin", store_id=store_id, next=url_for("schedule", store_id=store_id)))

    today = dt.date.today()

    # ===== POST: 保存処理 =====
    if request.method == "POST":
        # 送信年月（無ければ今日）
        year = int(request.form.get("year") or today.year)
        month = int(request.form.get("month") or today.month)

        # 例: day_15_morning_1 = "田中"
        # → day="15", shift="morning", slot="1|2"
        pat = re.compile(r"^day_(\d+)_([^_]+)_(1|2)$")

        data_flat: dict[str, dict] = {}

        for key, val in request.form.items():
            m = pat.match(key)
            if not m:
                continue
            day_str, shift_key, slot_str = m.groups()
            cur = data_flat.setdefault(day_str, {}).setdefault(shift_key, ["", ""])
            idx = 0 if slot_str == "1" else 1
            cur[idx] = val or ""

        # 1つもヒットしなくても空dictを書いておく（描画が安定）
        save_schedule(store_id, year, month, data_flat)
        flash("保存しました。", "success")
        return redirect(url_for("schedule", store_id=store_id, year=year, month=month))

    # ===== GET: 画面表示 =====
    year = int(request.args.get("year") or today.year)
    month = int(request.args.get("month") or today.month)

    employees = load_employees(store_id)

    # 保存データ（旧 {"d": {...}} もならす）
    schedules = load_schedule(store_id, year, month) or {}
    if isinstance(schedules, dict) and "d" in schedules and isinstance(schedules["d"], dict):
        schedules = schedules["d"]

    weeks = build_calendar(year, month)
    prev_y, prev_m, next_y, next_m = prev_next_year_month(year, month)
    year_options = list(range(today.year - 1, today.year + 2))
    month_options = list(range(1, 13))

    return render_template(
        "schedule.html",
        store_name=store_name(store_id),
        store_id=store_id,
        employees=employees,
        prefill=schedules,           # schedule.html は prefill["1"]["morning"] の形を参照
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

# ==========================================================
# ローカル実行用（Render では gunicorn が使用）
# ==========================================================
if __name__ == "__main__":
    # ローカルテスト時は python app.py で起動
    app.run(host="127.0.0.1", port=5000, debug=True)
