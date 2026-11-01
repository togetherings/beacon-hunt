"""
Make a small demo photo pack, offline, by running the real pack tool against
the pretend Mapillary (tests/fake_mapillary.py) with drawn pictures instead of
real photos. For trying the game and for the browser test. Needs Pillow.

    python -m tests.make_demo_pack OUTPUT_FOLDER
"""
import io
import sys

from PIL import Image, ImageDraw

from beacon_pack import build
from beacon_pack.mapillary import Client
from tests import fake_mapillary

# (lat, lon, 360°?) well inside West African countries
SPOTS = [
    (8.48, -13.23, True), (7.96, -11.74, False),      # Sierra Leone
    (6.31, -10.8, True), (6.75, -9.6, False),         # Liberia
    (5.6, -0.19, True), (6.69, -1.62, False),         # Ghana
    (14.69, -17.44, True), (12.37, -1.52, True),      # Senegal, Burkina Faso
    (6.52, 3.38, True), (9.06, 7.49, False),          # Nigeria
]


def picture(n, pano):
    """A pretend street scene: sky, ground, a road and a few buildings, with a number."""
    w, h = (2048, 1024) if pano else (1600, 1200)
    img = Image.new("RGB", (w, h), (120, 170, 230))
    d = ImageDraw.Draw(img)
    d.rectangle([0, h * 0.55, w, h], fill=(150 + n * 7 % 60, 110, 70))
    d.polygon([(w * 0.42, h), (w * 0.58, h), (w * 0.51, h * 0.55), (w * 0.49, h * 0.55)], fill=(70, 70, 75))
    for i in range(6):
        x = (i * 337 + n * 91) % (w - 200)
        d.rectangle([x, h * 0.35, x + 160, h * 0.56], fill=(200 + i * 9, 190 - i * 15, 160), outline=(60, 50, 40), width=4)
    d.text((w * 0.05, h * 0.08), "Demo photo %d%s" % (n, " (360)" if pano else ""), fill=(255, 255, 255))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=70)
    return out.getvalue()


def make(folder):
    photos = [(5000 + i, lat, lon, pano) for i, (lat, lon, pano) in enumerate(SPOTS)]
    fake = fake_mapillary.FakeMapillary(photos)
    pictures = {str(p[0]): picture(i, p[3]) for i, p in enumerate(photos)}

    def fetch(url, headers):
        if url.startswith("https://cdn.example/"):
            return pictures[url.rsplit("/", 1)[1][:-4]]
        return fake(url, headers)

    client = Client("MLY|test", pause=0, fetch=fetch, log=lambda *a: None)
    opts = build.Options(places=len(SPOTS), min_per_country=1, countries=["SLE", "LBR", "GHA", "SEN", "BFA", "NGA"],
                         legal_text="(The full CC BY-SA 4.0 license would be here.)")
    return build.build("west-africa", folder, client, opts, log=lambda *a: None)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    info, places = make(sys.argv[1])
    print("%d places in %s/west-africa" % (len(places), sys.argv[1]))
