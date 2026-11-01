"""Checking a finished photo pack (a folder or a .zip) before copying it to a device."""
import json
import os
import zipfile

from . import geo
from .build import FORMAT

PLACE_FIELDS = ("id", "photo", "lat", "lon", "country", "pano", "credit")


class _Reader(object):
    def __init__(self, path):
        self.path = path
        self.zip = zipfile.ZipFile(path) if path.lower().endswith(".zip") else None

    def read(self, name):
        if self.zip:
            try:
                return self.zip.read(name)
            except KeyError:
                return None
        full = os.path.join(self.path, *name.split("/"))
        if not os.path.isfile(full):
            return None
        with open(full, "rb") as f:
            return f.read()

    def size(self, name):
        if self.zip:
            try:
                return self.zip.getinfo(name).file_size
            except KeyError:
                return None
        full = os.path.join(self.path, *name.split("/"))
        return os.path.getsize(full) if os.path.isfile(full) else None


def check_pack(path, margin_km=0.0):
    """(problems, summary). No problems means the pack is ready to copy to a device."""
    r = _Reader(path)
    problems = []
    raw = r.read("pack.json")
    if raw is None:
        return ["No pack.json."], {}
    info = json.loads(raw.decode("utf-8"))
    if info.get("format") != FORMAT:
        problems.append("pack.json: format should be %d." % FORMAT)
    raw = r.read("places.json")
    if raw is None:
        return problems + ["No places.json."], {}
    places = json.loads(raw.decode("utf-8"))
    for name in ("LICENSE.txt", "CREDITS.txt"):
        if r.read(name) is None:
            problems.append("No %s." % name)
    countries = geo.load_countries()
    world = geo.WorldMap()
    ids, per_country, total_bytes, panos = set(), {}, 0, 0
    for p in places:
        missing = [f for f in PLACE_FIELDS if f not in p]
        if missing:
            problems.append("Place %s is missing %s." % (p.get("id"), ", ".join(missing)))
            continue
        if p["id"] in ids:
            problems.append("Place id %s is used twice." % p["id"])
        ids.add(p["id"])
        if p["country"] not in countries:
            problems.append("Place %s: %s isn't on the map." % (p["id"], p["country"]))
        size = r.size(p["photo"])
        if size is None:
            problems.append("Place %s: no photo %s." % (p["id"], p["photo"]))
        else:
            total_bytes += size
            head = r.read(p["photo"])[:2] if size else b""
            if head != b"\xff\xd8":
                problems.append("Place %s: %s isn't a JPEG." % (p["id"], p["photo"]))
        where, why = world.locate(p["lat"], p["lon"], margin_km)
        if where != p["country"]:
            problems.append("Place %s: the map puts it %s, not in %s." % (
                p["id"], ("in " + where) if where else "(%s)" % why, p["country"]))
        credit = p["credit"] if isinstance(p["credit"], dict) else {}
        if not credit.get("author") or not credit.get("url"):
            problems.append("Place %s: the credit needs an author and a url." % p["id"])
        per_country[p["country"]] = per_country.get(p["country"], 0) + 1
        panos += 1 if p["pano"] else 0
    listed = set(info.get("countries", []))
    if listed != set(per_country):
        problems.append("pack.json's countries don't match the places' countries.")
    summary = {"id": info.get("id"), "title": info.get("title"), "places": len(places), "panoramas": panos,
               "megabytes": round(total_bytes / 1e6, 1), "countries": dict(sorted(per_country.items()))}
    return problems, summary
