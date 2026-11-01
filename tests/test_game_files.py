"""The game's own files: its manifest, the map, and the things kept in step with the pack tool and Kolibri Games."""
import json
import os
import re

from beacon_pack import __version__, geo, jpeg, regions

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = os.path.join(ROOT, "game")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def test_the_manifest_matches_the_photo_guess_service():
    m = json.loads(read("game", "kolibri-game.json"))
    assert m["version"] == __version__, "the game and the pack tool share a version"
    assert m["service"] == "photo-guess" and m["data"] == [{"name": "photo-packs"}]
    assert os.path.exists(os.path.join(GAME, m["photos"]["countries"]))
    assert {s["key"]: s["type"] for s in m["settings"]} == {"mode": "choice", "map": "photo_map", "rounds": "integer"}
    for name in (m["entry"], m["icon"]):
        assert os.path.exists(os.path.join(GAME, name))


def test_the_manifest_is_valid_for_kolibri_games():
    try:
        from kolibri_games.manifest import loads
        from kolibri_games.pack import verify
        from kolibri_games.sources import FolderSource
    except ImportError:
        return  # Kolibri Games isn't installed here; CI checks this
    assert loads(read("game", "kolibri-game.json")).service == "photo-guess"
    manifest, problems = verify(FolderSource(GAME))
    assert problems == []


def test_every_country_can_be_scored_and_drawn():
    countries = geo.load_countries()
    world = geo.load_map()
    drawn = {r["key"] for r in world["regions"] if r.get("key") and not r.get("decor")}
    assert set(countries) == set(world["countries"])
    for code, c in countries.items():
        assert -60 <= c["lat"] <= 84 and -180 <= c["lon"] <= 180, code
        assert c["name"] and code in drawn, code
    # Each country's point is inside it, so a guess's distance is measured from the right place.
    m = geo.WorldMap(world)
    for code in ("SLE", "NGA", "GHA", "SEN", "MLI", "BRA", "FRA", "JPN", "AUS"):
        assert m.countries[code].contains(*m.xy(countries[code]["lat"], countries[code]["lon"])), code


def test_the_game_knows_the_same_continents_as_the_pack_tool():
    m = json.loads(read("game", "kolibri-game.json"))
    maps = {x["id"]: x["title"] for x in m["photos"]["maps"]}
    assert maps.pop("world") == "The whole world"
    assert maps == {cid: title for cid, (title, _subs) in regions.CONTINENTS.items()}
    js = read("game", "game.js")
    block = js[js.index("var CONTINENTS = {"):js.index("};", js.index("var CONTINENTS = {"))]
    assert dict(re.findall(r'"([a-z-]+)": \{ title: "([^"]+)"', block)) == maps
    # Every UN sub-region is on exactly one continent.
    subs = [s for _t, subs in regions.CONTINENTS.values() for s in subs]
    assert len(subs) == len(set(subs))
    assert {c["sub"] for c in geo.load_countries().values()} <= set(subs)


def test_countries_know_their_regions_continents_and_neighbours():
    c = geo.load_countries()
    assert not regions.EXCLUDED & set(c), "disputed areas are left out"
    assert {"HKG", "MAC", "GRL", "FRO", "FLK", "BMU", "GIB"} <= set(c)
    assert not {"JEY", "GGY", "IMN", "ALD", "SPM", "NFK", "SHN", "IOA"} & set(c), "other territories are left out"
    assert "PRI" in c and "PYF" in c  # island regions keep their territories
    world = geo.load_map()
    assert all(r.get("off") for r in world["regions"] if r.get("key") in ("JEY", "XCR")), "drawn, but can't be picked"
    assert c["RUS"]["continents"] == ["east-asia", "europe"] and "Northern Asia" in c["RUS"]["regions"]
    assert c["IDN"]["continents"] == ["east-asia", "oceania"] and c["TLS"]["continents"] == ["east-asia"]
    assert "south-america" in c["FRA"]["continents"]  # French Guiana
    assert "CUB" in c["USA"]["neighbours"] and "USA" in c["CUB"]["neighbours"]  # across water
    assert "FRA" in c["GBR"]["neighbours"] and "MYS" in c["SGP"]["neighbours"]
    assert "TUN" in c["ITA"]["neighbours"] and "AUS" not in c["TLS"]["neighbours"]
    # How often countries come up: (area x population) ** 1/4.
    for code in ("CHN", "NGA", "GRL", "LUX"):
        info = c[code]
        assert abs(info["weight"] - (info["area_km2"] * info["population"]) ** 0.25) <= 1, code
    assert c["GRL"]["weight"] < c["SLE"]["weight"] < c["NGA"]["weight"] < c["CHN"]["weight"]
    assert all(info["weight"] >= 1 and info["population"] > 0 for info in c.values())
    m = json.loads(read("game", "kolibri-game.json"))["photos"]
    assert m["weights"] == {"country": 1, "location": 2} and m["max_share"] and m["max_photo_ratio"]
    for code, info in c.items():
        for n in info["neighbours"]:
            assert code in c[n]["neighbours"], (code, n)


def test_tiny_places_and_left_out_places_are_found():
    w = geo.WorldMap()
    assert w.locate(36.14, -5.353)[0] == "GIB" and w.locate(41.9029, 12.4534)[0] == "VAT"
    assert w.locate(62.01, -6.77)[0] == "FRO" and w.locate(64.18, -51.72)[0] == "GRL"
    assert w.locate(49.19, -2.11) == (None, "in JEY, which the game leaves out")
    assert w.locate(44.95, 34.1)[0] is None  # Crimea


def test_where_russia_and_indonesia_are_split():
    assert regions.photo_region("RUS", "Eastern Europe", 55.75, 37.6) == "Eastern Europe"      # Moscow
    assert regions.photo_region("RUS", "Eastern Europe", 56.8, 60.6) == "Northern Asia"       # Yekaterinburg
    assert regions.photo_region("RUS", "Eastern Europe", 64.7, 177.5) == "Northern Asia"      # Anadyr
    assert regions.photo_region("RUS", "Eastern Europe", 66.0, -170.0) == "Northern Asia"     # Chukotka, past 180°
    papua = [(-2.53, 140.7), (-0.88, 131.25), (-0.2, 130.5), (-1.9, 130.0), (-8.5, 140.4), (-1.0, 136.1), (-3.1, 133.0)]
    rest = [(-3.7, 128.18), (-3.1, 130.5), (0.8, 127.4), (-0.2, 129.4), (-5.6, 132.7), (-6.2, 134.4), (-7.6, 131.4),
            (-8.56, 125.57), (-6.2, 106.8), (1.5, 124.8)]
    assert all(regions.in_papua(lat, lon) for lat, lon in papua)
    assert not any(regions.in_papua(lat, lon) for lat, lon in rest)
    assert regions.photo_region("IDN", "South-Eastern Asia", -2.53, 140.7) == "Melanesia"
    assert regions.photo_region("FRA", "South America", 4.93, -52.33) == "South America"


def test_metadata_stripping_matches_kolibri_games():
    try:
        from kolibri_games import photos
    except ImportError:
        return
    import inspect

    assert inspect.getsource(jpeg.strip_jpeg_metadata) == inspect.getsource(photos.strip_jpeg_metadata)


def test_the_page_loads_its_scripts_in_order():
    html = read("game", "index.html")
    scripts = re.findall(r'<script src="([^"]+)"', html)
    assert scripts == ["__kolibri_games__/sdk.js", "map/world.js", "map.js", "viewer.js", "game.js"]
    for s in scripts[1:]:
        assert os.path.exists(os.path.join(GAME, s)), s
