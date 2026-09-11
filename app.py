import os
from datetime import date
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, MongoClient
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY"),
    MONGO_URI=os.environ.get("MONGO_URI"),
    MONGO_DB_NAME=os.environ.get("MONGO_DB_NAME", "learner_vault"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",
)

if not app.config["SECRET_KEY"] or not app.config["MONGO_URI"]:
    raise RuntimeError("SECRET_KEY and MONGO_URI environment variables are required")


mongo_client = MongoClient(app.config["MONGO_URI"], serverSelectionTimeoutMS=5000)
database = mongo_client[app.config["MONGO_DB_NAME"]]
users_collection = database["users"]
users_collection.create_index([("email", ASCENDING)], unique=True)
bookings_collection = database["bookings"]
bookings_collection.create_index([("user_id", ASCENDING), ("session_date", ASCENDING)])

SESSION_TYPES = ("Spinning", "Swimming", "Weight room")

csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please sign in to view your account."


class User(UserMixin):
    def __init__(self, document):
        self.id = str(document["_id"])
        self.email = document["email"]
        self.password_hash = document["password_hash"]
        self._profile = document.get("profile")

    @property
    def profile(self):
        return self._profile


@login_manager.user_loader
def load_user(user_id):
    try:
        document = users_collection.find_one({"_id": ObjectId(user_id)})
    except InvalidId:
        return None
    return User(document) if document else None


def normalize_email(email):
    return email.strip().lower()


def account_profile_required(view):
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        return view(*args, **kwargs)

    return wrapped_view


@app.get("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = normalize_email(request.form.get("email", ""))
        password = request.form.get("password", "")
        if not email or "@" not in email or len(password) < 12:
            flash("Use a valid email and a password of at least 12 characters.", "error")
            return render_template("register.html")
        if users_collection.find_one({"email": email}, {"_id": 1}):
            flash("An account with that email already exists.", "error")
            return render_template("register.html")

        document = {
            "email": email,
            "password_hash": generate_password_hash(password),
            "profile": None,
        }
        result = users_collection.insert_one(document)
        user = User({**document, "_id": result.inserted_id})
        login_user(user)
        return redirect(url_for("profile"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = normalize_email(request.form.get("email", ""))
        document = users_collection.find_one({"email": email})
        user = User(document) if document else None
        if not user or not check_password_hash(user.password_hash, request.form.get("password", "")):
            flash("Invalid email or password.", "error")
            return render_template("login.html")
        login_user(user)
        return redirect(url_for("profile"))

    return render_template("login.html")


@app.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    user_id = ObjectId(current_user.id)
    if request.method == "POST":
        session_type = request.form.get("session_type", "").strip()
        session_date = request.form.get("session_date", "").strip()
        if session_type not in SESSION_TYPES:
            flash("Choose a valid gym session.", "error")
            return redirect(url_for("dashboard"))
        try:
            parsed_date = date.fromisoformat(session_date)
        except ValueError:
            flash("Choose a valid session date.", "error")
            return redirect(url_for("dashboard"))
        if parsed_date < date.today():
            flash("Choose today or a future date.", "error")
            return redirect(url_for("dashboard"))

        bookings_collection.insert_one({
            "user_id": user_id,
            "session_type": session_type,
            "session_date": parsed_date.isoformat(),
        })
        flash("Your gym session was booked.", "success")
        return redirect(url_for("dashboard"))

    bookings = list(bookings_collection.find({"user_id": user_id}).sort("session_date", ASCENDING))
    return render_template(
        "dashboard.html",
        bookings=bookings,
        session_types=SESSION_TYPES,
        today=date.today().isoformat(),
    )


@app.post("/dashboard/bookings/<booking_id>/delete")
@login_required
def delete_booking(booking_id):
    try:
        booking_object_id = ObjectId(booking_id)
    except InvalidId:
        flash("That booking could not be found.", "error")
        return redirect(url_for("dashboard"))

    result = bookings_collection.delete_one({
        "_id": booking_object_id,
        "user_id": ObjectId(current_user.id),
    })
    if result.deleted_count:
        flash("Your gym session was cancelled.", "success")
    else:
        flash("That booking could not be found.", "error")
    return redirect(url_for("dashboard"))


@app.route("/profile", methods=["GET", "POST"])
@account_profile_required
def profile():
    profile_record = current_user.profile
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        if not full_name:
            flash("Full name is required.", "error")
            return render_template("profile.html", profile=profile_record)

        date_value = request.form.get("date_of_birth", "").strip()
        try:
            parsed_date = date.fromisoformat(date_value) if date_value else None
        except ValueError:
            flash("Enter a valid date of birth.", "error")
            return render_template("profile.html", profile=profile_record)

        profile_record = {
            "full_name": full_name,
            "date_of_birth": parsed_date.isoformat() if parsed_date else None,
            "institution": request.form.get("institution", "").strip() or None,
            "qualification": request.form.get("qualification", "").strip() or None,
        }
        graduation_year = request.form.get("graduation_year", "").strip()
        profile_record["graduation_year"] = int(graduation_year) if graduation_year.isdigit() else None
        users_collection.update_one(
            {"_id": ObjectId(current_user.id)},
            {"$set": {"profile": profile_record}},
        )
        flash("Your details were saved.", "success")

    return render_template("profile.html", profile=profile_record)


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_ENV") != "production")
