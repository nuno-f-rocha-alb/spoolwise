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
    admin_required,
    disable_local_login,
    hash_password,
    trust_proxy_auth,
    verify_password,
)
from .models import (
    Filament,
    FilamentPurchase,
    OrderFile,
    OrderLink,
    PlateFilament,
    PrintOrder,
    PrintPlate,
    Setting,
    User,
    db,
)
from .routes import (
    _ALLOWED_UPLOAD_EXTS,
    _fetch_og,
    _parse_bambu_3mf,
    _snapshot_price_factory,
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


@api_bp.get("/settings")
@login_required
def settings_get():
    return jsonify(
        {
            "electricity_price_per_kwh": float(
                Setting.get("electricity_price_per_kwh") or 0
            ),
            "printer_power_watts": float(Setting.get("printer_power_watts") or 0),
            "default_profit_pct": float(Setting.get("default_profit_pct") or 30),
            "currency_symbol": Setting.get("currency_symbol", cast=str) or "€",
            "retail_mode_enabled": Setting.get_bool("retail_mode_enabled"),
            "default_vat_rate_pct": float(
                Setting.get("default_vat_rate_pct") or Decimal("23")
            ),
        }
    )


@api_bp.put("/settings")
@login_required
def settings_update():
    data = request.get_json(silent=True) or {}
    Setting.set("electricity_price_per_kwh", _dec(data.get("electricity_price_per_kwh")))
    Setting.set("printer_power_watts", _dec(data.get("printer_power_watts")))
    Setting.set("default_profit_pct", _dec(data.get("default_profit_pct")))
    currency = (data.get("currency_symbol") or "€").strip() or "€"
    Setting.set("currency_symbol", currency)
    Setting.set(
        "retail_mode_enabled",
        "true" if data.get("retail_mode_enabled") else "false",
    )
    Setting.set(
        "default_vat_rate_pct",
        _dec(data.get("default_vat_rate_pct"), default=Decimal("23")),
    )
    db.session.commit()
    return settings_get()


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


def _user_purchase_or_404(fid, pid):
    f = _user_filament_or_404(fid)
    p = FilamentPurchase.query.filter_by(id=pid, filament_id=f.id).first()
    if p is None:
        abort(404)
    return f, p


@api_bp.put("/filaments/<int:fid>/purchases/<int:pid>")
@login_required
def filament_purchase_edit(fid, pid):
    f, p = _user_purchase_or_404(fid, pid)
    data = request.get_json(silent=True) or {}
    quantity_g = _dec(data.get("quantity_g"))
    price_per_kg = _dec(data.get("price_per_kg"))
    if quantity_g <= 0 or price_per_kg <= 0:
        return jsonify({"error": "Quantity and price must be positive."}), 400
    try:
        f.edit_purchase(p, quantity_g, price_per_kg)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    db.session.commit()
    purchases = (
        FilamentPurchase.query.filter_by(filament_id=f.id)
        .order_by(FilamentPurchase.purchased_at.desc())
        .all()
    )
    return jsonify(
        {"filament": serialize_filament(f), "purchases": [serialize_purchase(x) for x in purchases]}
    )


@api_bp.delete("/filaments/<int:fid>/purchases/<int:pid>")
@login_required
def filament_purchase_delete(fid, pid):
    f, p = _user_purchase_or_404(fid, pid)
    try:
        f.delete_purchase(p)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    db.session.commit()
    purchases = (
        FilamentPurchase.query.filter_by(filament_id=f.id)
        .order_by(FilamentPurchase.purchased_at.desc())
        .all()
    )
    return jsonify(
        {"filament": serialize_filament(f), "purchases": [serialize_purchase(x) for x in purchases]}
    )


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
        "price_per_kg_override": (
            float(it.price_per_kg_override) if it.price_per_kg_override is not None else None
        ),
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


# ---------- Order create / update ----------

def _parse_plates_payload(plates_raw):
    """Validate the plates array. Returns (plates_data, error).

    plates_data: list of (print_time_hours, name|None, [(filament_id, weight_g, override|None)])."""
    if not isinstance(plates_raw, list) or not plates_raw:
        return None, "Add at least one plate."
    plates_data = []
    for i, p in enumerate(plates_raw):
        p = p or {}
        pt = _dec(p.get("print_time_hours"))
        pname = (p.get("name") or "").strip() or None
        if pt <= 0:
            return None, f"Plate {i + 1}: print time must be positive."
        items = []
        for it in p.get("filaments") or []:
            fid = (it or {}).get("filament_id")
            w = _dec((it or {}).get("weight_g"))
            if not fid or w <= 0:
                continue
            raw_override = (it or {}).get("price_per_kg_override")
            override = _dec(raw_override, default=None)
            if raw_override is not None and raw_override != "" and (override is None or override <= 0):
                return None, f"Plate {i + 1}: override price must be a positive number."
            try:
                items.append((int(fid), w, override))
            except (ValueError, TypeError):
                continue  # skip malformed filament_id
        if not items:
            return None, f"Plate {i + 1}: add at least one filament with weight > 0."
        plates_data.append((pt, pname, items))
    if not plates_data:
        return None, "Add at least one plate."
    return plates_data, None


def _order_form_fields(data):
    """Common scalar fields shared by create + update."""
    retail_on = Setting.get_bool("retail_mode_enabled")
    is_internal = bool(data.get("is_internal"))
    has_vat = retail_on and not is_internal and bool(data.get("has_vat"))
    vat_rate_pct = None
    if has_vat:
        vat_rate_pct = _dec(
            data.get("vat_rate_pct"),
            default=Setting.get("default_vat_rate_pct") or Decimal("23"),
        )
    try:
        quantity = max(1, int(data.get("quantity") or 1))
    except (ValueError, TypeError):
        quantity = 1
    return {
        "name": (data.get("name") or "").strip(),
        "customer": (data.get("customer") or "").strip() or None,
        "notes": (data.get("notes") or "").strip() or None,
        "raw_urls": [u.strip() for u in (data.get("model_urls") or []) if u and u.strip()],
        "is_internal": is_internal,
        "skip_stock_check": bool(data.get("skip_stock_check")),
        "profit_pct": _dec(
            data.get("profit_pct"),
            default=Setting.get("default_profit_pct") or Decimal(30),
        ),
        "quantity": quantity,
        "has_vat": has_vat,
        "vat_rate_pct": vat_rate_pct,
    }


@api_bp.post("/orders")
@login_required
def order_create():
    data = request.get_json(silent=True) or {}
    fields = _order_form_fields(data)
    if not fields["name"]:
        return jsonify({"error": "Name is required."}), 400

    plates_data, err = _parse_plates_payload(data.get("plates"))
    if err:
        return jsonify({"error": err}), 400

    skip = fields["skip_stock_check"]
    qty_dec = Decimal(fields["quantity"])

    filament_usage: dict = {}
    for _pt, _pn, items in plates_data:
        for fid, w, _override in items:
            filament_usage[fid] = filament_usage.get(fid, Decimal(0)) + w * qty_dec

    filament_objs: dict = {}
    stock_warnings: list = []
    for fid, total_w in filament_usage.items():
        f = Filament.query.filter_by(id=fid, user_id=current_user.id).first()
        if f is None:
            return jsonify({"error": "Invalid filament."}), 400
        if not skip and Decimal(str(f.stock_g or 0)) < total_w:
            short = total_w - Decimal(str(f.stock_g or 0))
            stock_warnings.append(
                f"{f.name} {f.material} {f.color}: requested {total_w} g, "
                f"in stock {f.stock_g} g (short by {short} g)"
            )
        filament_objs[fid] = f

    order = PrintOrder(
        user_id=current_user.id,
        name=fields["name"],
        customer=fields["customer"],
        notes=fields["notes"],
        model_url=fields["raw_urls"][0] if fields["raw_urls"] else None,
        profit_pct=fields["profit_pct"],
        is_internal=fields["is_internal"],
        skip_stock_deduction=skip,
        quantity=fields["quantity"],
        has_vat=fields["has_vat"],
        vat_rate_pct=fields["vat_rate_pct"],
        electricity_price_per_kwh=Setting.get("electricity_price_per_kwh"),
        printer_power_watts=Setting.get("printer_power_watts"),
    )
    db.session.add(order)
    db.session.flush()

    for pos, url in enumerate(fields["raw_urls"]):
        title, image = _fetch_og(url)
        db.session.add(
            OrderLink(order_id=order.id, position=pos, url=url, title=title, image=image)
        )

    snapshot_price = _snapshot_price_factory(fields["has_vat"], current_user.id)
    for pos, (pt, pname, items) in enumerate(plates_data, start=1):
        plate = PrintPlate(order_id=order.id, position=pos, name=pname, print_time_hours=pt)
        db.session.add(plate)
        db.session.flush()
        for fid, w, override in items:
            f = filament_objs[fid]
            db.session.add(
                PlateFilament(
                    plate_id=plate.id,
                    filament_id=f.id,
                    weight_g=w,
                    price_per_kg_snapshot=override if override else snapshot_price(f),
                    price_per_kg_override=override,
                )
            )

    if not skip:
        for fid, total_w in filament_usage.items():
            filament_objs[fid].stock_g = (
                Decimal(str(filament_objs[fid].stock_g or 0)) - total_w
            )

    db.session.commit()
    return (
        jsonify(
            {
                "order": serialize_order_detail(order),
                "stock_warnings": stock_warnings if not skip else [],
            }
        ),
        201,
    )


# ---------- Combined quote ----------

def serialize_quote_item(o: PrintOrder) -> dict:
    """Per-order line for the combined quote (money fields only — the customer
    view never needs cost/profit internals)."""
    return {
        "id": o.id,
        "name": o.name,
        "customer": o.customer,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "is_internal": o.is_internal,
        "has_vat": o.has_vat,
        "vat_rate_pct": float(o.vat_rate_pct) if o.vat_rate_pct is not None else None,
        "quantity": o.qty,
        "unit_sell_price": float(o.unit_sell_price),
        "sell_price": float(o.sell_price),
        "vat_amount": float(o.vat_amount),
        "sell_price_with_vat": float(o.sell_price_with_vat),
    }


@api_bp.get("/quote/combined")
@login_required
def quote_combined():
    """Aggregated quote for several orders (mirrors the Jinja order_quote_combined).
    Personal-use (internal) orders are excluded from the money totals."""
    raw_ids = request.args.get("ids", "")
    try:
        ids = [int(x) for x in raw_ids.split(",") if x.strip()]
    except ValueError:
        ids = []
    if not ids:
        return jsonify({"error": "Select at least one order to combine."}), 400

    orders = (
        PrintOrder.query.filter(
            PrintOrder.user_id == current_user.id, PrintOrder.id.in_(ids)
        )
        .order_by(PrintOrder.created_at.asc())
        .all()
    )
    if not orders:
        abort(404)

    billable = [o for o in orders if not o.is_internal]
    subtotal = sum((o.sell_price for o in billable), Decimal(0))
    vat_total = sum((o.vat_amount for o in billable), Decimal(0))
    total = subtotal + vat_total
    has_any_vat = any(o.has_vat for o in billable)
    vat_rates = sorted(
        {
            float(o.vat_rate_pct)
            for o in billable
            if o.has_vat and o.vat_rate_pct is not None
        }
    )

    return jsonify(
        {
            "currency": Setting.get("currency_symbol", cast=str) or "€",
            "orders": [serialize_quote_item(o) for o in orders],
            "subtotal": float(subtotal),
            "vat_total": float(vat_total),
            "total": float(total),
            "has_any_vat": has_any_vat,
            "vat_rates": vat_rates,
        }
    )


@api_bp.put("/orders/<int:oid>")
@login_required
def order_update(oid):
    order = _user_order_or_404(oid)
    data = request.get_json(silent=True) or {}
    fields = _order_form_fields(data)
    if not fields["name"]:
        return jsonify({"error": "Name is required."}), 400

    plates_data, err = _parse_plates_payload(data.get("plates"))
    if err:
        return jsonify({"error": err}), 400

    skip = fields["skip_stock_check"]
    qty_dec = Decimal(fields["quantity"])

    filament_usage: dict = {}
    for _pt, _pn, items in plates_data:
        for fid, w, _override in items:
            filament_usage[fid] = filament_usage.get(fid, Decimal(0)) + w * qty_dec

    # How much the order currently has deducted (old quantity, active plates only).
    old_qty = Decimal(int(order.quantity or 1))
    originally_deducted: dict = {}
    if not order.skip_stock_deduction:
        for plate in order.plates:
            if not plate.is_skipped:
                for it in plate.items:
                    if it.filament is not None:
                        originally_deducted[it.filament_id] = originally_deducted.get(
                            it.filament_id, Decimal(0)
                        ) + Decimal(str(it.weight_g)) * old_qty

    filament_objs: dict = {}
    stock_warnings: list = []
    for fid, total_w in filament_usage.items():
        f = Filament.query.filter_by(id=fid, user_id=current_user.id).first()
        if f is None:
            return jsonify({"error": "Invalid filament."}), 400
        effective_stock = Decimal(str(f.stock_g or 0)) + originally_deducted.get(
            fid, Decimal(0)
        )
        if not skip and effective_stock < total_w:
            short = total_w - effective_stock
            stock_warnings.append(
                f"{f.name} {f.material} {f.color}: requested {total_w} g, "
                f"available {effective_stock} g (short by {short} g)"
            )
        filament_objs[fid] = f

    # Restore old stock.
    for fid, deducted in originally_deducted.items():
        f = Filament.query.filter_by(id=fid, user_id=current_user.id).first()
        if f is not None:
            f.stock_g = Decimal(str(f.stock_g or 0)) + deducted

    old_link_map = {link.url: link for link in order.links}
    for link in list(order.links):
        db.session.delete(link)
    for plate in list(order.plates):
        db.session.delete(plate)
    db.session.flush()

    order.name = fields["name"]
    order.customer = fields["customer"]
    order.notes = fields["notes"]
    order.model_url = fields["raw_urls"][0] if fields["raw_urls"] else None
    order.profit_pct = fields["profit_pct"]
    order.is_internal = fields["is_internal"]
    order.skip_stock_deduction = skip
    order.quantity = fields["quantity"]
    order.has_vat = fields["has_vat"]
    order.vat_rate_pct = fields["vat_rate_pct"]
    order.electricity_price_per_kwh = Setting.get("electricity_price_per_kwh")
    order.printer_power_watts = Setting.get("printer_power_watts")

    for pos, url in enumerate(fields["raw_urls"]):
        old = old_link_map.get(url)
        if old is not None:
            db.session.add(
                OrderLink(order_id=order.id, position=pos, url=url, title=old.title, image=old.image)
            )
        else:
            title, image = _fetch_og(url)
            db.session.add(
                OrderLink(order_id=order.id, position=pos, url=url, title=title, image=image)
            )

    snapshot_price = _snapshot_price_factory(fields["has_vat"], current_user.id)
    for pos, (pt, pname, items) in enumerate(plates_data, start=1):
        plate = PrintPlate(order_id=order.id, position=pos, name=pname, print_time_hours=pt)
        db.session.add(plate)
        db.session.flush()
        for fid, w, override in items:
            f = filament_objs[fid]
            db.session.add(
                PlateFilament(
                    plate_id=plate.id,
                    filament_id=f.id,
                    weight_g=w,
                    price_per_kg_snapshot=override if override else snapshot_price(f),
                    price_per_kg_override=override,
                )
            )

    if not skip:
        for fid, total_w in filament_usage.items():
            filament_objs[fid].stock_g = (
                Decimal(str(filament_objs[fid].stock_g or 0)) - total_w
            )

    db.session.commit()
    return jsonify(
        {
            "order": serialize_order_detail(order),
            "stock_warnings": stock_warnings if not skip else [],
        }
    )


# ---------- Statistics ----------

@api_bp.get("/stats")
@login_required
def stats():
    """Business analytics for the SPA (faithful port of the Jinja `stats` route).
    Only *delivered commercial* orders count toward revenue/profit; personal-use
    orders are tracked as real cost only. Aggregation is server-side; the charts
    derive their inputs from `monthly` and `stock` client-side."""
    import calendar
    from collections import defaultdict

    retail_on = Setting.get_bool("retail_mode_enabled")

    all_orders = (
        PrintOrder.query.filter_by(user_id=current_user.id)
        .order_by(PrintOrder.created_at)
        .all()
    )
    commercial = [o for o in all_orders if not o.is_internal]
    internal = [o for o in all_orders if o.is_internal]
    delivered = [o for o in commercial if o.delivered_at]

    revenue = sum((o.sell_price for o in delivered), Decimal(0))
    filament_cost_c = sum((o.filament_cost for o in delivered), Decimal(0))
    electricity_cost_c = sum((o.electricity_cost for o in delivered), Decimal(0))
    total_cost_c = filament_cost_c + electricity_cost_c
    profit = revenue - total_cost_c

    delivered_retail = [o for o in delivered if o.has_vat]
    revenue_retail = sum((o.sell_price for o in delivered_retail), Decimal(0))
    revenue_particular = sum(
        (o.sell_price for o in delivered if not o.has_vat), Decimal(0)
    )
    vat_collected = sum((o.vat_amount for o in delivered_retail), Decimal(0))

    filament_cost_i = sum((o.filament_cost for o in internal), Decimal(0))
    electricity_cost_i = sum((o.electricity_cost for o in internal), Decimal(0))

    print_hours_all = sum((o.total_print_time_hours for o in all_orders), Decimal(0))
    print_hours_c = sum((o.total_print_time_hours for o in commercial), Decimal(0))
    print_hours_i = sum((o.total_print_time_hours for o in internal), Decimal(0))

    purchases = FilamentPurchase.query.filter_by(user_id=current_user.id).all()
    purchased_spend = sum(
        (
            (Decimal(str(p.quantity_g)) / Decimal(1000)) * Decimal(str(p.price_per_kg))
            for p in purchases
        ),
        Decimal(0),
    )

    filaments = (
        Filament.query.filter_by(user_id=current_user.id).order_by(Filament.name).all()
    )
    stock_value = sum((f.stock_value for f in filaments), Decimal(0))
    stock_kg = sum((f.stock_kg for f in filaments), Decimal(0))

    # Monthly breakdown (delivered commercial), at most the last 24 months.
    monthly = defaultdict(
        lambda: {"revenue": Decimal(0), "cost": Decimal(0), "vat": Decimal(0), "orders": 0}
    )
    for o in delivered:
        key = o.delivered_at.strftime("%Y-%m")
        monthly[key]["revenue"] += o.sell_price
        monthly[key]["cost"] += o.total_cost
        monthly[key]["vat"] += o.vat_amount
        monthly[key]["orders"] += 1

    monthly_rows = []
    for key in sorted(monthly.keys())[-24:]:
        year, month = map(int, key.split("-"))
        m = monthly[key]
        monthly_rows.append(
            {
                "key": key,
                "label": f"{calendar.month_abbr[month]}/{year}",
                "orders": m["orders"],
                "revenue": float(m["revenue"]),
                "cost": float(m["cost"]),
                "vat": float(m["vat"]),
                "profit": float(m["revenue"] - m["cost"]),
            }
        )

    # Top filaments by cost in delivered commercial orders.
    spend = defaultdict(
        lambda: {
            "name": "",
            "material": "",
            "color": "",
            "weight_g": Decimal(0),
            "cost": Decimal(0),
        }
    )
    for o in delivered:
        for plate in o.plates:
            for it in plate.items:
                row = spend[it.filament_id]
                if it.filament:
                    row["name"] = it.filament.name
                    row["material"] = it.filament.material
                    row["color"] = it.filament.color
                else:
                    row["name"] = "(removed)"
                row["weight_g"] += Decimal(str(it.weight_g))
                row["cost"] += it.cost
    top_filaments = [
        {
            "name": r["name"],
            "material": r["material"],
            "color": r["color"],
            "weight_g": float(r["weight_g"]),
            "cost": float(r["cost"]),
        }
        for r in sorted(spend.values(), key=lambda x: x["cost"], reverse=True)[:10]
    ]

    # In-stock filaments (stock > 0), largest value first — used by table + chart.
    stock = [
        {
            "id": f.id,
            "name": f.name,
            "material": f.material,
            "color": f.color,
            "color_hex": f.color_hex,
            "stock_kg": float(f.stock_kg),
            "stock_value": float(f.stock_value),
        }
        for f in sorted(filaments, key=lambda f: f.stock_value, reverse=True)
        if f.stock_g > 0
    ]

    return jsonify(
        {
            "currency": Setting.get("currency_symbol", cast=str) or "€",
            "retail_mode_enabled": retail_on,
            "totals": {
                "revenue": float(revenue),
                "filament_cost_commercial": float(filament_cost_c),
                "electricity_cost_commercial": float(electricity_cost_c),
                "total_cost_commercial": float(total_cost_c),
                "profit": float(profit),
                "vat_collected": float(vat_collected),
                "revenue_retail": float(revenue_retail),
                "revenue_particular": float(revenue_particular),
                "delivered_retail_count": len(delivered_retail),
                "filament_cost_internal": float(filament_cost_i),
                "electricity_cost_internal": float(electricity_cost_i),
                "print_hours_all": float(print_hours_all),
                "print_hours_commercial": float(print_hours_c),
                "print_hours_internal": float(print_hours_i),
                "filament_purchased_spend": float(purchased_spend),
                "stock_value": float(stock_value),
                "stock_kg": float(stock_kg),
                "filament_count": len(filaments),
            },
            "counts": {
                "total": len(all_orders),
                "commercial": len(commercial),
                "internal": len(internal),
                "pending": sum(1 for o in all_orders if o.status == "pending"),
                "printed": sum(1 for o in all_orders if o.status == "printed"),
                "delivered": sum(1 for o in all_orders if o.status == "delivered"),
            },
            "monthly": monthly_rows,
            "top_filaments": top_filaments,
            "stock": stock,
        }
    )


# ---------- Admin: users ----------

def serialize_admin_user(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "display_name": u.display_name,
        "email": u.email,
        "is_admin": bool(u.is_admin),
        "is_active": bool(u.is_active),
        "initials": u.initials,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
    }


@api_bp.get("/admin/users")
@admin_required
def admin_users_list():
    users = User.query.order_by(User.created_at.asc()).all()
    return jsonify(
        {
            "trust_proxy_auth": trust_proxy_auth(),
            "users": [serialize_admin_user(u) for u in users],
        }
    )


@api_bp.post("/admin/users")
@admin_required
def admin_users_create():
    """Port of admin.users_create — password optional only in proxy-auth mode."""
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip() or None
    display_name = (data.get("display_name") or "").strip() or None
    password = data.get("password") or ""

    if not username:
        return jsonify({"error": "Username is required."}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": f"User '{username}' already exists."}), 409
    if not trust_proxy_auth() and not password:
        return jsonify({"error": "Password is required when not in proxy-auth mode."}), 400

    user = User(
        username=username,
        email=email,
        display_name=display_name,
        password_hash=hash_password(password) if password else None,
        is_admin=bool(data.get("is_admin")),
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()
    Setting.ensure_defaults(user_id=user.id)
    db.session.commit()
    return jsonify({"user": serialize_admin_user(user)}), 201


@api_bp.post("/admin/users/<int:uid>/toggle-active")
@admin_required
def admin_users_toggle_active(uid):
    user = db.session.get(User, uid) or abort(404)
    if user.id == current_user.id:
        return jsonify({"error": "You cannot deactivate your own account."}), 400
    user.is_active = not user.is_active
    db.session.commit()
    return jsonify({"user": serialize_admin_user(user)})


@api_bp.post("/admin/users/<int:uid>/reset-password")
@admin_required
def admin_users_reset_password(uid):
    user = db.session.get(User, uid) or abort(404)
    new_password = (request.get_json(silent=True) or {}).get("password") or ""
    if not new_password:
        return jsonify({"error": "Password cannot be empty."}), 400
    user.password_hash = hash_password(new_password)
    db.session.commit()
    return jsonify({"ok": True})


@api_bp.delete("/admin/users/<int:uid>")
@admin_required
def admin_users_delete(uid):
    """Port of admin.users_delete — refuses self, last admin, or data owners."""
    user = db.session.get(User, uid) or abort(404)
    if user.id == current_user.id:
        return jsonify({"error": "You cannot delete your own account."}), 400
    if user.is_admin:
        remaining = User.query.filter(
            User.is_admin.is_(True), User.id != user.id
        ).count()
        if remaining == 0:
            return jsonify({"error": "Cannot delete the last remaining admin."}), 400
    if (
        Filament.query.filter_by(user_id=user.id).first()
        or PrintOrder.query.filter_by(user_id=user.id).first()
    ):
        return (
            jsonify(
                {
                    "error": (
                        f"Cannot delete '{user.username}': they still own filaments "
                        "or orders. Deactivate the account instead, or remove their "
                        "data first."
                    )
                }
            ),
            409,
        )
    # The user's Setting rows are their own config (settings.user_id has no DB
    # cascade) — remove them first, else the FK blocks the delete with a raw 500.
    Setting.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    return jsonify({"ok": True})
