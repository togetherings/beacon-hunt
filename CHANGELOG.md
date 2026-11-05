# Changelog

## 0.1.0

First version. Needs Kolibri Games 0.2.0 or later. It's a Server Game (`"type": "server"`): the
plugin's server keeps the answers, so it's installed on the games page, not put in a channel.

- The game: a street photo (360° photos can be looked around) and a world map. Two modes: find
  the country (1,000 points, or 500 for a country next door, 300 for the same region, 100 for the
  same continent) or put a pin on the place (up to 1,000 points, fewer the further away).
- Maps: the whole world or one of seven continents. Disputed areas and some territories are left
  out for now.
- How often countries come up: by (area × population)^¼ in country mode, so small countries still
  come up regularly, and by its square in place mode, so big, populous countries come up much more
  often. No country gets more than 5% of the rounds, or much more than its share of the photos.
  Populations are Natural Earth's (`tools/population.json`).
- After each guess: the answer on the map, the points and the photo's credit. 1 to 10 photos a game.
- The pack tool, `beacon-pack`: makes a region's photo pack from Mapillary, spread over the
  region's countries and away from borders, with the photos' credits and license, and each
  photo's region, continent and neighbouring countries for scoring.
- The world map comes from SINGE (Natural Earth borders).
