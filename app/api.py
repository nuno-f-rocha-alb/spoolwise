"""JSON API for the React SPA.

Same-origin, session-cookie based — it reuses Flask-Login exactly like the
server-rendered pages, so no tokens are involved. In production the SPA is
served by Flask itself; in dev Vite proxies /api to Flask, so the session
cookie is first-party in both cases.

This blueprint is additive: the existing public /api/orders/* endpoint and all
Jinja routes are left untouched.
"""
from datetime import datetime

from flask import Blueprint, jsonify, request, session
from flask_login import current_user, login_required, login_user, logout_user

from .auth import (
    disable_local_login,
    trust_proxy_auth,
    verify_password,
)
from .models import Setting, User, db

api_bp = Blueprint("api", __name__, url_prefix="/api")


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "is_admin": bool(user.is_admin),
        "initials": user.initials,
    }


def auth_context() -> dict:
    """Per-request flags + user settings the SPA needs to bootstrap the shell."""
    return {
        "currency": Setting.get("currency_symbol", cast=str) or "€",
        "retail_mode_enabled": Setting.get_bool("retail_mode_enabled"),
        "trust_proxy_auth": trust_proxy_auth(),
        "disable_local_login": disable_local_login(),
        "sso_session": bool(session.get("sso")),
    }


@api_bp.get("/auth/me")
def auth_me():
    """Current session identity + bootstrap context, or 401 when anonymous."""
    if not current_user.is_authenticated:
        return jsonify({"authenticated": False}), 401
    return jsonify(
        {
            "authenticated": True,
            "user": serialize_user(current_user),
            **auth_context(),
        }
    )


@api_bp.post("/auth/login")
def auth_login():
    """Username/password login mirroring the Jinja /login POST handler."""
    if disable_local_login():
        # Strict SSO: native login is owned by the upstream IdP.
        return jsonify({"error": "Local login is disabled."}), 404

    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    remember = bool(data.get("remember"))

    user = User.query.filter_by(username=username).first()
    if user is None or not user.is_active or not verify_password(user.password_hash, password):
        return jsonify({"error": "Invalid credentials."}), 401

    user.last_login_at = datetime.utcnow()
    db.session.commit()
    login_user(user, remember=remember)
    session["sso"] = False
    return jsonify({"user": serialize_user(user), **auth_context()})


@api_bp.post("/auth/logout")
@login_required
def auth_logout():
    if disable_local_login():
        return jsonify({"error": "Logout is owned by the identity provider."}), 404
    was_sso = bool(session.get("sso"))
    logout_user()
    session.pop("sso", None)
    return jsonify({"ok": True, "was_sso": was_sso})
