# ---------- Add or Move Bird ----------
def ensure_bird_columns():
  try:
    conn = db()
    c = conn.cursor()
    cols = [r[1] for r in c.execute("PRAGMA table_info(birds)").fetchall()]
    for n in ("leg_band", "extra_tags", "color", "source", "seller", "notes", "photo_path"):
      if cols and n not in cols:
        c.execute("ALTER TABLE birds ADD COLUMN %s TEXT" % n)
    conn.commit()
    conn.close()
  except Exception as e:
    print("ensure_bird_columns:", e)


ensure_bird_columns()


@app.route("/bird/form")
def bird_form():
  ensure_bird_columns()
  pens_all = q("SELECT id, pen_name FROM breeding_pens ORDER BY id")
  return render_template("bird_form.html", pens=pens_all)


@app.route("/bird/add", methods=["GET", "POST"])
def bird_place():
  from flask import redirect as _redir, flash as _flash
  ensure_bird_columns()
  if request.method == "GET":
    return _redir("/?add=1")
  f = request.form
  g = lambda k: f.get(k, "").strip()
  mode = g("mode") or "single"
  band, leg, toe = g("band_number"), g("leg_band"), g("toe_punch")
  sex, hatch, color = g("sex"), g("hatch_date"), g("color")
  bloodline, sire, dam = g("bloodline"), g("sire"), g("dam")
  source = g("source")
  seller = g("seller") if source == "Bought" else ""
  notes = g("notes")
  st = g("status") or "Active"
  status = "Active (Breeding)" if st == "Active" else st
  types, vals = f.getlist("extra_type"), f.getlist("extra_val")
  extra = "; ".join("%s: %s" % (t, v.strip()) for t, v in zip(types, vals) if v.strip())
  pen_choice = g("pen_id")
  new_name = g("new_pen_name")
  if not pen_choice or (pen_choice == "new" and not new_name):
    _flash("Choose a pen.", "error")
    return _redir("/?add=1")
  count = 1
  if mode == "batch":
    count = to_int(f.get("count")) or 0
    if count < 1 or count > 200:
      _flash("Number of Birds must be 1 to 200.", "error")
      return _redir("/?add=1")
    if not hatch:
      _flash("Enter the Hatch Date.", "error")
      return _redir("/?add=1")
  elif not (band or leg or toe):
    _flash("Enter at least one tag.", "error")
    return _redir("/?add=1")
  if pen_choice == "new":
    run("INSERT INTO breeding_pens (pen_name) VALUES (?)", (new_name,))
    r = q("SELECT id FROM breeding_pens WHERE pen_name=? ORDER BY id DESC LIMIT 1", (new_name,), one=True)
    pen_id = r["id"] if r else None
  else:
    pen_id = valid_pen_id(pen_choice)
  if not pen_id:
    _flash("Choose a pen.", "error")
    return _redir("/?add=1")
  sql = ("INSERT INTO birds (band_number, leg_band, toe_punch, extra_tags, bloodline, sex, sire, dam, "
         "hatch_date, color, source, seller, notes, photo_path, status, pen_id) "
         "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
  if mode == "batch":
    for i in range(count):
      run(sql, ("", "", toe, "", bloodline, sex, sire, dam, hatch, color, source, seller, notes, "", status, pen_id))
    _flash("%d birds added." % count, "ok")
    return _redir("/pen/%d" % pen_id)
  found = None
  if band:
    found = q("SELECT * FROM birds WHERE band_number=?", (band,), one=True)
  elif toe:
    rows = q("SELECT * FROM birds WHERE toe_punch=?", (toe,))
    if len(rows) > 1:
      _flash("Several birds share this toe-punch. Use the wingband.", "error")
      return _redir("/?add=1")
    found = rows[0] if rows else None
  if found:
    run("UPDATE birds SET pen_id=? WHERE id=?", (pen_id, found["id"]))
    _flash("Bird moved to the pen.", "ok")
    return _redir("/pen/%d" % pen_id)
  photo = ""
  file = request.files.get("photo")
  if file and file.filename:
    import os, time
    from werkzeug.utils import secure_filename
    d = os.path.join(app.root_path, "static", "birds")
    os.makedirs(d, exist_ok=True)
    fn = "%d_%s" % (int(time.time()), secure_filename(file.filename))
    file.save(os.path.join(d, fn))
    photo = "birds/" + fn
  run(sql, (band, leg, toe, extra, bloodline, sex, sire, dam, hatch, color, source, seller, notes, photo, status, pen_id))
  _flash("Bird added.", "ok")
  return _redir("/pen/%d" % pen_id)
