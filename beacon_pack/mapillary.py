"""
Talking to Mapillary (https://www.mapillary.com/developer/api-documentation).

Two kinds of request:

* coverage tiles (vector tiles of where photos are), one per map square:
  https://tiles.mapillary.com/maps/vtp/mly1_public/2/{z}/{x}/{y}
* the Graph API, for one photo's details:
  https://graph.mapillary.com/{image id}?fields=...

Both need your client token, read from the MAPILLARY_TOKEN environment
variable. It's sent with each request and never written to a file or printed:
error messages show the address without it.

Tiles are kept in the build folder, so a second run doesn't fetch them again.
Every request is followed by a short pause, and busy or failed requests are
tried again a few times, more slowly each time.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

TILE_URL = "https://tiles.mapillary.com/maps/vtp/mly1_public/2/{z}/{x}/{y}"
GRAPH_URL = "https://graph.mapillary.com/"
IMAGE_FIELDS = ("id,geometry,computed_geometry,is_pano,camera_type,captured_at,creator,"
                "thumb_2048_url,width,height,sequence")
TOKEN_ENV = "MAPILLARY_TOKEN"
TRIES = 4
#: Some sites (like creativecommons.org) refuse Python's default user agent.
USER_AGENT = "beacon-pack (BeaconHunt pack tool; https://github.com/togetherings/beacon-hunt)"


class MapillaryError(Exception):
    def __init__(self, message, status=None):
        super(MapillaryError, self).__init__(message)
        self.status = status


def token_from_env():
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise MapillaryError(
            "Set your Mapillary client token first, for example:\n"
            "    export %s='MLY|...'\n"
            "(Find it under Developers on mapillary.com. Don't put it in a file in this repository.)" % TOKEN_ENV)
    return token


def _urlopen(url, headers, timeout=60):
    req = urllib.request.Request(url, headers=dict(headers, **{"User-Agent": USER_AGENT}))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


class Client(object):
    """
    ``fetch(url, headers) -> bytes`` does the actual request; the tests pass a
    fake one. It should raise urllib.error.HTTPError for HTTP errors.
    """

    def __init__(self, token, cache_dir=None, pause=0.1, fetch=_urlopen, log=print):
        self.token = token
        self.cache_dir = cache_dir
        self.pause = pause
        self.fetch = fetch
        self.log = log
        self.requests = 0

    def _get(self, url, headers, what, uses_token=True):
        """GET with retries. ``what`` names the request in messages (never the token).

        uses_token=False for downloads that don't send the token (photo files,
        the license text), so a refusal isn't blamed on the token.
        """
        delay = max(self.pause, 1.0)
        for attempt in range(TRIES):
            try:
                self.requests += 1
                data = self.fetch(url, headers)
                if self.pause:
                    time.sleep(self.pause)
                return data
            except urllib.error.HTTPError as e:
                status = e.code
                if status in (401, 403) and not uses_token:
                    raise MapillaryError("%s refused the download (%s for %s)." % (
                        urllib.parse.urlparse(url).netloc, status, what), status)
                if status in (401, 403):
                    raise MapillaryError("Mapillary refused the token (%s for %s). Check %s." % (status, what, TOKEN_ENV), status)
                if status == 404:
                    raise MapillaryError("Not found: %s" % what, status)
                if status not in (429, 500, 502, 503, 504) or attempt == TRIES - 1:
                    raise MapillaryError("Mapillary answered %s for %s." % (status, what), status)
                problem = "busy (%s)" % status
            except (urllib.error.URLError, OSError) as e:
                if attempt == TRIES - 1:
                    raise MapillaryError("Couldn't reach Mapillary for %s: %s" % (what, getattr(e, "reason", e)))
                problem = "no answer"
            self.log("  Mapillary %s for %s; trying again in %d s" % (problem, what, delay))
            time.sleep(delay)
            delay *= 4
        raise MapillaryError("Gave up on %s." % what)

    # ------------------------------------------------------------ coverage tiles

    def tile(self, z, x, y):
        """A coverage tile's bytes (from the cache when we already have it)."""
        path = os.path.join(self.cache_dir, "tiles", str(z), str(x), "%d.mvt" % y) if self.cache_dir else None
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
        url = TILE_URL.format(z=z, x=x, y=y) + "?" + urllib.parse.urlencode({"access_token": self.token})
        try:
            data = self._get(url, {}, "tile %d/%d/%d" % (z, x, y))
        except MapillaryError as e:
            if e.status == 404:  # no photos in this square
                data = b""
            else:
                raise
        if path:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path + ".part", "wb") as f:
                f.write(data)
            os.replace(path + ".part", path)
        return data

    # ------------------------------------------------------------ graph API

    def image(self, image_id):
        """A photo's details (see IMAGE_FIELDS)."""
        url = GRAPH_URL + urllib.parse.quote(str(image_id)) + "?" + urllib.parse.urlencode({"fields": IMAGE_FIELDS})
        data = self._get(url, {"Authorization": "OAuth " + self.token}, "photo %s" % image_id)
        return json.loads(data.decode("utf-8"))

    def download(self, url, what):
        """A file that needs no token: a photo (its address comes from the Graph API) or the license text."""
        return self._get(url, {}, what, uses_token=False)
