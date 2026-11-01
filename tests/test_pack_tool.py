"""The pack tool, run against a pretend Mapillary (tests/fake_mapillary.py)."""
import json
import os
import random
import zipfile

import pytest

from beacon_pack import build, check, geo, mvt, regions
from beacon_pack.mapillary import Client, MapillaryError
from tests.fake_mapillary import FakeMapillary

# Spots well inside each country (lat, lon), and a few that must be skipped.
SLE = [(8.48, -13.23), (8.97, -11.9), (7.96, -11.74), (9.3, -12.4), (8.1, -12.6), (8.7, -12.0)]
LBR = [(6.31, -10.8), (6.75, -9.6), (6.5, -9.9)]
GHA = [(5.6, -0.19), (6.69, -1.62), (9.4, -0.85)]
NEAR_BORDER = [(9.92, -12.0)]   # Sierra Leone, a few km from Guinea
SEA = [(5.0, -20.0)]
FRANCE = [(48.85, 2.35)]


def photos():
    out, n = [], 1000
    for spots, pano in ((SLE, True), (LBR, False), (GHA, True), (NEAR_BORDER, True), (SEA, True), (FRANCE, True)):
        for lat, lon in spots:
            n += 1
            out.append((n, lat, lon, pano))
    return out


def quiet(*_a):
    pass


def make(tmp_path, places=8, **kw):
    fake = FakeMapillary(photos(), **{k: kw.pop(k) for k in ("moved", "broken") if k in kw})
    client = Client("MLY|test", pause=0, fetch=fake, log=quiet)
    opts = build.Options(places=places, min_per_country=kw.pop("min_per_country", 2),
                         countries=kw.pop("countries", ["SLE", "LBR", "GHA"]), **kw)
    info, chosen = build.build("west-africa", str(tmp_path), client, opts, log=quiet)
    return fake, info, chosen


# ------------------------------------------------------------------ pieces


def test_the_map_knows_where_places_are():
    world = geo.WorldMap()
    assert world.locate(8.484, -13.234) == ("SLE", "ok")      # Freetown
    assert world.locate(14.69, -17.44)[0] == "SEN"             # Dakar, on the coast
    assert world.locate(9.92, -12.0)[0] is None                 # next to Guinea
    assert world.locate(5.0, -20.0) == (None, "not on land on the map")
    assert 850000 < world.area_km2("NGA") < 1000000


def test_regions_are_un_sub_regions():
    assert regions.countries_in("west-africa") == [
        "BEN", "BFA", "CIV", "CPV", "GHA", "GIN", "GMB", "GNB", "LBR", "MLI", "MRT", "NER", "NGA", "SEN", "SLE", "TGO"]
    seen = {}
    for rid in regions.REGIONS:
        for c in regions.countries_in(rid):
            assert c not in seen, "%s is in %s and %s" % (c, seen[c], rid)
            seen[c] = rid


def test_vector_tiles_round_trip():
    tile = mvt.encode({"sequence": [({"id": "s1", "image_id": 123456789012345, "is_pano": True},
                                     [(0, 0), (4096, 4096)], 2)]})
    (props, points), = mvt.decode(tile, 8, 120, 121)["sequence"]
    assert props == {"id": "s1", "image_id": 123456789012345, "is_pano": True}
    assert points[0] == mvt.tile_to_lon_lat(8, 120, 121) and points[1] == mvt.tile_to_lon_lat(8, 121, 122)


def test_places_are_shared_out_by_size():
    world = geo.WorldMap()
    found = {"NGA": [0] * 500, "GMB": [0] * 500, "CPV": [0] * 3}
    quota = build.share_out(world, found, 100, 10)
    assert sum(quota.values()) == 100 and quota["CPV"] == 3 and quota["NGA"] > 3 * quota["GMB"] >= 30


def test_spread_puts_panoramas_first_and_spreads_out():
    world = geo.WorldMap()
    city = [{"lat": 8.48 + i * 0.001, "lon": -13.23, "pano": False} for i in range(50)]
    far = [{"lat": 9.5, "lon": -11.5, "pano": True}]
    order = build.spread(world, city + far, 2, random.Random(1))
    assert far[0] in order[:2]


# ------------------------------------------------------------------ the whole tool


def test_a_pack_is_built_and_passes_its_check(tmp_path):
    fake, info, chosen = make(tmp_path, make_zip=True)
    pack = tmp_path / "west-africa"
    assert info["countries"] == ["GHA", "LBR", "SLE"] and info["places"] == 8 == len(chosen)
    places = json.loads((pack / "places.json").read_text())
    assert {p["country"] for p in places} == {"SLE", "LBR", "GHA"}
    assert not any(abs(p["lat"] - 9.92) < 0.01 or p["lat"] > 40 for p in places)  # border, France skipped
    p = places[0]
    assert p["photo"] == "photos/%s.jpg" % p["id"]
    assert p["credit"]["url"] == "https://www.mapillary.com/app/?pKey=" + p["id"]
    assert p["credit"]["license"] == "CC BY-SA 4.0" and p["credit"]["captured"] == "2023-07-22"
    photo = (pack / p["photo"]).read_bytes()
    assert photo.startswith(b"\xff\xd8") and b"GPS" not in photo
    assert "pretend legal code" in (pack / "LICENSE.txt").read_text()
    assert p["id"] in (pack / "CREDITS.txt").read_text()
    problems, summary = check.check_pack(str(pack))
    assert problems == [] and summary["places"] == 8
    with zipfile.ZipFile(str(tmp_path / "west-africa.zip")) as z:
        assert "pack.json" in z.namelist() and z.getinfo(p["photo"]).compress_type == zipfile.ZIP_STORED
    assert check.check_pack(str(tmp_path / "west-africa.zip"))[0] == []


def test_a_second_run_reuses_what_it_has(tmp_path):
    fake, _info, first = make(tmp_path)
    fake2, _info, second = make(tmp_path)
    assert [p["id"] for p in first] == [p["id"] for p in second]
    assert fake2.calls == [] or all("creativecommons" in c for c in fake2.calls)


def test_photos_that_moved_or_vanished_are_replaced(tmp_path):
    # Photo 1001 (Freetown) turns out to be in Liberia, and 1002 doesn't exist any more.
    _fake, _info, chosen = make(tmp_path, places=12, moved={1001: (6.31, -10.8)}, broken={1002})
    ids = {p["id"] for p in chosen}
    assert "1001" not in ids and "1002" not in ids and len(chosen) == 10  # 12 wanted, 10 usable


def test_the_token_is_never_shown(tmp_path):
    fake = FakeMapillary(photos())
    client = Client("MLY|wrong", pause=0, fetch=fake, log=quiet)
    with pytest.raises(MapillaryError) as e:
        build.build("west-africa", str(tmp_path), client, build.Options(countries=["SLE"]), log=quiet)
    assert "refused the token" in str(e.value) and "MLY|" not in str(e.value)
    for root, _dirs, files in os.walk(str(tmp_path)):
        for name in files:
            with open(os.path.join(root, name), "rb") as f:
                assert b"MLY|" not in f.read()


def test_the_check_finds_problems(tmp_path):
    make(tmp_path)
    pack = tmp_path / "west-africa"
    places = json.loads((pack / "places.json").read_text())
    places[0]["country"] = "FRA"
    os.remove(str(pack / places[1]["photo"]))
    (pack / "places.json").write_text(json.dumps(places))
    problems, _ = check.check_pack(str(pack))
    text = " ".join(problems)
    assert "not in FRA" in text and "no photo" in text and "countries don't match" in text


def test_a_refused_license_download_isnt_blamed_on_the_token(tmp_path):
    fake = FakeMapillary(photos())
    def fetch(url, headers):
        if "creativecommons.org" in url:
            raise fake._error(url, 403)
        return fake(url, headers)

    messages = []
    client = Client("MLY|test", pause=0, fetch=fetch, log=quiet)
    build.build("west-africa", str(tmp_path), client, build.Options(places=3, countries=["SLE"]), log=messages.append)
    text = " ".join(messages)
    assert "creativecommons.org refused the download" in text and "token" not in text
    assert build.LEGALCODE_URL in (tmp_path / "west-africa" / "LICENSE.txt").read_text()
