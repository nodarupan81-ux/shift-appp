from flask import Flask, render_template, request, redirect, url_for, session, abort, flash
import os, json, calendar
import datetime as dt
from pathlib import Path

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "CHANGE_ME_TO_A_RANDOM_STRING")

# ====== 店舗名 ======
STORES = {
    "wakaba2": "若葉2丁目店",
    "akitsu": "秋津新町店",
}

# ====== 管理者アカウント ======
ADMIN_USER = "365836"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")

# ====== スタッフ共通パスワード ======
STAFF_PASSWORD = os.environ.get("STAFF_PASSWORD", "test123")

# ====== シフト定義 ======
SHIFTS = ["early", "morning", "afternoon", "evening", "night"]
SHIFTS_LABELS = {
    "early": "早朝",
    "morning": "午前",
    "afternoon": "午後",
    "evening": "夕方",
    "night": "深夜"
}

# ====== 保存ディレクトリ ======
DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
DATA_DIR.mkdir(exist_ok=True, parents=True)


# ====== ログイン関連 ======
@app.route("/<store_id>/login-admin", methods=["GET", "POST"])
def login_admin(store_id):
    if request.method == "POST":
        user = request.form.get("username", "")
        pw = request.form.get("password", "")
        if user == ADMIN_USER and pw == ADMIN_PASSWORD:
            session["admin_" + store_id] = True
            return redirect(request.args.get("next") or url_for("view", store_id=store_id))
        flash("ログイン失敗", "error")
    return render_template("login_admin.html", store_id=store_id, site_name=STORES[store_id])


@app.route("/<store_id>/staff-login", methods=["GET", "POST"])
def login_staff(store_id):
    if request.method == "POST":
        pw = request.form.get("password", "")
        if pw == STAFF_PASSWORD:
            session["staff_" + store_id] = True
            return redirect(request.args.get("next") or url_for("view", store_id=store_id))
        flash("パスワードが違います", "error")
    return render_template("login_staff.html", store_id=store_id, site_name=STORES[store_id])


@app.route("/<store_id>/logout")
def logout(store_id):
    session.clear()
    return redirect(url_for("index"))


# ====== TOP ======
@app.route("/")
def index():
    return render_template("index.html", stores=STORES)


# ====== シフト表示 ======
@app.route("/<store_id>/view")
def view(store_id):
    year = int(request.args.get("year", dt.date.today().year))
    month = int(request.args.get("month", dt.date.today().month))
    sched_file = DATA_DIR / store_id / f"schedule-{year}-{month:02}.json"
    sched = {}
    if sched_file.exists():
        with open(sched_file, "r", encoding="utf-8") as f:
            sched = json.load(f)

    return render_template(
        "view.html",
        store_id=store_id,
        site_name=STORES[store_id],
        year=year,
        month=month,
        monthrange=calendar.monthrange(year, month)[1],
        sched=sched,
        shifts=SHIFTS,
        shifts_labels=SHIFTS_LABELS,
    )


# ====== シフト編集（管理者用） ======
@app.route("/<store_id>/schedule", methods=["GET", "POST"])
def schedule(store_id):
    if not session.get("admin_" + store_id):
        return redirect(url_for("login_admin", store_id=store_id, next=request.path))

    year = int(request.args.get("year", dt.date.today().year))
    month = int(request.args.get("month", dt.date.today().month))
    sched_file = DATA_DIR / store_id / f"schedule-{year}-{month:02}.json"

    if request.method == "POST":
        data = {}
        for d in range(1, calendar.monthrange(year, month)[1] + 1):
            daykey = f"{year}-{month:02}-{d:02}"
            data[daykey] = {}
            for s in SHIFTS:
                key = f"e_{s}_{d}"
                val = request.form.getlist(key)
                if val:
                    data[daykey][s] = val
        sched_file.parent.mkdir(exist_ok=True, parents=True)
        with open(sched_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        flash("保存しました", "ok")
        return redirect(url_for("schedule", store_id=store_id, year=year, month=month))

    sched = {}
    if sched_file.exists():
        with open(sched_file, "r", encoding="utf-8") as f:
            sched = json.load(f)

    return render_template(
        "schedule.html",
        store_id=store_id,
        site_name=STORES[store_id],
        year=year,
        month=month,
        monthrange=calendar.monthrange(year, month)[1],
        sched=sched,
        shifts=SHIFTS,
        shifts_labels=SHIFTS_LABELS,
    )


# ====== スタッフ名設定（一覧表示＋追加＋削除） ======
@app.route("/<store_id>/settings", methods=["GET", "POST"])
def settings(store_id):
    if not session.get("admin_" + store_id):
        return redirect(url_for("login_admin", store_id=store_id, next=request.path))

    staff_file = DATA_DIR / f"employees_{store_id}.json"

    # 現在のリストを読み込み
    staff = []
    if staff_file.exists():
        try:
            with open(staff_file, "r", encoding="utf-8") as f:
                staff = json.load(f)
        except Exception:
            staff = []
    if not isinstance(staff, list):
        staff = []

    if request.method == "POST":
        # 単体削除
        if "delete_name" in request.form:
            delname = request.form.get("delete_name", "").strip()
            staff = [s for s in staff if s != delname]

        # 追加保存
        elif request.form.get("action") == "add":
            new_staff = []
            for i in range(1, 6):
                val = (request.form.get(f"staff{i}") or "").strip()
                if val:
                    new_staff.append(val)

            bulk = (request.form.get("bulk") or "").strip()
            if bulk:
                for token in bulk.replace("、", ",").replace("\r", "").split("\n"):
                    for p in token.split(","):
                        name = p.strip()
                        if name:
                            new_staff.append(name)

            staff = list(dict.fromkeys(staff + new_staff))

        # 一括削除
        elif request.form.get("action") == "bulk_delete":
            targets = request.form.getlist("chk[]")
            targets = set(t.strip() for t in targets if t.strip())
            staff = [s for s in staff if s not in targets]

        # 保存
        with open(staff_file, "w", encoding="utf-8") as f:
            json.dump(staff, f, ensure_ascii=False, indent=2)

        flash("スタッフ名を更新しました。", "ok")
        return redirect(url_for("settings", store_id=store_id))

    return render_template(
        "settings.html",
        store_id=store_id,
        site_name=STORES[store_id],
        staff=staff
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
