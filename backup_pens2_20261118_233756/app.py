import os
import sqlite3
from datetime import datetime, timedelta

from flask import Flask, flash, redirect, render_template, request, send_file, url_for

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "gamefarm.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED = {"jpg", "jpeg", "png", "webp"}
PEN_TYPES = ["Breeding Pen", "Cage", "Flying Pen", "Range Area", "Brooder", "Other"]

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "totskie-gamefarm-local")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024


def db():
  conn = sqlite3.connect(DATABASE)
  conn.row_factory = sqlite3.Row
  return conn


def q(sql, args=(), one=False):
  conn = db()
  rows = conn.execute(sql, args).fetchall()
  conn.close()
  if one:
    return rows[0] if rows else None
  return rows


def run(sql, args=()):
  conn = db()
  cur = conn.execute(sql, args)
  conn.commit()
  last = cur.lastrowid
  conn.close()
  return last


def to_int(v, default=0):
  try:
    return int(str(v).strip())
  except (TypeError, ValueError):
    return default


def today():
  return datetime.now().strftime("%Y-%m-%d")


def init_db():
  conn = db()
  c = conn.cursor()
  c.execute("""CREATE TABLE IF NOT EXISTS farm_profile (
      id INTEGER PRIMARY KEY AUTOINCREMENT, farm_name TEXT NOT NULL,
      location TEXT, owner_name TEXT, contact TEXT, logo_path TEXT)""")
  c.execute("""CREATE TABLE IF NOT EXISTS birds (
      id INTEGER PRIMARY KEY AUTOINCREMENT, band_number TEXT, figba_tag TEXT,
      toe_punch TEXT, bloodline TEXT, sex TEXT, sire TEXT, dam TEXT,
      hatch_date TEXT, fighting_style TEXT,
      status TEXT DEFAULT 'Active (Breeding)', status_notes TEXT)""")
  c.execute("""CREATE TABLE IF NOT EXISTS breeding_pens (
      id INTEGER PRIMARY KEY AUTOINCREMENT, pen_name TEXT, sire TEXT, dam TEXT,
      date_paired TEXT, eggs_set INTEGER, hatched_count INTEGER,
      batch_mark TEXT, status TEXT DEFAULT 'Active')""")
  c.execute("""CREATE TABLE IF NOT EXISTS programs_and_tasks (
      id INTEGER PRIMARY KEY AUTOINCREMENT, bird_id INTEGER, program_type TEXT,
      task_title TEXT, due_date TEXT, is_done INTEGER DEFAULT 0, notes TEXT)""")
  c.execute("""CREATE TABLE IF NOT EXISTS weight_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT, bird_id INTEGER, log_date TEXT,
      weight_g INTEGER, flag TEXT)""")
  cols = [r[1] for r in c.execute("PRAGMA table_info(breeding_pens)").fetchall()]
  if "pen_type" not in cols:
    c.execute("ALTER TABLE breeding_pens ADD COLUMN pen_type TEXT DEFAULT 'Breeding Pen'")
  c.execute("UPDATE breeding_pens SET pen_type='Breeding Pen' WHERE pen_type IS NULL OR pen_type=''")
  cols = [r[1] for r in c.execute("PRAGMA table_info(birds)").fetchall()]
  if "pen_id" not in cols:
    c.execute("ALTER TABLE birds ADD COLUMN pen_id INTEGER")
  if not c.execute("SELECT 1 FROM farm_profile LIMIT 1").fetchone():
    c.execute("INSERT INTO farm_profile (farm_name) VALUES ('Totskie Gamefarm')")
  conn.commit()
  conn.close()


init_db()


@app.context_processor
def inject_farm():
  farm = q("SELECT * FROM farm_profile LIMIT 1", one=True)
  logo = None
  if farm and farm["logo_path"]:
    p = os.path.join(BASE_DIR, "static", farm["logo_path"])
    if os.path.isfile(p):
      logo = url_for("static", filename=farm["logo_path"]) + "?v=" + str(int(os.path.getmtime(p)))
  if not logo and os.path.isfile(os.path.join(BASE_DIR, "static", "totskie_logo.svg")):
    logo = url_for("static", filename="totskie_logo.svg")
  return {"hdr_farm": farm, "hdr_logo": logo}


@app.template_filter("blabel")
def blabel(b):
  return b["band_number"] or b["figba_tag"] or b["toe_punch"] or "#%s" % b["id"]


# ---------- Dashboard ----------
@app.route("/")
def dashboard():
  t = today()
  pens = q("SELECT COUNT(*) c FROM breeding_pens WHERE status='Active'", one=True)["c"]
  pen_counts = q("SELECT pen_type, COUNT(*) c FROM breeding_pens WHERE status='Active' GROUP BY pen_type ORDER BY pen_type")
  keep = q("SELECT COUNT(*) c FROM birds WHERE status='Active (Conditioning)'", one=True)["c"]
  sick = q("SELECT COUNT(*) c FROM programs_and_tasks WHERE program_type='Sick Bay' AND is_done=0", one=True)["c"]
  tasks = q("""SELECT t.*, b.band_number, b.figba_tag, b.toe_punch
      FROM programs_and_tasks t LEFT JOIN birds b ON b.id = t.bird_id
      WHERE t.program_type != 'Sick Bay'
        AND (t.due_date = ? OR (t.due_date < ? AND t.is_done = 0))
      ORDER BY t.is_done, t.due_date""", (t, t))
  return render_template("dashboard.html", pens=pens, pen_counts=pen_counts, keep=keep, sick=sick, tasks=tasks, today=t)


@app.route("/task/<int:task_id>/toggle", methods=["POST"])
def task_toggle(task_id):
  run("UPDATE programs_and_tasks SET is_done = 1 - is_done WHERE id=?", (task_id,))
  return redirect(request.referrer or url_for("dashboard"))


# ---------- Settings ----------
def save_logo(file):
  name = file.filename
  ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
  if ext not in ALLOWED:
    return None
  os.makedirs(UPLOAD_DIR, exist_ok=True)
  original = os.path.join(UPLOAD_DIR, "logo_original." + ext)
  file.save(original)
  try:
    from PIL import Image
    img = Image.open(original).convert("RGBA")
    img.thumbnail((512, 512))
    img.save(os.path.join(UPLOAD_DIR, "logo.png"), "PNG")
    return "uploads/logo.png"
  except Exception:
    return "uploads/logo_original." + ext


@app.route("/farm-profile", methods=["GET", "POST"])
def farm_profile():
  farm = q("SELECT * FROM farm_profile LIMIT 1", one=True)
  if request.method == "POST":
    f = request.form
    name = f.get("farm_name", "").strip()
    if not name:
      flash("Farm name is required.", "error")
      return redirect(url_for("farm_profile"))
    logo = farm["logo_path"] if farm else None
    if f.get("remove_logo"):
      logo = None
    up = request.files.get("logo")
    if up and up.filename:
      saved = save_logo(up)
      if saved:
        logo = saved
      else:
        flash("Logo must be JPG, PNG or WEBP.", "error")
    vals = (name, f.get("location", "").strip(), f.get("owner_name", "").strip(),
            f.get("contact", "").strip(), logo)
    if farm:
      run("UPDATE farm_profile SET farm_name=?, location=?, owner_name=?, contact=?, logo_path=? WHERE id=?",
          vals + (farm["id"],))
    else:
      run("INSERT INTO farm_profile (farm_name, location, owner_name, contact, logo_path) VALUES (?,?,?,?,?)", vals)
    flash("Farm profile saved.", "ok")
    return redirect(url_for("dashboard"))
  return render_template("farm_profile.html", farm=farm)


# ---------- Search ----------
@app.route("/search")
def search_bird():
  term = request.args.get("q", "").strip()
  birds = []
  if term:
    like = "%" + term + "%"
    birds = q("""SELECT * FROM birds WHERE band_number LIKE ? OR figba_tag LIKE ?
        OR toe_punch LIKE ? OR bloodline LIKE ? ORDER BY id DESC""", (like,) * 4)
  return render_template("search_results.html", birds=birds, term=term)


# ---------- Breeding ----------
@app.route("/breeding")
def breeding():
  pens = q("""SELECT p.*, (SELECT COUNT(*) FROM birds b WHERE b.pen_id = p.id) AS bird_count
      FROM breeding_pens p ORDER BY p.status, p.pen_type, p.pen_name""")
  birds = q("""SELECT b.*, p.pen_name AS pen_name FROM birds b
      LEFT JOIN breeding_pens p ON p.id = b.pen_id ORDER BY b.id DESC""")
  active_pens = q("SELECT id, pen_name, pen_type FROM breeding_pens WHERE status='Active' ORDER BY pen_type, pen_name")
  return render_template("breeding.html", pens=pens, birds=birds, active_pens=active_pens, pen_types=PEN_TYPES)


@app.route("/breeding/pen/add", methods=["POST"])
def pen_add():
  f = request.form
  name = f.get("pen_name", "").strip()
  ptype = f.get("pen_type", "Breeding Pen")
  if ptype not in PEN_TYPES:
    ptype = "Other"
  if not name:
    flash("Name is required.", "error")
    return redirect(url_for("breeding"))
  if q("SELECT 1 FROM breeding_pens WHERE lower(pen_name)=lower(?) AND status='Active'", (name,), one=True):
    flash("An active pen or area named %s already exists." % name, "error")
    return redirect(url_for("breeding"))
  if ptype == "Breeding Pen":
    sire, dam = f.get("sire", "").strip(), f.get("dam", "").strip()
    paired, eggs = f.get("date_paired", ""), max(0, to_int(f.get("eggs_set")))
    mark = f.get("batch_mark", "").strip()
  else:
    sire = dam = paired = mark = ""
    eggs = 0
  run("""INSERT INTO breeding_pens (pen_name, pen_type, sire, dam, date_paired, eggs_set,
      hatched_count, batch_mark) VALUES (?,?,?,?,?,?,?,?)""",
      (name, ptype, sire, dam, paired, eggs, 0, mark))
  flash("%s added." % ptype, "ok")
  return redirect(url_for("breeding"))


@app.route("/breeding/pen/<int:pen_id>/update", methods=["POST"])
def pen_update(pen_id):
  run("UPDATE breeding_pens SET eggs_set=?, hatched_count=? WHERE id=?",
      (to_int(request.form.get("eggs_set")), to_int(request.form.get("hatched_count")), pen_id))
  return redirect(url_for("breeding"))


@app.route("/breeding/pen/<int:pen_id>/toggle", methods=["POST"])
def pen_toggle(pen_id):
  run("UPDATE breeding_pens SET status = CASE WHEN status='Active' THEN 'Closed' ELSE 'Active' END WHERE id=?",
      (pen_id,))
  return redirect(url_for("breeding"))


def valid_pen_id(v):
  pid = to_int(v)
  if pid and q("SELECT 1 FROM breeding_pens WHERE id=?", (pid,), one=True):
    return pid
  return None


@app.route("/breeding/bird/add", methods=["POST"])
def bird_add():
  f = request.form
  if not any(f.get(k, "").strip() for k in ("band_number", "figba_tag", "toe_punch")):
    flash("Enter a toe-punch, wingband or FIGBA tag.", "error")
    return redirect(url_for("breeding"))
  run("""INSERT INTO birds (band_number, figba_tag, toe_punch, bloodline, sex, sire,
      dam, hatch_date, fighting_style, pen_id) VALUES (?,?,?,?,?,?,?,?,?,?)""",
      tuple(f.get(k, "").strip() for k in ("band_number", "figba_tag", "toe_punch",
            "bloodline", "sex", "sire", "dam", "hatch_date", "fighting_style"))
      + (valid_pen_id(f.get("pen_id")),))
  flash("Bird added.", "ok")
  return redirect(url_for("breeding"))


@app.route("/breeding/bird/<int:bird_id>/move", methods=["POST"])
def bird_move(bird_id):
  run("UPDATE birds SET pen_id=? WHERE id=?", (valid_pen_id(request.form.get("pen_id")), bird_id))
  flash("Location updated.", "ok")
  return redirect(url_for("breeding"))


@app.route("/breeding/bird/<int:bird_id>/tag", methods=["POST"])
def bird_tag(bird_id):
  f = request.form
  run("UPDATE birds SET band_number=?, figba_tag=? WHERE id=?",
      (f.get("band_number", "").strip(), f.get("figba_tag", "").strip(), bird_id))
  flash("Tags updated.", "ok")
  return redirect(url_for("breeding"))


# ---------- Conditioning ----------
@app.route("/conditioning")
def conditioning():
  in_keep = q("""SELECT b.*,
      (SELECT weight_g FROM weight_log w WHERE w.bird_id=b.id ORDER BY w.log_date DESC, w.id DESC LIMIT 1) AS last_weight,
      (SELECT flag FROM weight_log w WHERE w.bird_id=b.id ORDER BY w.log_date DESC, w.id DESC LIMIT 1) AS last_flag,
      (SELECT task_title FROM programs_and_tasks t WHERE t.bird_id=b.id AND t.program_type='Keep' AND t.is_done=0 ORDER BY t.due_date LIMIT 1) AS next_task,
      (SELECT due_date FROM programs_and_tasks t WHERE t.bird_id=b.id AND t.program_type='Keep' AND t.is_done=0 ORDER BY t.due_date LIMIT 1) AS next_due
      FROM birds b WHERE b.status='Active (Conditioning)' ORDER BY b.id DESC""")
  candidates = q("SELECT * FROM birds WHERE status != 'Active (Conditioning)' ORDER BY id DESC")
  return render_template("conditioning.html", in_keep=in_keep, candidates=candidates, today=today())


@app.route("/conditioning/start", methods=["POST"])
def keep_start():
  f = request.form
  bird_id = to_int(f.get("bird_id"))
  bird = q("SELECT * FROM birds WHERE id=?", (bird_id,), one=True)
  if not bird:
    flash("Choose a bird first.", "error")
    return redirect(url_for("conditioning"))
  try:
    start = datetime.strptime(f.get("start_date") or today(), "%Y-%m-%d")
  except ValueError:
    flash("Invalid start date.", "error")
    return redirect(url_for("conditioning"))
  days = max(2, min(to_int(f.get("days"), 21), 45))
  spar = {int(x) for x in f.get("spar_days", "").replace(" ", "").split(",") if x.isdigit()}
  vitamins = f.get("vitamins", "").strip()
  label = blabel(bird)
  for d in range(1, days + 1):
    parts = []
    if d == 1:
      parts.append("Deworm & delouse")
    if d in spar:
      parts.append("Sparring (early morning)")
    if (d - 1) in spar:
      parts.append("Bathe/clean after sparring")
    if d == days:
      parts = ["FIGHT DAY"]
    elif d == days - 1:
      parts.append("Rest, light feeding")
    if vitamins and d != days:
      parts.append("Vitamins: " + vitamins)
    if not parts:
      parts.append("Feed, exercise, weigh")
    due = (start + timedelta(days=d - 1)).strftime("%Y-%m-%d")
    run("""INSERT INTO programs_and_tasks (bird_id, program_type, task_title, due_date, is_done, notes)
        VALUES (?, 'Keep', ?, ?, 0, ?)""", (bird_id, "Day %d: %s" % (d, " • ".join(parts)), due, label))
  run("UPDATE birds SET status='Active (Conditioning)' WHERE id=?", (bird_id,))
  flash("%d-day keep started for %s." % (days, label), "ok")
  return redirect(url_for("conditioning"))


@app.route("/conditioning/weight", methods=["POST"])
def weight_add():
  f = request.form
  bird_id, w = to_int(f.get("bird_id")), to_int(f.get("weight_g"))
  if not bird_id or w <= 0:
    flash("Enter a valid weight in grams.", "error")
    return redirect(url_for("conditioning"))
  run("INSERT INTO weight_log (bird_id, log_date, weight_g, flag) VALUES (?,?,?,?)",
      (bird_id, f.get("log_date") or today(), w, f.get("flag", "")))
  flash("Weight logged.", "ok")
  return redirect(url_for("conditioning"))


@app.route("/conditioning/<int:bird_id>/end", methods=["POST"])
def keep_end(bird_id):
  run("UPDATE birds SET status='Active (Breeding)' WHERE id=?", (bird_id,))
  run("DELETE FROM programs_and_tasks WHERE bird_id=? AND program_type='Keep' AND is_done=0", (bird_id,))
  flash("Keep ended.", "ok")
  return redirect(url_for("conditioning"))


# ---------- Health ----------
@app.route("/health")
def health():
  sick = q("""SELECT t.*, b.band_number, b.figba_tag, b.toe_punch FROM programs_and_tasks t
      LEFT JOIN birds b ON b.id = t.bird_id WHERE t.program_type='Sick Bay'
      ORDER BY t.is_done, t.id DESC""")
  upcoming = q("""SELECT t.*, b.band_number, b.figba_tag, b.toe_punch FROM programs_and_tasks t
      LEFT JOIN birds b ON b.id = t.bird_id WHERE t.program_type='Health' AND t.is_done=0
      ORDER BY t.due_date LIMIT 30""")
  birds = q("SELECT * FROM birds ORDER BY id DESC")
  return render_template("health.html", sick=sick, upcoming=upcoming, birds=birds, today=today())


@app.route("/health/sick", methods=["POST"])
def sick_add():
  f = request.form
  title = f.get("title", "").strip()
  if not title:
    flash("Describe the problem.", "error")
    return redirect(url_for("health"))
  run("""INSERT INTO programs_and_tasks (bird_id, program_type, task_title, due_date, is_done, notes)
      VALUES (?, 'Sick Bay', ?, ?, 0, ?)""",
      (to_int(f.get("bird_id")) or None, title, today(), f.get("notes", "").strip()))
  flash("Added to Sick Bay.", "ok")
  return redirect(url_for("health"))


@app.route("/health/<int:task_id>/recover", methods=["POST"])
def sick_recover(task_id):
  run("UPDATE programs_and_tasks SET is_done = 1 WHERE id=?", (task_id,))
  flash("Marked recovered.", "ok")
  return redirect(url_for("health"))


@app.route("/health/task", methods=["POST"])
def health_task_add():
  f = request.form
  title = f.get("title", "").strip()
  try:
    start = datetime.strptime(f.get("due_date") or today(), "%Y-%m-%d")
  except ValueError:
    flash("Invalid date.", "error")
    return redirect(url_for("health"))
  if not title:
    flash("Enter a task title.", "error")
    return redirect(url_for("health"))
  gap = max(0, to_int(f.get("repeat_days")))
  times = min(max(1, to_int(f.get("times"), 1)), 60) if gap else 1
  bird_id = to_int(f.get("bird_id")) or None
  for i in range(times):
    due = (start + timedelta(days=gap * i)).strftime("%Y-%m-%d")
    run("""INSERT INTO programs_and_tasks (bird_id, program_type, task_title, due_date, is_done, notes)
        VALUES (?, 'Health', ?, ?, 0, '')""", (bird_id, title, due))
  flash("Health task scheduled.", "ok")
  return redirect(url_for("health"))


# ---------- Tools ----------
@app.route("/tools")
def tools():
  return render_template("tools.html")


@app.route("/help")
def help_page():
  return render_template("help.html")


@app.route("/tools/backup")
def tools_backup():
  stamp = datetime.now().strftime("%Y%m%d_%H%M")
  return send_file(DATABASE, as_attachment=True, download_name="totskie_backup_%s.db" % stamp)


if __name__ == "__main__":
  app.run(debug=False, host="0.0.0.0", port=5000)
