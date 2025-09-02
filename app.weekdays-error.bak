import os
import json
import calendar
import datetime as dt
from pathlib import Path
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, abort
)

# ====== 蝓ｺ譛ｬ險ｭ螳・======
app = Flask(__name__)

# 繧ｻ繝・す繝ｧ繝ｳ骰ｵ・亥ｿ・茨ｼ・
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

# 繝代せ繝ｯ繝ｼ繝会ｼ亥・騾壹ヱ繧ｹ繝ｯ繝ｼ繝画婿蠑擾ｼ・
STAFF_PASSWORD = os.environ.get("STAFF_PASSWORD", "staffpass")   # 蠕捺･ｭ蜩｡逕ｨ
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "adminpass")   # 邂｡逅・・畑・域里蟄倥・邂｡逅・・Ο繧ｰ繧､繝ｳ・・

# 蜿匁桶縺・ｺ苓・
STORES = {
    "wakaba2": "若葉2丁目店",
    "akitsu": "秋津新町店",
}

# 繝・・繧ｿ繝・ぅ繝ｬ繧ｯ繝医Μ
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


# ====== 繝ｦ繝ｼ繝・ぅ繝ｪ繝・ぅ ======
def store_exists(store_id: str) -> bool:
    return store_id in STORES

def month_bounds(year: int, month: int):
    """縺昴・譛医・1譌･縲懈忰譌･縺ｮ譌･莉倡ｯ・峇繧定ｿ斐☆"""
    first = dt.date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    last = dt.date(year, month, last_day)
    return first, last

def build_calendar(year: int, month: int):
    """陦ｨ遉ｺ逕ｨ縺ｫ騾ｱ縺斐→縺ｮ譌･莉倬・蛻暦ｼ・縺ｯ隧ｲ蠖薙↑縺暦ｼ峨ｒ菴懊ｋ"""
    cal = calendar.Calendar(firstweekday=0)  # 譛域屆髢句ｧ九↑繧・0竊・繧定ｪｿ謨ｴ
    weeks = []
    month_days = cal.monthdayscalendar(year, month)
    for w in month_days:
        weeks.append(w)
    return weeks

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


# ====== 逕ｻ髱｢蜈ｱ騾壹・繝槭せ繧ｿ ======
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]
SHIFTS = ["socho", "gozen", "gogo", "yugata", "shinya"]
SHIFTS_LABELS = {
    "socho":  "早朝",
    "gozen":  "午前",
    "gogo":   "午後",
    "yugata": "夕方",
    "shinya": "深夜",
}


# ====== 繝ｩ繝ｳ繝・ぅ繝ｳ繧ｰ ======
@app.route("/")
def landing():
    return render_template("landing.html", stores=STORES)


# ====== 蠕捺･ｭ蜩｡繝ｭ繧ｰ繧､繝ｳ ======
@app.route("/<store_id>/staff-login", methods=["GET", "POST"])
def staff_login(store_id):
    require_store_or_404(store_id)
    if request.method == "POST":
        pwd = request.form.get("password", "")
        next_url = request.form.get("next") or url_for("view", store_id=store_id)
        if pwd == STAFF_PASSWORD:
            session[f"staff_authed_{store_id}"] = True
            return redirect(next_url)
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
        now=dt.date.today(),
    )


# ====== 邂｡逅・・ｼ壼錐邁ｿ繝ｻ螳壼藤 ======
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
                flash("蜈･蜉帙′遨ｺ縺ｮ縺溘ａ蜷咲ｰｿ縺ｯ螟画峩縺励∪縺帙ｓ縺ｧ縺励◆縲・, "info")
            return redirect(url_for("settings", store_id=store_id))

        return redirect(url_for("settings", store_id=store_id))

    return render_template(
        "settings.html",
        store_id=store_id,
        store_name=store_name(store_id),
        employees=employees,
        employees_text="\n".join(employees),
    )


# ====== 逶ｴ謗･URL縺ｧ /<store_id>/ 縺ｫ譚･縺溘ｉ髢ｲ隕ｧ縺ｸ ======
@app.route("/<store_id>/")
def go_store_root(store_id):
    require_store_or_404(store_id)
    return redirect(url_for("view", store_id=store_id))


# ====== 繝ｭ繝ｼ繧ｫ繝ｫ襍ｷ蜍慕畑 ======
if __name__ == "__main__":
    app.run(debug=True)



# redeploy 2025-09-02T14:07:07
