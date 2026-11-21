
import re
from contextlib import contextmanager
from datetime import date

import pymysql
import pymysql.cursors
from flask import (Flask, abort, flash, g, redirect, render_template,
                   request, url_for)

import config

app = Flask(__name__)
app.secret_key = "repairpass-dev-key"  



def get_db():
    if "db" not in g:
        g.db = pymysql.connect(
            host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER,
            password=config.DB_PASSWORD, database=config.DB_NAME,
            charset="utf8mb4", autocommit=True,
            cursorclass=pymysql.cursors.DictCursor)
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def q(sql, params=()):
    """Run a SELECT and return all rows as dicts."""
    with get_db().cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def q1(sql, params=()):
    rows = q(sql, params)
    return rows[0] if rows else None


@contextmanager
def tx():
    """One transaction: commits on success, rolls back on any error."""
    db = get_db()
    db.begin()
    try:
        with db.cursor() as cur:
            yield cur
        db.commit()
    except Exception:
        db.rollback()
        raise


def db_error(e):
    """Short readable text from a MySQL error."""
    return e.args[-1] if e.args else str(e)


PK = {
    "MANUFACTURER": "manufacturer_id", "CATEGORY": "category_id",
    "PRODUCT_MODEL": "model_id", "PRODUCT": "product_id", "OWNER": "owner_id",
    "OWNERSHIP": "ownership_id", "REPAIR_CENTER": "center_id",
    "REPAIR": "repair_id", "PART": "part_id",
    "WARRANTY_PROVIDER": "provider_id", "WARRANTY": "warranty_id",
}
PREFIX = {
    "MANUFACTURER": "MF", "CATEGORY": "C", "PRODUCT_MODEL": "M",
    "PRODUCT": "P", "OWNER": "O", "OWNERSHIP": "H", "REPAIR_CENTER": "RC",
    "REPAIR": "R", "PART": "PT", "WARRANTY_PROVIDER": "WP", "WARRANTY": "W",
}
ALL_TABLES = list(PK) + ["REPAIR_PART"]


MASTER = {
    "MANUFACTURER": ["name", "country", "support_website"],
    "CATEGORY": ["category_name"],
    "PRODUCT_MODEL": ["manufacturer_id", "category_id", "model_name", "release_year"],
    "OWNER": ["name", "contact_info"],
    "REPAIR_CENTER": ["center_name", "city", "contact_info", "is_authorized"],
    "PART": ["part_name", "part_type"],
    "WARRANTY_PROVIDER": ["provider_name", "contact_info"],
}
FK_LOOKUP = {
    "manufacturer_id": ("MANUFACTURER", "manufacturer_id", "name"),
    "category_id": ("CATEGORY", "category_id", "category_name"),
}


def next_id(cur, table):
    """Generate the next ID such as P1003, MF03, RC02."""
    col, pfx = PK[table], PREFIX[table]
    cur.execute(f"SELECT {col} AS id FROM {table}")
    nums = []
    for r in cur.fetchall():
        digits = re.sub(r"\D", "", r["id"])
        if digits:
            nums.append(int(digits))
    return f"{pfx}{max(nums, default=0) + 1:02d}"


def parse_date(s):
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None



@app.route("/")
def index():
    devices = q("""
        SELECT p.serial_number, mf.name AS maker, m.model_name, c.category_name,
               (SELECT o.name FROM OWNERSHIP h JOIN OWNER o ON o.owner_id = h.owner_id
                 WHERE h.product_id = p.product_id AND h.end_date IS NULL) AS current_owner
        FROM PRODUCT p
        JOIN PRODUCT_MODEL m ON m.model_id = p.model_id
        JOIN MANUFACTURER mf ON mf.manufacturer_id = m.manufacturer_id
        JOIN CATEGORY c ON c.category_id = m.category_id
        ORDER BY p.product_id""")
    return render_template("index.html", devices=devices)


@app.route("/search")
def search():
    serial = request.args.get("serial", "").strip()
    if not serial:
        return redirect(url_for("index"))
    return redirect(url_for("passport", serial=serial))



@app.route("/passport/<serial>")
def passport(serial):
    d = q1("""
        SELECT p.*, m.model_name, m.release_year, mf.name AS maker,
               mf.support_website, c.category_name
        FROM PRODUCT p
        JOIN PRODUCT_MODEL m ON m.model_id = p.model_id
        JOIN MANUFACTURER mf ON mf.manufacturer_id = m.manufacturer_id
        JOIN CATEGORY c ON c.category_id = m.category_id
        WHERE p.serial_number = %s""", (serial,))
    if d is None:
        flash(f"No device found with serial/IMEI '{serial}'.", "error")
        return redirect(url_for("index"))
    pid = d["product_id"]

    owners = q("""
        SELECT o.name, o.contact_info, h.start_date, h.end_date
        FROM OWNERSHIP h JOIN OWNER o ON o.owner_id = h.owner_id
        WHERE h.product_id = %s ORDER BY h.start_date""", (pid,))
    current = next((o for o in owners if o["end_date"] is None), None)

    
    repairs = q("""
        SELECT r.repair_id, r.repair_date, r.issue_description, r.work_performed,
               r.labour_cost, rc.center_name, rc.city, rc.is_authorized,
               r.labour_cost + COALESCE(SUM(rp.part_cost * rp.quantity), 0) AS total_cost
        FROM REPAIR r
        JOIN REPAIR_CENTER rc ON rc.center_id = r.center_id
        LEFT JOIN REPAIR_PART rp ON rp.repair_id = r.repair_id
        WHERE r.product_id = %s
        GROUP BY r.repair_id, r.repair_date, r.issue_description, r.work_performed,
                 r.labour_cost, rc.center_name, rc.city, rc.is_authorized
        ORDER BY r.repair_date""", (pid,))

    parts_by_repair = {}
    for row in q("""
        SELECT rp.repair_id, pt.part_name, rp.quantity, rp.part_cost
        FROM REPAIR_PART rp
        JOIN PART pt ON pt.part_id = rp.part_id
        JOIN REPAIR r ON r.repair_id = rp.repair_id
        WHERE r.product_id = %s""", (pid,)):
        parts_by_repair.setdefault(row["repair_id"], []).append(row)

    
    warranties = q("""
        SELECT wp.provider_name, wp.contact_info, w.start_date, w.end_date,
               CASE WHEN CURDATE() BETWEEN w.start_date AND w.end_date
                    THEN 'Active' ELSE 'Expired' END AS status
        FROM WARRANTY w JOIN WARRANTY_PROVIDER wp ON wp.provider_id = w.provider_id
        WHERE w.product_id = %s ORDER BY w.start_date""", (pid,))

    
    view_rows = q("SELECT * FROM vw_DevicePassport WHERE serial_number = %s", (serial,))
    view_cols = list(view_rows[0].keys()) if view_rows else []

    
    timeline = []
    for o in owners:
        timeline.append((o["start_date"], "Ownership", f"Device acquired by {o['name']}"))
    for r in repairs:
        timeline.append((r["repair_date"], "Repair",
                         f"{r['issue_description']} at {r['center_name']} (total {r['total_cost']:.2f})"))
    for w in warranties:
        timeline.append((w["start_date"], "Warranty", f"{w['provider_name']} warranty starts"))
        timeline.append((w["end_date"], "Warranty", f"{w['provider_name']} warranty ends"))
    timeline.sort(key=lambda t: t[0])

    return render_template(
        "passport.html", d=d, owners=owners, current=current, repairs=repairs,
        parts_by_repair=parts_by_repair, warranties=warranties, timeline=timeline,
        view_rows=view_rows, view_cols=view_cols,
        owner_list=q("SELECT * FROM OWNER ORDER BY name"),
        centers=q("SELECT * FROM REPAIR_CENTER ORDER BY center_name"),
        part_list=q("SELECT * FROM PART ORDER BY part_name"),
        providers=q("SELECT * FROM WARRANTY_PROVIDER ORDER BY provider_name"),
        today=date.today().isoformat(),
    )



@app.route("/device/new", methods=["GET", "POST"])
def new_device():
    if request.method == "POST":
        f = request.form
        serial = f.get("serial_number", "").strip()
        purchase = f.get("purchase_date", "")
        if not serial or not parse_date(purchase) or not f.get("model_id"):
            flash("Serial number, model and a valid purchase date are required.", "error")
            return redirect(url_for("new_device"))
        try:
            with tx() as cur:
                owner_id = f.get("owner_id")
                if owner_id == "NEW":
                    if not f.get("new_owner_name", "").strip():
                        raise ValueError("Enter the new owner's name.")
                    owner_id = next_id(cur, "OWNER")
                    cur.execute("INSERT INTO OWNER VALUES (%s,%s,%s)",
                                (owner_id, f["new_owner_name"].strip(),
                                 f.get("new_owner_contact", "").strip()))
                pid = next_id(cur, "PRODUCT")
                cur.execute("INSERT INTO PRODUCT VALUES (%s,%s,%s,%s)",
                            (pid, serial, f["model_id"], purchase))
                cur.execute("INSERT INTO OWNERSHIP VALUES (%s,%s,%s,%s,NULL)",
                            (next_id(cur, "OWNERSHIP"), pid, owner_id, purchase))
        except pymysql.err.IntegrityError as e:
            if e.args and e.args[0] == 1062:
                flash("That serial/IMEI is already registered.", "error")
            else:
                flash(f"Could not register device: {db_error(e)}", "error")
            return redirect(url_for("new_device"))
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("new_device"))
        except pymysql.MySQLError as e:
            flash(f"Database error: {db_error(e)}", "error")
            return redirect(url_for("new_device"))
        flash("Device registered.", "ok")
        return redirect(url_for("passport", serial=serial))

    models = q("""
        SELECT m.model_id, CONCAT(mf.name, ' ', m.model_name) AS label
        FROM PRODUCT_MODEL m JOIN MANUFACTURER mf ON mf.manufacturer_id = m.manufacturer_id
        ORDER BY label""")
    owners = q("SELECT * FROM OWNER ORDER BY name")
    return render_template("new_device.html", models=models, owners=owners,
                           today=date.today().isoformat())


def device_or_404(pid):
    d = q1("SELECT serial_number FROM PRODUCT WHERE product_id = %s", (pid,))
    if d is None:
        abort(404)
    return d



@app.route("/device/<pid>/transfer", methods=["POST"])
def transfer(pid):
    d = device_or_404(pid)
    back = redirect(url_for("passport", serial=d["serial_number"]))
    f = request.form
    start = parse_date(f.get("start_date", ""))
    if not start:
        flash("Enter a valid transfer date.", "error")
        return back
    try:
        with tx() as cur:
            
            cur.execute("SELECT * FROM OWNERSHIP WHERE product_id = %s AND end_date IS NULL FOR UPDATE",
                        (pid,))
            current = cur.fetchone()
            if current and start < current["start_date"]:
                raise ValueError("Transfer date cannot be before the current owner's start date "
                                 f"({current['start_date']}).")
            owner_id = f.get("owner_id")
            if owner_id == "NEW":
                if not f.get("new_owner_name", "").strip():
                    raise ValueError("Enter the new owner's name.")
                owner_id = next_id(cur, "OWNER")
                cur.execute("INSERT INTO OWNER VALUES (%s,%s,%s)",
                            (owner_id, f["new_owner_name"].strip(),
                             f.get("new_owner_contact", "").strip()))
            if current and current["owner_id"] == owner_id:
                raise ValueError("That person is already the current owner.")
            if current:
                cur.execute("UPDATE OWNERSHIP SET end_date = %s WHERE ownership_id = %s",
                            (start, current["ownership_id"]))
            cur.execute("INSERT INTO OWNERSHIP VALUES (%s,%s,%s,%s,NULL)",
                        (next_id(cur, "OWNERSHIP"), pid, owner_id, start))
    except ValueError as e:
        flash(str(e), "error")
        return back
    except pymysql.MySQLError as e:
        flash(f"Database error: {db_error(e)}", "error")
        return back
    flash("Ownership transferred. Previous owner's end date = new owner's start date.", "ok")
    return back



@app.route("/device/<pid>/repair", methods=["POST"])
def add_repair(pid):
    d = device_or_404(pid)
    back = redirect(url_for("passport", serial=d["serial_number"]))
    f = request.form
    if not parse_date(f.get("repair_date", "")) or not f.get("center_id"):
        flash("Repair date and repair center are required.", "error")
        return back
    issue = f.get("issue_description", "").strip()
    work = f.get("work_performed", "").strip()
    if not issue or not work:
        flash("Describe the issue and the work performed.", "error")
        return back
    try:
        labour = float(f.get("labour_cost") or 0)
    except ValueError:
        flash("Labour cost must be a number.", "error")
        return back

    parts = []
    for i in range(1, 4):
        part_id = f.get(f"part_id_{i}")
        if not part_id:
            continue
        try:
            parts.append((part_id, int(f.get(f"qty_{i}") or 1), float(f.get(f"cost_{i}") or 0)))
        except ValueError:
            flash("Part quantity and cost must be numbers.", "error")
            return back
    if len({p[0] for p in parts}) != len(parts):
        flash("The same part is listed twice; combine it into one line with a quantity.", "error")
        return back

    try:
        with tx() as cur:
            rid = next_id(cur, "REPAIR")
            cur.execute("INSERT INTO REPAIR VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (rid, pid, f["center_id"], f["repair_date"], issue, work, labour))
            for part_id, qty, cost in parts:
                cur.execute("INSERT INTO REPAIR_PART VALUES (%s,%s,%s,%s)",
                            (rid, part_id, qty, cost))
    except pymysql.MySQLError as e:
        flash(f"Could not save repair: {db_error(e)}", "error")
        return back
    flash("Repair added to the device history.", "ok")
    return back


# --------------------------------------------------------------------------
# Add warranty
# --------------------------------------------------------------------------
@app.route("/device/<pid>/warranty", methods=["POST"])
def add_warranty(pid):
    d = device_or_404(pid)
    back = redirect(url_for("passport", serial=d["serial_number"]))
    f = request.form
    s, e = parse_date(f.get("start_date", "")), parse_date(f.get("end_date", ""))
    if not (s and e) or not f.get("provider_id"):
        flash("Provider, start date and end date are required.", "error")
        return back
    if e < s:
        flash("Warranty end date cannot be before the start date.", "error")
        return back
    try:
        with tx() as cur:
            cur.execute("INSERT INTO WARRANTY VALUES (%s,%s,%s,%s,%s)",
                        (next_id(cur, "WARRANTY"), pid, f["provider_id"], s, e))
    except pymysql.MySQLError as ex:
        flash(f"Could not save warranty: {db_error(ex)}", "error")
        return back
    flash("Warranty added.", "ok")
    return back


# --------------------------------------------------------------------------
# Table browser (all 12 tables) + add rows to lookup tables
# --------------------------------------------------------------------------
@app.route("/tables")
def tables():
    counts = {t: q1(f"SELECT COUNT(*) AS n FROM {t}")["n"] for t in ALL_TABLES}
    return render_template("tables.html", name=None, counts=counts, tables=ALL_TABLES)


@app.route("/tables/<name>", methods=["GET", "POST"])
def table_view(name):
    name = name.upper()
    if name not in ALL_TABLES:
        abort(404)

    if request.method == "POST":
        if name not in MASTER:
            abort(403)
        cols = MASTER[name]
        vals = [request.form.get(c, "").strip() for c in cols]
        if not vals[0] or any(not v for c, v in zip(cols, vals) if c in FK_LOOKUP):
            flash("Please fill the required fields.", "error")
            return redirect(url_for("table_view", name=name))
        vals = [(int(v) if c == "release_year" and v else (None if c == "release_year" else v))
                for c, v in zip(cols, vals)] if "release_year" in cols else vals
        try:
            with tx() as cur:
                cur.execute(
                    f"INSERT INTO {name} ({PK[name]}, {', '.join(cols)}) "
                    f"VALUES ({', '.join(['%s'] * (len(cols) + 1))})",
                    [next_id(cur, name)] + vals)
            flash(f"Row added to {name}.", "ok")
        except pymysql.MySQLError as e:
            flash(f"Could not add row: {db_error(e)}", "error")
        return redirect(url_for("table_view", name=name))

    rows = q(f"SELECT * FROM {name}")
    with get_db().cursor() as cur:
        cur.execute(f"SELECT * FROM {name} LIMIT 0")
        columns = [c[0] for c in cur.description]

    fields = []
    if name in MASTER:
        for c in MASTER[name]:
            spec = {"name": c, "kind": "text"}
            if c in FK_LOOKUP:
                t, idc, lab = FK_LOOKUP[c]
                spec["kind"] = "select"
                spec["options"] = [(r[idc], r[lab]) for r in
                                   q(f"SELECT {idc}, {lab} FROM {t} ORDER BY {lab}")]
            elif c == "is_authorized":
                spec["kind"] = "select"
                spec["options"] = [("No", "No"), ("Yes", "Yes")]
            elif c == "release_year":
                spec["kind"] = "number"
            fields.append(spec)
    return render_template("tables.html", name=name, columns=columns, rows=rows,
                           fields=fields, tables=ALL_TABLES, counts=None)


if __name__ == "__main__":
    app.run(debug=True)
