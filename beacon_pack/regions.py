"""
Regions, continents and the special cases, shared by the pack tool and the
map import (tools/import_singe_map.py). The game has the same continent list
in game/kolibri-game.json and game/game.js; a test checks they match.

* **Regions** are the UN's 20 sub-regions (the "sub" of each country on the
  map). Photo packs are made one region at a time.
* **Continents** group the regions. They're the game's maps (besides the
  whole world), and a wrong country guess on the photo's continent scores 100.
* A country can be in more than one region (Russia: Eastern Europe and
  Northern Asia; France has land in the Caribbean, South America and East
  Africa). A photo's region is where it was taken: see photo_region().
* **Left out:** disputed areas (Crimea, Western Sahara, Northern Cyprus,
  Somaliland) can't be guessed, and photos taken there are skipped.
"""
from . import geo

#: Pack regions: id -> (title, [UN sub-regions], include territories).
#: Regions made mostly of islands that belong to other countries (the
#: Caribbean, the Pacific) include territories; the others include only UN
#: members, observers and partly recognised countries, plus INCLUDED_TERRITORIES.
REGIONS = {
    "west-africa": ("West Africa", ["Western Africa"], False),
    "north-africa": ("North Africa", ["Northern Africa"], False),
    "east-africa": ("East Africa", ["Eastern Africa"], False),
    "central-africa": ("Central Africa", ["Middle Africa"], False),
    "southern-africa": ("Southern Africa", ["Southern Africa"], False),
    "northern-america": ("Northern America", ["Northern America"], False),
    "central-america": ("Central America", ["Central America"], False),
    "caribbean": ("Caribbean", ["Caribbean"], True),
    "south-america": ("South America", ["South America"], False),
    "northern-europe": ("Northern Europe", ["Northern Europe"], False),
    "western-europe": ("Western Europe", ["Western Europe"], False),
    "southern-europe": ("Southern Europe", ["Southern Europe"], False),
    "eastern-europe": ("Eastern Europe", ["Eastern Europe"], False),
    "western-asia": ("Western Asia", ["Western Asia"], False),
    "central-asia": ("Central Asia", ["Central Asia"], False),
    "southern-asia": ("South Asia", ["Southern Asia"], False),
    "eastern-asia": ("East Asia", ["Eastern Asia"], False),
    "south-eastern-asia": ("Southeast Asia", ["South-Eastern Asia"], False),
    "oceania": ("Australia and New Zealand", ["Australia and New Zealand"], False),
    "pacific-islands": ("Pacific Islands", ["Melanesia", "Micronesia", "Polynesia"], True),
}

#: Asian Russia's region (not a UN sub-region: the UN puts all of Russia in Eastern Europe).
NORTHERN_ASIA = "Northern Asia"

#: Continents (the game's maps): id -> (title, [regions]).
CONTINENTS = {
    "africa": ("Africa", ["Northern Africa", "Western Africa", "Middle Africa", "Eastern Africa", "Southern Africa"]),
    "europe": ("Europe", ["Northern Europe", "Western Europe", "Southern Europe", "Eastern Europe"]),
    "north-america": ("North America", ["Northern America", "Central America", "Caribbean"]),
    "south-america": ("South America", ["South America"]),
    "west-south-asia": ("West and South Asia", ["Western Asia", "Central Asia", "Southern Asia"]),
    "east-asia": ("East and Southeast Asia", ["Eastern Asia", "South-Eastern Asia", NORTHERN_ASIA]),
    "oceania": ("Oceania", ["Australia and New Zealand", "Melanesia", "Micronesia", "Polynesia"]),
}

#: Territories that get photos even in regions that otherwise leave territories
#: out: places with their own look and plenty of photos on Mapillary.
INCLUDED_TERRITORIES = {"HKG", "MAC"}

#: Disputed areas left out of the game, at least for now.
EXCLUDED = {"XCR", "SAH", "CYN", "SOL"}


def continent_of(region):
    for cid, (_title, subs) in CONTINENTS.items():
        if region in subs:
            return cid
    return None


def photo_region(country, piece_region, lat, lon):
    """The region a photo counts as, from the part of the country it was taken in.

    * Russia east of the Urals (taken as 60°E, and the far east past 180°)
      is Northern Asia; west of it, Eastern Europe.
    * Indonesia's Papua (western New Guinea and the islands near it) is
      Melanesia; the rest of Indonesia is South-Eastern Asia.
    * Anywhere else: the region of the piece of the map the photo is in (so a
      photo in Hawaii is in Polynesia, one in Réunion in Eastern Africa).
    """
    if country == "RUS" and piece_region == "Eastern Europe" and (lon >= 60.0 or lon < 0):
        return NORTHERN_ASIA
    if country == "IDN" and in_papua(lat, lon):
        return "Melanesia"
    return piece_region


def in_papua(lat, lon):
    """Is this spot in Indonesian Papua (the Papua provinces)?

    Two boxes, drawn through the sea so they cut no island:

    * north of 2.55°S and east of 129.6°E: the Bird's Head, Raja Ampat
      (Waigeo, Batanta, Salawati, Misool, Kofiau), Biak and the north coast,
      but not Seram (its north coast is at about 2.8°S) or Halmahera and Gebe
      (west of 129.6°E);
    * east of 131.5°E and north of a line from 4.6°S at 131.5°E to 5.0°S at
      135.2°E and 9.5°S at 136.5°E (then 12°S): the rest of the island down
      to Merauke, but not the Kei, Aru or Tanimbar islands (Maluku).
    """
    if lon >= 129.6 and lat > -2.55:
        return True
    if lon < 131.5:
        return False
    line = [(131.5, -4.6), (135.2, -5.0), (136.5, -9.5), (180.0, -12.0)]
    for (x0, y0), (x1, y1) in zip(line, line[1:]):
        if x0 <= lon <= x1:
            return lat > y0 + (y1 - y0) * (lon - x0) / (x1 - x0)
    return False


def countries_in(region_id, countries=None):
    """The country codes in a pack region, sorted."""
    if region_id not in REGIONS:
        raise KeyError(region_id)
    countries = countries or geo.load_countries()
    _title, subs, territories = REGIONS[region_id]
    return sorted(code for code, c in countries.items()
                  if code not in EXCLUDED and c.get("sub") in subs
                  and (territories or c.get("kind") != "territory" or code in INCLUDED_TERRITORIES))


def title(region_id):
    return REGIONS[region_id][0]
