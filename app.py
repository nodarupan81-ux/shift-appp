from flask import Flask, render_template, request, redirect, url_for, session
import os, json, calendar
import datetime as dt
from pathlib import Path

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "CHANGE_ME_TO_A_RANDOM_STRING")

# ----------------------------
# 複数店舗 定義
# ----------------------------
STORES = {
    "wakaba2": "若葉2丁目店",
    "akitsu":  "秋津新町店",
}

# 管理者ログイン（共通ユーザー/パスの例）
ADMIN_USER = "365836"
ADMIN_PASSWORD = "admin"

# シフト定義
SHIFTS = ["early", "morning", "afternoon", "evening", "night"]  # 早朝/午前/午後/夕方/深夜
SHIFTS_LABELS = {
    "early": "早朝",
    "morning": "午前",
    "afternoon": "午後",
    "evening": "夕方",
    "night": "深夜",
}
WEEKDAYS_JP = ["日", "月", "火", "水", "木", "金", "土"]

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"  # 店舗ごとに data/<store_id>/ 以下に保存

# ----------------------------
# 共通ユーティリティ
# ----------------------------
def store_root(store_id: str) -> Path:
    root = DATA_DIR / store_id
    root.mkdir(parents=True, exist_ok=True)
    return root

def employees_path(store_id: str) -> Path:
    return store_root(store_id) / "employees.json"

def month_path(store_id: str, year: int, month: int) -> Path:
    return store_root(store_id) / f"{year:04d}-{month:02d}.json"

def is_admin(store_id: str) -> bool:
    return session.get("role") == "admin" and session.get("admin_store") == store_id

def login_required_admin(store_id: str):
    if not is_admin(store_id):
        return redirect(url_for("login_admin", store_id=store_id, next=url_for("schedule", store_id=store_id)))

def load_employees(store_id: str):
    """名簿と定員"""
    def default_employees():
        return {
            "employees": ["店長", "マネージャー", "Aさん", "Bさん", "Cさん"],
            "required_per_shift": {s: (1 if s == "night" else 2) for s in SHIFTS},
        }

    p = employees_path(store_id)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = default_employees()
    else:
        data = default_employees()

    # 形式の安全化
    if "employees" not in data or not isinstance(data["employees"], list):
        data["employees"] = []
    if "required_per_shift" not in data or not isinstance(data["required_per_shift"], dict):
        data["required_per_shift"] = {s: (1 if s == "night" else 2) for s in SHIFTS}
    for s in SHIFTS:
        data["required_per_shift"].setdefault(s, (1 if s == "night" else 2))

    # 名簿クレンジング
    cleaned, seen = [], set()
    for name in data["employees"]:
        if not isinstance(name, str): 
            continue
        n = name.strip()
        if n and n not in seen:
            cleaned.append(n)
            seen.add(n)
    data["employees"] = cleaned
    return data

def save_employees(store_id: str, data: dict):
    p = employees_path(store_id)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def load_month(store_id: str, year: int, month: int):
    p = month_path(store_id, year, month)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    last_day = calendar.monthrange(year, month)[1]
    return {str(d): {s: "" for s in SHIFTS} for d in range(1, last_day + 1)}

def save_month(store_id: str, year: int, month: int, data: dict):
    p = month_path(store_id, year, month)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def make_calendar(year: int, month: int):
    cal = calendar.Calendar(firstweekday=6)  # 日曜はじまり
    weeks = cal.monthdayscalendar(year, month)
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    return weeks, prev_year, prev_month, next_year, next_month

def make_prefill(data):
    """保存形式(カンマ文字列)→2枠リストの表示用に整形"""
    prefill = {}
    for d_str, shifts in data.items():
        try:
            d = int(d_str)
        except ValueError:
            continue
        prefill[d] = {}
        for s in SHIFTS:
            raw = shifts.get(s, "")
            if not isinstance(raw, str):
                raw = ""
            raw = raw.replace("，", ",")
            parts = [p.strip() for p in raw.split(",") if p.strip()] if raw else []
            a = parts[0] if len(parts) > 0 else ""
            b = parts[1] if len(parts) > 1 else ""
            prefill[d][s] = [a, b]
    return prefill

# ----------------------------
# ルーティング
# ----------------------------
@app.route("/")
def landing():
    """店舗選択ページ"""
    return render_template("landing.html", stores=STORES)

# --- 管理者ログイン ---
@app.route("/<store_id>/login-admin", methods=["GET", "POST"])
def login_admin(store_id):
    if store_id not in STORES:
        return redirect(url_for("landing"))
    if request.method == "POST":
        user = request.form.get("username", "").strip()
        pw = request.form.get("password", "")
        if user == ADMIN_USER and pw == ADMIN_PASSWORD:
            session.clear()
            session["role"] = "admin"
            session["admin_store"] = store_id
            next_url = request.args.get("next") or url_for("schedule", store_id=store_id)
            return redirect(next_url)
        return render_template("login_admin.html", store_id=store_id, store_name=STORES[store_id],
                               error="ユーザー名またはパスワードが違います。")
    return render_template("login_admin.html", store_id=store_id, store_name=STORES[store_id])

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))

# --- 設定（名簿・定員） 管理者のみ ---
@app.route("/<store_id>/settings", methods=["GET", "POST"])
def settings(store_id):
    if store_id not in STORES:
        return redirect(url_for("landing"))
    need = login_required_admin(store_id)
    if need:
        return need

    emp = load_employees(store_id)

    if request.method == "POST":
        # 名簿
        raw = request.form.get("employees", "")
        employees, seen = [], set()
        for line in raw.splitlines():
            name = line.strip()
            if name and name not in seen:
                employees.append(name)
                seen.add(name)
        # 定員
        req = {}
        for s in SHIFTS:
            try:
                val = int(request.form.get(f"req_{s}", "2"))
                val = max(0, min(10, val))
            except ValueError:
                val = 2
            req[s] = val

        emp = {"employees": employees, "required_per_shift": req}
        save_employees(store_id, emp)
        return redirect(url_for("settings", store_id=store_id))

    employees_text = "\n".join(emp["employees"])
    return render_template(
        "settings.html",
        store_id=store_id,
        store_name=STORES[store_id],
        shifts=SHIFTS, labels=SHIFTS_LABELS,
        employees_text=employees_text,
        required=emp["required_per_shift"]
    )

# --- 管理者用：シフト編集 ---
@app.route("/<store_id>/schedule", methods=["GET", "POST"])
def schedule(store_id):
    if store_id not in STORES:
        return redirect(url_for("landing"))
    need = login_required_admin(store_id)
    if need:
        return need

    today = dt.date.today()
    year = int(request.values.get("year", today.year))
    month = int(request.values.get("month", today.month))

    data = load_month(store_id, year, month)
    emp = load_employees(store_id)

    # 保存
    if request.method == "POST":
        for key in list(request.form.keys()):
            if key.startswith("day_") and key.endswith("_1"):
                # day_5_morning_1 → d_str=5, s=morning
                _, d_str, s, _ = key.split("_", 3)
                if d_str in data and s in SHIFTS:
                    n1 = request.form.get(f"day_{d_str}_{s}_1", "").strip()
                    n2 = request.form.get(f"day_{d_str}_{s}_2", "").strip()
                    data[d_str][s] = ", ".join([x for x in (n1, n2) if x])
        save_month(store_id, year, month, data)
        return redirect(url_for("schedule", store_id=store_id, year=year, month=month))

    # 画面用
    prefill = make_prefill(data)
    weeks, prev_year, prev_month, next_year, next_month = make_calendar(year, month)
    year_options = list(range(today.year - 1, today.year + 2))
    month_options = list(range(1, 13))

    return render_template(
        "schedule.html",
        store_id=store_id,
        store_name=STORES[store_id],
        is_admin=True,
        year=year, month=month, weeks=weeks,
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
        year_options=year_options, month_options=month_options,
        shifts=SHIFTS, shifts_labels=SHIFTS_LABELS,
        weekdays=WEEKDAYS_JP,
        prefill=prefill,
        employees=emp["employees"],
        required=emp["required_per_shift"],
        now={"year": today.year, "month": today.month},
    )

# --- 従業員閲覧 ---
@app.route("/<store_id>/view")
def view(store_id):
    if store_id not in STORES:
        return redirect(url_for("landing"))

    today = dt.date.today()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))

    data = load_month(store_id, year, month)
    emp = load_employees(store_id)

    prefill = make_prefill(data)
    weeks, prev_year, prev_month, next_year, next_month = make_calendar(year, month)
    year_options = list(range(today.year - 1, today.year + 2))
    month_options = list(range(1, 13))

    return render_template(
        "schedule.html",
        store_id=store_id,
        store_name=STORES[store_id],
        is_admin=False,
        year=year, month=month, weeks=weeks,
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
        year_options=year_options, month_options=month_options,
        shifts=SHIFTS, shifts_labels=SHIFTS_LABELS,
        weekdays=WEEKDAYS_JP,
        prefill=prefill,
        employees=emp["employees"],
        required=emp["required_per_shift"],
        now={"year": today.year, "month": today.month},
    )

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

