"""
Make BeaconHunt's map files from SINGE's world map (maps/world.js in the SINGE
game, built from Natural Earth's public-domain country borders).

    python tools/import_singe_map.py path/to/singe/maps/world.js

Writes:

* game/map/world.js        the shapes the game draws: every country's outline
                           (SVG path in SINGE's Miller projection), its code,
                           UN sub-region, a marker point and the inset boxes for
                           small islands. A script (window.BEACON_MAP = {...}),
                           so the game can load it with a plain <script> tag.
* game/map/countries.json  code -> name, kind (un, observer, partial or
                           territory), its UN sub-region ("sub"), every region
                           and continent it has land in, its neighbours, and a point
                           inside the country's largest piece (lat/lon). The
                           server uses it to score guesses (see
                           kolibri-games/docs/PHOTO_PACKS.md), and the pack tool
                           uses world.json to tell which country a photo is in.

Run it again if SINGE's map changes. Nothing else needs editing by hand.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from beacon_pack import geo, regions as R  # noqa: E402  (the continents and the special cases)

#: Countries within this distance across water count as neighbours (on the map,
#: whose simplified coasts put Florida 153 km from Cuba).
NEIGHBOUR_KM = 160.0

#: world.js is this line followed by the map's JSON and ";" (beacon_pack/geo.py reads it back).
MAP_PREFIX = "/* Made by tools/import_singe_map.py from SINGE's world map. Don't edit by hand. */\nwindow.BEACON_MAP = "
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "game", "map")


def miller_inverse(y_deg):
    """Latitude for a Miller 'degree-equivalent' y (the inverse of SINGE's miller())."""
    return math.degrees((math.atan(math.exp(0.8 * math.radians(y_deg))) - math.pi / 4) / 0.4)


def miller(lat):
    r = math.radians(max(-89.0, min(89.0, lat)))
    return math.degrees(1.25 * math.log(math.tan(math.pi / 4 + 0.4 * r)))


def to_lat_lon(x, y, projection):
    k = projection["k"]
    lon = x / k - 180.0
    lat = miller_inverse(miller(projection["lat_top"]) - y / k)
    return round(lat, 4), round(((lon + 180) % 360) - 180, 4)


def load(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return json.loads(text[text.index(".push(") + 6:text.rindex(")")])


def convert(src):
    m = load(src)
    by_name = {r["name"]: r for r in m["regions"]}

    def key_of(r):
        """The country a region counts as: parts (Alaska, Saba...) count as their country."""
        if r.get("kind") == "decor":
            return None
        if r.get("kind") == "part" and r.get("part_of") in by_name:
            return key_of(by_name[r["part_of"]])
        return r["code"]

    regions, countries = [], {}
    for r in m["regions"]:
        key = key_of(r)
        out = {"name": r["name"], "key": key, "sub": r.get("sub"), "cont": r.get("cont"), "d": r.get("d", "")}
        for field in ("s", "mk", "sz", "small", "ins", "decor", "twin", "iso2"):
            if field in r:
                out[field] = r[field]
        if key in R.EXCLUDED:
            out["off"] = 1  # a disputed area left out of the game: drawn, but can't be picked
        regions.append(out)
        if key and key not in R.EXCLUDED and r.get("kind") != "part" and key not in countries:
            mk = r.get("mk")
            if mk is None:  # a territory made only of separate parts (Saint Helena...): use its largest part
                parts = [p for p in m["regions"] if p.get("part_of") == r["name"] and p.get("mk")]
                if not parts:
                    continue
                mk = max(parts, key=lambda p: p.get("sz", 0))["mk"]
            lat, lon = to_lat_lon(mk[0], mk[1], m["projection"])
            countries[key] = {"name": r["name"], "kind": r.get("kind"), "sub": r.get("sub"), "cont": r.get("cont"),
                              "iso2": r.get("iso2"), "lat": lat, "lon": lon}
    # Every region and continent a country has land in (its parts count: Hawaii
    # puts the United States in Polynesia), and Asian Russia and Papua.
    for r in regions:
        if r["key"] in countries and r.get("sub"):
            countries[r["key"]].setdefault("regions", set()).add(r["sub"])
    countries["RUS"]["regions"].add(R.NORTHERN_ASIA)
    countries["IDN"]["regions"].add("Melanesia")
    for c in countries.values():
        c["regions"] = sorted(c.get("regions", ()))
        c["continents"] = sorted({R.continent_of(s) for s in c["regions"]} - {None})
    world_shapes = {"projection": m["projection"], "regions": regions}
    neighbours = geo.find_neighbours(geo.outline_points(world_shapes, skip=R.EXCLUDED), NEIGHBOUR_KM)
    for key, c in countries.items():
        c["neighbours"] = [n for n in neighbours.get(key, []) if n in countries]
    # How often each country comes up in a game: the square root of its area (in km),
    # so big countries come up more often than tiny ones, but every country sometimes.
    world_map = geo.WorldMap({"projection": m["projection"], "regions": regions})
    for key, c in countries.items():
        area = world_map.area_km2(key) if key in world_map.countries else 0
        c["weight"] = max(1, int(round(math.sqrt(area))))

    world = {
        "source": "SINGE world map (tools/import_singe_map.py), from Natural Earth 10m Admin 0 - Countries (public domain).",
        "projection": m["projection"], "size": m["size"], "strip": m["strip"], "strip_y": m.get("strip_y"),
        "insets": m["insets"],
        "lakes": m.get("lakes", []), "regions": regions,
        # The country names and points the game needs (the same as countries.json).
        "countries": {k: {"name": c["name"], "kind": c["kind"], "sub": c["sub"], "lat": c["lat"], "lon": c["lon"],
                          "continents": c["continents"]}
                      for k, c in sorted(countries.items())},
    }
    return world, countries


def main(argv):
    if len(argv) != 1:
        sys.exit(__doc__)
    world, countries = convert(argv[0])
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "world.js"), "w", encoding="utf-8") as f:
        f.write(MAP_PREFIX)
        json.dump(world, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    with open(os.path.join(OUT, "countries.json"), "w", encoding="utf-8") as f:
        f.write("{\n" + ",\n".join("%s: %s" % (json.dumps(k), json.dumps(v, ensure_ascii=False))
                                    for k, v in sorted(countries.items())) + "\n}\n")
    print("%d regions, %d countries -> %s" % (len(world["regions"]), len(countries), os.path.abspath(OUT)))


if __name__ == "__main__":
    main(sys.argv[1:])
