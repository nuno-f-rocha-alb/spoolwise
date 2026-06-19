"""JSON API for the React SPA.

Same-origin, session-cookie based — it reuses Flask-Login exactly like the
server-rendered pages, so no tokens are involved. In production the SPA is
served by Flask itself; in dev Vite proxies /api to Flask, so the session
cookie is first-party in both cases.

This blueprint is additive: the existing public /api/orders/* endpoint and all
Jinja routes are left untouched.
"""
import base64
import os
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, current_app, jsonify, request, session
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from .auth import (
    disable_local_login,
    trust_proxy_auth,
    verify_password,
)
from .models import (
    Filament,
    FilamentPurchase,
    OrderFile,
    PrintOrder,
    Setting,
    User,
    db,
)
from .routes import (
    _ALLOWED_UPLOAD_EXTS,
    _parse_bambu_3mf,
    _sync_order_printed,
    _user_file_or_404,
    _user_plate_or_404,
)

LOW_STOCK_G = Decimal(100)

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _dec(value, default=Decimal(0)):
    """Coerce a JSON value (number or string, comma or dot) to Decimal.

    Rejects values with more than one separator (e.g. thousand-separated
    "1,234.56") rather than silently corrupting them."""
    if value is None or value == "":
        return default
    try:
        s = str(value).strip()
        if s.count(",") + s.count(".") > 1:
            return default
        return Decimal(s.replace(",", "."))
    except InvalidOperation:
        return default


def _user_filament_or_404(fid):
    f = Filament.query.filter_by(id=fid, user_id=current_user.id).first()
    if f is None:
        abort(404)
    return f


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


def serialize_filament(f: Filament) -> dict:
    stock_g = Decimal(str(f.stock_g or 0))
    return {
        "id": f.id,
        "name": f.name,
        "material": f.material,
        "color": f.color,
        "color_hex": f.color_hex,
        "stock_g": float(stock_g),
        "stock_kg": float(f.stock_kg),
        "avg_price_per_kg": float(f.avg_price_per_kg or 0),
        "stock_value": float(f.stock_value),
        "is_zero_stock": stock_g <= 0,
        "is_low_stock": 0 < stock_g <= LOW_STOCK_G,
    }


def serialize_order_summary(o: PrintOrder) -> dict:
    return {
        "id": o.id,
        "name": o.name,
        "customer": o.customer,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "is_internal": o.is_internal,
        "status": o.status,
        "total_cost": float(o.total_cost),
        "sell_price": float(o.sell_price),
    }


@api_bp.get("/dashboard")
@login_required
def dashboard():
    """Inventory snapshot + recent orders for the SPA dashboard (per-user)."""
    filaments = (
        Filament.query.filter_by(user_id=current_user.id)
        .order_by(Filament.name)
        .all()
    )
    recent = (
        PrintOrder.query.filter_by(user_id=current_user.id)
        .order_by(PrintOrder.created_at.desc())
        .limit(5)
        .all()
    )
    total_stock_value = sum((f.stock_value for f in filaments), Decimal(0))
    total_stock_kg = sum((f.stock_kg for f in filaments), Decimal(0))
    low_stock_count = sum(
        1 for f in filaments if Decimal(str(f.stock_g or 0)) <= LOW_STOCK_G
    )

    return jsonify(
        {
            "currency": Setting.get("currency_symbol", cast=str) or "€",
            "totals": {
                "stock_kg": float(total_stock_kg),
                "stock_value": float(total_stock_value),
                "filament_count": len(filaments),
                "low_stock_count": low_stock_count,
            },
            "filaments": [serialize_filament(f) for f in filaments],
            "recent_orders": [serialize_order_summary(o) for o in recent],
        }
    )


# ---------- Filaments ----------

def serialize_purchase(p: FilamentPurchase) -> dict:
    return {
        "id": p.id,
        "quantity_g": float(p.quantity_g),
        "price_per_kg": float(p.price_per_kg),
        "purchased_at": p.purchased_at.isoformat() if p.purchased_at else None,
    }


@api_bp.get("/filaments")
@login_required
def filaments_list():
    """All of the user's filaments + distinct brand/material facets. Filtering
    and sorting are done client-side (the per-user list is small)."""
    filaments = (
        Filament.query.filter_by(user_id=current_user.id)
        .order_by(Filament.name)
        .all()
    )
    materials = sorted({f.material for f in filaments})
    brands = sorted({f.name for f in filaments})
    return jsonify(
        {
            "currency": Setting.get("currency_symbol", cast=str) or "€",
            "filaments": [serialize_filament(f) for f in filaments],
            "materials": materials,
            "brands": brands,
        }
    )


@api_bp.get("/filaments/<int:fid>")
@login_required
def filament_detail(fid):
    f = _user_filament_or_404(fid)
    purchases = (
        FilamentPurchase.query.filter_by(filament_id=f.id)
        .order_by(FilamentPurchase.purchased_at.desc())
        .all()
    )
    return jsonify(
        {
            "currency": Setting.get("currency_symbol", cast=str) or "€",
            "filament": serialize_filament(f),
            "purchases": [serialize_purchase(p) for p in purchases],
        }
    )


@api_bp.post("/filaments")
@login_required
def filament_create():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    material = (data.get("material") or "PLA").strip()
    color = (data.get("color") or "").strip()
    color_hex = (data.get("color_hex") or "").strip() or None
    stock_g = _dec(data.get("stock_g"))
    price_per_kg = _dec(data.get("price_per_kg"))

    if not name:
        return jsonify({"error": "Name is required."}), 400

    existing = Filament.query.filter_by(
        user_id=current_user.id, name=name, material=material, color=color
    ).first()
    if existing:
        return (
            jsonify(
                {
                    "error": (
                        f"Filament '{name} · {material} · {color}' already exists. "
                        "Use Buy to add more stock."
                    ),
                    "existing_id": existing.id,
                }
            ),
            409,
        )

    f = Filament(
        user_id=current_user.id,
        name=name,
        material=material,
        color=color,
        color_hex=color_hex,
    )
    db.session.add(f)
    db.session.flush()
    if stock_g > 0 and price_per_kg > 0:
        f.add_purchase(stock_g, price_per_kg)
    db.session.commit()
    return jsonify({"filament": serialize_filament(f)}), 201


@api_bp.post("/filaments/<int:fid>/purchase")
@login_required
def filament_purchase(fid):
    f = _user_filament_or_404(fid)
    data = request.get_json(silent=True) or {}
    quantity_g = _dec(data.get("quantity_g"))
    price_per_kg = _dec(data.get("price_per_kg"))
    if quantity_g <= 0 or price_per_kg <= 0:
        return jsonify({"error": "Quantity and price must be positive."}), 400
    f.add_purchase(quantity_g, price_per_kg)
    db.session.commit()
    return jsonify({"filament": serialize_filament(f)})


@api_bp.post("/filaments/<int:fid>/adjust")
@login_required
def filament_adjust(fid):
    f = _user_filament_or_404(fid)
    data = request.get_json(silent=True) or {}
    new_stock = _dec(data.get("stock_g"), default=None)
    if new_stock is None or new_stock < 0:
        return jsonify({"error": "Invalid stock value."}), 400
    # Inventory correction only — does NOT touch the weighted-average price.
    f.stock_g = new_stock
    db.session.commit()
    return jsonify({"filament": serialize_filament(f)})


@api_bp.delete("/filaments/<int:fid>")
@login_required
def filament_delete(fid):
    f = _user_filament_or_404(fid)
    db.session.delete(f)
    try:
        db.session.commit()
    except IntegrityError:
        # Referenced by one or more orders (plate filaments) — the FK blocks it.
        db.session.rollback()
        return (
            jsonify(
                {
                    "error": "This filament is used by one or more orders and can't be deleted."
                }
            ),
            409,
        )
    return jsonify({"ok": True})


# ---------- Orders ----------

def _user_order_or_404(oid):
    o = PrintOrder.query.filter_by(id=oid, user_id=current_user.id).first()
    if o is None:
        abort(404)
    return o


def serialize_order_list(o: PrintOrder) -> dict:
    """Row-level fields for the orders table (no plate/file detail)."""
    return {
        "id": o.id,
        "name": o.name,
        "customer": o.customer,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "is_internal": o.is_internal,
        "skip_stock_deduction": o.skip_stock_deduction,
        "has_vat": o.has_vat,
        "vat_rate_pct": float(o.vat_rate_pct) if o.vat_rate_pct is not None else None,
        "quantity": o.qty,
        "status": o.status,
        "plate_count": len(o.plates),
        "total_print_time_hours": float(o.total_print_time_hours),
        "total_cost": float(o.total_cost),
        "sell_price": float(o.sell_price),
        "sell_price_with_vat": float(o.sell_price_with_vat),
        "profit_value": float(o.profit_value),
    }


@api_bp.get("/orders")
@login_required
def orders_list():
    """All of the user's orders (newest first). Status/type filtering is done
    client-side."""
    orders = (
        PrintOrder.query.filter_by(user_id=current_user.id)
        .order_by(PrintOrder.created_at.desc())
        .all()
    )
    return jsonify(
        {
            "currency": Setting.get("currency_symbol", cast=str) or "€",
            "retail_mode_enabled": Setting.get_bool("retail_mode_enabled"),
            "orders": [serialize_order_list(o) for o in orders],
        }
    )


@api_bp.delete("/orders/<int:oid>")
@login_required
def order_delete(oid):
    """Delete an order, restoring stock for any plates that deducted it
    (mirrors the Jinja order_delete)."""
    order = _user_order_or_404(oid)
    restored = not order.skip_stock_deduction
    if restored:
        qty = Decimal(str(order.quantity or 1))
        for plate in order.plates:
            if not plate.is_skipped:  # skipped plates already restored on skip
                for it in plate.items:
                    if it.filament is not None:
                        it.filament.stock_g = (
                            Decimal(str(it.filament.stock_g or 0))
                            + Decimal(str(it.weight_g)) * qty
                        )
    db.session.delete(order)
    db.session.commit()
    return jsonify({"ok": True, "stock_restored": restored})


# ---------- Order detail ----------

def serialize_plate_item(it) -> dict:
    f = it.filament
    return {
        "id": it.id,
        "filament_id": it.filament_id,
        "weight_g": float(it.weight_g),
        "price_per_kg_snapshot": float(it.price_per_kg_snapshot),
        "cost": float(it.cost),
        "filament": {
            "id": f.id,
            "name": f.name,
            "material": f.material,
            "color": f.color,
            "color_hex": f.color_hex,
        }
        if f
        else None,
    }


def serialize_plate(p) -> dict:
    return {
        "id": p.id,
        "position": p.position,
        "name": p.name,
        "print_time_hours": float(p.print_time_hours),
        "printed_at": p.printed_at.isoformat() if p.printed_at else None,
        "is_skipped": p.is_skipped,
        "filament_cost": float(p.filament_cost),
        "electricity_cost": float(p.electricity_cost),
        "total_cost": float(p.total_cost),
        "items": [serialize_plate_item(it) for it in p.items],
    }


def serialize_link(link) -> dict:
    return {"id": link.id, "url": link.url, "title": link.title, "image": link.image}


def serialize_file(f) -> dict:
    return {
        "id": f.id,
        "filename": f.filename,
        "original_name": f.original_name,
        "file_type": f.file_type,
        "is_plate_thumb": f.is_plate_thumb,
        "plate_index": f.plate_index,
        "is_viewable_3d": f.is_viewable_3d,
        "is_image": f.is_image,
    }


def serialize_order_detail(o: PrintOrder) -> dict:
    return {
        "id": o.id,
        "name": o.name,
        "customer": o.customer,
        "notes": o.notes,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "printed_at": o.printed_at.isoformat() if o.printed_at else None,
        "delivered_at": o.delivered_at.isoformat() if o.delivered_at else None,
        "status": o.status,
        "is_internal": o.is_internal,
        "skip_stock_deduction": o.skip_stock_deduction,
        "has_vat": o.has_vat,
        "vat_rate_pct": float(o.vat_rate_pct) if o.vat_rate_pct is not None else None,
        "quantity": o.qty,
        "profit_pct": float(o.profit_pct),
        "printer_power_watts": float(o.printer_power_watts),
        "electricity_price_per_kwh": float(o.electricity_price_per_kwh),
        "total_print_time_hours": float(o.total_print_time_hours),
        "unit_print_time_hours": float(o.unit_print_time_hours),
        "filament_cost": float(o.filament_cost),
        "electricity_cost": float(o.electricity_cost),
        "total_cost": float(o.total_cost),
        "unit_cost": float(o.unit_cost),
        "sell_price": float(o.sell_price),
        "unit_sell_price": float(o.unit_sell_price),
        "vat_amount": float(o.vat_amount),
        "sell_price_with_vat": float(o.sell_price_with_vat),
        "profit_value": float(o.profit_value),
        "plates": [serialize_plate(p) for p in o.plates],
        "links": [serialize_link(link) for link in o.links],
        "files": [serialize_file(f) for f in o.files],
    }


@api_bp.get("/orders/<int:oid>")
@login_required
def order_detail(oid):
    o = _user_order_or_404(oid)
    return jsonify(
        {
            "currency": Setting.get("currency_symbol", cast=str) or "€",
            "retail_mode_enabled": Setting.get_bool("retail_mode_enabled"),
            "order": serialize_order_detail(o),
        }
    )


@api_bp.post("/orders/<int:oid>/plates/<int:pid>/toggle-printed")
@login_required
def plate_toggle_printed(oid, pid):
    plate = _user_plate_or_404(pid)
    if plate.order_id != oid:
        abort(404)
    plate.printed_at = None if plate.printed_at else datetime.utcnow()
    _sync_order_printed(plate.order)
    db.session.commit()
    order = plate.order
    return jsonify(
        {
            "plate_printed": plate.printed_at is not None,
            "order_status": order.status,
            "order_printed_at": order.printed_at.isoformat()
            if order.printed_at
            else None,
        }
    )


@api_bp.post("/orders/<int:oid>/plates/<int:pid>/toggle-skipped")
@login_required
def plate_toggle_skipped(oid, pid):
    plate = _user_plate_or_404(pid)
    if plate.order_id != oid:
        abort(404)
    plate.is_skipped = not plate.is_skipped
    if plate.is_skipped:
        plate.printed_at = None

    # Restore stock when skipping, deduct again when unskipping (× quantity).
    if not plate.order.skip_stock_deduction:
        qty = Decimal(str(plate.order.quantity or 1))
        for it in plate.items:
            if it.filament is not None:
                delta = Decimal(str(it.weight_g)) * qty
                if plate.is_skipped:
                    it.filament.stock_g = Decimal(str(it.filament.stock_g or 0)) + delta
                else:
                    it.filament.stock_g = Decimal(str(it.filament.stock_g or 0)) - delta

    _sync_order_printed(plate.order)
    db.session.commit()
    order = plate.order
    return jsonify(
        {
            "plate_skipped": plate.is_skipped,
            "plate_printed": plate.printed_at is not None,
            "order_status": order.status,
        }
    )


@api_bp.post("/orders/<int:oid>/printed")
@login_required
def order_mark_printed(oid):
    order = _user_order_or_404(oid)
    marking = bool((request.get_json(silent=True) or {}).get("value"))
    order.mark_printed(marking)
    now = datetime.utcnow() if marking else None
    for plate in order.plates:
        if not plate.is_skipped:
            plate.printed_at = now
    db.session.commit()
    return jsonify({"status": order.status})


@api_bp.post("/orders/<int:oid>/delivered")
@login_required
def order_mark_delivered(oid):
    order = _user_order_or_404(oid)
    order.mark_delivered(bool((request.get_json(silent=True) or {}).get("value")))
    db.session.commit()
    return jsonify({"status": order.status})


@api_bp.post("/orders/<int:oid>/files")
@login_required
def order_file_upload(oid):
    order = _user_order_or_404(oid)
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "No file selected."}), 400

    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in _ALLOWED_UPLOAD_EXTS:
        return jsonify({"error": f"File type .{ext} not supported."}), 400

    upload_dir = current_app.config["UPLOAD_FOLDER"]
    stored = f"{uuid.uuid4()}.{ext}"
    dest = os.path.join(upload_dir, stored)
    f.save(dest)

    db.session.add(
        OrderFile(
            order_id=oid,
            filename=stored,
            original_name=secure_filename(f.filename),
            file_type=ext,
        )
    )

    warning = None
    if ext == "3mf":
        parsed = _parse_bambu_3mf(dest)
        for plate in parsed.get("plates", []):
            thumb_b64 = plate.get("thumb_b64")
            if not thumb_b64:
                continue
            try:
                _, data = thumb_b64.split(",", 1)
                thumb_bytes = base64.b64decode(data)
                thumb_stored = f"{uuid.uuid4()}.png"
                with open(os.path.join(upload_dir, thumb_stored), "wb") as tf:
                    tf.write(thumb_bytes)
                db.session.add(
                    OrderFile(
                        order_id=oid,
                        filename=thumb_stored,
                        original_name=f"plate_{plate['index']}_thumbnail.png",
                        file_type="png",
                        is_plate_thumb=True,
                        plate_index=plate["index"],
                    )
                )
            except Exception as exc:  # noqa: BLE001
                current_app.logger.warning("plate thumbnail save failed: %s", exc)
        warning = parsed.get("warning")

    db.session.commit()
    return jsonify({"order": serialize_order_detail(order), "warning": warning})


@api_bp.delete("/files/<int:fid>")
@login_required
def file_delete(fid):
    f = _user_file_or_404(fid)
    oid = f.order_id
    upload_dir = current_app.config["UPLOAD_FOLDER"]

    to_delete = [f]
    if f.file_type == "3mf":
        # Mirrors the Jinja route: a 3MF's extracted plate thumbnails go with it.
        thumbs = OrderFile.query.filter_by(order_id=oid, is_plate_thumb=True).all()
        to_delete.extend(thumbs)

    for entry in to_delete:
        try:
            os.remove(os.path.join(upload_dir, entry.filename))
        except OSError:
            pass
        db.session.delete(entry)

    db.session.commit()
    return jsonify({"ok": True})
