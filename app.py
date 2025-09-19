# -*- coding: utf-8 -*-
import os, json, calendar, re
from pathlib import Path
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, session, abort, flash

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")
app.jinja_env.globals.update(enumerate=enumerate, range=range, len=len)

SITE_NAME = "シフト管理アプリ"
DATA_DIR = Path("data"); DATA_DIR.mkdir(exist_ok=True, parents=True)

STORES = {
    "wakaba2": "若葉２丁目店",
    "akitsu":  "秋津新町店",
}

# ←ここを固定値にします
ADMIN_PASSWORD = "admin"
STAFF_PASSWORD = "test123"

def store_dir(store_id: str) -> Path:
    p = DATA_DIR / store_id
    p.mkdir(exist_ok=True, parents=True)
    return p

def read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default

def write_json(path: Path, payload):
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def load_schedule(store_id: str, year: int, month: int) -> dict:
    return read_json(store_dir(store_id) / f"schedule-{year:04d}-{month:02d}.json", {})

def save_schedule(store_id: str, year: int, month: int, payload: dict):
    p = store_dir(store_id) / f"schedule-{year:04d}-{month:02d}.json"
    if p.exists():
        try:
            p.with_suffix(".json.bak").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass
    write_json(p, payload)

def load_employees(store_id: str) -> dict:
    return read_json(store_dir(store_id) / "employees.json", {"employees": []})

def save_employees(store_id: str, names: list[str]):
    write_json(store_dir(store_id) / "employees.json", {"employees": names})

def is_admin() -> bool:
    return session.get("role") == "admin"

def require_store_or_404(store_id: str):
    if store_id not in STORES:
        abort(404)

def month_nav(year: int, month: int):
    pm_y, pm_m = (year - 1, 12) if month == 1 else (year, month - 1)
    nm_y, nm_m = (year + 1, 1) if month == 12 else (year, month + 1)
    return pm_y, pm_m, nm_y, nm_m

@app.get("/")
def index():
    return render_template("landing.html", site_name=SITE_NAME, STORES=STORES)

@app.route("/<store_id>/login-admin", methods=["GET", "POST"])
def login_admin(store_id):
    require_store_or_404(store_id)
    next_url = request.args.get("next") or url_for("schedule", store_id=store_id)
    if request.method == "POST":
        # ここで必ず name="password" を受け取ります
        if request.form.get("password", "") == ADMIN_PASSWORD:
            session["role"] = "admin"
            flash("管理者ログイン成功", "ok")
            return redirect(next_url)
        flash("パスワードが違います", "err")
    return render_template("login_admin.html", site_name=SITE_NAME, store_id=store_id, STORES=STORES)

@app.route("/<store_id>/staff-login", methods=["GET", "POST"])
def staff_login(store_id):
    require_store_or_404(store_id)
    next_url = request.args.get("next") or url_for("view", store_id=store_id)
    if request.method == "POST":
        if request.form.get("password", "") == STAFF_PASSWORD:
            session["role"] = "staff"
            flash("スタッフログイン成功", "ok")
            return redirect(next_url)
        flash("パスワードが違います", "err")
    return render_template("staff_login.html", site_name=SITE_NAME, store_id=store_id, STORES=STORES)

@app.get("/<store_id>/logout")
def logout(store_id):
    session.clear()
    return redirect(url_for("index"))

@app.route("/<store_id>/settings", methods=["GET", "POST"])
def settings(store_id):
    require_store_or_404(store_id)
    if not is_admin():
        return redirect(url_for("login_admin", store_id=store_id, next=url_for("settings", store_id=store_id)))
    if request.method == "POST":
        raw = request.form.get("employees", "") or request.form.get("names", "")
        parts = [p.strip() for p in raw.replace("、", ",").replace("\r", "").replace("\n", ",").split(",")]
        names = [p for p in parts if p]
        save_employees(store_id, names)
        flash("従業員リストを更新しました。", "ok")
        return redirect(url_for("settings", store_id=store_id))
    names = load_employees(store_id).get("employees", [])
    return render_template("settings.html", site_name=SITE_NAME, store_id=store_id, names=names, STORES=STORES)

@app.route("/<store_id>/schedule", methods=["GET", "POST"])
def schedule(store_id):
    require_store_or_404(store_id)
    if not is_admin():
        return redirect(url_for("login_admin", store_id=store_id, next=url_for("schedule", store_id=store_id)))

    today = date.today()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))
    ndays = calendar.monthrange(year, month)[1]

    if request.method == "POST":
        existing = load_schedule(store_id, year, month)

        # e_DD_key_i を集計
        payload = {}
        pat = re.compile(r"^e_(\d{2})_(am0|am|pm|eve|night)_(\d+)$")
        for k, v in request.form.items():
            m = pat.match(k)
            if not m: continue
            dd, key, idx = m.group(1), m.group(2), int(m.group(3))
            day = str(int(dd))
            payload.setdefault(day, {}).setdefault(key, [])
            arr = payload[day][key]
            while len(arr) < idx: arr.append("")
            arr[idx-1] = v.strip()

        # 何も入力が無ければ保存しない
        has_any = any(any(any(x for x in assigns) for assigns in day_dict.values()) for day_dict in payload.values())
        if not has_any:
            flash("入力が空のため、保存をスキップしました。", "err")
            return redirect(url_for("schedule", store_id=store_id, year=year, month=month))

        merged = existing.copy() if isinstance(existing, dict) else {}
        for day, assigns in payload.items():
            merged.setdefault(day, {})
            for key, arr in assigns.items():
                merged[day][key] = arr

        save_schedule(store_id, year, month, merged)
        flash("シフトを保存しました。", "ok")
        return redirect(url_for("schedule", store_id=store_id, year=year, month=month))

    names = load_employees(store_id).get("employees", [])
    data = load_schedule(store_id, year, month)
    prev_y, prev_m, next_y, next_m = month_nav(year, month)
    return render_template("schedule.html",
        site_name=SITE_NAME, store_id=store_id,
        year=year, month=month, ndays=ndays,
        prev_y=prev_y, prev_m=prev_m, next_y=next_y, next_m=next_m,
        names=names, data=data, now=today, calendar=calendar, STORES=STORES)

@app.get("/<store_id>/view")
def view(store_id):
    require_store_or_404(store_id)
    today = date.today()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))
    ndays = calendar.monthrange(year, month)[1]
    data = load_schedule(store_id, year, month)
    prev_y, prev_m, next_y, next_m = month_nav(year, month)
    return render_template("view.html",
        site_name=SITE_NAME, store_id=store_id,
        year=year, month=month, ndays=ndays,
        prev_y=prev_y, prev_m=prev_m, next_y=next_y, next_m=next_m,
        data=data, now=today, calendar=calendar, STORES=STORES)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
