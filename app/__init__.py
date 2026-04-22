import json
import os
import time
from flask import Flask
from flask_bootstrap import Bootstrap5
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from .models import db
from .routes import bp as main_bp


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

    db.init_app(app)
    Bootstrap5(app)

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
        return {"currency": Setting.get("currency_symbol", cast=str) or "€"}

    with app.app_context():
        for attempt in range(10):
            try:
                db.create_all()
                break
            except OperationalError:
                if attempt == 9:
                    raise
                time.sleep(3)
        # Additive migrations: add columns introduced after initial schema
        _run_additive_migrations(app)
        _migrate_order_links()
        _backfill_color_hex(app)
        from .models import Setting
        Setting.ensure_defaults()
        db.session.commit()

    return app
