"""
Making a photo pack for one region (see docs/PACK_TOOL.md and, in kolibri-games,
docs/PHOTO_PACKS.md for the format).

The steps, each of which can be stopped and run again (finished work is kept
in <out>/.build/<region>/, a hidden folder that Kolibri Games ignores):

1. Coverage: fetch Mapillary's coverage tiles over the region's countries. At
   zoom 8 a tile is about 150 km across; its "sequence" layer lists every
   sequence (a run of photos taken one after another) with its route and the
   id of its first photo. One sequence = one possible place.
2. Places: keep the sequences that start inside one of the region's countries
   and not near a border (using the game's own map, beacon_pack/geo.py), and
   share the places out between the countries: bigger countries get more, every
   country gets at least a few, and inside a country the places are spread out
   over a grid so a game doesn't show the same city again and again. 360°
   photos are picked over ordinary ones.
3. Check: ask the Graph API about each picked photo (its exact spot, author,
   date and download address) and check its spot again. Photos that fail are
   replaced by the next one on the list.
4. Download the 2048-pixel version of each photo and remove any hidden data
   (EXIF with GPS and so on).
5. Write pack.json, places.json, LICENSE.txt and CREDITS.txt (and a .zip, if
   asked).
"""
import datetime
import hashlib
import json
import math
import os
import random
import zipfile

from . import geo, mvt, regions
from .mapillary import MapillaryError
from .jpeg import strip_jpeg_metadata

FORMAT = 1
LICENSE = "CC BY-SA 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
LEGALCODE_URL = "https://creativecommons.org/licenses/by-sa/4.0/legalcode.txt"
PHOTO_URL = "https://www.mapillary.com/app/?pKey=%s"
MIN_WIDTH = 1000  # skip photos smaller than this (the 2048 version would be blown up)


class BuildError(Exception):
    pass


class Options(object):
    def __init__(self, places=1000, zoom=8, margin_km=5.0, min_per_country=15, seed=1,
                 pano_only=False, since=None, countries=None, make_zip=False, legal_text=None):
        self.places = places
        self.zoom = zoom
        self.margin_km = margin_km
        self.min_per_country = min_per_country
        self.seed = seed
        self.pano_only = pano_only
        self.since = since  # a year: skip photos taken before it
        self.countries = countries  # override the region's list
        self.make_zip = make_zip
        self.legal_text = legal_text  # the license's full text, if already known (tests)


def _save_json(path, data, indent=None):
    with open(path + ".part", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
    os.replace(path + ".part", path)


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# ---------------------------------------------------------------- 1. coverage


def fetch_coverage(client, world, countries, zoom, log):
    """{(x, y)} tiles over the countries, fetched (or read from the cache)."""
    tiles = set()
    for code in countries:
        south, west, north, east = world.country_bbox(code)
        tiles.update(mvt.tiles_for_bbox(zoom, south, west, north, east))
    tiles = sorted(tiles)
    log("Coverage: %d tiles at zoom %d" % (len(tiles), zoom))
    for i, (x, y) in enumerate(tiles):
        client.tile(zoom, x, y)
        if (i + 1) % 50 == 0:
            log("  %d of %d tiles" % (i + 1, len(tiles)))
    return tiles


# ---------------------------------------------------------------- 2. places


def find_candidates(client, world, countries, tiles, opts, log):
    """{country: [candidate]} where a candidate is a sequence's first photo."""
    wanted = set(countries)
    since_ms = None
    if opts.since:
        since_ms = int(datetime.datetime(int(opts.since), 1, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000)
    seen, found, skipped = set(), {}, 0
    for x, y in tiles:
        data = client.tile(opts.zoom, x, y)
        if not data:
            continue
        for props, points in mvt.decode(data, opts.zoom, x, y, layers={"sequence"}).get("sequence", []):
            seq, image_id = props.get("id"), props.get("image_id")
            if not points or image_id is None or seq in seen:
                continue
            seen.add(seq)
            pano = bool(props.get("is_pano"))
            if opts.pano_only and not pano:
                continue
            if since_ms and (props.get("captured_at") or 0) < since_ms:
                continue
            lon, lat = points[0]
            code, _why = world.locate(lat, lon, opts.margin_km)
            if code not in wanted:
                skipped += 1
                continue
            found.setdefault(code, []).append({"image": str(image_id), "sequence": str(seq), "lat": lat,
                                               "lon": lon, "pano": pano})
    total = sum(len(v) for v in found.values())
    log("Places: %d possible places (sequences) in %d countries; %d elsewhere or near a border"
        % (total, len(found), skipped))
    return found


def share_out(world, found, total, minimum):
    """{country: how many places}. Bigger countries get more (by the square root of their area)."""
    have = {c: len(v) for c, v in found.items() if v}
    weights = {c: math.sqrt(world.area_km2(c)) for c in have}
    # Everyone gets the minimum first (or what they have, if less).
    minimum = min(minimum, total // max(1, len(have)))
    quota = {c: min(minimum, have[c]) for c in have}
    left = total - sum(quota.values())
    # Then the rest goes out by size. A country that runs out of places passes
    # its share on to the others in the next round.
    while left > 0:
        open_ = sorted(c for c in have if quota[c] < have[c])
        if not open_:
            break
        weight = sum(weights[c] for c in open_)
        exact = {c: left * weights[c] / weight for c in open_}
        give = {c: min(int(exact[c]), have[c] - quota[c]) for c in open_}
        # Hand out what rounding left over to the biggest remainders.
        spare = left - sum(give.values())
        for c in sorted(open_, key=lambda c: exact[c] - int(exact[c]), reverse=True):
            if spare <= 0:
                break
            if quota[c] + give[c] < have[c]:
                give[c] += 1
                spare -= 1
        given = sum(give.values())
        if given == 0:
            break
        for c in open_:
            quota[c] += give[c]
        left -= given
    return quota


def spread(world, candidates, quota, rng):
    """The candidates in the order to try them: spread over a grid, 360° photos first in each square.

    The grid is sized so there are about twice as many squares as places,
    then the squares are visited in turn, taking one photo from each.
    """
    if not candidates:
        return []
    lat0 = sum(c["lat"] for c in candidates) / len(candidates)
    lats = [c["lat"] for c in candidates]
    lons = [c["lon"] for c in candidates]
    height_km = (max(lats) - min(lats)) * geo.KM_PER_DEGREE + 1
    width_km = (max(lons) - min(lons)) * geo.KM_PER_DEGREE * math.cos(math.radians(lat0)) + 1
    cell_km = max(1.0, math.sqrt(width_km * height_km / max(1, 2 * quota)))
    cells = {}
    for c in candidates:
        key = (int(c["lat"] * geo.KM_PER_DEGREE // cell_km),
               int(c["lon"] * geo.KM_PER_DEGREE * math.cos(math.radians(lat0)) // cell_km))
        cells.setdefault(key, []).append(c)
    order = sorted(cells)
    rng.shuffle(order)
    for key in order:
        rng.shuffle(cells[key])
        cells[key].sort(key=lambda c: not c["pano"])  # stable: panoramas first, random within each kind
    out = []
    while any(cells[k] for k in order):
        for k in order:
            if cells[k]:
                out.append(cells[k].pop(0))
    return out


# ---------------------------------------------------------------- 3. check


def check_photo(world, info, code, margin_km, pano_only):
    """(place, None) if a photo can be used for country ``code``, else (None, reason)."""
    geom = info.get("computed_geometry") or info.get("geometry") or {}
    coords = geom.get("coordinates") if isinstance(geom, dict) else None
    if not coords or len(coords) < 2:
        return None, "no location"
    if not info.get("thumb_2048_url"):
        return None, "no 2048-pixel version"
    width = info.get("width") or 0
    if width and width < MIN_WIDTH:
        return None, "too small (%d pixels wide)" % width
    pano = bool(info.get("is_pano"))
    if pano_only and not pano:
        return None, "not 360°"
    lon, lat = float(coords[0]), float(coords[1])
    where, why = world.locate(lat, lon, margin_km)
    if where != code:
        return None, why if where is None else "actually in %s" % where
    creator = info.get("creator") or {}
    captured = info.get("captured_at")
    date = ""
    if isinstance(captured, (int, float)):
        date = datetime.datetime.fromtimestamp(captured / 1000.0, datetime.timezone.utc).strftime("%Y-%m-%d")
    place = {
        "id": str(info["id"]),
        "photo": "photos/%s.jpg" % info["id"],
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "country": code,
        "pano": pano,
        "credit": {
            "author": creator.get("username") or "unknown",
            "source": "Mapillary",
            "url": PHOTO_URL % info["id"],
            "license": LICENSE,
            "captured": date,
        },
    }
    return place, None


def choose(client, world, ordered, quota, opts, checked, save, log):
    """{country: [place]}: the first photos on each country's list that pass the check."""
    chosen = {}
    calls = 0
    for code in sorted(ordered):
        want = quota.get(code, 0)
        got, sequences = [], set()
        for cand in ordered[code]:
            if len(got) >= want:
                break
            if cand["sequence"] in sequences:
                continue
            info = checked.get(cand["image"])
            if info is None:
                try:
                    info = client.image(cand["image"])
                except MapillaryError as e:
                    if e.status is None or e.status in (401, 403):
                        raise
                    info = {"error": str(e)}
                checked[cand["image"]] = info
                calls += 1
                if calls % 25 == 0:
                    save()
            if "error" in info:
                continue
            place, _why = check_photo(world, info, code, opts.margin_km, opts.pano_only)
            if place:
                got.append(place)
                sequences.add(cand["sequence"])
        chosen[code] = got
        log("  %s: %d of %d places" % (code, len(got), want))
    save()
    return chosen


# ---------------------------------------------------------------- 4 and 5. files


def download_photos(client, pack_dir, places, checked, log):
    photos = os.path.join(pack_dir, "photos")
    os.makedirs(photos, exist_ok=True)
    keep = set()
    done = 0
    for place in places:
        name = os.path.basename(place["photo"])
        keep.add(name)
        path = os.path.join(photos, name)
        if os.path.exists(path):
            continue
        info = checked[place["id"]]
        try:
            data = client.download(info["thumb_2048_url"], "photo %s" % place["id"])
        except MapillaryError as e:
            if e.status == 403:  # the download address has expired: ask for a new one
                info = client.image(place["id"])
                checked[place["id"]] = info
                data = client.download(info["thumb_2048_url"], "photo %s" % place["id"])
            else:
                raise
        if data[:2] != b"\xff\xd8":
            raise BuildError("Photo %s isn't a JPEG." % place["id"])
        with open(path + ".part", "wb") as f:
            f.write(strip_jpeg_metadata(data))
        os.replace(path + ".part", path)
        done += 1
        if done % 50 == 0:
            log("  downloaded %d photos" % done)
    for name in os.listdir(photos):  # photos left from an earlier run that are no longer used
        if name not in keep:
            os.remove(os.path.join(photos, name))
    log("Photos: %d downloaded, %d already there" % (done, len(places) - done))


def license_text(region_title, legal):
    head = (
        "The photos in this pack (%s) come from Mapillary (www.mapillary.com) and are\n"
        "licensed under the Creative Commons Attribution-ShareAlike 4.0 International\n"
        "license (CC BY-SA 4.0): %s\n\n"
        "Each photo's author, date and Mapillary address are in CREDITS.txt and places.json,\n"
        "and BeaconHunt shows them with the photo. The photos are Mapillary's 2048-pixel\n"
        "versions, unchanged except that hidden data in the files (such as GPS) was removed.\n\n"
        "You may share and adapt these photos, also for commercial use, if you give\n"
        "credit, say if you changed them, and share your changes under the same license.\n"
        % (region_title, LICENSE_URL)
    )
    if legal:
        return head + "\nThe full license follows.\n\n" + "=" * 72 + "\n\n" + legal.strip() + "\n"
    return head + "\nThe full license: %s\n" % LEGALCODE_URL


def credits_text(region_title, places, countries):
    lines = ["Photos in the %s photo pack, all from Mapillary under CC BY-SA 4.0." % region_title,
             "Photo id, author, date taken, address on Mapillary.", ""]
    for p in sorted(places, key=lambda p: p["id"]):
        c = p["credit"]
        lines.append("%s  %s  %s  %s" % (p["id"], c["author"], c["captured"] or "date unknown", c["url"]))
    return "\n".join(lines) + "\n"


def get_legal_text(client, build_dir, log):
    """The license's full text, downloaded once (it goes into LICENSE.txt)."""
    path = os.path.join(build_dir, "cc-by-sa-4.0.txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    try:
        text = client.download(LEGALCODE_URL, "the license text").decode("utf-8")
    except (MapillaryError, UnicodeDecodeError) as e:
        log("Couldn't download the license text (%s); LICENSE.txt will give its address instead." % e)
        return None
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return text


def write_zip(pack_dir, zip_path):
    with zipfile.ZipFile(zip_path + ".part", "w") as z:
        for root, _dirs, files in os.walk(pack_dir):
            for name in sorted(files):
                full = os.path.join(root, name)
                arc = os.path.relpath(full, pack_dir).replace(os.sep, "/")
                kind = zipfile.ZIP_STORED if name.lower().endswith(".jpg") else zipfile.ZIP_DEFLATED
                z.write(full, arc, compress_type=kind)
    os.replace(zip_path + ".part", zip_path)


# ---------------------------------------------------------------- all together


def build(region_id, out_dir, client, opts=None, log=print, today=None):
    opts = opts or Options()
    if region_id not in regions.REGIONS:
        raise BuildError("Unknown region %r. See: beacon-pack regions" % region_id)
    title = regions.title(region_id)
    countries = opts.countries or regions.countries_in(region_id)
    build_dir = os.path.join(out_dir, ".build", region_id)
    pack_dir = os.path.join(out_dir, region_id)
    os.makedirs(build_dir, exist_ok=True)
    client.cache_dir = build_dir
    world = geo.WorldMap()
    unknown = [c for c in countries if c not in world.countries]
    if unknown:
        raise BuildError("Not on the map: %s" % ", ".join(unknown))
    log("%s: %d countries (%s), %d places" % (title, len(countries), " ".join(countries), opts.places))

    tiles = fetch_coverage(client, world, countries, opts.zoom, log)
    found = find_candidates(client, world, countries, tiles, opts, log)
    if not found:
        raise BuildError("Mapillary has no photos in these countries (or none away from borders).")
    quota = share_out(world, found, opts.places, opts.min_per_country)
    # The same seed gives the same places, so a second run carries on where the first stopped.
    seed = int(hashlib.sha256(("%s/%s" % (region_id, opts.seed)).encode()).hexdigest()[:12], 16)
    ordered = {c: spread(world, found[c], quota[c], random.Random(seed + i)) for i, c in enumerate(sorted(found))}

    checked_path = os.path.join(build_dir, "checked.json")
    checked = _load_json(checked_path, {})
    log("Check: asking Mapillary about the picked photos")
    chosen = choose(client, world, ordered, quota, opts, checked, lambda: _save_json(checked_path, checked), log)
    places = [p for c in sorted(chosen) for p in chosen[c]]
    short = opts.places - len(places)
    if short > 0:
        log("Only %d places could be found (%d short): Mapillary doesn't have more here." % (len(places), short))

    download_photos(client, pack_dir, places, checked, log)
    _save_json(checked_path, checked)

    today = today or datetime.date.today()
    with_photos = sorted({p["country"] for p in places})
    info = {
        "format": FORMAT,
        "id": region_id,
        "title": title,
        "version": today.strftime("%Y.%m.%d"),
        "countries": with_photos,
        "places": len(places),
        "license": LICENSE,
        "source": "Mapillary",
        "made_with": "BeaconHunt pack tool (github.com/togetherings/beacon-hunt)",
    }
    legal = opts.legal_text if opts.legal_text is not None else get_legal_text(client, build_dir, log)
    _save_json(os.path.join(pack_dir, "pack.json"), info, indent=2)
    _save_json(os.path.join(pack_dir, "places.json"), places, indent=1)
    with open(os.path.join(pack_dir, "LICENSE.txt"), "w", encoding="utf-8") as f:
        f.write(license_text(title, legal))
    with open(os.path.join(pack_dir, "CREDITS.txt"), "w", encoding="utf-8") as f:
        f.write(credits_text(title, places, countries))
    if opts.make_zip:
        write_zip(pack_dir, os.path.join(out_dir, region_id + ".zip"))
    counts = {c: len(chosen.get(c, [])) for c in countries}
    log("Done: %d places in %s (%s)" % (len(places), pack_dir,
                                        ", ".join("%s %d" % kv for kv in sorted(counts.items()))))
    log("Mapillary requests: %d" % client.requests)
    return info, places
