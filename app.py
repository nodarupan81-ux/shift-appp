from flask import Flask, render_template, request, redirect, url_for, session, abort
import os, json, calendar
import datetime as dt
from pathlib import Path

app = Flask(__name__)

# ===== セキュリティ（必ず設定） =====
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "CHANGE_ME_FOR_PRODUCTION")

# ===== 共通パスワード（従業員閲覧用） =====
STAFF_PASSWORD = os.environ.get("STAFF_PASSWORD", "")  # 例: "staff123"（Renderの環境変数で設定）

# ===== 店舗定義 =====
STORES = {
    "wakaba2": {"name": "若葉2丁目店"},
    "akitsu":  {"name": "秋津新町店"},
}

# ===== シフト種別 =====
SHIFTS = ["early", "morning", "afternoon", "evening", "night"]
SHIFTS_LABELS = {
    "early": "早朝",
    "morning": "午前",
    "afternoon": "午後",
    "evening": "夕方",
    "night": "深夜",
}
WEEKDAYS_JP = ["日", "月", "火", "水", "木", "金", "土"]

# ===== データ保存場所 =====
DATA_DIR = Path("data")

def data_paths(store_id: str):
    """店舗ごとの保存先（名簿/シフト）"""
    base = DATA_DIR / store_id
    base.mkdir(parents=True, exist_ok=True)
    emp_json = base / "employees.json"
    return base, emp_json

def is_valid_store(store_id: str) -> bool:
    return store_id in STORES

# ---------- 名簿/定員 ----------
def load_employees(store_id: str):
    _, emp_path = data_paths(store_id)

    def default_employees():
        return {
            "employees": ["店長", "マネージャー", "Aさん", "Bさん", "Cさん"],
            "required_per_shift": {
                s: (1 if s == "night" else 2) for s in SHIFTS
            },
        }

    if emp_path.exists():
        try:
            with emp_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = default_employees()
    else:
        data = default_employees()

    # 安全化
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
    _, emp_path = data_paths(store_id)
    with emp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------- 月別シフト ----------
def month_path(store_id: str, year: int, month: int) -> Path:
    base, _ = data_paths(store_id)
    return base / f"{year:04d}-{month:02d}.json"

def load_month(store_id: str, year: int, month: int):
    p = month_path(store_id, year, month)
    if p.exists():
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    last_day = calendar.monthrange(year, month)[1]
    return {str(d): {s: "" for s in SHIFTS} for d in range(1, last_day + 1)}

def save_month(store_id: str, year: int, month: int, data: dict):
    p = month_path(store_id, year, month)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def make_calendar(year: int, month: int):
    cal = calendar.Calendar(firstweekday=6)  # 日曜はじまり
    weeks = cal.monthdayscalendar(year, month)
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    return weeks, prev_year, prev_month, next_year, next_month

def make_prefill(data):
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

# ===== ランディング =====
@app.route("/")
def landing():
    # 店舗一覧から選ぶ
    return render_template("landing.html", stores=STORES)

# ===== 従業員ログイン（共通パスワード方式） =====
@app.route("/<store_id>/staff-login", methods=["GET", "POST"])
def staff_login(store_id):
    if not is_valid_store(store_id):
        abort(404)

    error = None
    if request.method == "POST":
        pw = request.form.get("password", "")
        if not STAFF_PASSWORD:
            # パスワード未設定なら常に拒否（運用ミス防止）
            error = "現在このサイトは一時的に閲覧停止中です（パスワード未設定）。管理者にご連絡ください。"
        elif pw == STAFF_PASSWORD:
            session.clear()
            session["role"] = "viewer"
            session["store_id"] = store_id
            next_url = request.args.get("next") or url_for("view", store_id=store_id)
            return redirect(next_url)
        else:
            error = "パスワードが違います。"

    return render_template("staff_login.html",
                           store_id=store_id,
                           store_name=STORES[store_id]["name"],
                           error=error)

def viewer_required(store_id):
    # パスワードが設定されている場合のみ閲覧にログインを要求
    if STAFF_PASSWORD:
        if session.get("role") != "viewer" or session.get("store_id") != store_id:
            return redirect(url_for("staff_login", store_id=store_id, next=request.path))
    return None

# ===== 閲覧（従業員） =====
@app.route("/<store_id>/view")
def view(store_id):
    if not is_valid_store(store_id):
        abort(404)

    # ログイン必須にする（共通パスワード設定時）
    need = viewer_required(store_id)
    if need:
        return need

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
        store_name=STORES[store_id]["name"],
        year=year, month=month, weeks=weeks,
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
        year_options=year_options, month_options=month_options,
        shifts=SHIFTS, shifts_labels=SHIFTS_LABELS,
        weekdays=WEEKDAYS_JP,
        prefill=prefill,
        employees=emp["employees"],
        required=emp["required_per_shift"],
        is_admin=False,
        dt=dt,
    )

# ===== 管理者ログイン/編集は省略（既存のままでもOK） =====
# 例）/wakaba2/schedule, /wakaba2/settings 等の管理系ルートは
# これまでお渡ししたものをそのままお使いください。

# ===== ルーティング確認 =====
@app.route("/routes")
def routes():
    rules = sorted(str(r) for r in app.url_map.iter_rules())
    return "<pre>" + "\n".join(rules) + "</pre>"

if __name__ == "__main__":
    app.run(debug=True)
