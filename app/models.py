from datetime import datetime
from decimal import Decimal
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Numeric

db = SQLAlchemy()


class Setting(db.Model):
    __tablename__ = "settings"
    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.String(255), nullable=False)

    DEFAULTS = {
        "electricity_price_per_kwh": "0.1600",
        "printer_power_watts": "250",
        "default_profit_pct": "30",
        "currency_symbol": "€",
    }

    @classmethod
    def ensure_defaults(cls):
        for k, v in cls.DEFAULTS.items():
            if db.session.get(cls, k) is None:
                db.session.add(cls(key=k, value=v))

    @classmethod
    def get(cls, key, cast=Decimal):
        row = db.session.get(cls, key)
        if row is None:
            return None
        return cast(row.value)

    @classmethod
    def set(cls, key, value):
        row = db.session.get(cls, key)
        if row is None:
            row = cls(key=key, value=str(value))
            db.session.add(row)
        else:
            row.value = str(value)


class Filament(db.Model):
    __tablename__ = "filaments"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    material = db.Column(db.String(40), nullable=False, default="PLA")
    color = db.Column(db.String(40), nullable=False, default="")
    color_hex = db.Column(db.String(7), nullable=True)
    stock_g = db.Column(Numeric(12, 2), nullable=False, default=0)
    avg_price_per_kg = db.Column(Numeric(12, 4), nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    purchases = db.relationship(
        "FilamentPurchase", backref="filament", cascade="all, delete-orphan"
    )

    __table_args__ = (
        db.UniqueConstraint("name", "material", "color", name="uq_filament_ident"),
    )

    @property
    def stock_kg(self):
        return (self.stock_g or Decimal(0)) / Decimal(1000)

    @property
    def stock_value(self):
        return self.stock_kg * (self.avg_price_per_kg or Decimal(0))

    def add_purchase(self, quantity_g, price_per_kg):
        quantity_g = Decimal(str(quantity_g))
        price_per_kg = Decimal(str(price_per_kg))
        current_kg = self.stock_kg
        add_kg = quantity_g / Decimal(1000)
        total_kg = current_kg + add_kg
        if total_kg > 0:
            self.avg_price_per_kg = (
                (current_kg * (self.avg_price_per_kg or Decimal(0)))
                + (add_kg * price_per_kg)
            ) / total_kg
        self.stock_g = (self.stock_g or Decimal(0)) + quantity_g
        db.session.add(
            FilamentPurchase(
                filament_id=self.id,
                quantity_g=quantity_g,
                price_per_kg=price_per_kg,
            )
        )


class FilamentPurchase(db.Model):
    __tablename__ = "filament_purchases"
    id = db.Column(db.Integer, primary_key=True)
    filament_id = db.Column(db.Integer, db.ForeignKey("filaments.id"), nullable=False)
    quantity_g = db.Column(Numeric(12, 2), nullable=False)
    price_per_kg = db.Column(Numeric(12, 4), nullable=False)
    purchased_at = db.Column(db.DateTime, default=datetime.utcnow)


class PrintOrder(db.Model):
    __tablename__ = "print_orders"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    customer = db.Column(db.String(160), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    model_url = db.Column(db.String(500), nullable=True)
    model_title = db.Column(db.String(300), nullable=True)
    model_image = db.Column(db.String(500), nullable=True)
    profit_pct = db.Column(Numeric(6, 2), nullable=False, default=30)
    electricity_price_per_kwh = db.Column(Numeric(10, 4), nullable=False)
    printer_power_watts = db.Column(Numeric(10, 2), nullable=False)
    is_internal = db.Column(db.Boolean, nullable=False, default=False)
    skip_stock_deduction = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    printed_at = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)

    plates = db.relationship(
        "PrintPlate",
        backref="order",
        cascade="all, delete-orphan",
        order_by="PrintPlate.position",
    )
    links = db.relationship(
        "OrderLink",
        backref="order",
        cascade="all, delete-orphan",
        order_by="OrderLink.position",
    )
    files = db.relationship(
        "OrderFile",
        backref="order",
        cascade="all, delete-orphan",
        order_by="OrderFile.uploaded_at",
    )

    @property
    def total_print_time_hours(self):
        return sum((Decimal(str(p.print_time_hours)) for p in self.plates), Decimal(0))

    @property
    def filament_cost(self):
        return sum((p.filament_cost for p in self.plates), Decimal(0))

    @property
    def electricity_cost(self):
        return sum((p.electricity_cost for p in self.plates), Decimal(0))

    @property
    def total_cost(self):
        return self.filament_cost + self.electricity_cost

    @property
    def sell_price(self):
        return self.total_cost * (Decimal(1) + Decimal(str(self.profit_pct)) / Decimal(100))

    @property
    def profit_value(self):
        return self.sell_price - self.total_cost

    @property
    def status(self):
        if self.delivered_at:
            return "delivered"
        if self.printed_at:
            return "printed"
        return "pending"

    def mark_printed(self, value: bool):
        if value:
            self.printed_at = self.printed_at or datetime.utcnow()
        else:
            self.printed_at = None
            self.delivered_at = None

    def mark_delivered(self, value: bool):
        if value:
            self.printed_at = self.printed_at or datetime.utcnow()
            self.delivered_at = self.delivered_at or datetime.utcnow()
        else:
            self.delivered_at = None


class OrderLink(db.Model):
    __tablename__ = "order_links"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("print_orders.id"), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    url = db.Column(db.Text, nullable=False)
    title = db.Column(db.String(300), nullable=True)
    image = db.Column(db.String(500), nullable=True)


class PrintPlate(db.Model):
    __tablename__ = "print_plates"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("print_orders.id"), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=1)
    print_time_hours = db.Column(Numeric(8, 2), nullable=False)
    printed_at = db.Column(db.DateTime, nullable=True)
    is_skipped = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship(
        "PlateFilament", backref="plate", cascade="all, delete-orphan"
    )

    @property
    def filament_cost(self):
        return sum((it.cost for it in self.items), Decimal(0))

    @property
    def electricity_cost(self):
        kwh = (
            Decimal(str(self.order.printer_power_watts)) / Decimal(1000)
        ) * Decimal(str(self.print_time_hours))
        return kwh * Decimal(str(self.order.electricity_price_per_kwh))

    @property
    def total_cost(self):
        return self.filament_cost + self.electricity_cost


class OrderFile(db.Model):
    __tablename__ = "order_files"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("print_orders.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)       # UUID-based stored name
    original_name = db.Column(db.String(255), nullable=False)  # original upload filename
    file_type = db.Column(db.String(10), nullable=False)       # stl, 3mf, png, jpg …
    is_plate_thumb = db.Column(db.Boolean, nullable=False, default=False)
    plate_index = db.Column(db.Integer, nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def is_viewable_3d(self):
        return self.file_type in ("stl", "3mf")

    @property
    def is_image(self):
        return self.file_type in ("png", "jpg", "jpeg", "gif", "webp")


class PlateFilament(db.Model):
    __tablename__ = "plate_filaments"
    id = db.Column(db.Integer, primary_key=True)
    plate_id = db.Column(db.Integer, db.ForeignKey("print_plates.id"), nullable=False)
    filament_id = db.Column(db.Integer, db.ForeignKey("filaments.id"), nullable=False)
    weight_g = db.Column(Numeric(12, 2), nullable=False)
    price_per_kg_snapshot = db.Column(Numeric(12, 4), nullable=False)

    filament = db.relationship("Filament")

    @property
    def cost(self):
        return (Decimal(str(self.weight_g)) / Decimal(1000)) * Decimal(
            str(self.price_per_kg_snapshot)
        )
