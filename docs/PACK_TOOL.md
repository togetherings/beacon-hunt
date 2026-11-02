# Making photo packs

BeaconHunt's photos come in **photo packs**, one per region of the world (West Africa, South
America, and so on). The pack tool, `beacon-pack`, makes a pack from
[Mapillary](https://www.mapillary.com)'s street photos. Run it on a computer with internet (Linux,
macOS, or Windows with WSL), then copy the pack to the device.

The pack format is described in Kolibri Games' `docs/PHOTO_PACKS.md`. Change the two together.

## Set up (once)

You need Python 3.8 or later and a Mapillary client token: on mapillary.com, go to
**Developers**, register an app, and copy its **client token** (it starts with `MLY|`).

```bash
git clone https://github.com/togetherings/beacon-hunt
cd beacon-hunt
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

The tool uses only Python's standard library. It reads the game's map (`game/map/`), so run it
from this folder.

**Without a virtual environment.** On Ubuntu (and WSL), `python3 -m venv` fails until you
install `python3-venv` (`sudo apt install python3.12-venv`, with your Python's version). You can
skip the virtual environment and the `pip install` altogether: run the tool from this folder as
`python3 -m beacon_pack` in place of `beacon-pack`, for example
`python3 -m beacon_pack build west-africa --out packs --zip`.

## Make a pack

```bash
export MAPILLARY_TOKEN='MLY|...'      # your client token
beacon-pack build west-africa --out packs --zip
beacon-pack check packs/west-africa
```

The token is read from `MAPILLARY_TOKEN` and never written to a file or shown in a message.
Don't save it in a file inside this repository. To avoid typing it each time, put the `export`
line in `~/.bashrc` (outside the repository).

`beacon-pack regions` lists the regions (the UN's 20 sub-regions) and their countries.

**Left out:** disputed areas (Crimea, Western Sahara, Northern Cyprus and Somaliland) and some
territories (Jersey, Guernsey, the Isle of Man, Åland, Saint Pierre and Miquelon, Norfolk Island,
Saint Helena and the Indian Ocean Territories) aren't in the game. They're drawn on the map but
can't be picked, and photos taken there are skipped, never counted for a neighbouring country.
Territories in the Caribbean and the Pacific are in, and so are Hong Kong, Macau, Greenland, the
Faroe Islands, the Falkland Islands, Bermuda and Gibraltar.

### What it does

1. **Finds where Mapillary has photos**, from Mapillary's coverage map (vector tiles about 150 km
   across). Each *sequence* (a run of photos one person took one after another) is one possible
   place.
2. **Picks the places.** It keeps places inside one of the region's countries and at least 5 km
   from any other country, using the same map the learner clicks, so a photo is never "in" a
   different country on the map than in real life. Bigger countries get more places (by the
   square root of their area), and every country gets at least 15 if it has them. Inside a
   country the places are spread out on a grid, so a game doesn't keep showing the capital.
   360° photos are picked first in each grid square.
3. **Checks each photo** with Mapillary's Graph API: its exact location (checked again against
   the map), author, date and download address. Photos that fail are replaced by the next one.
4. **Downloads** the 2048-pixel version of each photo and removes any hidden data (EXIF with GPS,
   and so on).
5. **Works out how each photo is scored** in country mode: its region (where it was taken: a
   photo in Hawaii is in Polynesia; Russia east of the Urals is Northern Asia; Indonesian Papua is
   Melanesia), its continent, and which countries count as neighbours for it. A neighbour must
   border the photo's country (on land, or across up to about 150 km of water) and be within
   500 km of the photo: Cuba counts for a photo in Miami, not for one in Kansas.
6. **Writes** `pack.json`, `places.json`, `LICENSE.txt` (with the full CC BY-SA 4.0 text) and
   `CREDITS.txt`, and with `--zip`, `packs/west-africa.zip`.

Reading the coverage tiles and checking which country each possible place is in can take
several minutes for big, well-photographed regions (North and South America, Europe). The tool
prints its progress, and saves the result, so running it again skips this step.

You can stop it (Ctrl+C) at any time. Run the same command again and it carries on: coverage
tiles, photo details and downloaded photos are kept (in `packs/.build/`, which Kolibri Games
ignores). Running it again later with the same options gives the same places, plus any changes on
Mapillary.

### Options

| Option | What it does |
|---|---|
| `--places 1000` | how many places (default 1000) |
| `--zip` | also make `<region>.zip` |
| `--pano-only` | only 360° photos |
| `--since 2018` | skip photos taken before 2018 |
| `--countries SLE,LBR` | only these countries (for a small test pack) |
| `--border-km 5` | how far from other countries a photo must be |
| `--min-per-country 15` | places every country gets, if it has them |
| `--seed 2` | a different choice of places |
| `--pause 0.1` | seconds between requests |
| `--zoom 8` | zoom of the coverage tiles (higher: more detail, many more tiles) |

### How long and how big

For West Africa with 1,000 places, expect a few hundred coverage tiles, about 1,000 to 1,500
photo-detail requests and 1,000 downloads: well inside Mapillary's limits, and roughly half an
hour to an hour. A pack of 1,000 photos at 2048 pixels is about 0.4 to 0.8 GB; `beacon-pack
check` prints the real size.

A first small test:

```bash
beacon-pack build west-africa --countries SLE --places 20 --out test-packs
```

## Copy it to the device

Copy the pack folder (or the .zip) into the photo-packs folder:

* Internet-in-a-Box: `/library/kolibri/kolibri_games/photo-packs/`
* elsewhere: `<KOLIBRI_HOME>/kolibri_games/photo-packs/`

For example, with the zip on a USB stick, on the Pi:

```bash
sudo cp /media/usb/west-africa.zip /library/kolibri/kolibri_games/photo-packs/
```

Then open Kolibri Games' **Setup** page: the photo packs panel lists the pack and anything wrong
with it. BeaconHunt plays every pack's photos, on the whole world map or on a continent's map.

## The license

Mapillary's photos are under **CC BY-SA 4.0**. That means:

* credit the author: BeaconHunt shows the author, date, "Mapillary", the license and the photo's
  Mapillary address with every answer. On a device without internet the address is plain text,
  not a link, which the license allows (it asks for credit "reasonable to the medium").
* include the license: each pack has `LICENSE.txt` with the full text, and `CREDITS.txt`.
* share alike: a pack (or changed photos) you pass on stays under CC BY-SA 4.0.

The photos are not under this repository's MIT license, so packs are never committed here
(`packs/` is in `.gitignore`).
