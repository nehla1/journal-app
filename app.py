import sqlite3
from flask import Flask, render_template, request, redirect, session, url_for, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import date

DB = "journal.db"
SECRET_KEY = "replace-this-with-a-secret-before-deploying"

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY

# ------------------- DB helpers -------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    c = db.cursor()

    # users table
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT
    )""")

    # shared journals (collaboration spaces)
    c.execute("""
    CREATE TABLE IF NOT EXISTS journals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        owner_id INTEGER NOT NULL,
        FOREIGN KEY(owner_id) REFERENCES users(id)
    )""")

    # memberships (which users belong to which journals)
    c.execute("""
    CREATE TABLE IF NOT EXISTS journal_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        journal_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        FOREIGN KEY(journal_id) REFERENCES journals(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")

    # entries: either personal (journal_id NULL) or in a shared journal
    c.execute("""
    CREATE TABLE IF NOT EXISTS entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER NOT NULL,
        journal_id INTEGER,
        entry_date TEXT NOT NULL,
        content TEXT NOT NULL,
        is_public INTEGER DEFAULT 0,
        FOREIGN KEY(owner_id) REFERENCES users(id),
        FOREIGN KEY(journal_id) REFERENCES journals(id)
    )""")

    db.commit()

# Initialize DB on startup
with app.app_context():
    init_db()

# ------------------- Auth helpers -------------------
def current_user():
    """
    Return current user row or None. Cache in g to avoid repeated DB hits.
    """
    if getattr(g, "current_user", None) is not None:
        return g.current_user

    user_id = session.get("user_id")
    if not user_id:
        g.current_user = None
        return None

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    g.current_user = user  # maybe None
    return user

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        # make user available in g.user for route handlers/templates
        g.user = user
        return f(*args, **kwargs)
    return wrapper

# ------------------- Routes -------------------
@app.route("/")
def home():
    if current_user():
        return redirect(url_for("dashboard"))
    return render_template("login.html")

# ---------- Signup / Login / Logout ----------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        name = request.form.get("name", "")

        if not email or not password:
            flash("Email and password are required.", "danger")
            return redirect(url_for("signup"))

        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            flash("Email already registered. Please log in.", "warning")
            return redirect(url_for("login"))

        hash_pw = generate_password_hash(password)
        db.execute("INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)",
                   (email, hash_pw, name))
        db.commit()
        flash("Account created. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["email"] = user["email"]
            flash("Logged in successfully.", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid credentials.", "danger")
        return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("login"))

# ---------- Dashboard ----------
@app.route("/dashboard")
@login_required
def dashboard():
    # decorator has already loaded user into g.user
    user = g.get("user") or current_user()
    db = get_db()

    # personal entries (journal_id IS NULL) belonging to current user
    personal = db.execute(
        "SELECT * FROM entries WHERE owner_id = ? AND journal_id IS NULL ORDER BY id DESC",
        (user["id"],)
    ).fetchall()

    # journals the user owns or is a member of
    owned = db.execute("SELECT * FROM journals WHERE owner_id = ?", (user["id"],)).fetchall()
    member = db.execute("""
        SELECT j.* FROM journals j
        JOIN journal_members m ON m.journal_id = j.id
        WHERE m.user_id = ?
    """, (user["id"],)).fetchall()

    # combine and remove duplicates (if owner is also member)
    journals = {j["id"]: j for j in owned}
    for j in member:
        journals[j["id"]] = j
    journals = list(journals.values())

    return render_template("dashboard.html", user=user, personal=personal, journals=journals)

# ---------- Create personal entry or entry in a journal ----------
@app.route("/entry/new", methods=["GET", "POST"])
@login_required
def new_entry():
    db = get_db()
    user = g.get("user") or current_user()

    if request.method == "POST":
        content = request.form.get("content", "").strip()
        journal_id = request.form.get("journal_id")
        is_public = 1 if request.form.get("is_public") == "on" else 0

        if not content:
            flash("Entry content cannot be empty.", "danger")
            return redirect(url_for("new_entry"))

        if journal_id in (None, "", "none"):
            journal_id_val = None
        else:
            try:
                journal_id_val = int(journal_id)
            except ValueError:
                journal_id_val = None

        today = date.today().isoformat()
        db.execute("""
            INSERT INTO entries (owner_id, journal_id, entry_date, content, is_public)
            VALUES (?, ?, ?, ?, ?)
        """, (user["id"], journal_id_val, today, content, is_public))
        db.commit()
        flash("Entry added.", "success")
        return redirect(url_for("dashboard"))

    # GET -> show form with list of journals user can post into
    journals = db.execute("""
        SELECT j.* FROM journals j
        WHERE j.owner_id = ? OR j.id IN (SELECT journal_id FROM journal_members WHERE user_id = ?)
    """, (user["id"], user["id"])).fetchall()

    return render_template("new_entry.html", journals=journals)

# ---------- Create a new shared journal ----------
@app.route("/journal/create", methods=["GET", "POST"])
@login_required
def create_journal():
    db = get_db()
    user = g.get("user") or current_user()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Journal name required.", "danger")
            return redirect(url_for("create_journal"))
        cur = db.execute("INSERT INTO journals (name, owner_id) VALUES (?, ?)", (name, user["id"]))
        db.commit()
        journal_id = cur.lastrowid

        # owner is automatically a member
        db.execute("INSERT INTO journal_members (journal_id, user_id) VALUES (?, ?)", (journal_id, user["id"]))
        db.commit()
        flash(f"Journal '{name}' created. Share ID {journal_id} to invite friends.", "success")
        return redirect(url_for("dashboard"))
    return render_template("create_journal.html")

# ---------- Join an existing journal by ID ----------
@app.route("/journal/join", methods=["GET", "POST"])
@login_required
def join_journal():
    db = get_db()
    user = g.get("user") or current_user()
    if request.method == "POST":
        try:
            journal_id = int(request.form.get("journal_id", ""))
        except ValueError:
            flash("Invalid journal ID.", "danger")
            return redirect(url_for("join_journal"))

        j = db.execute("SELECT * FROM journals WHERE id = ?", (journal_id,)).fetchone()
        if not j:
            flash("Journal not found.", "danger")
            return redirect(url_for("join_journal"))

        existing = db.execute("SELECT * FROM journal_members WHERE journal_id = ? AND user_id = ?",
                              (journal_id, user["id"])).fetchone()
        if existing:
            flash("You are already a member of that journal.", "info")
            return redirect(url_for("dashboard"))

        db.execute("INSERT INTO journal_members (journal_id, user_id) VALUES (?, ?)", (journal_id, user["id"]))
        db.commit()
        flash(f"Joined journal '{j['name']}'!", "success")
        return redirect(url_for("dashboard"))
    return render_template("join_journal.html")

# ---------- View entries for a journal or personal entries (list page) ----------
# ---------- View entries for a journal or personal entries (list page) ----------
@app.route("/entries")
@login_required
def entries_page():
    db = get_db()
    user = current_user()  # get full user row

    # fetch entries the user can access
    rows = db.execute("""
        SELECT e.*, u.email as owner_email, j.name as journal_name
        FROM entries e
        JOIN users u ON u.id = e.owner_id
        LEFT JOIN journals j ON j.id = e.journal_id
        WHERE
            (e.owner_id = ?)
            OR (e.journal_id IN (SELECT journal_id FROM journal_members WHERE user_id = ?))
            OR (e.is_public = 1)
        ORDER BY e.entry_date DESC, e.id DESC
    """, (user["id"], user["id"])).fetchall()

    # DEBUG: print to console so you can see what Flask got
    print("DEBUG entries:", rows)

    return render_template("entries.html", entries=rows)
# ---------- View a single entry ----------
@app.route("/entry/<int:entry_id>")
@login_required
def entry_detail(entry_id):
    db = get_db()
    user = current_user()

    entry = db.execute("""
        SELECT e.*, u.email as owner_email, j.name as journal_name
        FROM entries e
        JOIN users u ON u.id = e.owner_id
        LEFT JOIN journals j ON j.id = e.journal_id
        WHERE e.id = ?
    """, (entry_id,)).fetchone()

    if not entry:
        flash("Entry not found.", "danger")
        return redirect(url_for("entries_page"))

    # Optional: restrict access if entry is private and user is not owner or journal member
    if entry["is_public"] == 0 and entry["owner_id"] != user["id"]:
        members = db.execute("SELECT user_id FROM journal_members WHERE journal_id = ?", (entry["journal_id"],)).fetchall()
        member_ids = [m["user_id"] for m in members]
        if entry["journal_id"] and user["id"] not in member_ids:
            flash("You cannot view this entry.", "danger")
            return redirect(url_for("entries_page"))

    return render_template("entry_detail.html", entry=entry)



# ---------- Calendar page showing accessible entries (with JS calendar UI) ----------
@app.route("/calendar")
@login_required
def calendar_page():
    db = get_db()
    user = g.get("user") or current_user()

    # fetch entries user can see
    rows = db.execute("""
    SELECT e.id, e.entry_date, e.content, e.owner_id, u.email as owner_email, e.journal_id
    FROM entries e
    JOIN users u ON u.id = e.owner_id
    WHERE (e.owner_id = ?)
       OR (e.journal_id IN (SELECT journal_id FROM journal_members WHERE user_id = ?))
       OR (e.is_public = 1)
    ORDER BY e.entry_date DESC
    """, (user["id"], user["id"])).fetchall()

    # we'll pass entries to template and JS will render calendar
    return render_template("calendar.html", entries=rows)

# ------------------- Run -------------------
if __name__ == "__main__":
    app.run(debug=True)
