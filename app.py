import os
import json
import calendar
import datetime as dt
from pathlib import Path
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, abort
)

# ====== 基本設定 ======
app = Flask(__name__)

# セッション鍵（必須）
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

# パスワード（共通パスワード方式）
STAFF_PASSWORD = os.environ.get("STAFF_PASSWORD", "staffpass")   # 従業員用
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "adminpass")   # 管理者用（既存の管理者ログイン）

# 取扱い店舗
STORES = {
    "wakaba2": "若葉2丁目店",
    "akitsu": "秋津新町店",
}

# データディレクトリ
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


# ====== ユーティリティ ======
def store_exists(store_id: str) -> bool:
    return store_id in STORES

def month_bounds(year: int, month: int):
    """その月の1日〜末日の日付範囲を返す"""
    first = dt.date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    last = dt.date(year, month, last_day)
    return first, last

def build_calendar(year: int, month: int):
    """表示用に週ごとの日付配列（0は該当なし）を作る"""
    cal = calendar.Calendar(firstweekday=0)  # 月曜開始なら 0→6を調整
    # ここでは「月曜=0, 日曜=6」のまま schedule.html と連携
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
    # data/<store_id>/employees.json が優先、なければ data/employees.json のフォールバック
    path_primary = DATA_DIR / store_id / "employees.json"
    path_fallback = DATA_DIR / "employees.json"
    p = path_primary if path_primary.exists() else path_fallback
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return []

def schedule_file_path(store_id: str, year: int, month: int) -> Path:
    # data/<store_id>/<YYYY-MM>.json
    subdir = DATA_DIR / store_id
    subdir.mkdir(parents=True, exist_ok=True)
    return subdir / f"{year:04d}-{month:02d}.json"

def load_schedule(store_id: str, year: int, month: int):
    p = schedule_file_path(store_id, year, month)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    # 既定の空データ
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


# ====== 画面共通のマスタ（schedule.htmlが使う前提に合わせる） ======
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]
# 5シフト定義（内部キー）
SHIFTS = ["socho", "gozen", "gogo", "yugata", "shinya"]

# 画面に出す日本語ラベル
SHIFTS_LABELS = {
    "socho":  "早朝",
    "gozen":  "午前",
    "gogo":   "午後",
    "yugata": "夕方",
    "shinya": "深夜",
}


# ====== ランディング（店舗選択） ======
@app.route("/")
def landing():
    # ストア一覧をカード表示
    return render_template("landing.html", stores=STORES)


# ====== 従業員ログイン（共通パスワード） ======
@app.route("/<store_id>/staff-login", methods=["GET", "POST"])
def staff_login(store_id):
    require_store_or_404(store_id)
    if request.method == "POST":
        pwd = request.form.get("password", "")
        next_url = request.form.get("next") or url_for("view", store_id=store_id)
        if pwd == STAFF_PASSWORD:
            session[f"staff_authed_{store_id}"] = True
            # 従業員ログインは adminフラグは付与しない
            return redirect(next_url)
        flash("パスワードが違います。", "error")
    # GET の場合
    next_url = request.args.get("next") or url_for("view", store_id=store_id)
    return render_template("staff_login.html", store_id=store_id, store_name=store_name(store_id), next_url=next_url)


@app.route("/<store_id>/staff-logout")
def staff_logout(store_id):
    require_store_or_404(store_id)
    session.pop(f"staff_authed_{store_id}", None)
    flash("スタッフとしてログアウトしました。", "info")
    return redirect(url_for("staff_login", store_id=store_id))


# ====== 管理者ログイン（既存の管理者パスワード） ======
@app.route("/<store_id>/login-admin", methods=["GET", "POST"])
def login_admin(store_id):
    require_store_or_404(store_id)
    if request.method == "POST":
        pwd = request.form.get("password", "")
        next_url = request.args.get("next") or request.form.get("next") or url_for("schedule", store_id=store_id)
        if pwd == ADMIN_PASSWORD:
            session[f"is_admin_{store_id}"] = True
            # 管理者は閲覧も編集も可能
            session[f"staff_authed_{store_id}"] = True
            return redirect(next_url)
        flash("パスワードが違います。", "error")
    # GET
    next_url = request.args.get("next") or url_for("schedule", store_id=store_id)
    return render_template("login_admin.html", store_id=store_id, store_name=store_name(store_id), next_url=next_url)


@app.route("/logout")
def logout():
    # 全店舗のフラグをまとめてオフ
    for sid in STORES.keys():
        session.pop(f"is_admin_{sid}", None)
        session.pop(f"staff_authed_{sid}", None)
    flash("ログアウトしました。", "info")
    return redirect(url_for("landing"))


# ====== 従業員閲覧（カレンダー表示のみ） ======
@app.route("/<store_id>/view")
def view(store_id):
    require_store_or_404(store_id)

    # スタッフ・管理者いずれかの認証が必要
    if not (is_staff_authed(store_id) or is_admin(store_id)):
        return redirect(url_for("staff_login", store_id=store_id, next=url_for("view", store_id=store_id)))

    # 年月の決定（クエリ指定がなければ今月）
    today = dt.date.today()
    year = int(request.args.get("year") or today.year)
    month = int(request.args.get("month") or today.month)

    employees = load_employees(store_id)
    schedules = load_schedule(store_id, year, month)  # { "1": {"am": ["A","B"], "pm": ["C",""]}, ... }

    # schedule.html に合わせたコンテキスト構築
    weeks = build_calendar(year, month)
    prev_y, prev_m, next_y, next_m = prev_next_year_month(year, month)

    # セレクト用
    year_options = list(range(today.year - 1, today.year + 2))
    month_options = list(range(1, 13))

    return render_template(
        "schedule.html",
        title=None,
        store_name=store_name(store_id),
        store_id=store_id,
        employees=employees,
        prefill=schedules,          # schedule.html 側では prefill を参照
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
        is_admin=False,             # 従業員閲覧
        dt=dt,                      # jinja内で dt.utcnow() などを使う用
        now=dt.date.today(),        # ←「now が未定義」対策
    )


# ====== 管理者：シフト編集 ======
@app.route("/<store_id>/schedule", methods=["GET", "POST"])
def schedule(store_id):
    require_store_or_404(store_id)

    # 管理者のみ
    if not is_admin(store_id):
        return redirect(url_for("login_admin", store_id=store_id, next=url_for("schedule", store_id=store_id)))

    today = dt.date.today()
    if request.method == "POST":
        # POSTで来たら保存処理
        year = int(request.form.get("year") or today.year)
        month = int(request.form.get("month") or today.month)

        # 既存データを読み取り
        data = load_schedule(store_id, year, month)

        # 1〜末日を走査し、フォームの day_X_am_1 などから値を反映
        _, last = month_bounds(year, month)
        for day in range(1, last.day + 1):
            day_key = str(day)
            if day_key not in data:
                data[day_key] = {}
            for s in SHIFTS:
                a1 = request.form.get(f"day_{day}_{s}_1", "")
                a2 = request.form.get(f"day_{day}_{s}_2", "")
                data[day_key][s] = [a1, a2]
        save_schedule(store_id, year, month, data)
        flash("保存しました。", "success")
        # PRGパターン
        return redirect(url_for("schedule", store_id=store_id, year=year, month=month))

    # GET：編集画面表示
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
        is_admin=True,              # 管理者編集
        dt=dt,
        now=dt.date.today(),
    )


# ====== 管理者：名簿・定員（プレースホルダ） ======
@app.route("/<store_id>/settings", methods=["GET", "POST"])
def settings(store_id):
    require_store_or_404(store_id)
    if not is_admin(store_id):
        return redirect(url_for("login_admin", store_id=store_id, next=url_for("settings", store_id=store_id)))

    employees = load_employees(store_id)

    if request.method == "POST":
        # 簡易：CSV っぽいテキストで名簿を更新する例
        raw = request.form.get("employees_text", "").strip()
        new_list = [line.strip() for line in raw.splitlines() if line.strip()]
        target_path = DATA_DIR / store_id / "employees.json"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(json.dumps(new_list, ensure_ascii=False, indent=2), encoding="utf-8")
        flash("名簿を更新しました。", "success")
        return redirect(url_for("settings", store_id=store_id))

    return render_template(
        "settings.html",
        store_id=store_id,
        store_name=store_name(store_id),
        employees=employees,
    )


# ====== 直接URLで /<store_id>/ に来たら、とりあえず閲覧へ ======
@app.route("/<store_id>/")
def go_store_root(store_id):
    require_store_or_404(store_id)
    return redirect(url_for("view", store_id=store_id))


# ====== ローカル起動用 ======
if __name__ == "__main__":
    app.run(debug=True)
