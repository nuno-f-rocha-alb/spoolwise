"""Auth: login manager, password hashing, trusted-header SSO, login/logout routes.

Two modes, switched by the TRUST_PROXY_AUTH env var:

* ``false`` (default) — native login form at ``/login``; passwords hashed with
  argon2-cffi.
* ``true`` — identity comes from ``Remote-User`` / ``Remote-Email`` /
  ``Remote-Name`` headers set by an upstream Authelia + reverse proxy. Native
  login form is disabled. ``TRUSTED_PROXY_IPS`` (CSV) restricts which client
  IPs are allowed to set those headers.
"""
from datetime import datetime
from functools import wraps
from ipaddress import ip_address, ip_network
import os

from flask import (
    Blueprint, abort, current_app, flash, g, redirect, render_template,
    request, session, url_for,
)
from flask_login import (
    LoginManager, current_user, login_required, login_user, logout_user,
)
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash

from .models import User, db


login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please sign in to continue."
login_manager.login_message_category = "warning"

_hasher = PasswordHasher()

bp = Blueprint("auth", __name__)
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ---------- password helpers ----------

def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(hashed: str | None, plain: str) -> bool:
    if not hashed or not plain:
        return False
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHash):
        return False


# ---------- mode helpers ----------

def trust_proxy_auth() -> bool:
    return (os.getenv("TRUST_PROXY_AUTH") or "false").strip().lower() == "true"


def disable_local_login() -> bool:
    """Strict SSO mode — disables the native /login form entirely.

    Default off, so TRUST_PROXY_AUTH=true gives a hybrid setup where the
    form is still reachable (useful for direct LAN access while a reverse
    proxy handles SSO at the public hostname). Set to "true" to lock down
    to SSO only."""
    return (os.getenv("DISABLE_LOCAL_LOGIN") or "false").strip().lower() == "true"


def _trusted_proxy_networks():
    raw = os.getenv("TRUSTED_PROXY_IPS") or ""
    nets = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            nets.append(ip_network(part, strict=False))
        except ValueError:
            current_app.logger.warning("Invalid TRUSTED_PROXY_IPS entry: %r", part)
    return nets


def _client_ip_allowed() -> bool:
    nets = _trusted_proxy_networks()
    if not nets:
        return True  # no allowlist configured — trust the network path
    raw = request.remote_addr
    if not raw:
        return False
    try:
        addr = ip_address(raw)
    except ValueError:
        return False
    return any(addr in n for n in nets)


# ---------- decorators ----------

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if not getattr(current_user, "is_admin", False):
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


# ---------- login manager ----------

@login_manager.user_loader
def _load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


# ---------- trusted-header SSO before_request ----------

def _admin_group_name() -> str:
    return (os.getenv("ADMIN_GROUP") or "admins").strip()


def _should_be_admin_from_headers():
    """Return True/False based on Remote-Groups, or None if header absent.

    None means 'do not change is_admin' — important so misconfigured proxies
    that omit Remote-Groups never accidentally demote an admin."""
    raw = request.headers.get("Remote-Groups")
    if raw is None:
        return None
    groups = {g.strip() for g in raw.split(",") if g.strip()}
    return _admin_group_name() in groups


def _trusted_header_login():
    """If TRUST_PROXY_AUTH=true and a Remote-User header is present from an
    allowed proxy, log the corresponding user in (creating the account if
    needed). Runs before each request."""
    if not trust_proxy_auth():
        return
    if current_user.is_authenticated:
        return
    if not _client_ip_allowed():
        return
    remote_user = (request.headers.get("Remote-User") or "").strip()
    if not remote_user:
        return
    email = (request.headers.get("Remote-Email") or "").strip() or None
    display_name = (request.headers.get("Remote-Name") or "").strip() or None
    should_be_admin = _should_be_admin_from_headers()  # None | True | False

    user = User.query.filter_by(username=remote_user).first()
    if user is None:
        user = User(
            username=remote_user,
            email=email,
            display_name=display_name,
            is_admin=bool(should_be_admin),
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()
    else:
        # Sync identity + admin flag from the IdP. Email / display_name follow
        # whatever Authelia sends (fall back to existing if blank). Admin flag
        # only changes when Remote-Groups is actually present.
        changed = False
        if email and user.email != email:
            user.email = email
            changed = True
        if display_name and user.display_name != display_name:
            user.display_name = display_name
            changed = True
        if should_be_admin is not None and user.is_admin != should_be_admin:
            user.is_admin = should_be_admin
            changed = True
        if changed:
            db.session.commit()

    if not user.is_active:
        abort(403)

    user.last_login_at = datetime.utcnow()
    db.session.commit()
    login_user(user, remember=True)
    session["sso"] = True


# ---------- routes ----------

@bp.route("/login", methods=["GET", "POST"])
def login():
    if disable_local_login():
        abort(404)
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        remember = bool(request.form.get("remember"))

        user = User.query.filter_by(username=username).first()
        if user is None or not user.is_active or not verify_password(user.password_hash, password):
            flash("Invalid credentials.", "danger")
            return render_template("login.html", username=username), 401

        user.last_login_at = datetime.utcnow()
        db.session.commit()
        login_user(user, remember=remember)
        session["sso"] = False
        next_url = request.args.get("next")
        return redirect(next_url or url_for("main.dashboard"))

    return render_template("login.html")


@bp.route("/logout", methods=["POST", "GET"])
@login_required
def logout():
    if disable_local_login():
        # Strict SSO: logout is owned by the upstream IdP.
        abort(404)
    was_sso = bool(session.get("sso"))
    logout_user()
    session.pop("sso", None)
    if was_sso:
        flash(
            "Local session cleared. Sign out of your identity provider to fully sign out.",
            "info",
        )
    else:
        flash("Signed out.", "info")
    return redirect(url_for("auth.login"))


@admin_bp.route("/users", methods=["GET"])
@admin_required
def users_list():
    users = User.query.order_by(User.created_at.asc()).all()
    return render_template("admin/users.html", users=users)


@admin_bp.route("/users/create", methods=["POST"])
@admin_required
def users_create():
    username = (request.form.get("username") or "").strip()
    email = (request.form.get("email") or "").strip() or None
    display_name = (request.form.get("display_name") or "").strip() or None
    password = request.form.get("password") or ""
    is_admin = bool(request.form.get("is_admin"))

    if not username:
        flash("Username is required.", "danger")
        return redirect(url_for("admin.users_list"))
    if User.query.filter_by(username=username).first():
        flash(f"User '{username}' already exists.", "warning")
        return redirect(url_for("admin.users_list"))
    if not trust_proxy_auth() and not password:
        flash("Password is required when not in proxy-auth mode.", "danger")
        return redirect(url_for("admin.users_list"))

    user = User(
        username=username,
        email=email,
        display_name=display_name,
        password_hash=hash_password(password) if password else None,
        is_admin=is_admin,
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()
    flash(f"User '{username}' created.", "success")
    return redirect(url_for("admin.users_list"))


@admin_bp.route("/users/<int:uid>/toggle-active", methods=["POST"])
@admin_required
def users_toggle_active(uid):
    user = db.session.get(User, uid) or abort(404)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "warning")
        return redirect(url_for("admin.users_list"))
    user.is_active = not user.is_active
    db.session.commit()
    flash(
        f"User '{user.username}' {'activated' if user.is_active else 'deactivated'}.",
        "success",
    )
    return redirect(url_for("admin.users_list"))


@admin_bp.route("/users/<int:uid>/reset-password", methods=["POST"])
@admin_required
def users_reset_password(uid):
    user = db.session.get(User, uid) or abort(404)
    new_password = request.form.get("password") or ""
    if not new_password:
        flash("Password cannot be empty.", "danger")
        return redirect(url_for("admin.users_list"))
    user.password_hash = hash_password(new_password)
    db.session.commit()
    flash(f"Password for '{user.username}' updated.", "success")
    return redirect(url_for("admin.users_list"))


@admin_bp.route("/users/<int:uid>/delete", methods=["POST"])
@admin_required
def users_delete(uid):
    user = db.session.get(User, uid) or abort(404)
    if user.id == current_user.id:
        flash("You cannot delete your own account.", "warning")
        return redirect(url_for("admin.users_list"))
    if user.is_admin:
        remaining_admins = User.query.filter(
            User.is_admin.is_(True), User.id != user.id
        ).count()
        if remaining_admins == 0:
            flash("Cannot delete the last remaining admin.", "warning")
            return redirect(url_for("admin.users_list"))

    # Refuse if the user owns data — admin should deactivate instead, or
    # transfer/delete the data first.
    from .models import Filament, PrintOrder
    if (
        Filament.query.filter_by(user_id=user.id).first()
        or PrintOrder.query.filter_by(user_id=user.id).first()
    ):
        flash(
            f"Cannot delete '{user.username}': they still own filaments or orders. "
            "Deactivate the account instead, or remove their data first.",
            "warning",
        )
        return redirect(url_for("admin.users_list"))

    db.session.delete(user)
    db.session.commit()
    flash(f"User '{user.username}' deleted.", "success")
    return redirect(url_for("admin.users_list"))


def init_app(app):
    """Wire login manager + before_request hook + auth blueprint into the app."""
    login_manager.init_app(app)

    @app.before_request
    def _sso_hook():
        _trusted_header_login()

    @app.context_processor
    def _inject_auth_flags():
        return {
            "trust_proxy_auth": trust_proxy_auth(),
            "disable_local_login": disable_local_login(),
            "sso_session": bool(session.get("sso")),
        }

    app.register_blueprint(bp)
    app.register_blueprint(admin_bp)
