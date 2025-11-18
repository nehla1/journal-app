from flask import Flask, render_template, request, redirect
import sqlite3
from datetime import date

app = Flask(__name__)

# create database if not exists
def init_db():
    conn = sqlite3.connect("journal.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS entries (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 entry_date TEXT,
                 content TEXT
                 )""")
    conn.commit()
    conn.close()

init_db()

@app.route("/")
def home():
    conn = sqlite3.connect("journal.db")
    c = conn.cursor()
    c.execute("SELECT * FROM entries ORDER BY id DESC")
    entries = c.fetchall()
    conn.close()
    return render_template("index.html", entries=entries)

@app.route("/new", methods=["POST"])
def new_entry():
    content = request.form["content"]
    today = date.today().isoformat()
    conn = sqlite3.connect("journal.db")
    c = conn.cursor()
    c.execute("INSERT INTO entries (entry_date, content) VALUES (?, ?)",
              (today, content))
    conn.commit()
    conn.close()
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True)
