import json
import os
import secrets
import time
from flask import Flask
from flask_bootstrap import Bootstrap5
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from .models import db
from .routes import bp as main_bp
from . import auth as auth_module


def _run_additive_migrations(app):
    """Apply additive schema changes that db.create_all() cannot handle on existing tables."""
    with db.engine.connect() as conn:
        # print_orders.is_internal — added after initial release
        result = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = DATABASE() "
                "AND table_name = 'print_orders' "
                "AND column_name = 'is_internal'"
            )
        )
        if result.scalar() == 0:
            conn.execute(
                text(
                    "ALTER TABLE print_orders "
                    "ADD COLUMN is_internal TINYINT(1) NOT NULL DEFAULT 0"
                )
            )
            conn.commit()

        # print_plates.printed_at + is_skipped — per-plate print tracking
        for col_def in [
            ("printed_at", "DATETIME NULL"),
            ("is_skipped",  "TINYINT(1) NOT NULL DEFAULT 0"),
        ]:
            col_name, col_spec = col_def
            result = conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() "
                    "AND table_name = 'print_plates' "
                    "AND column_name = :col"
                ),
                {"col": col_name},
            )
            if result.scalar() == 0:
                conn.execute(text(f"ALTER TABLE print_plates ADD COLUMN {col_name} {col_spec}"))
                conn.commit()

        # print_orders.skip_stock_deduction — added for quote / no-stock-check mode
        result = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = DATABASE() "
                "AND table_name = 'print_orders' "
                "AND column_name = 'skip_stock_deduction'"
            )
        )
        if result.scalar() == 0:
            conn.execute(
                text(
                    "ALTER TABLE print_orders "
                    "ADD COLUMN skip_stock_deduction TINYINT(1) NOT NULL DEFAULT 0"
                )
            )
            conn.commit()

        # order_files — file attachments (STL, 3MF, images) per order
        result = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = 'order_files'"
            )
        )
        if result.scalar() == 0:
            conn.execute(text("""
                CREATE TABLE order_files (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    order_id INT NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    original_name VARCHAR(255) NOT NULL,
                    file_type VARCHAR(10) NOT NULL,
                    is_plate_thumb TINYINT(1) NOT NULL DEFAULT 0,
                    plate_index INT NULL,
                    uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (order_id) REFERENCES print_orders(id) ON DELETE CASCADE
                )
            """))
            conn.commit()

        # filaments.color_hex — added for Bambu color hex support
        result = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = DATABASE() "
                "AND table_name = 'filaments' "
                "AND column_name = 'color_hex'"
            )
        )
        if result.scalar() == 0:
            conn.execute(text("ALTER TABLE filaments ADD COLUMN color_hex VARCHAR(7) NULL"))
            conn.commit()

        # print_orders: retail mode columns (quantity, VAT)
        for col_name, col_spec in [
            ("quantity",     "INT NOT NULL DEFAULT 1"),
            ("has_vat",      "TINYINT(1) NOT NULL DEFAULT 0"),
            ("vat_rate_pct", "DECIMAL(6,2) NULL"),
        ]:
            result = conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() "
                    "AND table_name = 'print_orders' "
                    "AND column_name = :col"
                ),
                {"col": col_name},
            )
            if result.scalar() == 0:
                conn.execute(text(f"ALTER TABLE print_orders ADD COLUMN {col_name} {col_spec}"))
                conn.commit()


def _has_column(conn, table, column):
    return conn.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() "
            "AND table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).scalar() > 0


def _has_constraint(conn, table, constraint):
    return conn.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.table_constraints "
            "WHERE table_schema = DATABASE() "
            "AND table_name = :t AND constraint_name = :c"
        ),
        {"t": table, "c": constraint},
    ).scalar() > 0


def _bootstrap_admin(app):
    """If no users exist, create an initial admin from env vars.

    Returns the admin user (existing or newly created), or None when there
    are already users (no bootstrap needed).
    """
    from .models import User
    if User.query.count() > 0:
        return None

    username = (os.getenv("ADMIN_USERNAME") or "admin").strip() or "admin"
    email = (os.getenv("ADMIN_EMAIL") or "").strip() or None
    raw_password = os.getenv("ADMIN_PASSWORD") or ""
    generated = False
    if not raw_password:
        raw_password = secrets.token_urlsafe(18)
        generated = True

    admin = User(
        username=username,
        email=email,
        display_name=username,
        password_hash=auth_module.hash_password(raw_password),
        is_admin=True,
        is_active=True,
    )
    db.session.add(admin)
    db.session.commit()

    if generated:
        # Print to stdout so it lands in container logs. One-time only.
        print(
            "=" * 72 + "\n"
            f"  Spoolwise: created initial admin user '{username}'.\n"
            f"  Generated password: {raw_password}\n"
            "  CHANGE THIS PASSWORD AFTER FIRST LOGIN.\n"
            + "=" * 72,
            flush=True,
        )
    else:
        app.logger.info("Spoolwise: created initial admin user %r from env.", username)
    return admin


def _migrate_user_isolation(app):
    """Add user_id columns + FKs to existing data tables, backfill to admin,
    then update the filaments unique constraint to include user_id.

    Idempotent and safe across restarts."""
    from .models import User
    admin = User.query.filter_by(is_admin=True).order_by(User.id.asc()).first()
    if admin is None:
        # No users yet — bootstrap should have run before this. Bail safely.
        return

    with db.engine.connect() as conn:
        for table in ("filaments", "filament_purchases", "print_orders"):
            if not _has_column(conn, table, "user_id"):
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id INT NULL"))
                conn.commit()
                conn.execute(
                    text(f"UPDATE {table} SET user_id = :uid WHERE user_id IS NULL"),
                    {"uid": admin.id},
                )
                conn.commit()
                conn.execute(text(f"ALTER TABLE {table} MODIFY COLUMN user_id INT NOT NULL"))
                conn.commit()
                fk_name = f"fk_{table}_user_id"
                if not _has_constraint(conn, table, fk_name):
                    try:
                        conn.execute(text(
                            f"ALTER TABLE {table} ADD CONSTRAINT {fk_name} "
                            f"FOREIGN KEY (user_id) REFERENCES users(id)"
                        ))
                        conn.commit()
                    except Exception as e:  # noqa: BLE001
                        app.logger.warning("Could not add FK %s: %s", fk_name, e)
            else:
                # Table already has user_id — make sure no orphans remain.
                conn.execute(
                    text(f"UPDATE {table} SET user_id = :uid WHERE user_id IS NULL"),
                    {"uid": admin.id},
                )
                conn.commit()

        # filaments unique constraint: (name, material, color) -> (user_id, name, material, color)
        # The constraint name stays the same; we drop and recreate.
        existing = conn.execute(text(
            "SELECT GROUP_CONCAT(column_name ORDER BY ordinal_position) "
            "FROM information_schema.key_column_usage "
            "WHERE table_schema = DATABASE() "
            "AND table_name = 'filaments' "
            "AND constraint_name = 'uq_filament_ident'"
        )).scalar()
        target = "user_id,name,material,color"
        if existing and existing != target:
            try:
                conn.execute(text("ALTER TABLE filaments DROP INDEX uq_filament_ident"))
                conn.commit()
            except Exception as e:  # noqa: BLE001
                app.logger.warning("Could not drop old uq_filament_ident: %s", e)
            try:
                conn.execute(text(
                    "ALTER TABLE filaments ADD CONSTRAINT uq_filament_ident "
                    "UNIQUE (user_id, name, material, color)"
                ))
                conn.commit()
            except Exception as e:  # noqa: BLE001
                app.logger.warning("Could not add new uq_filament_ident: %s", e)


def _resolve_brand(bambu, brand):
    """Resolve brand name through aliases (case-insensitive)."""
    aliases = bambu.get("_aliases", {})
    brand_l = brand.lower()
    for alias, target in aliases.items():
        if alias.lower() == brand_l:
            return target
    return brand


def _lookup_bambu_hex(bambu, brand, material, color):
    """Look up hex by brand → material → color, with alias and case-insensitive support."""
    resolved = _resolve_brand(bambu, brand)
    brand_l = resolved.lower()
    material_l = material.lower()
    color_l = color.lower()
    for b_key, materials in bambu.items():
        if b_key.startswith("_") or b_key.lower() != brand_l:
            continue
        for m_key, colors in materials.items():
            if m_key.lower() != material_l:
                continue
            for c_key, hex_val in colors.items():
                if c_key.lower() == color_l:
                    return hex_val
    return None


def _migrate_order_links():
    """One-time: copy existing model_url/title/image into order_links rows."""
    from .models import PrintOrder, OrderLink
    orders = PrintOrder.query.filter(
        PrintOrder.model_url.isnot(None),
    ).all()
    for order in orders:
        if order.links:
            continue
        link = OrderLink(
            order_id=order.id,
            position=0,
            url=order.model_url,
            title=order.model_title,
            image=order.model_image,
        )
        db.session.add(link)
    db.session.commit()


def _backfill_color_hex(app):
    """Populate color_hex for filaments that don't have one yet."""
    bambu_path = os.path.join(app.root_path, "static", "bambu_colors.json")
    if not os.path.exists(bambu_path):
        return
    with open(bambu_path) as f:
        bambu = json.load(f)

    from .models import Filament
    to_update = Filament.query.filter(Filament.color_hex.is_(None)).all()
    for fil in to_update:
        hex_val = _lookup_bambu_hex(bambu, fil.name.strip(), fil.material.strip(), fil.color.strip())
        if hex_val:
            fil.color_hex = hex_val
    db.session.commit()


def create_app():
    load_dotenv()
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://printing:printing@localhost:3306/printing_app",
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["BOOTSTRAP_BOOTSWATCH_THEME"] = "flatly"
    app.config["MAX_CONTENT_LENGTH"] = 150 * 1024 * 1024  # 150 MB max upload
    upload_dir = os.path.join(app.root_path, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    app.config["UPLOAD_FOLDER"] = upload_dir

    db.init_app(app)
    Bootstrap5(app)
    auth_module.init_app(app)

    @app.template_filter("duration")
    def duration_filter(hours):
        from decimal import Decimal
        h = int(hours)
        m = round((Decimal(str(hours)) - h) * 60)
        if m == 60:
            h += 1
            m = 0
        return f"{h}h {m:02d}m"

    app.register_blueprint(main_bp)

    @app.context_processor
    def inject_currency():
        from .models import Setting
        return {
            "currency": Setting.get("currency_symbol", cast=str) or "€",
            "retail_mode_enabled": Setting.get_bool("retail_mode_enabled"),
        }

    with app.app_context():
        for attempt in range(10):
            try:
                db.create_all()
                break
            except OperationalError:
                if attempt == 9:
                    raise
                time.sleep(3)
        # Additive migrations: add columns introduced after initial schema.
        # After any ALTER TABLE we dispose the connection pool, otherwise
        # MariaDB returns 1412 ("Table definition has changed") on the next
        # SELECT against an existing connection that still has the old
        # table definition cached.
        _run_additive_migrations(app)
        db.session.close()
        db.engine.dispose()

        _bootstrap_admin(app)
        _migrate_user_isolation(app)
        db.session.close()
        db.engine.dispose()

        _migrate_order_links()
        _backfill_color_hex(app)
        from .models import Setting
        Setting.ensure_defaults()
        db.session.commit()

    return app
