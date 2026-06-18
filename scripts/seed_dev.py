"""Dev-only seed data for local visual verification of the SPA.

Run inside the app container:
    docker compose exec -T app python scripts/seed_dev.py

Idempotent-ish: skips filaments/orders that already exist by name.
Not used in production.
"""
from decimal import Decimal

from app import create_app
from app.models import (
    db,
    User,
    Filament,
    PrintOrder,
    PrintPlate,
    PlateFilament,
    Setting,
)

app = create_app()

with app.app_context():
    admin = User.query.filter_by(is_admin=True).order_by(User.id.asc()).first()
    if admin is None:
        raise SystemExit("No admin user found — start the app once to bootstrap it.")
    uid = admin.id

    def mkfil(name, material, color, hexc, stock_g, price):
        f = Filament.query.filter_by(
            user_id=uid, name=name, material=material, color=color
        ).first()
        if f:
            return f
        f = Filament(
            user_id=uid, name=name, material=material, color=color, color_hex=hexc
        )
        db.session.add(f)
        db.session.flush()
        if stock_g > 0 and price > 0:
            f.add_purchase(stock_g, price)
        return f

    fils = {
        "black": mkfil("Bambu", "PLA Basic", "Black", "#1a1a1a", 850, 19.99),
        "galaxy": mkfil("Bambu", "PLA Galaxy", "Galaxy Black", "#2b2b3a", 60, 24.99),
        "orange": mkfil("Polymaker", "PETG", "Orange", "#fd7e14", 0, 21.50),
        "ivory": mkfil("Bambu", "PLA Matte", "Ivory White", "#f3efe6", 1200, 18.00),
        "blue": mkfil("eSUN", "PLA+", "Blue", "#0d6efd", 430, 16.50),
    }
    db.session.commit()

    def mkorder(name, customer, internal, plates):
        if PrintOrder.query.filter_by(user_id=uid, name=name).first():
            return
        o = PrintOrder(
            user_id=uid,
            name=name,
            customer=customer,
            is_internal=internal,
            profit_pct=Decimal("30"),
            quantity=1,
            electricity_price_per_kwh=Setting.get(
                "electricity_price_per_kwh", user_id=uid
            ),
            printer_power_watts=Setting.get("printer_power_watts", user_id=uid),
        )
        db.session.add(o)
        db.session.flush()
        for pos, (hours, items) in enumerate(plates, start=1):
            p = PrintPlate(
                order_id=o.id, position=pos, print_time_hours=Decimal(str(hours))
            )
            db.session.add(p)
            db.session.flush()
            for fil, weight in items:
                db.session.add(
                    PlateFilament(
                        plate_id=p.id,
                        filament_id=fil.id,
                        weight_g=Decimal(str(weight)),
                        price_per_kg_snapshot=fil.avg_price_per_kg,
                    )
                )

    mkorder(
        "Hex keychain batch",
        "Maria S.",
        False,
        [(2.5, [(fils["black"], 45), (fils["orange"], 8)])],
    )
    mkorder(
        "Desk cable organizer",
        "TechCorp Lda.",
        False,
        [(6.0, [(fils["ivory"], 180)]), (4.25, [(fils["blue"], 95)])],
    )
    mkorder(
        "Replacement printer gear",
        None,
        True,
        [(1.75, [(fils["black"], 22)])],
    )
    db.session.commit()

    print(
        f"Seeded: {Filament.query.filter_by(user_id=uid).count()} filaments, "
        f"{PrintOrder.query.filter_by(user_id=uid).count()} orders for '{admin.username}'."
    )
