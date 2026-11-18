import os, shutil, glob, time, sys

def stop(msg):
    print("STOP: " + msg)
    print("Walay giusab nga file.")
    sys.exit(1)

for f in ("app.py", "templates/dashboard.html", "templates/pen.html"):
    if not os.path.isfile(f):
        stop("Wala makita ang " + f + " (i-run sa sulod sa ~/Gamefowl_Manager)")

app = open("app.py", encoding="utf-8").read()
dash = open("templates/dashboard.html", encoding="utf-8").read()

if "def bird_place" in app:
    stop("Na-patch na kini.")

ANCHOR = "# ---------- Search ----------"
if app.count(ANCHOR) != 1:
    stop("Wala makita ang Search marker sa app.py")

OLD_BTN = '<a class="btn-outline" href="{{ url_for(\'breeding\') }}">+ Add Pen</a></div>'
if dash.count(OLD_BTN) != 1:
    stop("Wala makita ang + Add Pen button sa dashboard.html")

ROUTE = '''# ---------- Add or Move Bird ----------
@app.route("/bird/add", methods=["GET", "POST"])
def bird_place():
  from flask import redirect as _redir, flash as _flash
  pens_all = q("SELECT id, pen_name FROM breeding_pens ORDER BY id")
  if request.method == "GET":
    return render_template("bird_place.html", pens=pens_all)
  f = request.form
  pen_id = valid_pen_id(f.get("pen_id"))
  band = f.get("band_number", "").strip()
  toe = f.get("toe_punch", "").strip()
  if not pen_id:
    _flash("Choose a pen.", "error")
    return _redir("/bird/add")
  if not band and not toe:
    _flash("Enter a wingband or toe-punch.", "error")
    return _redir("/bird/add")
  found = None
  if band:
    found = q("SELECT * FROM birds WHERE band_number=?", (band,), one=True)
  if not found and toe:
    rows = q("SELECT * FROM birds WHERE toe_punch=?", (toe,))
    if len(rows) > 1:
      _flash("Several birds share this toe-punch. Use the wingband.", "error")
      return _redir("/bird/add")
    found = rows[0] if rows else None
  if found:
    run("UPDATE birds SET pen_id=? WHERE id=?", (pen_id, found["id"]))
    _flash("Bird moved to the pen.", "ok")
  else:
    run("INSERT INTO birds (band_number, toe_punch, status, pen_id) VALUES (?,?,?,?)",
        (band, toe, "Active (Breeding)", pen_id))
    _flash("Bird added.", "ok")
  return _redir("/pen/%d" % pen_id)


'''

TEMPLATE = '''{% extends "base.html" %}
{% block content %}
<h1>Add or Move Bird</h1>
<p class="muted">Enter the tag and choose a pen. A new tag adds a new bird. An existing tag moves that bird to the pen.</p>
<form method="post" class="card form-grid">
  <label>Pen<select name="pen_id" required><option value="">— Choose pen —</option>{% for p in pens %}<option value="{{ p.id }}">{{ p.pen_name }}</option>{% endfor %}</select></label>
  <label>Wingband<input name="band_number"></label>
  <label>Toe-punch<input name="toe_punch"></label>
  <button type="submit">Save Bird</button>
</form>
{% endblock %}
'''

NEW_BTN = ('<span><a class="btn-outline" href="{{ url_for(\'breeding\') }}">+ Add Pen</a> '
           '<a class="btn-outline" href="/bird/add">+ Add Bird</a></span></div>')

stamp = time.strftime("%Y%m%d_%H%M%S")
bk = "backup_bird_" + stamp
os.makedirs(bk)
for f in ("app.py", "templates/dashboard.html", "templates/pen.html", "gamefarm.db"):
    if os.path.isfile(f):
        shutil.copy(f, bk)

app = app.replace(ANCHOR, ROUTE + ANCHOR)
app = app.replace("Chicken added.", "Bird added.")
open("app.py", "w", encoding="utf-8").write(app)

open("templates/dashboard.html", "w", encoding="utf-8").write(dash.replace(OLD_BTN, NEW_BTN))
open("templates/bird_place.html", "w", encoding="utf-8").write(TEMPLATE)

for t in glob.glob("templates/*.html"):
    s = open(t, encoding="utf-8").read()
    if "Chicken" in s:
        open(t, "w", encoding="utf-8").write(s.replace("Chicken", "Bird"))

print("Backup: " + os.path.abspath(bk))
print("OK! Na-add ang + Add Bird, ug 'Chicken' na 'Bird' na.")
