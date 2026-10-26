import os
import sqlite3
from functools import wraps
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("CHAT_DATA_DIR", APP_DIR / "data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("CHAT_DB_PATH", DATA_DIR / "database.db"))

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY and os.environ.get("APP_ENV") == "production":
    raise RuntimeError("Set a strong random SECRET_KEY environment variable before production deployment.")
SECRET_KEY = SECRET_KEY or "local-development-only-change-this"

app = Flask(__name__)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    MAX_CONTENT_LENGTH=16 * 1024,  # Requests should be tiny; messages are limited to 25 chars.
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "1" if os.environ.get("APP_ENV") == "production" else "0") == "1",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 14,
)
# Trust one reverse proxy (e.g. Nginx) for HTTPS scheme and client address.
if os.environ.get("TRUST_PROXY") == "1":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

csrf = CSRFProtect(app)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
)

MAX_MESSAGE_LENGTH = 25
MAX_MESSAGES = 20


def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                body TEXT NOT NULL CHECK(length(body) <= 25),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Content-Security-Policy",
        "default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; script-src 'self'; connect-src 'self'; "
        "img-src 'self' data:; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
    if request.is_secure or app.config["SESSION_COOKIE_SECURE"]:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "로그인이 필요해."}), 401
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped


@app.route("/")
def home():
    return redirect(url_for("chat" if "user_id" in session else "login"))


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not 3 <= len(username) <= 20 or not username.isprintable():
            flash("아이디는 사용할 수 있는 문자로 3~20자 입력해 줘.")
            return render_template("register.html")
        if len(password) < 8 or len(password) > 128:
            flash("비밀번호는 8~128자로 입력해 줘.")
            return render_template("register.html")
        try:
            with db() as conn:
                cur = conn.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, generate_password_hash(password))
                )
                session.clear()
                session.permanent = True
                session["user_id"] = cur.lastrowid
                session["username"] = username
            return redirect(url_for("chat"))
        except sqlite3.IntegrityError:
            flash("이미 사용 중인 아이디야.")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per minute", methods=["POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with db() as conn:
            user = conn.execute(
                "SELECT id, username, password_hash FROM users WHERE username = ? COLLATE NOCASE",
                (username,)
            ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("chat"))
        flash("아이디 또는 비밀번호가 올바르지 않아.")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/chat")
@login_required
def chat():
    return render_template("chat.html", username=session["username"])


@app.route("/api/messages", methods=["GET"])
@login_required
@limiter.limit("120 per minute")
def get_messages():
    with db() as conn:
        rows = conn.execute(
            "SELECT id, username, body, created_at FROM messages ORDER BY id DESC LIMIT ?",
            (MAX_MESSAGES,)
        ).fetchall()
    return jsonify([dict(row) for row in reversed(rows)])


@app.route("/api/messages", methods=["POST"])
@login_required
@limiter.limit("30 per minute")
def send_message():
    data = request.get_json(silent=True) or {}
    body = data.get("body", "")
    if not isinstance(body, str):
        return jsonify({"error": "메시지 형식이 올바르지 않아."}), 400
    body = body.strip()
    if not body:
        return jsonify({"error": "빈 메시지는 보낼 수 없어."}), 400
    if len(body) > MAX_MESSAGE_LENGTH:
        return jsonify({"error": "메시지는 최대 25자까지 보낼 수 있어."}), 400

    with db() as conn:
        conn.execute(
            "INSERT INTO messages (user_id, username, body) VALUES (?, ?, ?)",
            (session["user_id"], session["username"], body)
        )
        conn.execute("""
            DELETE FROM messages
            WHERE id NOT IN (
                SELECT id FROM messages ORDER BY id DESC LIMIT ?
            )
        """, (MAX_MESSAGES,))
    return jsonify({"ok": True})


@app.errorhandler(400)
def bad_request(error):
    # Preserve Flask-WTF CSRF error information without exposing internals.
    if "CSRF" in str(error).upper() or "csrf" in request.path.lower():
        return "요청이 만료됐어. 페이지를 새로고침한 뒤 다시 시도해 줘.", 400
    return "잘못된 요청이야.", 400


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "요청이 너무 커."}), 413


@app.errorhandler(429)
def rate_limited(_error):
    if request.path.startswith("/api/"):
        return jsonify({"error": "요청이 너무 많아. 잠시 후 다시 시도해 줘."}), 429
    return "요청이 너무 많아. 잠시 후 다시 시도해 줘.", 429


init_db()
