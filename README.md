# BeaconHunt

A geography game for [Kolibri Games](https://github.com/togetherings/kolibri-games): look at a
street photo (often a 360° one you can look around in) and find the country it was taken in.
Built for offline learning on Internet-in-a-Box and other Kolibri servers.

* Two modes. **Country:** click the country; the right one scores 1,000, a country next door
  500, one in the same part of the world (UN sub-region) 300 and one on the same continent 100.
  **Place:** put a pin where you think the photo was taken; up to 1,000 points, fewer the further
  away. A game has 1 to 10 photos (5 by default).
* Maps: the whole world, or one of seven continents (Africa, Europe, North America, South
  America, West and South Asia, East and Southeast Asia, Oceania). Coaches choose, and can set
  class challenges where everyone gets the same photos.
* The server keeps the answers: the browser never learns where a photo was taken until the
  learner has guessed, and hidden GPS data is removed from the photos.
* Photos come from [Mapillary](https://www.mapillary.com) (CC BY-SA 4.0), in photo packs made
  with this repository's pack tool, one pack per UN sub-region.

## What's here

| Folder | What it is |
|---|---|
| `game/` | the game: `kolibri-game.json`, the page, the map and the photo viewer |
| `game/map/` | the world map, from the SINGE geography game's map (Natural Earth borders, public domain) |
| `beacon_pack/` | the pack tool, `beacon-pack` (Python, standard library only) |
| `tools/import_singe_map.py` | makes `game/map/` from SINGE's map |
| `tests/` | tests, a pretend Mapillary and a demo pack |
| `docs/PACK_TOOL.md` | how to make photo packs |

## Install the game

Needs Kolibri Games 0.2.0 or later.

1. Download `beacon-hunt-<version>.zip` from this repository's
   [Releases](https://github.com/togetherings/beacon-hunt/releases).
2. In Kolibri, open **Games**, then **Setup** (device administrators), and install the zip.
3. Copy one or more photo packs into the photo-packs folder (see
   [docs/PACK_TOOL.md](docs/PACK_TOOL.md)). The Setup page lists the packs it finds.

## Make photo packs

See [docs/PACK_TOOL.md](docs/PACK_TOOL.md). In short, with your Mapillary client token:

```bash
pip install -e .
export MAPILLARY_TOKEN='MLY|...'
beacon-pack build west-africa --out packs --zip
```

## Try it on your computer

With Kolibri Games' preview server (no Kolibri needed):

```bash
pip install "kolibri-games @ git+https://github.com/togetherings/kolibri-games" pillow
python -m tests.make_demo_pack demo-packs          # 10 drawn "photos", no internet needed
mkdir -p demo-games && ln -s "$PWD/game" demo-games/beacon-hunt
kolibri-games-preview demo-games --photos demo-packs
```

Then open http://127.0.0.1:8765/.

## Tests

```bash
pip install -e ".[test]" "kolibri-games @ git+https://github.com/togetherings/kolibri-games"
python -m pytest                 # the pack tool (against a pretend Mapillary) and the game files
python -m tests.e2e_browser      # plays the game in a browser (Playwright with Chromium)
```

## How it works

The game is a page in Kolibri Games' sandbox. It uses the plugin's `photo-guess` service:

```
KolibriGames.start()                          -> the number of rounds and the first photo
KolibriGames.move("guess", {country: "SLE"})  -> how good the guess was, the points, the credit, the next photo
KolibriGames.move("guess", {lat: 8.5, lon: -13.2})  -> the same, in place mode, with the distance
KolibriGames.finish({})                       -> the server adds up the score
```

* `game/map.js` draws the map from `game/map/world.js` (SVG paths in a Miller projection) and
  handles zooming, panning and picking a country. Tiny countries get a circle to click, and small
  islands also appear, enlarged, in boxes under the map.
* `game/viewer.js` shows 360° photos with a small WebGL viewer (drag, wheel or pinch, arrow keys)
  and ordinary photos with click-to-zoom.
* `game/map/countries.json` gives each country's name, a point inside it, the regions and
  continents it has land in, its neighbours, and its weight: (area × population)^¼, from
  Natural Earth's populations. Country mode picks countries by the weight, place mode by its
  square, with caps set in `kolibri-game.json`. The server uses it to score country guesses; the
  pack tool uses the map to check which country each
  photo is in.

## License

The code is MIT (see LICENSE). The map is from Natural Earth (public domain) by way of SINGE.
Photo packs are CC BY-SA 4.0 (Mapillary contributors) and are not part of this repository.
