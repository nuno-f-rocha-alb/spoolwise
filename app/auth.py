"""Auth: login manager, password hashing, trusted-header SSO.

The SPA owns the login UI and calls the JSON endpoints in ``api.py``
(``/api/auth/*``); this module provides the shared pieces both modes need.
Two modes, switched by the TRUST_PROXY_AUTH env var:

* ``false`` (default) — native username/password login (passwords hashed with
  argon2-cffi).
* ``true`` — identity comes from ``Remote-User`` / ``Remote-Email`` /
  ``Remote-Name`` headers set by an upstream Authelia + reverse proxy.
  ``TRUSTED_PROXY_IPS`` (CSV) restricts which client IPs may set those headers.
"""
from datetime import datetime
from functools import wraps
from ipaddress import ip_address, ip_network
import os

from flask import abort, current_app, request, session
from flask_login import LoginManager, current_user, login_user
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash
from sqlalchemy.exc import IntegrityError

from .models import User, db


login_manager = LoginManager()
# No login_view: the SPA owns auth, so unauthenticated access to a protected
# endpoint returns 401 (the SPA's /api/auth/me drives the redirect to /login
# client-side) rather than redirecting to a server-rendered login page.
login_manager.login_view = None
login_manager.login_message = "Please sign in to continue."
login_manager.login_message_category = "warning"

_hasher = PasswordHasher()



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
        try:
            db.session.commit()
        except IntegrityError:
            # A concurrent request created the same user first. Roll back and
            # adopt the row that won the race.
            db.session.rollback()
            user = User.query.filter_by(username=remote_user).first()
            if user is None:
                raise
        else:
            from .models import Setting
            Setting.ensure_defaults(user_id=user.id)
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



def init_app(app):
    """Wire login manager + trusted-proxy SSO hook into the app.

    The Jinja auth/admin blueprints are no longer registered — the SPA owns
    login (`/api/auth/*`) and user management (`/api/admin/users*`). The
    `_sso_hook` is app-level, so hybrid auth (native login on LAN/VPN +
    Authelia header login externally) keeps working regardless."""
    login_manager.init_app(app)

    @app.before_request
    def _sso_hook():
        _trusted_header_login()
