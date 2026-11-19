
import os
import re
import secrets
from datetime import datetime, timezone
from getpass import getpass

from dotenv import load_dotenv
from flask import (
    Flask, render_template, redirect, url_for,
    request, flash, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user,
    logout_user, login_required, current_user
)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(
    __name__,
    static_folder=os.path.join(BASE_DIR, "static"),
    static_url_path="/static"
)

# SECURITY CONFIGURATION

app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY")

if not app.config["SECRET_KEY"]:
    raise RuntimeError("FLASK_SECRET_KEY is missing from .env")

database_url = os.environ.get("DATABASE_URL", "").strip()

if not database_url:
    raise RuntimeError("DATABASE_URL is missing from .env")

if database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://", "postgresql+psycopg://", 1
    )
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace(
        "postgresql://", "postgresql+psycopg://", 1
    )

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("SESSION_COOKIE_SECURE", "False").lower() == "true"
)

app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SECURE"] = app.config["SESSION_COOKIE_SECURE"]
app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"

db = SQLAlchemy(app)
csrf = CSRFProtect(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "admin_login"
login_manager.login_message = "Please log in to access the admin panel."
login_manager.login_message_category = "warning"


# DATABASE MODELS

class AdminUser(UserMixin, db.Model):

    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(
        db.String(80), unique=True, nullable=False, index=True
    )

    password_hash = db.Column(db.String(255), nullable=False)

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Article(db.Model):

    __tablename__ = "articles"

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(200), nullable=False)

    slug = db.Column(
        db.String(220), unique=True, nullable=False, index=True
    )

    category = db.Column(db.String(100), nullable=False)

    excerpt = db.Column(db.Text)

    content = db.Column(db.Text, nullable=False)

    status = db.Column(
        db.String(20), default="draft", nullable=False
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(AdminUser, int(user_id))


# PUBLIC WEBSITE ROUTES

PAGES = {
    "index",
    "experience",
    "academic",
    "articles",
    "literature",
    "sports"
}


def find_page(name):
    search_dirs = [
        BASE_DIR,
        os.path.join(BASE_DIR, "templates"),
        os.path.join(BASE_DIR, "pages"),
        os.path.join(BASE_DIR, "static"),
        os.path.join(BASE_DIR, "public"),
    ]

    for directory in search_dirs:
        path = os.path.join(directory, f"{name}.html")

        if os.path.isfile(path):
            return directory

    return None


def serve_page(name):
    directory = find_page(name)

    if not directory:
        abort(404)

    from flask import send_from_directory

    return send_from_directory(directory, f"{name}.html")


@app.route("/")
def home():
    return serve_page("index")


@app.route("/articles")
def public_articles():
    published_articles = Article.query.filter_by(
        status="published"
    ).order_by(
        Article.created_at.desc()
    ).all()

    return render_template(
        "articles.html",
        articles=published_articles
    )


@app.route("/articles/<slug>")
def article_detail(slug):
    article = Article.query.filter_by(
        slug=slug,
        status="published"
    ).first_or_404()

    return render_template(
        "article_detail.html",
        article=article
    )


@app.route("/<page>")
def clean_url(page):
    page = page[:-5] if page.endswith(".html") else page

    if page in PAGES:
        if page == "articles":
            return public_articles()

        return serve_page(page)

    abort(404)


@app.route("/health")
def health():
    return {"status": "ok"}


# ADMIN AUTHENTICATION

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if current_user.is_authenticated:
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        admin = AdminUser.query.filter_by(
            username=username
        ).first()

        if admin and admin.check_password(password):

            login_user(admin, remember=False)

            flash("Welcome back to PRIYO CMS.", "success")

            next_page = request.args.get("next")

            if next_page and next_page.startswith("/admin"):
                return redirect(next_page)

            return redirect(url_for("admin_dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("admin/login.html")


@app.route("/admin/logout", methods=["POST"])
@login_required
def admin_logout():

    logout_user()

    flash("You have been logged out.", "success")

    return redirect(url_for("admin_login"))


# ADMIN DASHBOARD

@app.route("/admin")
@login_required
def admin_dashboard():

    total_articles = Article.query.count()

    published_articles = Article.query.filter_by(
        status="published"
    ).count()

    draft_articles = Article.query.filter_by(
        status="draft"
    ).count()

    total_admins = AdminUser.query.count()

    recent_articles = Article.query.order_by(
        Article.created_at.desc()
    ).limit(6).all()

    return render_template(
        "admin/dashboard.html",
        total_articles=total_articles,
        published_articles=published_articles,
        draft_articles=draft_articles,
        total_admins=total_admins,
        recent_articles=recent_articles
    )


# ARTICLE MANAGEMENT

@app.route("/admin/articles")
@login_required
def admin_articles():

    articles = Article.query.order_by(
        Article.created_at.desc()
    ).all()

    return render_template(
        "admin/articles.html",
        articles=articles
    )


def make_slug(title):

    slug = title.lower().strip()

    slug = re.sub(r"[^a-z0-9]+", "-", slug)

    slug = slug.strip("-")

    if not slug:
        slug = secrets.token_hex(5)

    return slug


@app.route("/admin/articles/new", methods=["GET", "POST"])
@login_required
def new_article():

    if request.method == "POST":

        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip()
        excerpt = request.form.get("excerpt", "").strip()
        content = request.form.get("content", "").strip()
        status = request.form.get("status", "draft")

        if not title or not category or not content:
            flash("Please complete all required fields.", "danger")
            return render_template("admin/article_form.html", article=None)

        if status not in ("draft", "published"):
            abort(400)

        slug = make_slug(title)
        original_slug = slug
        counter = 1

        while Article.query.filter_by(slug=slug).first():
            slug = f"{original_slug}-{counter}"
            counter += 1

        article = Article(
            title=title,
            slug=slug,
            category=category,
            excerpt=excerpt,
            content=content,
            status=status
        )

        db.session.add(article)
        db.session.commit()

        flash("Article created successfully.", "success")

        return redirect(url_for("admin_articles"))

    return render_template("admin/article_form.html", article=None)


@app.route("/admin/articles/edit/<int:article_id>", methods=["GET", "POST"])
@login_required
def edit_article(article_id):

    article = db.get_or_404(Article, article_id)

    if request.method == "POST":

        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip()
        excerpt = request.form.get("excerpt", "").strip()
        content = request.form.get("content", "").strip()
        status = request.form.get("status", "draft")

        if not title or not category or not content:
            flash("Please complete all required fields.", "danger")
            return render_template(
                "admin/article_form.html",
                article=article
            )

        if status not in ("draft", "published"):
            abort(400)

        article.title = title
        article.category = category
        article.excerpt = excerpt
        article.content = content
        article.status = status

        db.session.commit()

        flash("Article updated successfully.", "success")

        return redirect(url_for("admin_articles"))

    return render_template(
        "admin/article_form.html",
        article=article
    )


@app.route("/admin/articles/delete/<int:article_id>", methods=["POST"])
@login_required
def delete_article(article_id):

    article = db.get_or_404(Article, article_id)

    db.session.delete(article)
    db.session.commit()

    flash("Article deleted successfully.", "success")

    return redirect(url_for("admin_articles"))


# DATABASE COMMANDS

@app.cli.command("init-db")
def init_db():

    db.create_all()

    print("PRIYO database tables created successfully.")


@app.cli.command("create-admin")
def create_admin():

    db.create_all()

    username = input("Choose admin username: ").strip()

    if not username:
        print("Username cannot be empty.")
        return

    if AdminUser.query.filter_by(username=username).first():
        print("This username already exists.")
        return

    password = getpass("Choose admin password (minimum 12 characters): ")
    confirm = getpass("Confirm password: ")

    if len(password) < 12:
        print("Password must contain at least 12 characters.")
        return

    if password != confirm:
        print("Passwords do not match.")
        return

    admin = AdminUser(username=username)
    admin.set_password(password)

    db.session.add(admin)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        print("Could not create administrator.")
        return

    print("PRIYO administrator created successfully.")


@app.after_request
def security_headers(response):

    if response.mimetype == "text/html":
        response.headers["Cache-Control"] = "no-cache"

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    return response


@app.errorhandler(404)
def not_found(error):

    return (
        "<!DOCTYPE html><html><head><title>404</title></head>"
        "<body style='background:#04060D;color:#F2ECDD;"
        "font-family:Georgia;text-align:center;padding:100px'>"
        "<h1>404</h1><p>Page not found.</p>"
        "<a href='/' style='color:#CDAE6B'>Back home</a>"
        "</body></html>",
        404
    )


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    )
