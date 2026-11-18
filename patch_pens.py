#!/usr/bin/env python3
# patch_pens.py - Pens simplification (Gamefowl_Manager)
# Run from inside ~/Gamefowl_Manager:  python patch_pens.py
import os, shutil, sys
from datetime import datetime

ROOT = os.getcwd()
if not os.path.isfile(os.path.join(ROOT, "app.py")) or not os.path.isdir(os.path.join(ROOT, "templates")):
  print("ERROR: Dili ni Gamefowl_Manager folder. Pag-cd una: cd ~/Gamefowl_Manager")
  sys.exit(1)

APP = os.path.join(ROOT, "app.py")
src = open(APP, encoding="utf-8").read()
if "pen_detail" in src:
  print("Na-patch na ni. Walay gibuhat.")
  sys.exit(0)

# ---- backup first ----
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
bdir = os.path.join(ROOT, "backup_pens2_" + stamp)
os.makedirs(os.path.join(bdir, "templates"))
shutil.copy2(APP, bdir)
for f in ("breeding.html", "dashboard.html"):
  shutil.copy2(os.path.join(ROOT, "templates", f), os.path.join(bdir, "templates"))
if os.path.isfile(os.path.join(ROOT, "gamefarm.db")):
  shutil.copy2(os.path.join(ROOT, "gamefarm.db"), bdir)
print("Backup: " + bdir)

def swap(text, old, new, label):
  if text.count(old) != 1:
    print("ERROR: dili makita ang parte sa app.py (" + label + "). Walay gibag-o. Ipakita kini sa chat.")
    sys.exit(1)
  return text.replace(old, new)

# 1) dashboard: pass the pen list
src = swap(src,
  '  return render_template("dashboard.html", pens=pens, pen_counts=pen_counts, keep=keep, sick=sick, tasks=tasks, today=t)',
  '  pen_list = q("""SELECT p.*, (SELECT COUNT(*) FROM birds b WHERE b.pen_id = p.id) AS bird_count\n'
  '      FROM breeding_pens p WHERE p.status=\'Active\' ORDER BY p.pen_name""")\n'
  '  return render_template("dashboard.html", pens=pens, pen_list=pen_list, pen_counts=pen_counts, keep=keep, sick=sick, tasks=tasks, today=t)',
  "dashboard")

# 2) pen_add: name only
start = src.index('@app.route("/breeding/pen/add", methods=["POST"])')
end = src.index('@app.route("/breeding/pen/<int:pen_id>/update", methods=["POST"])')
NEW_PEN_ADD = (
'@app.route("/breeding/pen/add", methods=["POST"])\n'
'def pen_add():\n'
'  name = request.form.get("pen_name", "").strip()\n'
'  if not name:\n'
'    flash("Name is required.", "error")\n'
'    return redirect(url_for("breeding"))\n'
'  if q("SELECT 1 FROM breeding_pens WHERE lower(pen_name)=lower(?) AND status=\'Active\'", (name,), one=True):\n'
'    flash("An active pen named %s already exists." % name, "error")\n'
'    return redirect(url_for("breeding"))\n'
'  run("""INSERT INTO breeding_pens (pen_name, pen_type, sire, dam, date_paired, eggs_set,\n'
'      hatched_count, batch_mark) VALUES (?,?,?,?,?,?,?,?)""",\n'
'      (name, "Pen", "", "", "", 0, 0, ""))\n'
'  flash("Pen added.", "ok")\n'
'  return redirect(url_for("breeding"))\n'
'\n\n')
src = src[:start] + NEW_PEN_ADD + src[end:]

# 3) new pen page routes (inserted before the bird_add route)
NEW_ROUTES = (
'@app.route("/pen/<int:pen_id>")\n'
'def pen_detail(pen_id):\n'
'  pen = q("SELECT * FROM breeding_pens WHERE id=?", (pen_id,), one=True)\n'
'  if not pen:\n'
'    flash("Pen not found.", "error")\n'
'    return redirect(url_for("breeding"))\n'
'  birds = q("SELECT * FROM birds WHERE pen_id=? ORDER BY id DESC", (pen_id,))\n'
'  other_pens = q("SELECT id, pen_name FROM breeding_pens WHERE status=\'Active\' AND id != ? ORDER BY pen_name", (pen_id,))\n'
'  return render_template("pen.html", pen=pen, birds=birds, other_pens=other_pens)\n'
'\n\n'
'@app.route("/pen/<int:pen_id>/breeding", methods=["POST"])\n'
'def pen_breeding(pen_id):\n'
'  f = request.form\n'
'  run("""UPDATE breeding_pens SET sire=?, dam=?, date_paired=?, eggs_set=?,\n'
'      hatched_count=?, batch_mark=? WHERE id=?""",\n'
'      (f.get("sire", "").strip(), f.get("dam", "").strip(), f.get("date_paired", ""),\n'
'       max(0, to_int(f.get("eggs_set"))), max(0, to_int(f.get("hatched_count"))),\n'
'       f.get("batch_mark", "").strip(), pen_id))\n'
'  flash("Breeding info saved.", "ok")\n'
'  return redirect(url_for("pen_detail", pen_id=pen_id))\n'
'\n\n'
'@app.route("/pen/<int:pen_id>/chicken/add", methods=["POST"])\n'
'def pen_chicken_add(pen_id):\n'
'  f = request.form\n'
'  if not any(f.get(k, "").strip() for k in ("band_number", "figba_tag", "toe_punch")):\n'
'    flash("Enter a toe-punch, wingband or FIGBA tag.", "error")\n'
'    return redirect(url_for("pen_detail", pen_id=pen_id))\n'
'  run("""INSERT INTO birds (band_number, figba_tag, toe_punch, bloodline, sex, sire,\n'
'      dam, hatch_date, fighting_style, pen_id) VALUES (?,?,?,?,?,?,?,?,?,?)""",\n'
'      tuple(f.get(k, "").strip() for k in ("band_number", "figba_tag", "toe_punch",\n'
'            "bloodline", "sex", "sire", "dam", "hatch_date", "fighting_style"))\n'
'      + (pen_id,))\n'
'  flash("Chicken added.", "ok")\n'
'  return redirect(url_for("pen_detail", pen_id=pen_id))\n'
'\n\n')
marker = '@app.route("/breeding/bird/add", methods=["POST"])'
src = swap(src, marker, NEW_ROUTES + marker, "bird_add marker")

# 4) move / tag go back to the page you came from
src = swap(src,
  '  flash("Location updated.", "ok")\n  return redirect(url_for("breeding"))',
  '  flash("Location updated.", "ok")\n  return redirect(request.referrer or url_for("breeding"))',
  "bird_move")
src = swap(src,
  '  flash("Tags updated.", "ok")\n  return redirect(url_for("breeding"))',
  '  flash("Tags updated.", "ok")\n  return redirect(request.referrer or url_for("breeding"))',
  "bird_tag")

# ---- syntax check before writing anything ----
try:
  compile(src, "app.py", "exec")
except SyntaxError as e:
  print("ERROR: syntax sa bag-ong app.py: %s. Walay gibag-o." % e)
  sys.exit(1)

BREEDING_HTML = r'''{% extends "base.html" %}
{% block content %}
<div class="section-head"><h3>🐣 Pens</h3></div>
<details class="card"><summary class="btn-outline">+ Add Pen</summary>
  <form method="post" action="{{ url_for('pen_add') }}" class="form-grid">
    <label>Name (example: Cage 1, Breeding Pen 1)<input name="pen_name" required></label>
    <button type="submit">Save</button>
  </form>
</details>
{% for p in pens %}
<div class="card">
  <div class="row"><a href="{{ url_for('pen_detail', pen_id=p.id) }}"><strong>{{ p.pen_name }}</strong></a><span class="badge {{ 'off' if p.status != 'Active' }}">{{ p.status }}</span></div>
  <p class="muted">Birds here: {{ p.bird_count }}</p>
  <a class="btn-outline" href="{{ url_for('pen_detail', pen_id=p.id) }}">Open</a>
  <form method="post" action="{{ url_for('pen_toggle', pen_id=p.id) }}"><button class="btn-outline" type="submit">{{ 'Close' if p.status == 'Active' else 'Reopen' }}</button></form>
</div>
{% else %}<div class="card muted">No pens yet.</div>{% endfor %}
{% endblock %}
'''

DASHBOARD_HTML = r'''{% extends "base.html" %}
{% block content %}
<section class="card">
  <h2>{{ hdr_farm.farm_name }}</h2>
  <p class="muted">{{ hdr_farm.location or 'Location not set' }} • Owner: {{ hdr_farm.owner_name or 'Not set' }}</p>
  {% if not hdr_farm.owner_name or not hdr_farm.location %}<p style="margin-top:10px"><a class="btn" href="{{ url_for('farm_profile') }}">Complete Farm Profile</a></p>{% endif %}
</section>
<div class="grid3">
  <a class="stat" href="{{ url_for('breeding') }}"><b>{{ pens }}</b>Pens</a>
  <a class="stat" href="{{ url_for('conditioning') }}"><b>{{ keep }}</b>In Keep</a>
  <a class="stat red" href="{{ url_for('health') }}"><b>{{ sick }}</b>Sick Bay</a>
</div>
<div class="section-head"><h3>🐣 My Pens</h3><a class="btn-outline" href="{{ url_for('breeding') }}">+ Add Pen</a></div>
{% for p in pen_list %}
<a class="card" href="{{ url_for('pen_detail', pen_id=p.id) }}" style="display:block;text-decoration:none;color:inherit">
  <div class="row"><strong>{{ p.pen_name }}</strong><span class="badge">{{ p.bird_count }} birds</span></div>
</a>
{% else %}<div class="card muted">No pens yet. Tap + Add Pen.</div>{% endfor %}
<div class="section-head"><h3>📋 Today's To-Do List</h3><a class="btn-outline" href="{{ url_for('conditioning') }}">+ Keep Program</a></div>
<div class="card">
  {% for t in tasks %}
  <form method="post" action="{{ url_for('task_toggle', task_id=t.id) }}" class="todo">
    <input type="checkbox" onchange="this.form.submit()" {{ 'checked' if t.is_done }}>
    <div class="{{ 'done' if t.is_done }}"><strong>{{ t.task_title }}</strong>
      <small class="muted">{{ t.program_type }}{% if t.band_number or t.figba_tag or t.toe_punch %} · {{ t.band_number or t.figba_tag or t.toe_punch }}{% endif %}{% if t.due_date < today and not t.is_done %} · overdue ({{ t.due_date }}){% endif %}</small></div>
  </form>
  {% else %}
  <p class="muted" style="text-align:center;padding:10px 0">Walay task karong adlawa. Hapsay ang tanan!</p>
  {% endfor %}
</div>
{% endblock %}
'''

PEN_HTML = r'''{% extends "base.html" %}
{% block content %}
<div class="section-head"><h3>🐣 {{ pen.pen_name }}</h3><a class="btn-outline" href="{{ url_for('breeding') }}">← Pens</a></div>

<div class="card">
  <div class="row"><strong>Breeding Info</strong><span class="badge {{ 'off' if pen.status != 'Active' }}">{{ pen.status }}</span></div>
  <p class="muted">{{ pen.sire or '?' }} × {{ pen.dam or '?' }} · paired {{ pen.date_paired or '—' }}{% if pen.batch_mark %} · Mark: {{ pen.batch_mark }}{% endif %}</p>
  <p>Eggs: {{ pen.eggs_set or 0 }} · Hatched: {{ pen.hatched_count or 0 }}{% if pen.eggs_set %} ({{ (100 * (pen.hatched_count or 0) / pen.eggs_set)|round|int }}%){% endif %}</p>
  <details><summary class="btn-outline">+ Breeding Info</summary>
    <form method="post" action="{{ url_for('pen_breeding', pen_id=pen.id) }}" class="form-grid">
      <label>Sire (cock)<input name="sire" value="{{ pen.sire or '' }}"></label>
      <label>Dam (hen)<input name="dam" value="{{ pen.dam or '' }}"></label>
      <label>Date paired<input type="date" name="date_paired" value="{{ pen.date_paired or '' }}"></label>
      <label>Eggs set<input type="number" name="eggs_set" min="0" value="{{ pen.eggs_set or 0 }}"></label>
      <label>Hatched<input type="number" name="hatched_count" min="0" value="{{ pen.hatched_count or 0 }}"></label>
      <label>Batch mark (toe-punch)<input name="batch_mark" value="{{ pen.batch_mark or '' }}"></label>
      <button type="submit">Save</button>
    </form>
  </details>
</div>

<div class="section-head"><h3>🐓 Chickens ({{ birds|length }})</h3></div>
<details class="card"><summary class="btn-outline">+ Add Chicken</summary>
  <form method="post" action="{{ url_for('pen_chicken_add', pen_id=pen.id) }}" class="form-grid">
    <label>Toe-punch (batch mark)<input name="toe_punch"></label>
    <label>Wingband<input name="band_number"></label>
    <label>FIGBA tag<input name="figba_tag"></label>
    <label>Bloodline<input name="bloodline"></label>
    <label>Sex<select name="sex"><option value="">—</option><option>Cock/Stag</option><option>Hen/Pullet</option><option>Chick (unsexed)</option></select></label>
    <label>Sire<input name="sire"></label>
    <label>Dam<input name="dam"></label>
    <label>Hatch date<input type="date" name="hatch_date"></label>
    <label>Fighting style<input name="fighting_style"></label>
    <button type="submit">Save Chicken</button>
  </form>
</details>
{% for b in birds %}
<div class="card">
  <div class="row"><strong>{{ b|blabel }}</strong><span class="badge">{{ b.status }}</span></div>
  <p class="muted">{{ b.bloodline or 'No bloodline' }} · {{ b.sex or '—' }} · Toe-punch: {{ b.toe_punch or '—' }}</p>
  <details><summary class="btn-outline" style="margin-top:8px">Move to another pen</summary>
    <form method="post" action="{{ url_for('bird_move', bird_id=b.id) }}" class="inline">
      <select name="pen_id"><option value="">— Not assigned —</option>{% for op in other_pens %}<option value="{{ op.id }}">{{ op.pen_name }}</option>{% endfor %}</select>
      <button type="submit">Move</button>
    </form>
  </details>
  <details><summary class="btn-outline" style="margin-top:8px">Update wingband / FIGBA</summary>
    <form method="post" action="{{ url_for('bird_tag', bird_id=b.id) }}" class="inline">
      <input name="band_number" value="{{ b.band_number or '' }}" placeholder="Wingband">
      <input name="figba_tag" value="{{ b.figba_tag or '' }}" placeholder="FIGBA">
      <button type="submit">Save</button>
    </form>
  </details>
</div>
{% else %}<div class="card muted">No chickens in this pen yet.</div>{% endfor %}

<form method="post" action="{{ url_for('pen_toggle', pen_id=pen.id) }}"><button class="btn-outline" type="submit">{{ 'Close pen' if pen.status == 'Active' else 'Reopen pen' }}</button></form>
{% endblock %}
'''

open(APP, "w", encoding="utf-8").write(src)
T = os.path.join(ROOT, "templates")
open(os.path.join(T, "breeding.html"), "w", encoding="utf-8").write(BREEDING_HTML)
open(os.path.join(T, "dashboard.html"), "w", encoding="utf-8").write(DASHBOARD_HTML)
open(os.path.join(T, "pen.html"), "w", encoding="utf-8").write(PEN_HTML)
print("OK! Na-update ang app.py, breeding.html, dashboard.html ug na-himo ang pen.html.")
print("I-restart ang app: i-Ctrl+C ang Flask, dayon python app.py")
