from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import re
import requests as http_requests
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort

from .models import (
    db,
    Setting,
    Filament,
    FilamentPurchase,
    PrintOrder,
    PrintPlate,
    PlateFilament,
)

bp = Blueprint("main", __name__)


class _OGParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.og = {}

    def handle_starttag(self, tag, attrs):
        if tag == "meta":
            a = dict(attrs)
            prop = a.get("property", "") or a.get("name", "")
            if prop in ("og:title", "og:image") and "content" in a:
                self.og[prop] = a["content"]


def _fetch_og_makerworld(url):
    """MakerWorld-specific: extract model ID and call their JSON API."""
    m = re.search(r"/models/(\d+)", url)
    if not m:
        return None, None
    try:
        api_url = f"https://makerworld.com/api/v1/design/detail?id={m.group(1)}"
        r = http_requests.get(api_url, timeout=5,
                              headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        title = data.get("title") or data.get("name")
        covers = data.get("cover") or data.get("coverList") or []
        image = covers[0].get("url") if isinstance(covers, list) and covers else None
        return title, image
    except Exception:
        return None, None


def _fetch_og(url):
    # MakerWorld fast-path (avoids Cloudflare entirely)
    if "makerworld.com" in url:
        title, image = _fetch_og_makerworld(url)
        if title:
            return title, image

    # General path: curl_cffi with real browser TLS fingerprint
    try:
        from curl_cffi import requests as cffi_requests
        r = cffi_requests.get(url, impersonate="chrome124", timeout=8)
        parser = _OGParser()
        parser.feed(r.text[:50000])
        return parser.og.get("og:title"), parser.og.get("og:image")
    except Exception:
        return None, None


def _dec(value, default=Decimal(0)):
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value).replace(",", "."))
    except InvalidOperation:
        return default


@bp.route("/")
def dashboard():
    filaments = Filament.query.order_by(Filament.name).all()
    recent = (
        PrintOrder.query.order_by(PrintOrder.created_at.desc()).limit(5).all()
    )
    total_stock_value = sum((f.stock_value for f in filaments), Decimal(0))
    total_stock_kg = sum((f.stock_kg for f in filaments), Decimal(0))
    return render_template(
        "dashboard.html",
        filaments=filaments,
        recent=recent,
        total_stock_value=total_stock_value,
        total_stock_kg=total_stock_kg,
    )


# ---------- Settings ----------

@bp.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        Setting.set(
            "electricity_price_per_kwh",
            _dec(request.form.get("electricity_price_per_kwh")),
        )
        Setting.set(
            "printer_power_watts",
            _dec(request.form.get("printer_power_watts")),
        )
        Setting.set(
            "default_profit_pct",
            _dec(request.form.get("default_profit_pct")),
        )
        db.session.commit()
        flash("Definições guardadas.", "success")
        return redirect(url_for("main.settings"))

    return render_template(
        "settings.html",
        electricity_price_per_kwh=Setting.get("electricity_price_per_kwh"),
        printer_power_watts=Setting.get("printer_power_watts"),
        default_profit_pct=Setting.get("default_profit_pct"),
    )


# ---------- Filaments ----------

@bp.route("/filaments")
def filaments_list():
    material_filter = request.args.get("material", "all")
    brand_filter = request.args.get("brand", "all")
    sort = request.args.get("sort", "name")
    direction = request.args.get("dir", "asc")

    sort_map = {
        "name": Filament.name,
        "material": Filament.material,
        "color": Filament.color,
        "stock": Filament.stock_g,
        "price": Filament.avg_price_per_kg,
    }
    sort_col = sort_map.get(sort, Filament.name)
    sort_col = sort_col.desc() if direction == "desc" else sort_col.asc()

    q = Filament.query
    if material_filter != "all":
        q = q.filter_by(material=material_filter)
    if brand_filter != "all":
        q = q.filter_by(name=brand_filter)

    filaments = q.order_by(sort_col).all()
    materials = [r[0] for r in db.session.query(Filament.material).distinct().order_by(Filament.material).all()]
    brands = [r[0] for r in db.session.query(Filament.name).distinct().order_by(Filament.name).all()]

    return render_template(
        "filaments_list.html",
        filaments=filaments,
        materials=materials,
        brands=brands,
        material_filter=material_filter,
        brand_filter=brand_filter,
        sort=sort,
        direction=direction,
    )


@bp.route("/filaments/new", methods=["GET", "POST"])
def filament_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        material = request.form.get("material", "PLA").strip()
        color = request.form.get("color", "").strip()
        stock_g = _dec(request.form.get("stock_g"))
        price_per_kg = _dec(request.form.get("price_per_kg"))

        if not name:
            flash("Nome é obrigatório.", "danger")
            return redirect(url_for("main.filament_new"))

        existing = Filament.query.filter_by(name=name, material=material, color=color).first()
        if existing:
            flash(
                f"O filamento '{name} · {material} · {color}' já existe. "
                f"Usa o botão Comprar para adicionar mais stock.",
                "warning",
            )
            return redirect(url_for("main.filaments_list"))

        f = Filament(name=name, material=material, color=color)
        db.session.add(f)
        db.session.flush()
        if stock_g > 0 and price_per_kg > 0:
            f.add_purchase(stock_g, price_per_kg)
        db.session.commit()
        flash("Filamento criado.", "success")
        return redirect(url_for("main.filaments_list"))

    return render_template("filament_form.html")


@bp.route("/filaments/<int:fid>/purchase", methods=["GET", "POST"])
def filament_purchase(fid):
    f = Filament.query.get_or_404(fid)
    if request.method == "POST":
        quantity_g = _dec(request.form.get("quantity_g"))
        price_per_kg = _dec(request.form.get("price_per_kg"))
        if quantity_g <= 0 or price_per_kg <= 0:
            flash("Quantidade e preço têm de ser positivos.", "danger")
            return redirect(url_for("main.filament_purchase", fid=f.id))
        f.add_purchase(quantity_g, price_per_kg)
        db.session.commit()
        flash(
            f"Adicionado {quantity_g} g. Novo preço médio: "
            f"{f.avg_price_per_kg:.2f} €/kg.",
            "success",
        )
        return redirect(url_for("main.filaments_list"))

    purchases = (
        FilamentPurchase.query.filter_by(filament_id=f.id)
        .order_by(FilamentPurchase.purchased_at.desc())
        .all()
    )
    return render_template("purchase_form.html", filament=f, purchases=purchases)


@bp.route("/filaments/<int:fid>/adjust", methods=["POST"])
def filament_adjust(fid):
    f = Filament.query.get_or_404(fid)
    new_stock = _dec(request.form.get("stock_g"), default=None)
    if new_stock is None or new_stock < 0:
        flash("Valor de stock inválido.", "danger")
        return redirect(url_for("main.filament_purchase", fid=f.id))
    f.stock_g = new_stock
    db.session.commit()
    flash(f"Stock de {f.name} ajustado para {new_stock} g.", "success")
    return redirect(url_for("main.filaments_list"))


@bp.route("/filaments/<int:fid>/delete", methods=["POST"])
def filament_delete(fid):
    f = Filament.query.get_or_404(fid)
    db.session.delete(f)
    db.session.commit()
    flash("Filamento removido.", "success")
    return redirect(url_for("main.filaments_list"))


# ---------- Orders ----------

@bp.route("/orders")
def orders_list():
    status_filter = request.args.get("status", "all")
    type_filter = request.args.get("type", "all")
    q = PrintOrder.query
    if status_filter == "pending":
        q = q.filter(PrintOrder.printed_at.is_(None))
    elif status_filter == "printed":
        q = q.filter(PrintOrder.printed_at.isnot(None), PrintOrder.delivered_at.is_(None))
    elif status_filter == "delivered":
        q = q.filter(PrintOrder.delivered_at.isnot(None))
    if type_filter == "commercial":
        q = q.filter(PrintOrder.is_internal.is_(False))
    elif type_filter == "internal":
        q = q.filter(PrintOrder.is_internal.is_(True))
    orders = q.order_by(PrintOrder.created_at.desc()).all()
    return render_template(
        "orders_list.html",
        orders=orders,
        status_filter=status_filter,
        type_filter=type_filter,
    )


@bp.route("/orders/new", methods=["GET", "POST"])
def order_new():
    filaments = Filament.query.order_by(Filament.name).all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        customer = request.form.get("customer", "").strip() or None
        notes = request.form.get("notes", "").strip() or None
        model_url = request.form.get("model_url", "").strip() or None
        is_internal = request.form.get("is_internal") == "1"
        profit_pct = _dec(
            request.form.get("profit_pct"),
            default=Setting.get("default_profit_pct") or Decimal(30),
        )

        try:
            num_plates = int(request.form.get("num_plates", 0))
        except (ValueError, TypeError):
            num_plates = 0

        if not name:
            flash("Nome é obrigatório.", "danger")
            return redirect(url_for("main.order_new"))

        if num_plates < 1:
            flash("Adicione pelo menos um prato.", "danger")
            return redirect(url_for("main.order_new"))

        # Parse all plates
        plates_data = []
        for i in range(num_plates):
            ph = _dec(request.form.get(f"plate_{i}_hours"))
            pm = _dec(request.form.get(f"plate_{i}_minutes"))
            pt = ph + pm / Decimal(60)
            fids = request.form.getlist(f"plate_{i}_filament_ids")
            weights = request.form.getlist(f"plate_{i}_weights")

            if pt <= 0:
                flash(f"Prato {i + 1}: tempo de impressão tem de ser positivo.", "danger")
                return redirect(url_for("main.order_new"))

            plate_items = []
            for fid_s, w_s in zip(fids, weights):
                if not fid_s:
                    continue
                w = _dec(w_s)
                if w <= 0:
                    continue
                plate_items.append((int(fid_s), w))

            if not plate_items:
                flash(f"Prato {i + 1}: adicione pelo menos um filamento com peso > 0.", "danger")
                return redirect(url_for("main.order_new"))

            plates_data.append((pt, plate_items))

        if not plates_data:
            flash("Adicione pelo menos um prato.", "danger")
            return redirect(url_for("main.order_new"))

        # Aggregate stock usage per filament across all plates
        filament_usage: dict = {}
        for _pt, plate_items in plates_data:
            for fid, w in plate_items:
                filament_usage[fid] = filament_usage.get(fid, Decimal(0)) + w

        # Validate stock for all filaments before touching anything
        filament_objs: dict = {}
        for fid, total_w in filament_usage.items():
            f = db.session.get(Filament, fid)
            if f is None:
                flash("Filamento inválido.", "danger")
                return redirect(url_for("main.order_new"))
            if Decimal(str(f.stock_g or 0)) < total_w:
                flash(
                    f"Stock insuficiente para {f.name} ({f.color}). "
                    f"Disponível: {f.stock_g} g, pedido total: {total_w} g.",
                    "danger",
                )
                return redirect(url_for("main.order_new"))
            filament_objs[fid] = f

        # Create order
        model_title, model_image = _fetch_og(model_url) if model_url else (None, None)

        order = PrintOrder(
            name=name,
            customer=customer,
            notes=notes,
            model_url=model_url,
            model_title=model_title,
            model_image=model_image,
            profit_pct=profit_pct,
            is_internal=is_internal,
            electricity_price_per_kwh=Setting.get("electricity_price_per_kwh"),
            printer_power_watts=Setting.get("printer_power_watts"),
        )
        db.session.add(order)
        db.session.flush()

        for pos, (pt, plate_items) in enumerate(plates_data, start=1):
            plate = PrintPlate(order_id=order.id, position=pos, print_time_hours=pt)
            db.session.add(plate)
            db.session.flush()
            for fid, w in plate_items:
                f = filament_objs[fid]
                db.session.add(
                    PlateFilament(
                        plate_id=plate.id,
                        filament_id=f.id,
                        weight_g=w,
                        price_per_kg_snapshot=f.avg_price_per_kg or Decimal(0),
                    )
                )

        # Deduct stock after all validation passes
        for fid, total_w in filament_usage.items():
            filament_objs[fid].stock_g = Decimal(str(filament_objs[fid].stock_g or 0)) - total_w

        db.session.commit()
        flash("Encomenda criada e stock atualizado.", "success")
        return redirect(url_for("main.order_detail", oid=order.id))

    return render_template(
        "order_form.html",
        filaments=filaments,
        default_profit_pct=Setting.get("default_profit_pct"),
    )


@bp.route("/orders/<int:oid>")
def order_detail(oid):
    order = PrintOrder.query.get_or_404(oid)
    return render_template("order_detail.html", order=order)


@bp.route("/orders/<int:oid>/printed", methods=["POST"])
def order_mark_printed(oid):
    order = PrintOrder.query.get_or_404(oid)
    order.mark_printed(request.form.get("value") == "1")
    db.session.commit()
    return redirect(request.referrer or url_for("main.orders_list"))


@bp.route("/orders/<int:oid>/delivered", methods=["POST"])
def order_mark_delivered(oid):
    order = PrintOrder.query.get_or_404(oid)
    order.mark_delivered(request.form.get("value") == "1")
    db.session.commit()
    return redirect(request.referrer or url_for("main.orders_list"))


@bp.route("/orders/<int:oid>/delete", methods=["POST"])
def order_delete(oid):
    order = PrintOrder.query.get_or_404(oid)
    for plate in order.plates:
        for it in plate.items:
            if it.filament is not None:
                it.filament.stock_g = Decimal(str(it.filament.stock_g or 0)) + Decimal(str(it.weight_g))
    db.session.delete(order)
    db.session.commit()
    flash("Encomenda removida e stock reposto.", "success")
    return redirect(url_for("main.orders_list"))


# ---------- Statistics ----------

@bp.route("/stats")
def stats():
    from collections import defaultdict
    import calendar

    all_orders = PrintOrder.query.order_by(PrintOrder.created_at).all()
    commercial_orders = [o for o in all_orders if not o.is_internal]
    internal_orders = [o for o in all_orders if o.is_internal]
    delivered_commercial = [o for o in commercial_orders if o.delivered_at]

    # --- Totals ---
    total_revenue = sum((o.sell_price for o in delivered_commercial), Decimal(0))
    total_filament_spend_commercial = sum(
        (o.filament_cost for o in delivered_commercial), Decimal(0)
    )
    total_electricity_commercial = sum(
        (o.electricity_cost for o in delivered_commercial), Decimal(0)
    )
    total_cost_commercial = total_filament_spend_commercial + total_electricity_commercial
    total_profit = total_revenue - total_cost_commercial

    total_filament_spend_internal = sum(
        (o.filament_cost for o in internal_orders), Decimal(0)
    )
    total_electricity_internal = sum(
        (o.electricity_cost for o in internal_orders), Decimal(0)
    )
    total_print_hours_all = sum(
        (o.total_print_time_hours for o in all_orders), Decimal(0)
    )
    total_print_hours_commercial = sum(
        (o.total_print_time_hours for o in commercial_orders), Decimal(0)
    )
    total_print_hours_internal = sum(
        (o.total_print_time_hours for o in internal_orders), Decimal(0)
    )

    # Total filament purchased (all purchases, not just used)
    all_purchases = FilamentPurchase.query.all()
    total_filament_purchased_spend = sum(
        (
            (Decimal(str(p.quantity_g)) / Decimal(1000)) * Decimal(str(p.price_per_kg))
            for p in all_purchases
        ),
        Decimal(0),
    )

    # Current stock value
    filaments = Filament.query.order_by(Filament.name).all()
    total_stock_value = sum((f.stock_value for f in filaments), Decimal(0))
    total_stock_kg = sum((f.stock_kg for f in filaments), Decimal(0))

    # --- Monthly breakdown (last 12 months, commercial delivered only) ---
    monthly = defaultdict(lambda: {"revenue": Decimal(0), "cost": Decimal(0), "orders": 0})
    for o in delivered_commercial:
        key = o.delivered_at.strftime("%Y-%m")
        monthly[key]["revenue"] += o.sell_price
        monthly[key]["cost"] += o.total_cost
        monthly[key]["orders"] += 1

    # Build sorted list of months (all months present in data, at most last 24)
    all_keys = sorted(monthly.keys())[-24:]
    monthly_rows = []
    for key in all_keys:
        year, month = map(int, key.split("-"))
        label = f"{calendar.month_abbr[month]}/{year}"
        rev = monthly[key]["revenue"]
        cost = monthly[key]["cost"]
        profit = rev - cost
        monthly_rows.append(
            {
                "key": key,
                "label": label,
                "revenue": rev,
                "cost": cost,
                "profit": profit,
                "orders": monthly[key]["orders"],
            }
        )

    # --- Top filaments by cost (commercial delivered) ---
    filament_spend: dict = defaultdict(lambda: {"name": "", "material": "", "color": "", "weight_g": Decimal(0), "cost": Decimal(0)})
    for o in delivered_commercial:
        for plate in o.plates:
            for it in plate.items:
                fid = it.filament_id
                if it.filament:
                    filament_spend[fid]["name"] = it.filament.name
                    filament_spend[fid]["material"] = it.filament.material
                    filament_spend[fid]["color"] = it.filament.color
                else:
                    filament_spend[fid]["name"] = "(removido)"
                filament_spend[fid]["weight_g"] += Decimal(str(it.weight_g))
                filament_spend[fid]["cost"] += it.cost

    top_filaments = sorted(filament_spend.values(), key=lambda x: x["cost"], reverse=True)[:10]

    # --- Order counts ---
    counts = {
        "total": len(all_orders),
        "commercial": len(commercial_orders),
        "internal": len(internal_orders),
        "pending": sum(1 for o in all_orders if o.status == "pending"),
        "printed": sum(1 for o in all_orders if o.status == "printed"),
        "delivered": sum(1 for o in all_orders if o.status == "delivered"),
    }

    # Chart data — floats only, safe for tojson
    chart_monthly = {
        "labels": [r["label"] for r in monthly_rows],
        "revenue": [float(r["revenue"]) for r in monthly_rows],
        "cost": [float(r["cost"]) for r in monthly_rows],
        "profit": [float(r["profit"]) for r in monthly_rows],
    }
    stock_filaments_sorted = sorted(
        [f for f in filaments if f.stock_g > 0],
        key=lambda f: f.stock_value,
    )
    chart_stock = {
        "labels": [f"{f.name} {f.material} {f.color}" for f in stock_filaments_sorted],
        "amounts": [float(f.stock_value) for f in stock_filaments_sorted],
    }

    return render_template(
        "stats.html",
        # totals — commercial
        total_revenue=total_revenue,
        total_filament_spend_commercial=total_filament_spend_commercial,
        total_electricity_commercial=total_electricity_commercial,
        total_cost_commercial=total_cost_commercial,
        total_profit=total_profit,
        # totals — internal
        total_filament_spend_internal=total_filament_spend_internal,
        total_electricity_internal=total_electricity_internal,
        # time
        total_print_hours_all=total_print_hours_all,
        total_print_hours_commercial=total_print_hours_commercial,
        total_print_hours_internal=total_print_hours_internal,
        # stock / purchases
        total_filament_purchased_spend=total_filament_purchased_spend,
        total_stock_value=total_stock_value,
        total_stock_kg=total_stock_kg,
        filaments=filaments,
        # monthly
        monthly_rows=monthly_rows,
        # top filaments
        top_filaments=top_filaments,
        # counts
        counts=counts,
        # chart data
        chart_monthly=chart_monthly,
        chart_stock=chart_stock,
    )
