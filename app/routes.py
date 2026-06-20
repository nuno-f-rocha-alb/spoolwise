from datetime import datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import base64
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile
import requests as http_requests
from flask import (
    Blueprint, request, abort, jsonify, send_from_directory, current_app,
)
from flask_login import login_required, current_user

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
                plate_name = (meta.get("plater_name") or meta.get("name") or "").strip()

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
                    "name": plate_name,
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

                        plate_name = ""
                        pjson_raw = _read(pjson_name)
                        if pjson_raw:
                            try:
                                pjson = json.loads(pjson_raw)
                                plate_name = (pjson.get("name") or pjson.get("plater_name") or "").strip()
                            except Exception:
                                pass

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
                            "name": plate_name,
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



# ---------- Public read-only API (no auth; for LAN dashboards) ----------
# Intentionally unauthenticated: Spoolwise is a LAN/VPN-only service and this
# exposes only non-sensitive, at-a-glance order fields (no pricing/cost). CORS
# (configured in create_app) restricts which browser origins may read it.

@bp.route("/api/orders/pending", methods=["GET"])
def api_orders_pending():
    """Return all not-yet-printed orders as JSON, newest first.

    Consumed by external LAN dashboards (e.g. Midgard). 'Pending' mirrors the
    web UI's own filter: printed_at IS NULL (also implies not delivered, since
    delivery sets printed_at)."""
    orders = (
        PrintOrder.query
        .filter(PrintOrder.printed_at.is_(None))
        .order_by(PrintOrder.created_at.desc())
        .all()
    )
    return jsonify({
        "count": len(orders),
        "orders": [
            {
                "id": o.id,
                "name": o.name,
                "customer": o.customer,
                "quantity": o.qty,
                "status": o.status,
                "is_internal": o.is_internal,
                "plates": len(o.plates),
                "print_time_hours": float(o.total_print_time_hours),
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in orders
        ],
    })


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

