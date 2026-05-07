from datetime import datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import base64
import json
import os
import re
import tempfile
import uuid
import xml.etree.ElementTree as ET
import zipfile
import requests as http_requests
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, abort, jsonify, send_from_directory, current_app,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from .models import (
    db,
    Setting,
    Filament,
    FilamentPurchase,
    PrintOrder,
    OrderLink,
    PrintPlate,
    PlateFilament,
    OrderFile,
)


def _retail_material_avg_prices(user_id):
    """Stock-weighted average price/kg per material across the user's stock.

    Returns ``{material: Decimal(price_per_kg)}``. Used by retail orders so
    the same product invoiced to a business has a stable cost regardless of
    which specific spool happened to be loaded — avoids charging the same
    deck box at different prices just because one filament is cheaper.

    Falls back per-material to whichever filaments have stock_g > 0.
    """
    from sqlalchemy import func
    rows = (
        db.session.query(
            Filament.material,
            func.sum(Filament.stock_g * Filament.avg_price_per_kg).label("value"),
            func.sum(Filament.stock_g).label("weight"),
        )
        .filter(Filament.user_id == user_id, Filament.stock_g > 0)
        .group_by(Filament.material)
        .all()
    )
    avg = {}
    for material, value, weight in rows:
        if weight is not None and Decimal(str(weight)) > 0:
            avg[material] = Decimal(str(value)) / Decimal(str(weight))
    return avg


def _snapshot_price_factory(has_vat, user_id):
    """Return a function(filament) -> Decimal price_per_kg to snapshot.

    For retail orders (has_vat=True), snapshots the material-weighted
    average. For everything else, the filament's own avg_price_per_kg —
    same as before this feature."""
    if not has_vat:
        return lambda f: Decimal(str(f.avg_price_per_kg or 0))
    avg = _retail_material_avg_prices(user_id)
    def _price(f):
        material_avg = avg.get(f.material)
        if material_avg is not None:
            return material_avg
        return Decimal(str(f.avg_price_per_kg or 0))
    return _price


def _user_filament_or_404(fid):
    f = Filament.query.filter_by(id=fid, user_id=current_user.id).first()
    if f is None:
        abort(404)
    return f


def _user_order_or_404(oid):
    o = PrintOrder.query.filter_by(id=oid, user_id=current_user.id).first()
    if o is None:
        abort(404)
    return o


def _user_plate_or_404(pid):
    plate = (
        db.session.query(PrintPlate)
        .join(PrintOrder, PrintPlate.order_id == PrintOrder.id)
        .filter(PrintPlate.id == pid, PrintOrder.user_id == current_user.id)
        .first()
    )
    if plate is None:
        abort(404)
    return plate


def _user_file_or_404(fid):
    f = (
        db.session.query(OrderFile)
        .join(PrintOrder, OrderFile.order_id == PrintOrder.id)
        .filter(OrderFile.id == fid, PrintOrder.user_id == current_user.id)
        .first()
    )
    if f is None:
        abort(404)
    return f


def _sync_order_printed(order):
    """Set or clear order.printed_at based on per-plate printed state."""
    active = [p for p in order.plates if not p.is_skipped]
    if active and all(p.printed_at for p in active):
        if not order.printed_at:
            order.printed_at = datetime.utcnow()
    else:
        order.printed_at = None

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


_ALLOWED_UPLOAD_EXTS = {"stl", "3mf", "obj", "png", "jpg", "jpeg", "gif", "webp"}


def _norm_color(hex_str):
    """Normalise Bambu #RRGGBBAA → #RRGGBB (strips alpha channel if present)."""
    h = (hex_str or "").strip()
    if h.startswith("#") and len(h) == 9:
        return h[:7]
    return h if h else "#888888"


def _match_filament_db(fil_type, fil_color_hex, filaments):
    """Best-effort match a 3MF filament type+color to a DB Filament row."""
    # Strip common brand prefixes ("Bambu PLA Basic" → "PLA Basic")
    t = fil_type.strip()
    for prefix in ("Bambu ", "Prusa ", "Generic ", "eSUN ", "Polymaker "):
        if t.startswith(prefix):
            t = t[len(prefix):]
            break
    t_low = t.lower()

    candidates = [f for f in filaments if f.material.lower() == t_low]
    if not candidates:
        candidates = [f for f in filaments
                      if t_low in f.material.lower() or f.material.lower() in t_low]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    # Prefer closest colour
    def _hex_dist(f):
        if not f.color_hex or not fil_color_hex:
            return 999999
        try:
            h1 = fil_color_hex.lstrip("#")
            h2 = f.color_hex.lstrip("#")
            r1, g1, b1 = int(h1[0:2], 16), int(h1[2:4], 16), int(h1[4:6], 16)
            r2, g2, b2 = int(h2[0:2], 16), int(h2[2:4], 16), int(h2[4:6], 16)
            return (r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2
        except Exception:
            return 999999

    return min(candidates, key=_hex_dist)


def _local(tag):
    """Strip XML namespace prefix, e.g. '{http://...}plate' → 'plate'."""
    return tag.split("}", 1)[1] if "}" in tag else tag


def _xml_iter(el, local_name):
    """Iterate all descendants of el whose local tag name matches local_name."""
    return [c for c in el.iter() if _local(c.tag) == local_name]


def _3mf_to_stl_bytes(zip_path, plate_n=None):
    """
    Extract mesh geometry from a .3mf ZIP and return binary STL bytes.
    If plate_n is given, only include objects assigned to that plate
    (resolved via Metadata/plate_N.json + Metadata/model_settings.config).
    Returns None if no geometry found.
    """
    import struct

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        names_ci = {n.lower(): n for n in names}

        def _read(path):
            path = path.lstrip("/")
            if path in names:
                return zf.read(path)
            key = names_ci.get(path.lower())
            return zf.read(key) if key else None

        def _parse_objects(xml_root):
            """Return {id: (verts, tris)} for all <object> elements with a <mesh>."""
            result = {}
            for obj in _xml_iter(xml_root, "object"):
                oid = obj.get("id")
                mesh_els = _xml_iter(obj, "mesh")
                if not mesh_els:
                    continue
                mesh = mesh_els[0]
                verts = [
                    (float(v.get("x", 0)), float(v.get("y", 0)), float(v.get("z", 0)))
                    for v in _xml_iter(mesh, "vertex")
                ]
                tris = [
                    (int(t.get("v1", 0)), int(t.get("v2", 0)), int(t.get("v3", 0)))
                    for t in _xml_iter(mesh, "triangle")
                ]
                result[oid] = (verts, tris)
            return result

        # Locate the main model file via package relationships
        model_path = "3D/3dmodel.model"
        rels_raw = _read("_rels/.rels")
        if rels_raw:
            try:
                for rel in _xml_iter(ET.fromstring(rels_raw), "Relationship"):
                    if "3dmodel" in (rel.get("Type") or "").lower():
                        t = rel.get("Target", "").lstrip("/")
                        if t:
                            model_path = t
                            break
            except ET.ParseError:
                pass

        model_raw = _read(model_path)
        if not model_raw:
            return None

        root = ET.fromstring(model_raw)

        # Collect mesh objects from the main model
        all_objects = _parse_objects(root)

        # Also load sub-model files referenced in the model's own .rels file.
        # Bambu stores each part's geometry in 3D/Objects/object_N.model.
        model_dir = model_path.rsplit("/", 1)[0] if "/" in model_path else ""
        model_fn  = model_path.rsplit("/", 1)[1] if "/" in model_path else model_path
        sub_rels_raw = _read(f"{model_dir}/_rels/{model_fn}.rels")
        if sub_rels_raw:
            try:
                for rel in _xml_iter(ET.fromstring(sub_rels_raw), "Relationship"):
                    sp = rel.get("Target", "").lstrip("/")
                    if not sp.lower().endswith(".model"):
                        continue
                    sub_raw = _read(sp)
                    if sub_raw:
                        try:
                            all_objects.update(_parse_objects(ET.fromstring(sub_raw)))
                        except ET.ParseError:
                            pass
            except ET.ParseError:
                pass

        # Parse assembly objects: main-model objects that reference mesh objects
        # via <components><component objectid="N"/></components>
        assembly = {}
        for obj in _xml_iter(root, "object"):
            comps = _xml_iter(obj, "component")
            if comps:
                assembly[obj.get("id")] = [
                    {"objectid": c.get("objectid"), "transform": c.get("transform")}
                    for c in comps
                ]

        # Per-plate filtering: resolve object IDs from plate_N.json + model_settings.config
        filter_oids = None
        if plate_n is not None:
            plate_raw = _read(f"Metadata/plate_{plate_n}.json")
            if plate_raw:
                try:
                    plate_data = json.loads(plate_raw)
                    plate_names = {
                        obj["name"] for obj in plate_data.get("bbox_objects", [])
                        if obj.get("name")
                    }
                    settings_raw = _read("Metadata/model_settings.config")
                    if settings_raw and plate_names:
                        try:
                            s_root = ET.fromstring(settings_raw)
                            filter_oids = set()
                            for obj_el in _xml_iter(s_root, "object"):
                                obj_id = obj_el.get("id")
                                for meta in _xml_iter(obj_el, "metadata"):
                                    if meta.get("key") == "name" and meta.get("value") in plate_names:
                                        filter_oids.add(obj_id)
                                        break
                        except ET.ParseError:
                            pass
                except (json.JSONDecodeError, KeyError):
                    pass

        def _apply_transform(verts, transform_str):
            if not transform_str:
                return verts
            try:
                m = [float(x) for x in transform_str.split()]
                if len(m) != 12:
                    return verts
                return [
                    (m[0]*x + m[3]*y + m[6]*z + m[9],
                     m[1]*x + m[4]*y + m[7]*z + m[10],
                     m[2]*x + m[5]*y + m[8]*z + m[11])
                    for x, y, z in verts
                ]
            except (ValueError, IndexError):
                return verts

        def _compose_transforms(outer_str, inner_str):
            """Compose two 3MF 3x4 column-major transforms: apply inner first, then outer."""
            if not inner_str:
                return outer_str
            if not outer_str:
                return inner_str
            try:
                o = [float(x) for x in outer_str.split()]
                i = [float(x) for x in inner_str.split()]
                if len(o) != 12 or len(i) != 12:
                    return outer_str
                r = [0.0] * 12
                for col in range(3):
                    for row in range(3):
                        for k in range(3):
                            r[col*3 + row] += o[k*3 + row] * i[col*3 + k]
                for row in range(3):
                    r[9 + row] = sum(o[k*3 + row] * i[9 + k] for k in range(3)) + o[9 + row]
                return " ".join(str(x) for x in r)
            except (ValueError, IndexError):
                return outer_str

        all_tris = []

        def _collect(oid, transform_str=None):
            if oid in all_objects:
                verts, tris = all_objects[oid]
                if transform_str:
                    verts = _apply_transform(verts, transform_str)
                for v1, v2, v3 in tris:
                    if v1 < len(verts) and v2 < len(verts) and v3 < len(verts):
                        all_tris.append((verts[v1], verts[v2], verts[v3]))
            elif oid in assembly:
                for comp in assembly[oid]:
                    # Compose outer (build item) and inner (component) transforms so
                    # objects land at their correct world-space positions.
                    _collect(comp["objectid"], _compose_transforms(transform_str, comp.get("transform")))

        build_items = _xml_iter(root, "item")
        if build_items:
            for item in build_items:
                oid = item.get("objectid")
                if filter_oids is not None and oid not in filter_oids:
                    continue
                _collect(oid, item.get("transform"))
        else:
            for oid in list(all_objects):
                if filter_oids is not None and oid not in filter_oids:
                    continue
                _collect(oid)

        if not all_tris:
            return None

        # Encode as binary STL
        buf = bytearray(b"\x00" * 80)
        buf += struct.pack("<I", len(all_tris))
        for (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) in all_tris:
            ax, ay, az = x2 - x1, y2 - y1, z2 - z1
            bx, by, bz = x3 - x1, y3 - y1, z3 - z1
            nx, ny, nz = ay*bz - az*by, az*bx - ax*bz, ax*by - ay*bx
            buf += struct.pack("<fff", nx, ny, nz)
            buf += struct.pack("<fff", x1, y1, z1)
            buf += struct.pack("<fff", x2, y2, z2)
            buf += struct.pack("<fff", x3, y3, z3)
            buf += struct.pack("<H", 0)
        return bytes(buf)


def _parse_bambu_3mf(zip_path, filaments_db=None):
    """
    Parse a Bambu .3mf ZIP.
    Returns dict:
      plates: [{index, print_time_hours, filaments:[{type,color,used_g,matched}], thumb_b64}]
      thumb_b64: overall thumbnail as data-URI or None
      warning: str or None
    """
    result = {"plates": [], "thumb_b64": None, "warning": None}

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Case-insensitive lookup of ZIP entries
            names_ci = {n.lower(): n for n in zf.namelist()}
            names    = set(zf.namelist())

            def _read(path):
                """Read a ZIP entry; tries exact path then case-insensitive."""
                if path in names:
                    return zf.read(path)
                key = names_ci.get(path.lower())
                return zf.read(key) if key else None

            # Overall thumbnail — try both old (Metadata/) and new (Auxiliaries/) Bambu paths
            for t in (
                "Metadata/thumbnail.png",
                "Metadata/thumbnail_small.png",
                "Auxiliaries/.thumbnails/thumbnail_3mf.png",
                "Auxiliaries/.thumbnails/thumbnail_middle.png",
            ):
                raw = _read(t)
                if raw:
                    result["thumb_b64"] = "data:image/png;base64," + base64.b64encode(raw).decode()
                    break

            slice_raw = _read("Metadata/slice_info.config")
            if slice_raw is None:
                result["warning"] = (
                    "No Bambu slice data found. "
                    "Slice the model in Bambu Studio / OrcaSlicer first."
                )
                return result

            root = ET.fromstring(slice_raw)

            # Use namespace-agnostic, depth-agnostic search so the parser works
            # regardless of XML namespace declarations or nesting differences
            # across Bambu Studio / OrcaSlicer versions.
            for plate_el in _xml_iter(root, "plate"):
                meta = {m.get("key"): m.get("value")
                        for m in _xml_iter(plate_el, "metadata")}

                idx    = int(meta.get("index", 1))
                pred_s = int(float(meta.get("prediction", 0) or 0))
                print_h = round(pred_s / 3600.0, 4)

                # Per-plate thumbnail (try both zero-padded and plain index)
                thumb_b64 = None
                for pname in (f"Metadata/plate_{idx}.png",
                              f"Metadata/plate_{idx:02d}.png"):
                    raw = _read(pname)
                    if raw:
                        thumb_b64 = "data:image/png;base64," + base64.b64encode(raw).decode()
                        break
                # Fallback to project thumbnail
                if thumb_b64 is None:
                    thumb_b64 = result["thumb_b64"]

                fils = []
                for fel in _xml_iter(plate_el, "filament"):
                    ftype  = (fel.get("type") or "").strip()
                    fcolor = _norm_color(fel.get("color") or "")
                    try:
                        used_g = round(float(fel.get("used_g") or 0), 2)
                    except (TypeError, ValueError):
                        used_g = 0.0

                    matched = None
                    if filaments_db:
                        m = _match_filament_db(ftype, fcolor, filaments_db)
                        if m:
                            matched = {
                                "id": m.id,
                                "brand": m.name,
                                "material": m.material,
                                "color": m.color,
                                "color_hex": m.color_hex or "",
                            }

                    fils.append({
                        "type": ftype,
                        "color": fcolor,
                        "used_g": used_g,
                        "matched": matched,
                    })

                result["plates"].append({
                    "index": idx,
                    "print_time_hours": print_h,
                    "filaments": fils,
                    "thumb_b64": thumb_b64,
                })

            if not result["plates"]:
                # ── Bambu Studio v02.06+ new format ──────────────────────────
                # slice_info.config now only holds a version header.
                # Plate list comes from plate_N.json files.
                # Filament types: filament_settings_N.config (JSON, "inherits" key).
                # Filament colors: project_settings.config → filament_colour[N-1].
                # Print time and per-plate weights are NOT stored in project files
                # (only in the generated G-code); they must be filled in manually.

                plate_json_names = sorted(
                    [n for n in names
                     if re.match(r"(?i)metadata/plate_(\d+)\.json$", n)],
                    key=lambda n: int(re.search(r"(\d+)", n).group(1))
                )

                if plate_json_names:
                    # Per-slot colors and basic types from project_settings.config
                    fil_colors = []
                    fil_types_basic = []
                    proj_raw = _read("Metadata/project_settings.config")
                    if proj_raw:
                        try:
                            proj = json.loads(proj_raw)
                            raw_colors = proj.get("filament_colour") or []
                            if isinstance(raw_colors, str):
                                raw_colors = [raw_colors]
                            fil_colors = [_norm_color(c) for c in raw_colors]
                            raw_types = proj.get("filament_type") or []
                            if isinstance(raw_types, str):
                                raw_types = [raw_types]
                            fil_types_basic = raw_types
                        except Exception:
                            pass

                    # Which extruder slots are actually assigned to objects?
                    # model_settings.config has <metadata key="extruder" value="N"/>
                    # per object. Collect the unique set so we skip idle AMS slots.
                    used_slots = set()
                    model_raw = _read("Metadata/model_settings.config")
                    if model_raw:
                        try:
                            mroot = ET.fromstring(model_raw)
                            for meta in _xml_iter(mroot, "metadata"):
                                if meta.get("key") == "extruder":
                                    try:
                                        used_slots.add(int(meta.get("value", 0)))
                                    except (ValueError, TypeError):
                                        pass
                        except ET.ParseError:
                            pass
                    # Fall back to all configured slots if we couldn't determine
                    if not used_slots:
                        used_slots = set(range(1, len(fil_colors) + 1))

                    for pjson_name in plate_json_names:
                        m = re.search(r"(\d+)\.json$", pjson_name, re.IGNORECASE)
                        if not m:
                            continue
                        idx = int(m.group(1))

                        thumb_b64 = None
                        for pname in (f"Metadata/plate_{idx}.png",
                                      f"Metadata/plate_{idx:02d}.png"):
                            raw = _read(pname)
                            if raw:
                                thumb_b64 = "data:image/png;base64," + base64.b64encode(raw).decode()
                                break
                        # Fallback to project thumbnail
                        if thumb_b64 is None:
                            thumb_b64 = result["thumb_b64"]

                        fils = []
                        for slot in sorted(used_slots):
                            i0 = slot - 1  # 0-based index into colour/type arrays
                            color_hex = fil_colors[i0] if i0 < len(fil_colors) else ""
                            fil_type  = fil_types_basic[i0] if i0 < len(fil_types_basic) else "PLA"
                            matched = None
                            if filaments_db:
                                mf = _match_filament_db(fil_type, color_hex or None, filaments_db)
                                if mf:
                                    matched = {
                                        "id": mf.id,
                                        "brand": mf.name,
                                        "material": mf.material,
                                        "color": mf.color,
                                        "color_hex": mf.color_hex or "",
                                    }
                            fils.append({
                                "type": fil_type,
                                "color": color_hex,
                                "used_g": 0.0,
                                "matched": matched,
                            })

                        result["plates"].append({
                            "index": idx,
                            "print_time_hours": 0.0,
                            "filaments": fils,
                            "thumb_b64": thumb_b64,
                        })

                    if result["plates"]:
                        result["warning"] = (
                            "Bambu Studio v02.06+ format: print time and filament "
                            "weights are not stored in project files — "
                            "please fill them in manually."
                        )

                if not result["plates"]:
                    result["warning"] = (
                        "This .3mf was saved before slicing — no plate data found. "
                        "In Bambu Studio: click ‘Slice plate’, "
                        "then File → Save Project, and import again."
                    )

    except zipfile.BadZipFile:
        result["warning"] = "Invalid .3mf file (not a valid ZIP archive)."
    except ET.ParseError as exc:
        result["warning"] = f"Could not parse slice_info.config: {exc}"

    return result


@bp.route("/")
@login_required
def dashboard():
    filaments = Filament.query.filter_by(user_id=current_user.id).order_by(Filament.name).all()
    recent = (
        PrintOrder.query.filter_by(user_id=current_user.id)
        .order_by(PrintOrder.created_at.desc()).limit(5).all()
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
@login_required
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
        currency = request.form.get("currency_symbol", "€").strip() or "€"
        Setting.set("currency_symbol", currency)
        Setting.set(
            "retail_mode_enabled",
            "true" if request.form.get("retail_mode_enabled") == "1" else "false",
        )
        Setting.set(
            "default_vat_rate_pct",
            _dec(request.form.get("default_vat_rate_pct"), default=Decimal("23")),
        )
        db.session.commit()
        flash("Settings saved.", "success")
        return redirect(url_for("main.settings"))

    return render_template(
        "settings.html",
        electricity_price_per_kwh=Setting.get("electricity_price_per_kwh"),
        printer_power_watts=Setting.get("printer_power_watts"),
        default_profit_pct=Setting.get("default_profit_pct"),
        currency_symbol=Setting.get("currency_symbol", cast=str) or "€",
        retail_mode_enabled=Setting.get_bool("retail_mode_enabled"),
        default_vat_rate_pct=Setting.get("default_vat_rate_pct") or Decimal("23"),
    )


# ---------- Filaments ----------

@bp.route("/filaments")
@login_required
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

    q = Filament.query.filter_by(user_id=current_user.id)
    if material_filter != "all":
        q = q.filter_by(material=material_filter)
    if brand_filter != "all":
        q = q.filter_by(name=brand_filter)

    filaments = q.order_by(sort_col).all()
    materials = [
        r[0] for r in db.session.query(Filament.material)
        .filter(Filament.user_id == current_user.id)
        .distinct().order_by(Filament.material).all()
    ]
    brands = [
        r[0] for r in db.session.query(Filament.name)
        .filter(Filament.user_id == current_user.id)
        .distinct().order_by(Filament.name).all()
    ]

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
@login_required
def filament_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        material = request.form.get("material", "PLA").strip()
        color = request.form.get("color", "").strip()
        color_hex = request.form.get("color_hex", "").strip() or None
        stock_g = _dec(request.form.get("stock_g"))
        price_per_kg = _dec(request.form.get("price_per_kg"))

        if not name:
            flash("Name is required.", "danger")
            return redirect(url_for("main.filament_new"))

        existing = Filament.query.filter_by(
            user_id=current_user.id, name=name, material=material, color=color,
        ).first()
        if existing:
            flash(
                f"Filament '{name} · {material} · {color}' already exists. "
                f"Use the Buy button to add more stock.",
                "warning",
            )
            return redirect(url_for("main.filaments_list"))

        f = Filament(
            user_id=current_user.id,
            name=name, material=material, color=color, color_hex=color_hex,
        )
        db.session.add(f)
        db.session.flush()
        if stock_g > 0 and price_per_kg > 0:
            f.add_purchase(stock_g, price_per_kg)
        db.session.commit()
        flash("Filament created.", "success")
        return redirect(url_for("main.filaments_list"))

    brands = [
        r[0] for r in db.session.query(Filament.name)
        .filter(Filament.user_id == current_user.id)
        .distinct().order_by(Filament.name).all()
    ]
    materials = [
        r[0] for r in db.session.query(Filament.material)
        .filter(Filament.user_id == current_user.id)
        .distinct().order_by(Filament.material).all()
    ]
    return render_template("filament_form.html", brands=brands, materials=materials)


@bp.route("/filaments/<int:fid>/purchase", methods=["GET", "POST"])
@login_required
def filament_purchase(fid):
    f = _user_filament_or_404(fid)
    if request.method == "POST":
        quantity_g = _dec(request.form.get("quantity_g"))
        price_per_kg = _dec(request.form.get("price_per_kg"))
        if quantity_g <= 0 or price_per_kg <= 0:
            flash("Quantity and price must be positive.", "danger")
            return redirect(url_for("main.filament_purchase", fid=f.id))
        f.add_purchase(quantity_g, price_per_kg)
        db.session.commit()
        flash(
            f"Added {quantity_g} g. New weighted average: "
            f"{f.avg_price_per_kg:.2f}/kg.",
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
@login_required
def filament_adjust(fid):
    f = _user_filament_or_404(fid)
    new_stock = _dec(request.form.get("stock_g"), default=None)
    if new_stock is None or new_stock < 0:
        flash("Invalid stock value.", "danger")
        return redirect(url_for("main.filament_purchase", fid=f.id))
    f.stock_g = new_stock
    db.session.commit()
    flash(f"Stock for {f.name} adjusted to {new_stock} g.", "success")
    return redirect(url_for("main.filaments_list"))


@bp.route("/filaments/<int:fid>/delete", methods=["POST"])
@login_required
def filament_delete(fid):
    f = _user_filament_or_404(fid)
    db.session.delete(f)
    db.session.commit()
    flash("Filament deleted.", "success")
    return redirect(url_for("main.filaments_list"))


# ---------- Orders ----------

@bp.route("/orders")
@login_required
def orders_list():
    status_filter = request.args.get("status", "all")
    type_filter = request.args.get("type", "all")
    q = PrintOrder.query.filter_by(user_id=current_user.id)
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
@login_required
def order_new():
    filaments = Filament.query.filter_by(user_id=current_user.id).order_by(Filament.name).all()

    if request.method == "POST":
        retail_on = Setting.get_bool("retail_mode_enabled")
        name = request.form.get("name", "").strip()
        customer = request.form.get("customer", "").strip() or None
        notes = request.form.get("notes", "").strip() or None
        raw_urls = [u.strip() for u in request.form.getlist("model_url") if u.strip()]
        model_url = "\n".join(raw_urls) or None
        is_internal = request.form.get("is_internal") == "1"
        profit_pct = _dec(
            request.form.get("profit_pct"),
            default=Setting.get("default_profit_pct") or Decimal(30),
        )

        try:
            quantity = max(1, int(request.form.get("quantity", 1) or 1))
        except (ValueError, TypeError):
            quantity = 1

        # VAT only applicable in retail mode AND for non-personal orders
        has_vat = retail_on and not is_internal and request.form.get("has_vat") == "1"
        vat_rate_pct = None
        if has_vat:
            vat_rate_pct = _dec(
                request.form.get("vat_rate_pct"),
                default=Setting.get("default_vat_rate_pct") or Decimal("23"),
            )

        try:
            num_plates = int(request.form.get("num_plates", 0))
        except (ValueError, TypeError):
            num_plates = 0

        if not name:
            flash("Name is required.", "danger")
            return redirect(url_for("main.order_new"))

        if num_plates < 1:
            flash("Add at least one plate.", "danger")
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
                flash(f"Plate {i + 1}: print time must be positive.", "danger")
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
                flash(f"Plate {i + 1}: add at least one filament with weight > 0.", "danger")
                return redirect(url_for("main.order_new"))

            plates_data.append((pt, plate_items))

        if not plates_data:
            flash("Add at least one plate.", "danger")
            return redirect(url_for("main.order_new"))

        skip_stock_check = request.form.get("skip_stock_check") == "1"

        # Aggregate stock usage per filament across all plates × quantity
        qty_dec = Decimal(quantity)
        filament_usage: dict = {}
        for _pt, plate_items in plates_data:
            for fid, w in plate_items:
                filament_usage[fid] = filament_usage.get(fid, Decimal(0)) + w * qty_dec

        # Resolve filaments and collect stock warnings (warn-but-allow policy)
        filament_objs: dict = {}
        stock_warnings: list = []
        for fid, total_w in filament_usage.items():
            f = Filament.query.filter_by(id=fid, user_id=current_user.id).first()
            if f is None:
                flash("Invalid filament.", "danger")
                return redirect(url_for("main.order_new"))
            if not skip_stock_check and Decimal(str(f.stock_g or 0)) < total_w:
                short = total_w - Decimal(str(f.stock_g or 0))
                stock_warnings.append(
                    f"{f.name} {f.material} {f.color}: requested {total_w} g, "
                    f"in stock {f.stock_g} g (short by {short} g)"
                )
            filament_objs[fid] = f

        # Create order
        order = PrintOrder(
            user_id=current_user.id,
            name=name,
            customer=customer,
            notes=notes,
            model_url=raw_urls[0] if raw_urls else None,
            profit_pct=profit_pct,
            is_internal=is_internal,
            skip_stock_deduction=skip_stock_check,
            quantity=quantity,
            has_vat=has_vat,
            vat_rate_pct=vat_rate_pct,
            electricity_price_per_kwh=Setting.get("electricity_price_per_kwh"),
            printer_power_watts=Setting.get("printer_power_watts"),
        )
        db.session.add(order)
        db.session.flush()

        for pos, url in enumerate(raw_urls):
            title, image = _fetch_og(url)
            db.session.add(OrderLink(
                order_id=order.id, position=pos, url=url, title=title, image=image
            ))

        snapshot_price = _snapshot_price_factory(has_vat, current_user.id)
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
                        price_per_kg_snapshot=snapshot_price(f),
                    )
                )

        # Deduct stock only if not in quote mode
        if not skip_stock_check:
            for fid, total_w in filament_usage.items():
                filament_objs[fid].stock_g = Decimal(str(filament_objs[fid].stock_g or 0)) - total_w

        db.session.commit()
        if skip_stock_check:
            flash("Order created as quote — no stock deducted.", "success")
        else:
            flash("Order created and stock updated.", "success")
        if stock_warnings and not skip_stock_check:
            flash(
                "Stock went negative for: " + "; ".join(stock_warnings)
                + ". Adjust inventory after the next purchase.",
                "warning",
            )
        return redirect(url_for("main.order_detail", oid=order.id))

    filaments_data = [
        {
            "id": f.id,
            "brand": f.name,
            "material": f.material,
            "color": f.color,
            "color_hex": f.color_hex or "",
            "stock_g": float(f.stock_g),
            "avg_price": float(f.avg_price_per_kg),
        }
        for f in filaments
    ]
    return render_template(
        "order_form.html",
        filaments=filaments,
        filaments_data=filaments_data,
        default_profit_pct=Setting.get("default_profit_pct"),
        default_vat_rate_pct=Setting.get("default_vat_rate_pct") or Decimal("23"),
    )


@bp.route("/orders/<int:oid>")
@login_required
def order_detail(oid):
    order = _user_order_or_404(oid)
    return render_template("order_detail.html", order=order)


@bp.route("/quote/<int:oid>")
@login_required
def order_quote(oid):
    order = _user_order_or_404(oid)
    return render_template("quote.html", order=order)


@bp.route("/quote/combined")
@login_required
def order_quote_combined():
    raw_ids = request.args.get("ids", "")
    try:
        ids = [int(x) for x in raw_ids.split(",") if x.strip()]
    except ValueError:
        ids = []
    if not ids:
        flash("Select at least one order to combine.", "warning")
        return redirect(url_for("main.orders_list"))

    orders = (
        PrintOrder.query
        .filter(PrintOrder.user_id == current_user.id, PrintOrder.id.in_(ids))
        .order_by(PrintOrder.created_at.asc())
        .all()
    )
    if not orders:
        abort(404)

    # Aggregate totals
    subtotal = sum((o.sell_price for o in orders if not o.is_internal), Decimal(0))
    vat_total = sum((o.vat_amount for o in orders if not o.is_internal), Decimal(0))
    total = subtotal + vat_total
    has_any_vat = any(o.has_vat and not o.is_internal for o in orders)
    vat_rates = sorted({Decimal(str(o.vat_rate_pct)) for o in orders
                        if o.has_vat and not o.is_internal and o.vat_rate_pct is not None})

    return render_template(
        "quote_combined.html",
        orders=orders,
        subtotal=subtotal,
        vat_total=vat_total,
        total=total,
        has_any_vat=has_any_vat,
        vat_rates=vat_rates,
    )


@bp.route("/orders/<int:oid>/edit", methods=["GET", "POST"])
@login_required
def order_edit(oid):
    order = _user_order_or_404(oid)
    filaments = Filament.query.filter_by(user_id=current_user.id).order_by(Filament.name).all()

    if request.method == "POST":
        retail_on = Setting.get_bool("retail_mode_enabled")
        name = request.form.get("name", "").strip()
        customer = request.form.get("customer", "").strip() or None
        notes = request.form.get("notes", "").strip() or None
        raw_urls = [u.strip() for u in request.form.getlist("model_url") if u.strip()]
        is_internal = request.form.get("is_internal") == "1"
        skip_stock_check = request.form.get("skip_stock_check") == "1"
        profit_pct = _dec(
            request.form.get("profit_pct"),
            default=Setting.get("default_profit_pct") or Decimal(30),
        )

        try:
            quantity = max(1, int(request.form.get("quantity", 1) or 1))
        except (ValueError, TypeError):
            quantity = 1

        has_vat = retail_on and not is_internal and request.form.get("has_vat") == "1"
        vat_rate_pct = None
        if has_vat:
            vat_rate_pct = _dec(
                request.form.get("vat_rate_pct"),
                default=Setting.get("default_vat_rate_pct") or Decimal("23"),
            )

        try:
            num_plates = int(request.form.get("num_plates", 0))
        except (ValueError, TypeError):
            num_plates = 0

        if not name:
            flash("Name is required.", "danger")
            return redirect(url_for("main.order_edit", oid=oid))

        if num_plates < 1:
            flash("Add at least one plate.", "danger")
            return redirect(url_for("main.order_edit", oid=oid))

        plates_data = []
        for i in range(num_plates):
            ph = _dec(request.form.get(f"plate_{i}_hours"))
            pm = _dec(request.form.get(f"plate_{i}_minutes"))
            pt = ph + pm / Decimal(60)
            fids = request.form.getlist(f"plate_{i}_filament_ids")
            weights = request.form.getlist(f"plate_{i}_weights")

            if pt <= 0:
                flash(f"Plate {i + 1}: print time must be positive.", "danger")
                return redirect(url_for("main.order_edit", oid=oid))

            plate_items = []
            for fid_s, w_s in zip(fids, weights):
                if not fid_s:
                    continue
                w = _dec(w_s)
                if w <= 0:
                    continue
                plate_items.append((int(fid_s), w))

            if not plate_items:
                flash(f"Plate {i + 1}: add at least one filament with weight > 0.", "danger")
                return redirect(url_for("main.order_edit", oid=oid))

            plates_data.append((pt, plate_items))

        if not plates_data:
            flash("Add at least one plate.", "danger")
            return redirect(url_for("main.order_edit", oid=oid))

        qty_dec = Decimal(quantity)
        filament_usage: dict = {}
        for _pt, plate_items in plates_data:
            for fid, w in plate_items:
                filament_usage[fid] = filament_usage.get(fid, Decimal(0)) + w * qty_dec

        # Compute how much the original order currently has deducted from stock.
        # Uses the OLD quantity (whatever it was when the previous deduction ran).
        # Skipped plates already had their stock restored on skip, so exclude them.
        old_qty = Decimal(int(order.quantity or 1))
        originally_deducted: dict = {}
        if not order.skip_stock_deduction:
            for plate in order.plates:
                if not plate.is_skipped:
                    for it in plate.items:
                        if it.filament is not None:
                            fid = it.filament_id
                            originally_deducted[fid] = (
                                originally_deducted.get(fid, Decimal(0)) + Decimal(str(it.weight_g)) * old_qty
                            )

        # Resolve filaments and collect stock warnings (warn-but-allow policy)
        filament_objs: dict = {}
        stock_warnings: list = []
        for fid, total_w in filament_usage.items():
            f = Filament.query.filter_by(id=fid, user_id=current_user.id).first()
            if f is None:
                flash("Invalid filament.", "danger")
                return redirect(url_for("main.order_edit", oid=oid))
            effective_stock = Decimal(str(f.stock_g or 0)) + originally_deducted.get(fid, Decimal(0))
            if not skip_stock_check and effective_stock < total_w:
                short = total_w - effective_stock
                stock_warnings.append(
                    f"{f.name} {f.material} {f.color}: requested {total_w} g, "
                    f"available {effective_stock} g (short by {short} g)"
                )
            filament_objs[fid] = f

        # All validation passed — apply changes atomically

        # Restore old stock
        for fid, deducted in originally_deducted.items():
            f = db.session.get(Filament, fid)
            if f is not None:
                f.stock_g = Decimal(str(f.stock_g or 0)) + deducted

        # Preserve OG data for unchanged URLs
        old_link_map = {link.url: link for link in order.links}

        # Remove old plates and links
        for link in list(order.links):
            db.session.delete(link)
        for plate in list(order.plates):
            db.session.delete(plate)
        db.session.flush()

        # Update order fields
        order.name = name
        order.customer = customer
        order.notes = notes
        order.model_url = raw_urls[0] if raw_urls else None
        order.profit_pct = profit_pct
        order.is_internal = is_internal
        order.skip_stock_deduction = skip_stock_check
        order.quantity = quantity
        order.has_vat = has_vat
        order.vat_rate_pct = vat_rate_pct
        order.electricity_price_per_kwh = Setting.get("electricity_price_per_kwh")
        order.printer_power_watts = Setting.get("printer_power_watts")

        # Add updated links (reuse OG data when URL unchanged)
        for pos, url in enumerate(raw_urls):
            if url in old_link_map:
                old = old_link_map[url]
                db.session.add(OrderLink(
                    order_id=order.id, position=pos, url=url,
                    title=old.title, image=old.image,
                ))
            else:
                title, image = _fetch_og(url)
                db.session.add(OrderLink(
                    order_id=order.id, position=pos, url=url,
                    title=title, image=image,
                ))

        # Add new plates and filaments
        snapshot_price = _snapshot_price_factory(has_vat, current_user.id)
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
                        price_per_kg_snapshot=snapshot_price(f),
                    )
                )

        # Deduct new stock (unless quote mode)
        if not skip_stock_check:
            for fid, total_w in filament_usage.items():
                filament_objs[fid].stock_g = Decimal(str(filament_objs[fid].stock_g or 0)) - total_w

        db.session.commit()
        flash("Order updated.", "success")
        if stock_warnings and not skip_stock_check:
            flash(
                "Stock went negative for: " + "; ".join(stock_warnings)
                + ". Adjust inventory after the next purchase.",
                "warning",
            )
        return redirect(url_for("main.order_detail", oid=order.id))

    # GET — prepare pre-population data for the edit form
    filaments_data = [
        {
            "id": f.id,
            "brand": f.name,
            "material": f.material,
            "color": f.color,
            "color_hex": f.color_hex or "",
            "stock_g": float(f.stock_g),
            "avg_price": float(f.avg_price_per_kg),
        }
        for f in filaments
    ]

    # Inflate stock display with what the order reserved (so the user sees full available)
    if not order.skip_stock_deduction:
        old_qty_f = float(order.quantity or 1)
        plate_usage: dict = {}
        for plate in order.plates:
            for it in plate.items:
                if it.filament_id:
                    plate_usage[it.filament_id] = plate_usage.get(it.filament_id, 0.0) + float(it.weight_g) * old_qty_f
        for fd in filaments_data:
            fd["stock_g"] += plate_usage.get(fd["id"], 0.0)

    edit_order_data = {
        "name": order.name,
        "customer": order.customer or "",
        "notes": order.notes or "",
        "profit_pct": float(order.profit_pct),
        "is_internal": order.is_internal,
        "skip_stock_deduction": order.skip_stock_deduction,
        "quantity": int(order.quantity or 1),
        "has_vat": bool(order.has_vat),
        "vat_rate_pct": float(order.vat_rate_pct) if order.vat_rate_pct is not None else None,
        "urls": [link.url for link in order.links] or ([order.model_url] if order.model_url else []),
        "plates": [
            {
                "print_time_hours": float(plate.print_time_hours),
                "filaments": [
                    {
                        "filament_id": it.filament_id,
                        "brand": it.filament.name if it.filament else "",
                        "material": it.filament.material if it.filament else "",
                        "color": it.filament.color if it.filament else "",
                        "weight_g": float(it.weight_g),
                    }
                    for it in plate.items
                    if it.filament
                ],
            }
            for plate in order.plates
        ],
    }

    return render_template(
        "order_form.html",
        filaments=filaments,
        filaments_data=filaments_data,
        default_profit_pct=order.profit_pct,
        default_vat_rate_pct=order.vat_rate_pct or Setting.get("default_vat_rate_pct") or Decimal("23"),
        edit_mode=True,
        order=order,
        edit_order_data=edit_order_data,
    )


@bp.route("/orders/<int:oid>/printed", methods=["POST"])
@login_required
def order_mark_printed(oid):
    order = _user_order_or_404(oid)
    marking = request.form.get("value") == "1"
    order.mark_printed(marking)
    now = datetime.utcnow() if marking else None
    for plate in order.plates:
        if not plate.is_skipped:
            plate.printed_at = now
    db.session.commit()
    return redirect(request.referrer or url_for("main.orders_list"))


@bp.route("/orders/<int:oid>/plates/<int:pid>/toggle-printed", methods=["POST"])
@login_required
def plate_toggle_printed(oid, pid):
    plate = _user_plate_or_404(pid)
    plate.printed_at = None if plate.printed_at else datetime.utcnow()
    _sync_order_printed(plate.order)
    db.session.commit()
    order = plate.order
    return jsonify({
        "plate_printed": plate.printed_at is not None,
        "order_status": order.status,
        "order_printed_at": order.printed_at.strftime("%Y-%m-%d %H:%M") if order.printed_at else None,
    })


@bp.route("/orders/<int:oid>/plates/<int:pid>/toggle-skipped", methods=["POST"])
@login_required
def plate_toggle_skipped(oid, pid):
    plate = _user_plate_or_404(pid)
    plate.is_skipped = not plate.is_skipped
    if plate.is_skipped:
        plate.printed_at = None

    # Restore stock when skipping, deduct again when unskipping (× quantity)
    if not plate.order.skip_stock_deduction:
        qty = Decimal(int(plate.order.quantity or 1))
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
    return jsonify({
        "plate_skipped": plate.is_skipped,
        "plate_printed": plate.printed_at is not None,
        "order_status": order.status,
        "order_printed_at": order.printed_at.strftime("%Y-%m-%d %H:%M") if order.printed_at else None,
    })


@bp.route("/orders/<int:oid>/delivered", methods=["POST"])
@login_required
def order_mark_delivered(oid):
    order = _user_order_or_404(oid)
    order.mark_delivered(request.form.get("value") == "1")
    db.session.commit()
    return redirect(request.referrer or url_for("main.orders_list"))


@bp.route("/orders/<int:oid>/delete", methods=["POST"])
@login_required
def order_delete(oid):
    order = _user_order_or_404(oid)
    if not order.skip_stock_deduction:
        qty = Decimal(int(order.quantity or 1))
        for plate in order.plates:
            if not plate.is_skipped:  # skipped plates were already restored on skip
                for it in plate.items:
                    if it.filament is not None:
                        it.filament.stock_g = (
                            Decimal(str(it.filament.stock_g or 0))
                            + Decimal(str(it.weight_g)) * qty
                        )
    db.session.delete(order)
    db.session.commit()
    msg = "Order deleted." if order.skip_stock_deduction else "Order deleted and stock restored."
    flash(msg, "success")
    return redirect(url_for("main.orders_list"))


# ---------- Files ----------

@bp.route("/orders/<int:oid>/files", methods=["POST"])
@login_required
def order_file_upload(oid):
    order = _user_order_or_404(oid)
    f = request.files.get("file")
    if not f or not f.filename:
        flash("No file selected.", "warning")
        return redirect(url_for("main.order_detail", oid=oid))

    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in _ALLOWED_UPLOAD_EXTS:
        flash(f"File type .{ext} not supported.", "danger")
        return redirect(url_for("main.order_detail", oid=oid))

    upload_dir = current_app.config["UPLOAD_FOLDER"]
    stored = f"{uuid.uuid4()}.{ext}"
    dest = os.path.join(upload_dir, stored)
    f.save(dest)

    db.session.add(OrderFile(
        order_id=oid,
        filename=stored,
        original_name=secure_filename(f.filename),
        file_type=ext,
    ))

    # For 3MF: extract and persist plate thumbnails
    if ext == "3mf":
        parsed = _parse_bambu_3mf(dest)
        for plate in parsed.get("plates", []):
            thumb_b64 = plate.get("thumb_b64")
            if not thumb_b64:
                continue
            # Decode and save thumbnail
            try:
                header, data = thumb_b64.split(",", 1)
                thumb_bytes = base64.b64decode(data)
                thumb_stored = f"{uuid.uuid4()}.png"
                with open(os.path.join(upload_dir, thumb_stored), "wb") as tf:
                    tf.write(thumb_bytes)
                db.session.add(OrderFile(
                    order_id=oid,
                    filename=thumb_stored,
                    original_name=f"plate_{plate['index']}_thumbnail.png",
                    file_type="png",
                    is_plate_thumb=True,
                    plate_index=plate["index"],
                ))
            except Exception as exc:
                current_app.logger.warning("plate thumbnail save failed: %s", exc)
        if parsed.get("warning"):
            flash(parsed["warning"], "warning")

    db.session.commit()
    flash("File uploaded.", "success")
    return redirect(url_for("main.order_detail", oid=oid))


@bp.route("/files/<int:fid>")
@login_required
def serve_file(fid):
    f = _user_file_or_404(fid)
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    # Images and 3D model files must be served without Content-Disposition so that
    # <img> tags and the Three.js XHR loader can read them inline.
    if f.is_image or f.is_plate_thumb or f.file_type in ("stl", "3mf"):
        return send_from_directory(upload_dir, f.filename)
    return send_from_directory(upload_dir, f.filename, download_name=f.original_name)


@bp.route("/files/<int:fid>/stl")
@login_required
def serve_file_as_stl(fid):
    """Convert a .3mf to binary STL on-the-fly for the 3D viewer."""
    from flask import Response
    f = _user_file_or_404(fid)
    if f.file_type != "3mf":
        abort(400)
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], f.filename)
    stl_bytes = _3mf_to_stl_bytes(path)
    if not stl_bytes:
        abort(404)
    return Response(stl_bytes, mimetype="application/octet-stream")


@bp.route("/files/<int:fid>/plate/<int:plate_n>/stl")
@login_required
def serve_file_plate_stl(fid, plate_n):
    """Convert a specific plate from a .3mf to binary STL for the per-plate 3D viewer."""
    from flask import Response
    f = _user_file_or_404(fid)
    if f.file_type != "3mf":
        abort(400)
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], f.filename)
    stl_bytes = _3mf_to_stl_bytes(path, plate_n=plate_n)
    if not stl_bytes:
        abort(404)
    return Response(stl_bytes, mimetype="application/octet-stream")


@bp.route("/files/<int:fid>/delete", methods=["POST"])
@login_required
def file_delete(fid):
    f = _user_file_or_404(fid)
    oid = f.order_id
    upload_dir = current_app.config["UPLOAD_FOLDER"]

    to_delete = [f]

    # Deleting a .3mf also removes its extracted plate thumbnails
    if f.file_type == "3mf":
        thumbs = OrderFile.query.filter_by(order_id=oid, is_plate_thumb=True).all()
        to_delete.extend(thumbs)

    for entry in to_delete:
        try:
            os.remove(os.path.join(upload_dir, entry.filename))
        except OSError:
            pass
        db.session.delete(entry)

    db.session.commit()
    flash("File deleted.", "success")
    return redirect(url_for("main.order_detail", oid=oid))


@bp.route("/api/parse-3mf", methods=["POST"])
@login_required
def api_parse_3mf():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file provided"}), 400

    with tempfile.NamedTemporaryFile(suffix=".3mf", delete=False) as tmp:
        f.save(tmp.name)
        tmp_path = tmp.name

    try:
        filaments_db = Filament.query.filter_by(user_id=current_user.id).order_by(Filament.name).all()
        result = _parse_bambu_3mf(tmp_path, filaments_db)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return jsonify(result)


# ---------- Statistics ----------

@bp.route("/stats")
@login_required
def stats():
    from collections import defaultdict
    import calendar

    all_orders = (
        PrintOrder.query.filter_by(user_id=current_user.id)
        .order_by(PrintOrder.created_at).all()
    )
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

    # Retail / particular split + VAT collected (delivered commercial only)
    delivered_retail = [o for o in delivered_commercial if o.has_vat]
    delivered_particular = [o for o in delivered_commercial if not o.has_vat]
    revenue_retail = sum((o.sell_price for o in delivered_retail), Decimal(0))
    revenue_particular = sum((o.sell_price for o in delivered_particular), Decimal(0))
    total_vat_collected = sum((o.vat_amount for o in delivered_retail), Decimal(0))

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
    all_purchases = FilamentPurchase.query.filter_by(user_id=current_user.id).all()
    total_filament_purchased_spend = sum(
        (
            (Decimal(str(p.quantity_g)) / Decimal(1000)) * Decimal(str(p.price_per_kg))
            for p in all_purchases
        ),
        Decimal(0),
    )

    # Current stock value
    filaments = Filament.query.filter_by(user_id=current_user.id).order_by(Filament.name).all()
    total_stock_value = sum((f.stock_value for f in filaments), Decimal(0))
    total_stock_kg = sum((f.stock_kg for f in filaments), Decimal(0))

    # --- Monthly breakdown (last 12 months, commercial delivered only) ---
    monthly = defaultdict(lambda: {"revenue": Decimal(0), "cost": Decimal(0), "vat": Decimal(0), "orders": 0})
    for o in delivered_commercial:
        key = o.delivered_at.strftime("%Y-%m")
        monthly[key]["revenue"] += o.sell_price
        monthly[key]["cost"] += o.total_cost
        monthly[key]["vat"] += o.vat_amount
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
        vat = monthly[key]["vat"]
        monthly_rows.append(
            {
                "key": key,
                "label": label,
                "revenue": rev,
                "cost": cost,
                "profit": profit,
                "vat": vat,
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
        "colors": [f.color_hex or "#6c757d" for f in stock_filaments_sorted],
    }

    return render_template(
        "stats.html",
        # totals — commercial
        total_revenue=total_revenue,
        total_filament_spend_commercial=total_filament_spend_commercial,
        total_electricity_commercial=total_electricity_commercial,
        total_cost_commercial=total_cost_commercial,
        total_profit=total_profit,
        # retail / VAT
        revenue_retail=revenue_retail,
        revenue_particular=revenue_particular,
        total_vat_collected=total_vat_collected,
        delivered_retail_count=len(delivered_retail),
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
