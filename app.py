import os
from flask import Flask, render_template, request, redirect, url_for, flash,jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# Configuration
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")  # change in production
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + DB_PATH
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"  # redirect to login if @login_required

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    password_hash = db.Column(db.String(256), nullable=False)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)
# Chat session
class ChatSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), default="New Chat")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    messages = db.relationship("Message", backref="session", lazy=True, cascade="all, delete-orphan")

     # Fetch all sessions for a user
    @classmethod
    def get_sessions_by_user(cls, user_id):
        return cls.query.filter_by(user_id=user_id).all()

    # Add new session
    @classmethod
    def add_session(cls, user_id, title="New Chat"):
        new_session = cls(user_id=user_id, title=title)
        db.session.add(new_session)
        db.session.commit()
        return new_session

# Messages
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(10), nullable=False)  # "user" or "ai"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("chat_session.id"), nullable=False)

    # 1. Get messages by session_id
    @classmethod
    def get_messages_by_session(cls, session_id):
        return cls.query.filter_by(session_id=session_id).order_by(cls.created_at.asc()).all()

    # 2. Add a new message
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

# create DB if not exists
with app.app_context():
    db.create_all()

# Helpers
'''
def create_session(user, title="New Chat"):
    session = ChatSession(user_id=user.id, title=title)
    db.session.add(session)
    db.session.commit()
    return session
add_session(cls, user_id, title="New Chat"):
def send_message(user, session, content, role="user"):
    message = Message(
        content=content,
        role=role,
        user_id=user.id,
        session_id=session.id
    )
    db.session.add(message)
    db.session.commit()
    return message

def get_user_sessions(user):
    return ChatSession.query.filter_by(user_id=user.id).order_by(ChatSession.created_at.desc()).all()

def get_session_messages(session):
    return Message.query.filter_by(session_id=session.id).order_by(Message.created_at.asc()).all()

'''
# Views


# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
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
    session=ChatSession.get_sessions_by_user(current_user.id)
    return render_template("dashboard.html", username=current_user.username, sessions=session)

@app.route("/new_session", methods=["POST"])
@login_required
def new_session():
    # Create a new chat session for the logged-in user
    new_sess = ChatSession.add_session(user_id=current_user.id, title="New Chat")
    
    # Return session info as JSON
    return jsonify({
        "status": "success",
        "session_id": new_sess.id,
        "title": new_sess.title
    })
@app.route("/load_messages/<int:session_id>")
@login_required
def load_messages(session_id):
    messages = Message.get_messages_by_session(session_id)
    
    # Convert messages to list of dicts
    messages_list = []
    for m in messages:
        messages_list.append({
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.strftime("%Y-%m-%d %H:%M")
        })
    
    return jsonify(messages_list)

@app.route("/send_message", methods=["POST"])
@login_required
def send_message():
    data = request.get_json()
    content = data.get("content")
    session_id = data.get("session_id")

    if not content or not session_id:
        return jsonify({"status": "error", "message": "Missing data"}), 400

    # Add new message as "user"
    new_msg = Message.add_message(
        content=content,
        role="user",
        user_id=current_user.id,
        session_id=session_id
    )

    # Return the new message to update chat window
    return jsonify({
        "status": "success",
        "message": {
            "role": new_msg.role,
            "content": new_msg.content,
            "created_at": new_msg.created_at.strftime("%Y-%m-%d %H:%M")
        }
    })

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)