"""
Which country a point is in, using the same map the game draws (game/map/world.js).

Using the game's own map keeps the pack and the game in step: a photo is only
put in a country if, on the map the learner clicks, the photo's spot is inside
that country and not close to a border.

The map is in SINGE's Miller projection (see tools/import_singe_map.py):

    x = (lon + 180) * k
    y = (miller(lat_top) - miller(lat)) * k

Country outlines are SVG paths made only of "M x,y" (absolute), "l dx,dy ..."
(relative lines) and "z", so they're easy to read without an SVG library.
"""
import json
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
MAP_FILE = os.path.join(HERE, "..", "game", "map", "world.js")
COUNTRIES_FILE = os.path.join(HERE, "..", "game", "map", "countries.json")
KM_PER_DEGREE = 111.32


def miller(lat):
    r = math.radians(max(-89.0, min(89.0, lat)))
    return math.degrees(1.25 * math.log(math.tan(math.pi / 4 + 0.4 * r)))


def load_map(path=MAP_FILE):
    """The map's JSON (world.js is "window.BEACON_MAP = {...};")."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return json.loads(text[text.index("{"):text.rindex("}") + 1])


def load_countries(path=COUNTRIES_FILE):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


_TOKEN = re.compile(r"[MLlz]|-?\d+(?:\.\d+)?")


def parse_path(d):
    """A list of rings (lists of (x, y)) from an SVG path of M, l and z commands."""
    rings, ring, cmd, nums = [], [], None, []
    x = y = 0.0
    for tok in _TOKEN.findall(d or ""):
        if tok in ("M", "l", "L", "z"):
            cmd = tok
            if tok == "z":
                if len(ring) >= 3:
                    rings.append(ring)
                ring = []
            continue
        nums.append(float(tok))
        if len(nums) < 2:
            continue
        a, b = nums
        nums = []
        if cmd == "M":
            if len(ring) >= 3:
                rings.append(ring)
            x, y = a, b
            ring = [(x, y)]
            cmd = "l"  # numbers after an M are lines (SVG rule), relative here
        elif cmd == "L":
            x, y = a, b
            ring.append((x, y))
        else:
            x, y = x + a, y + b
            ring.append((x, y))
    if len(ring) >= 3:
        rings.append(ring)
    return rings


def _bbox(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _ring_area(ring):
    a = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i - 1]
        x2, y2 = ring[i]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


def _seg_dist2(px, py, ax, ay, bx, by, sx, sy):
    """Squared distance from a point to a segment, with x and y scaled to km."""
    ax, ay, bx, by = (ax - px) * sx, (ay - py) * sy, (bx - px) * sx, (by - py) * sy
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length))
    cx, cy = ax + t * dx, ay + t * dy
    return cx * cx + cy * cy


def _ring_contains(ring, x, y):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


class Country(object):
    def __init__(self, key, off=False):
        self.key = key
        self.off = off    # a disputed area left out of the game: photos there are skipped
        self.rings = []   # [(bbox, ring)]
        self.subs = []    # the region of each ring's piece of the map (Hawaii: Polynesia)
        self.area = 0.0   # in map units squared (only used to compare countries)

    def add(self, ring, sub=None):
        self.rings.append((_bbox(ring), ring))
        self.subs.append(sub)
        self.area += _ring_area(ring)

    def piece_region(self, x, y, sx, sy):
        """The region of the piece of this country at (or nearest to) the point."""
        best, best_d = None, None
        for ((x0, y0, x1, y1), ring), sub in zip(self.rings, self.subs):
            if x0 <= x <= x1 and y0 <= y <= y1 and _ring_contains(ring, x, y):
                return sub
            # not inside: how far away is this piece (by its box, which is enough to pick one)
            dx = max(x0 - x, 0, x - x1) * sx
            dy = max(y0 - y, 0, y - y1) * sy
            d = dx * dx + dy * dy
            if best_d is None or d < best_d:
                best, best_d = sub, d
        return best

    @property
    def bbox(self):
        boxes = [b for b, _ in self.rings]
        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))

    def contains(self, x, y):
        """Even-odd rule over all the rings, so holes (like Lesotho in South Africa) work."""
        inside = False
        for (x0, y0, x1, y1), ring in self.rings:
            if x < x0 or x > x1 or y < y0 or y > y1:
                continue
            j = len(ring) - 1
            for i in range(len(ring)):
                xi, yi = ring[i]
                xj, yj = ring[j]
                if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                    inside = not inside
                j = i
        return inside

    def distance_km(self, x, y, sx, sy, limit_km):
        """Distance from the point to this country's outline, if it's under limit_km (else None)."""
        mx, my = limit_km / sx, limit_km / sy
        best = None
        for (x0, y0, x1, y1), ring in self.rings:
            if x < x0 - mx or x > x1 + mx or y < y0 - my or y > y1 + my:
                continue
            for i in range(len(ring)):
                ax, ay = ring[i - 1]
                bx, by = ring[i]
                d = _seg_dist2(x, y, ax, ay, bx, by, sx, sy)
                if best is None or d < best:
                    best = d
        if best is None:
            return None
        d = math.sqrt(best)
        return d if d <= limit_km else None


class WorldMap(object):
    """The countries of the game's map, for finding where a point is."""

    def __init__(self, data=None, keys=None):
        data = data or load_map()
        p = data["projection"]
        self.k = float(p["k"])
        self.top = miller(p["lat_top"])
        self.countries = {}
        for r in data["regions"]:
            key = r.get("key")
            if not key or r.get("decor") or (keys is not None and key not in keys):
                continue
            country = self.countries.setdefault(key, Country(key, off=bool(r.get("off"))))
            for ring in parse_path(r.get("d")):
                country.add(ring, r.get("sub"))
        self.countries = {k: c for k, c in self.countries.items() if c.rings}

    def xy(self, lat, lon):
        return (lon + 180.0) * self.k, (self.top - miller(lat)) * self.k

    def scale(self, lat):
        """Kilometres per map unit across (x) and down (y) at this latitude."""
        sx = KM_PER_DEGREE * math.cos(math.radians(lat)) / self.k
        sy = KM_PER_DEGREE * math.cos(math.radians(0.8 * lat)) / self.k  # Miller: dy/dlat = 1/cos(0.8 lat)
        return sx, sy

    def country_bbox(self, key):
        """(south, west, north, east) in degrees."""
        x0, y0, x1, y1 = self.countries[key].bbox
        return self.lat_of(y1), x0 / self.k - 180, self.lat_of(y0), x1 / self.k - 180

    def lat_of(self, y):
        m = self.top - y / self.k
        return math.degrees((math.atan(math.exp(0.8 * math.radians(m))) - math.pi / 4) / 0.4)

    def area_km2(self, key):
        """Rough land area (good enough for sharing photos out between countries)."""
        c = self.countries[key]
        south, _w, north, _e = self.country_bbox(key)
        sx, sy = self.scale((south + north) / 2)
        return c.area * sx * sy

    def locate(self, lat, lon, margin_km=5.0, coast_km=5.0):
        """(country key, why) for a point; key is None when the point is unsafe to use.

        A point is used only when it's inside exactly one country (the smaller
        one wins where one country sits in a hole in another) and no other
        country is within margin_km. Points just off the coast (the map's
        coastline is simplified) count for the nearest country if it's within
        coast_km and nothing else is near.
        """
        x, y = self.xy(lat, lon)
        sx, sy = self.scale(lat)
        inside = [c for c in self.countries.values() if c.contains(x, y)]
        if inside:
            home = min(inside, key=lambda c: c.area)
            if home.off:
                return None, "in %s, which the game leaves out" % home.key
        else:
            near = []
            for c in self.countries.values():
                d = c.distance_km(x, y, sx, sy, coast_km)
                if d is not None:
                    near.append((d, c))
            if not near:
                return None, "not on land on the map"
            home = min(near, key=lambda n: n[0])[1]
            if home.off:
                return None, "next to %s, which the game leaves out" % home.key
        for c in self.countries.values():
            if c is home:
                continue
            if c.distance_km(x, y, sx, sy, margin_km) is not None:
                return None, "within %g km of %s" % (margin_km, c.key)
        return home.key, "ok"

    def piece_region(self, key, lat, lon):
        """The UN sub-region of the piece of the country a point is in (see regions.photo_region)."""
        x, y = self.xy(lat, lon)
        sx, sy = self.scale(lat)
        return self.countries[key].piece_region(x, y, sx, sy)


# ---------------------------------------------------------------- neighbours


def outline_points(data, skip=()):
    """{country key: [(lat, lon), ...]}: every corner of each country's outline,
    plus its marker point (tiny islands like Gibraltar have no outline of their own)."""
    p = data["projection"]
    k, top = float(p["k"]), miller(p["lat_top"])

    def lat_of(y):
        m = top - y / k
        return math.degrees((math.atan(math.exp(0.8 * math.radians(m))) - math.pi / 4) / 0.4)

    out = {}
    for r in data["regions"]:
        key = r.get("key")
        if not key or r.get("decor") or r.get("off") or key in skip:
            continue
        pts = out.setdefault(key, [])
        for ring in parse_path(r.get("d")):
            pts.extend((lat_of(y), x / k - 180.0) for x, y in ring)
        if r.get("mk"):
            pts.append((lat_of(r["mk"][1]), r["mk"][0] / k - 180.0))
    return out


def _flat_km(lat1, lon1, lat2, lon2):
    """Distance in km, close enough for a few hundred km (flat-earth approximation)."""
    dlon = (lon2 - lon1 + 540.0) % 360.0 - 180.0
    x = dlon * math.cos(math.radians((lat1 + lat2) / 2))
    return KM_PER_DEGREE * math.hypot(x, lat2 - lat1)


class PointIndex(object):
    """Outline points in a grid of 1-degree squares, for finding what's near a spot quickly."""

    def __init__(self, points):
        self.cells = {}
        for key, pts in points.items():
            for lat, lon in pts:
                self.cells.setdefault((int(math.floor(lat)), int(math.floor(lon))), []).append((lat, lon, key))

    def near(self, lat, lon, km, skip=None):
        """{country key: distance} for countries with an outline point within km of the spot."""
        dlat = int(math.ceil(km / KM_PER_DEGREE)) + 1
        dlon = int(math.ceil(km / (KM_PER_DEGREE * max(0.05, math.cos(math.radians(min(85.0, abs(lat)))))))) + 1
        dlon = min(dlon, 180)
        found = {}
        i0, j0 = int(math.floor(lat)), int(math.floor(lon))
        for i in range(i0 - dlat, i0 + dlat + 1):
            for j in range(j0 - dlon, j0 + dlon + 1):
                jj = (j + 180) % 360 - 180
                for plat, plon, key in self.cells.get((i, jj), ()):
                    if key == skip:
                        continue
                    d = _flat_km(lat, lon, plat, plon)
                    if d <= km and d < found.get(key, km + 1):
                        found[key] = d
        return found


def find_neighbours(points, max_km=150.0):
    """{country: sorted [countries]} that share a border or are within max_km across water.

    Every outline corner is checked against the corners of other countries
    nearby (the map's corners are a few km apart, so this is close enough).
    """
    index = PointIndex(points)
    out = {key: set() for key in points}
    for key, pts in points.items():
        seen = set()
        for lat, lon in pts:
            for other in index.near(lat, lon, max_km, skip=key):
                seen.add(other)
        for other in seen:
            out[key].add(other)
            out[other].add(key)
    return {k: sorted(v) for k, v in out.items()}
