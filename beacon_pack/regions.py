"""
The world regions a pack can cover. Each is one or more UN sub-regions (the
"sub" of each country in game/map/countries.json), so the regions fit together
into the whole world with no country in two of them.

Regions made mostly of islands that belong to other countries (the Caribbean,
the Pacific) include territories; the others include only UN members and
observers and partly recognised countries.
"""
from . import geo

# id: (title, [UN sub-regions], include territories)
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

COUNTRY_KINDS = ("un", "observer", "partial")


def countries_in(region_id, countries=None):
    """The country codes in a region, sorted."""
    if region_id not in REGIONS:
        raise KeyError(region_id)
    countries = countries or geo.load_countries()
    _title, subs, territories = REGIONS[region_id]
    return sorted(code for code, c in countries.items()
                  if c.get("sub") in subs and (territories or c.get("kind") in COUNTRY_KINDS))


def title(region_id):
    return REGIONS[region_id][0]
