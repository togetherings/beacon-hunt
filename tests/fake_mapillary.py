"""A pretend Mapillary for the pack tool's tests: coverage tiles, photo details and photo files, all offline."""
import io
import json
import math
import urllib.error
import urllib.parse

from beacon_pack import mvt

# A tiny JPEG with an EXIF block (holding pretend GPS) that the tool must remove.
EXIF = b"Exif\x00\x00GPSLatitude=8.48"
JPEG = (b"\xff\xd8" + b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        + b"\xff\xe1" + (len(EXIF) + 2).to_bytes(2, "big") + EXIF
        + b"\xff\xda\x00\x02picture\xff\xd9")


def _tile_xy(z, lon, lat):
    n = 2 ** z
    fx = (lon + 180.0) / 360.0 * n
    r = math.radians(lat)
    fy = (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n
    return int(fx), int(fy), int((fx % 1) * 4096), int((fy % 1) * 4096)


class FakeMapillary(object):
    """
    ``photos``: [(image id, lat, lon, is_pano)], each the first photo of its own
    sequence. ``moved``: {image id: (lat, lon)} where the Graph API says a photo
    really is (to test the second check). ``broken``: ids the Graph API says
    don't exist.
    """

    def __init__(self, photos, zoom=8, moved=None, broken=(), token="MLY|test"):
        self.zoom = zoom
        self.photos = {str(p[0]): p for p in photos}
        self.moved = {str(k): v for k, v in (moved or {}).items()}
        self.broken = {str(b) for b in broken}
        self.token = token
        self.calls = []
        tiles = {}
        for image_id, lat, lon, pano in photos:
            tx, ty, px, py = _tile_xy(zoom, lon, lat)
            tiles.setdefault((tx, ty), []).append(
                ({"id": "seq%s" % image_id, "image_id": int(image_id), "is_pano": pano,
                  "captured_at": 1690000000000}, [(px, py), (px + 3, py + 3)], 2))
        self.tiles = {k: mvt.encode({"sequence": v}) for k, v in tiles.items()}

    def _error(self, url, code):
        return urllib.error.HTTPError(url, code, "error", {}, io.BytesIO(b""))

    def __call__(self, url, headers):
        u = urllib.parse.urlparse(url)
        q = urllib.parse.parse_qs(u.query)
        self.calls.append(u.netloc + u.path)
        if u.netloc == "tiles.mapillary.com":
            if q.get("access_token") != [self.token]:
                raise self._error(url, 401)
            z, x, y = (int(v) for v in u.path.rsplit("/", 3)[1:])
            if (x, y) not in self.tiles:
                raise self._error(url, 404)
            return self.tiles[(x, y)]
        if u.netloc == "graph.mapillary.com":
            if headers.get("Authorization") != "OAuth " + self.token:
                raise self._error(url, 401)
            image_id = u.path.strip("/")
            if image_id in self.broken or image_id not in self.photos:
                raise self._error(url, 404)
            _id, lat, lon, pano = self.photos[image_id]
            lat, lon = self.moved.get(image_id, (lat, lon))
            return json.dumps({
                "id": image_id, "is_pano": pano, "camera_type": "spherical" if pano else "perspective",
                "computed_geometry": {"type": "Point", "coordinates": [lon, lat]},
                "captured_at": 1690000000000, "creator": {"username": "mapper%s" % image_id[-1], "id": "1"},
                "thumb_2048_url": "https://cdn.example/%s.jpg" % image_id, "width": 4096, "height": 2048,
            }).encode()
        if u.netloc == "cdn.example":
            return JPEG
        if u.netloc == "creativecommons.org":
            return b"Attribution-ShareAlike 4.0 International (pretend legal code)"
        raise AssertionError("unexpected request " + url)
