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
    assert {s["key"]: s["type"] for s in m["settings"]} == {"region": "photo_region", "rounds": "integer"}
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


def test_the_game_knows_the_same_regions_as_the_pack_tool():
    js = read("game", "game.js")
    block = js[js.index("var REGIONS = {"):js.index("};", js.index("var REGIONS = {"))]
    in_game = {k: re.findall(r'"([^"]+)"', v) for k, v in re.findall(r'"([a-z-]+)": \[([^\]]*)\]', block)}
    assert in_game == {rid: subs for rid, (_t, subs, _terr) in regions.REGIONS.items()}
    islands = re.search(r'islands = (.*?),', js).group(1)
    assert sorted(re.findall(r'"([a-z-]+)"', islands)) == sorted(r for r, v in regions.REGIONS.items() if v[2])


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
