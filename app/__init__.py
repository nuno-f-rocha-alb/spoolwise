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
        from .models import Setting
        Setting.ensure_defaults()
        db.session.commit()

    return app
