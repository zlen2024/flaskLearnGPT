import os
import requests
#import markdown
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask_socketio import SocketIO, emit, join_room

# Configuration
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")  # change in production
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + DB_PATH
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# 🔹 Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# -------------------------------
# Models
# -------------------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    password_hash = db.Column(db.String(256), nullable=False)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class ChatSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), default="New Chat")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    messages = db.relationship("Message", backref="session", lazy=True, cascade="all, delete-orphan")

    @classmethod
    def get_sessions_by_user(cls, user_id):
        return cls.query.filter_by(user_id=user_id).all()

    @classmethod
    def add_session(cls, user_id, title="New Chat"):
        new_session = cls(user_id=user_id, title=title)
        db.session.add(new_session)
        db.session.commit()
        return new_session


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(10), nullable=False)  # "user" or "ai"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("chat_session.id"), nullable=False)

    @classmethod
    def get_messages_by_session(cls, session_id):
        return cls.query.filter_by(session_id=session_id).order_by(cls.created_at.asc()).all()

    @classmethod
    def add_message(cls, content, role, user_id, session_id):
        new_msg = cls(
            content=content,
            role=role,
            user_id=user_id,
            session_id=session_id,
        )
        db.session.add(new_msg)
        db.session.commit()
        return new_msg


with app.app_context():
    db.create_all()


import requests
import os
from flask import jsonify

def call_langflow_api(user_input: str, session_id: str ):
    """
    Call Langflow API and return the response in jsonify format.
    """
    # API key from environment
    api_key = "sk-YtA3hrFUMLj0xPB1oUYFv5AE_BcfTRWzQzZO3fbMSEg"
    if not api_key:
        print("LANGFLOW_API_KEY not set")
        return jsonify({"status": "error", "message": "LANGFLOW_API_KEY not set"}), 500

    # API endpoint
    url = "http://localhost:7860/api/v1/run/1cee7155-05ef-4255-907d-76e3ef0a3717"

    # Payload
    payload = {
     "output_type": "chat",
     "input_type": "chat",
     "tweaks": {
        "ChatInput-AGAod": {
      "files": "",
      "input_value": user_input
    },
    "TextInput-9ec2D": {
      "input_value": str(session_id)
    }
     }
    }
    print("Payload:", payload)

    # Headers
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        ai_reply = (
            data.get("outputs", [{}])[0]
                .get("outputs", [{}])[0]
                .get("results", {})
                .get("message", {})
                .get("data", {})
                .get("text", "")
        )

        print("AI Reply:", ai_reply)
        return ai_reply
    except requests.exceptions.RequestException as e:
        print("Error calling Langflow API:", e)
        return "error"

# -------------------------------
# Flask-Login loader
# -------------------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -------------------------------
# Routes
# -------------------------------
@app.route("/home1")
def index():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required.", "warning")
            return render_template("register.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "warning")
            return render_template("register.html")

        existing = User.query.filter_by(username=username).first()
        if existing:
            flash("Username already taken.", "warning")
            return render_template("register.html")

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/db_url")
@login_required   # only logged-in users can see it (optional but safer)
def get_db_url():
    """
    Show the database connection URL (without password for safety).
    """
    db_url = app.config["SQLALCHEMY_DATABASE_URI"]

    # Hide sensitive parts (like password if using Postgres/MySQL in future)
    if "@" in db_url and ":" in db_url:
        # Example: postgresql://user:pass@host:port/dbname
        parts = db_url.split("@")
        safe_url = parts[0].split(":")[0] + ":***@" + parts[1]
    else:
        safe_url = db_url

    return jsonify({
        "status": "success",
        "database_url": safe_url
    })

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash("Logged in successfully.", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))
        else:
            flash("Invalid username or password.", "danger")
            return render_template("login.html")

    return render_template("login.html")

@app.route("/dashboard")
@login_required
def dashboard():
    sessions = ChatSession.get_sessions_by_user(current_user.id)
    return render_template("dashboard.html", username=current_user.username, sessions=sessions)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

@app.route("/new_session", methods=["POST"])
@login_required
def new_session():
    titled = datetime.now().strftime("Session %b %d, %Y · %I:%M %p")
    # Create a new chat session for the logged-in user
    new_sess = ChatSession.add_session(user_id=current_user.id, title=titled)

    # Return session info as JSON
    return jsonify({
        "status": "success",
        "id": new_sess.id,
        "title": new_sess.title,
        "created_at": new_sess.created_at.isoformat()
    })
# -------------------------------
# SocketIO Events
# -------------------------------
@socketio.on("join_session")
def handle_join_session(data):
    session_id = data["session_id"]
    join_room(session_id)
    messages = Message.get_messages_by_session(session_id)
    emit("load_messages", [{"content": m.content, "role": m.role} for m in messages])



@socketio.on("send_message")
def handle_send_message(data):
    session_id = data["session_id"]
    content = data["content"]
    role = data.get("role", "user")

    # 1. Save + emit USER message immediately
    new_msg = Message.add_message(
        content=content,
        role=role,
        user_id=current_user.id,
        session_id=session_id
    )
    emit("receive_message", {"content": new_msg.content, "role": new_msg.role}, room=session_id)
    socketio.start_background_task(target=process_ai, content=content, session_id=session_id)

    # 2. Process AI in a separate thread
def process_ai(content, session_id):
        with app.app_context():
            response = call_langflow_api(content, session_id)
            ai_msg = Message.add_message(
                content=response,
                role="ai",
                user_id=999,
                session_id=session_id
            )
            socketio.emit("receive_message", {"content": response, "role": "ai"}, room=session_id)

   

#@app.template_filter('markdown')
#def markdown_filter(s):
 #   return markdown.markdown(s)

# -------------------------------
# Run
# -------------------------------
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
