from flask import Flask, render_template, request, redirect, url_for, session, abort, flash
import os, json, calendar
import datetime as dt
from pathlib import Path

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "CHANGE_ME_TO_A_RANDOM_STRING")

# ====== 店舗名（ヘッダー表示用） ======
SITE_NAME = "若葉2丁目店"   # ここを変えると画面の店名が変わります

# ====== 管理者アカウント ======
ADMIN_USER = "365836"
ADMIN_PASSWORD = "admin"

# ====== データ保存用ディレクトリ ======
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# ====== シフト定義 ======
SHIFTS = ["early", "morning", "afternoon", "evening", "night"]
SHIFTS_LABELS = {
    "early": "早朝",
    "morning": "午前",
    "afternoon": "午後",
    "evening": "夕方",
    "night": "深夜",
}

# ====== ユーザー管理 ======
USERS = {
    "staff": {"password": "staffpass"},  # スタッフログイン用
}

# ---------- ユーティリティ ----------
def schedule_file_path(store_id: str, year: int, month: int) -> Path:
    subdir = DATA_DIR / store_id
    subdir.mkdir(parents=True, exist_ok=True)
    return subdir / f"{year:04d}-{month:02d}.json"

def load_schedule(store_id: str, year: int, month: int) -> dict:
    p = schedule_file_path(store_id, year, month)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}

def save_schedule(store_id: str, year: int, month: int, payload: dict):
    p = schedule_file_path(store_id, year, month)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def load_employees(store_id: str) -> list:
    path = DATA_DIR / store_id / "employees.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []

def save_employees(store_id: str, employees: list):
    path = DATA_DIR / store_id / "employees.json"
    path.write_text(json.dumps(employees, ensure_ascii=False, indent=2), encoding="utf-8")

# ---------- 認証 ----------
@app.route("/<store_id>/login-admin", methods=["GET", "POST"])
def login_admin(store_id):
    if request.method == "POST":
        user = request.form.get("username")
        pw = request.form.get("password")
        if user == ADMIN_USER and pw == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("schedule", store_id=store_id))
        flash("ログイン失敗")
    return render_template("login_admin.html")

@app.route("/<store_id>/logout")
def logout(store_id):
    session.clear()
    return redirect(url_for("index"))

@app.route("/<store_id>/staff-login", methods=["GET", "POST"])
def staff_login(store_id):
    if request.method == "POST":
        user = request.form.get("username")
        pw = request.form.get("password")
        if user in USERS and USERS[user]["password"] == pw:
            session["is_staff"] = True
            return redirect(url_for("view", store_id=store_id))
        flash("ログイン失敗")
    return render_template("staff_login.html")

# ---------- トップページ ----------
@app.route("/")
def index():
    return render_template("index.html", site_name=SITE_NAME)

# ---------- シフト編集（管理者専用） ----------
@app.route("/<store_id>/schedule", methods=["GET", "POST"])
def schedule(store_id):
    if not session.get("is_admin"):
        return redirect(url_for("login_admin", store_id=store_id, next=request.path))

    today = dt.date.today()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))

    if request.method == "POST":
        payload = request.form.to_dict(flat=False)
        save_schedule(store_id, year, month, payload)
        flash("保存しました。")
        return redirect(url_for("schedule", store_id=store_id, year=year, month=month))

    employees = load_employees(store_id)
    schedule_data = load_schedule(store_id, year, month)

    return render_template(
        "schedule.html",
        store_id=store_id,
        site_name=SITE_NAME,
        shifts=SHIFTS,
        shifts_labels=SHIFTS_LABELS,
        employees=employees,
        schedule=schedule_data,
        year=year,
        month=month,
        now=today,
    )

# ---------- スタッフ一覧（名前登録ページ） ----------
@app.route("/<store_id>/settings", methods=["GET", "POST"])
def settings(store_id):
    if not session.get("is_admin"):
        return redirect(url_for("login_admin", store_id=store_id, next=request.path))

    employees = load_employees(store_id)

    if request.method == "POST":
        names = request.form.getlist("employees[]")
        employees = [n for n in names if n.strip()]
        save_employees(store_id, employees)
        flash("スタッフ名を更新しました。")
        return redirect(url_for("settings", store_id=store_id))

    return render_template(
        "settings.html",
        store_id=store_id,
        employees=employees,
        site_name=SITE_NAME
    )

# ---------- 閲覧ページ（誰でも見れる） ----------
@app.route("/<store_id>/view")
def view(store_id):
    today = dt.date.today()
    year, month = today.year, today.month
    schedule_data = load_schedule(store_id, year, month)
    employees = load_employees(store_id)
    return render_template(
        "view.html",
        site_name=SITE_NAME,
        shifts=SHIFTS,
        shifts_labels=SHIFTS_LABELS,
        employees=employees,
        schedule=schedule_data,
        year=year,
        month=month,
    )

if __name__ == "__main__":
    app.run(debug=True)

