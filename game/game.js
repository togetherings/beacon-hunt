/* BeaconHunt: look at a street photo and find where it was taken.
 *
 * The Kolibri Games server ("photo-guess" service) does the real work: it
 * picks the photos from the device's photo packs, sends one round at a time,
 * and only says where a photo was taken after the guess. This page shows the
 * photo and the map and passes on the learner's guess:
 *
 *   KolibriGames.start()                                the rounds and the first photo
 *   KolibriGames.move("guess", {country: "SLE"})        country mode
 *   KolibriGames.move("guess", {lat: 8.5, lon: -13.2})  location mode
 *   KolibriGames.finish({})                             the server adds up the points
 *
 * The game's "map" setting is the whole world or one continent, and "mode"
 * is country or location (see kolibri-game.json).
 */
(function () {
  "use strict";
  var KG = window.KolibriGames;
  var $ = function (id) { return document.getElementById(id); };

  // The continents (the same as beacon_pack/regions.py and kolibri-game.json): the area
  // each map shows, [west, south, east, north] in degrees. Countries with land on the
  // continent are bright; the rest of the world is faded but still there.
  var CONTINENTS = {
    "africa": { title: "Africa", bounds: [-26, -36, 60, 38] },
    "europe": { title: "Europe", bounds: [-25, 34, 65, 72] },
    "north-america": { title: "North America", bounds: [-170, 5, -15, 78] },
    "south-america": { title: "South America", bounds: [-92, -56, -30, 13] },
    "west-south-asia": { title: "West and South Asia", bounds: [25, -2, 98, 56] },
    "east-asia": { title: "East and Southeast Asia", bounds: [60, -12, 180, 78] },
    "oceania": { title: "Oceania", bounds: [110, -50, 180, 10] }
  };

  // What a country guess earned (the server decides; see kolibri_games/photoguess.py).
  var TIERS = {
    right: "Right!",
    neighbour: "Close: next door.",
    region: "Same part of the world.",
    continent: "Same continent.",
    none: "Not this time."
  };

  var S = { info: null, state: null, guess: null, busy: false, map: null, viewer: null };

  // ------------------------------------------------------------------ helpers

  function show(id) {
    ["intro", "play", "done"].forEach(function (s) { $(s).hidden = s !== id; });
    $("hud").hidden = id !== "play";
    document.body.setAttribute("data-screen", id);
  }

  function num(n) { return String(Math.round(n || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, ","); }

  function clock(sec) {
    sec = Math.max(0, Math.round(sec || 0));
    return Math.floor(sec / 60) + ":" + (sec % 60 < 10 ? "0" : "") + (sec % 60);
  }

  function error(where, text) {
    var e = $(where + "-error");
    e.textContent = text || "";
    e.hidden = !text;
  }

  function mapTitle(id) {
    return CONTINENTS[id] ? CONTINENTS[id].title : "the whole world";
  }

  // Show the game's map: the whole world, or a continent with the rest faded.
  function focusMap(id) {
    var c = CONTINENTS[id], countries = window.BEACON_MAP.countries;
    if (!c) return S.map.focus(null);
    S.map.focus(Object.keys(countries).filter(function (k) {
      return (countries[k].continents || []).indexOf(id) >= 0;
    }), c.bounds);
  }

  function isLocation() { return S.state && S.state.mode === "location"; }

  // ------------------------------------------------------------------ rounds

  function drawHud() {
    var p = S.state;
    $("hud-round").textContent = "Round " + p.round + " of " + p.rounds;
    $("hud-points").textContent = num(p.total) + " points";
  }

  // A new photo to guess.
  function drawRound() {
    var p = S.state;
    drawHud();
    S.guess = null;
    $("result").hidden = true;
    $("guessbar").hidden = false;
    $("pick-name").textContent = isLocation() ? "Click the map where you think it is" : "Click a country on the map";
    $("btn-guess").disabled = true;
    S.map.clear();
    error("play", "");
    S.viewer.show(p.photo.url, p.photo.pano).catch(function (e) { error("play", e.message); });
  }

  function onPick(key, name) {
    if (S.busy || !$("result").hidden) return;
    S.guess = key;
    $("pick-name").textContent = name;
    $("btn-guess").disabled = false;
  }

  function onPin(lat, lon) {
    if (S.busy || !$("result").hidden) return;
    S.guess = { lat: lat, lon: lon };
    $("pick-name").textContent = "Your pin: " + Math.abs(lat).toFixed(1) + "°" + (lat < 0 ? "S" : "N") + ", " +
      Math.abs(lon).toFixed(1) + "°" + (lon < 0 ? "W" : "E");
    $("btn-guess").disabled = false;
  }

  function guess() {
    if (S.busy || !S.guess) return;
    S.busy = true;
    $("btn-guess").disabled = true;
    error("play", "");
    var data = isLocation() ? S.guess : { country: S.guess };
    KG.move("guess", data).then(function (reply) {
      S.state = reply;
      drawResult(reply.result, reply.done);
    }).catch(function (e) {
      error("play", e.message);
      $("btn-guess").disabled = false;
    }).then(function () { S.busy = false; });
  }

  // What happened in a round: right or wrong, how far, the points and who took the photo.
  function drawResult(r, done) {
    $("guessbar").hidden = true;
    $("result").hidden = false;
    var good = isLocation() ? r.points >= 500 : r.tier === "right";
    $("result").className = "result " + (good ? "right" : "wrong");
    if (isLocation()) {
      $("result-title").textContent = (r.distance_km < 1 ? "Spot on" : num(r.distance_km) + " km away") +
        ". It's in " + r.answer_name + ".";
      $("result-detail").textContent = r.points >= 900 ? "Brilliant!" : r.points >= 500 ? "Good guess." : "";
    } else {
      $("result-title").textContent = r.tier === "right" ? "Right! It's " + r.answer_name + "." : "It's " + r.answer_name + ".";
      $("result-detail").textContent = r.tier === "right" ? "Well spotted." : TIERS[r.tier] + " You guessed " + r.guess_name + ".";
    }
    $("result-points").textContent = "+" + num(r.points) + " points";
    var c = r.credit || {};
    $("credit").textContent = "Photo by " + (c.author || "unknown") + " on " + (c.source || "Mapillary") +
      (c.captured ? ", " + c.captured : "") + ". " + (c.license || "CC BY-SA 4.0") + ".";
    $("credit-url").textContent = (c.url || "").replace(/^https?:\/\/(www\.)?/, "");
    $("btn-next").textContent = done ? "See your score" : "Next photo";
    drawHud();
    $("hud-round").textContent = "Round " + r.round + " of " + S.state.rounds;
    S.map.reveal(r.answer, r.guess, r.lat, r.lon, isLocation() ? { lat: r.guess_lat, lon: r.guess_lon } : null);
    $("btn-next").focus();
  }

  function next() {
    if (S.state.done) finish();
    else drawRound();
  }

  // ------------------------------------------------------------------ start and end

  function begin() {
    error("intro", "");
    $("btn-start").disabled = true;
    KG.start({ resume: true }).then(function (res) {
      S.state = res.public;
      show("play");
      if (!S.map) {
        S.map = BeaconMap.create($("map"), window.BEACON_MAP, { onPick: onPick, onPin: onPin });
        S.viewer = BeaconViewer.create($("photo"));
        window.BeaconHuntMap = S.map;   // for the browser test and for debugging in the console
      }
      S.map.setMode(S.state.mode);
      focusMap(S.state.map);
      if (S.state.done) return finish();
      drawRound();
    }).catch(function (e) {
      error("intro", e.message);
    }).then(function () { $("btn-start").disabled = false; });
  }

  function finish() {
    return KG.finish({}).then(function (res) {
      var a = res.attempt, d = a.detail || {};
      $("done-title").textContent = num(a.score) + " points";
      var location = d.mode === "location", time = a.seconds ? " in " + clock(a.seconds) : "";
      $("done-summary").textContent = location
        ? "Your pins were " + num(d.average_km) + " km away on average" + time + "."
        : "You found " + (d.correct || 0) + " of " + (d.rounds || []).length + " countries" + time + ".";
      $("rounds-guess").textContent = location ? "Distance" : "Your guess";
      var body = $("rounds").querySelector("tbody");
      body.innerHTML = "";
      (d.rounds || []).forEach(function (r) {
        var tr = document.createElement("tr");
        tr.className = r.correct || (location && r.points >= 500) ? "right" : "wrong";
        var guessed = location ? num(r.distance_km) + " km" : r.correct ? "Right" : r.guess_name;
        [r.round, r.answer_name, guessed, num(r.points)].forEach(function (v, i) {
          var td = document.createElement("td");
          td.textContent = v;
          if (i === 0 || i === 3) td.className = "num";
          tr.appendChild(td);
        });
        body.appendChild(tr);
      });
      var note = "";
      if (res.standing) note = "You're number " + res.standing.rank + " of " + res.standing.of + " on the scoreboard.";
      $("done-standing").textContent = note;
      show("done");
      if (S.info && S.info.challenge) return KG.scoreboard().then(drawBoard);
      $("board").hidden = true;
    }).catch(function (err) {
      $("done-title").textContent = "Couldn't save your score";
      $("done-summary").textContent = err.message;
      show("done");
    });
  }

  function drawBoard(data) {
    var rows = (data && data.rows) || [];
    var body = $("board").querySelector("tbody");
    body.innerHTML = "";
    rows.slice(0, 10).forEach(function (r) {
      var tr = document.createElement("tr");
      if (r.me) tr.className = "me";
      [r.rank, r.name + (r.me ? " (you)" : ""), num(r.score), clock(r.seconds)].forEach(function (v, i) {
        var td = document.createElement("td");
        td.textContent = v;
        if (i !== 1) td.className = "num";
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
    $("board").hidden = rows.length === 0;
  }

  // ------------------------------------------------------------------ controls

  $("btn-start").addEventListener("click", begin);
  $("btn-guess").addEventListener("click", guess);
  $("btn-next").addEventListener("click", next);
  $("btn-again").addEventListener("click", function () { show("intro"); begin(); });
  $("btn-exit").addEventListener("click", function () { KG.exit(); });
  $("zoom-in").addEventListener("click", function () { S.map.zoomIn(); });
  $("zoom-out").addEventListener("click", function () { S.map.zoomOut(); });
  $("zoom-home").addEventListener("click", function () { S.map.reset(); });
  // On small screens the photo and the map share the screen; this button gives one of them more room.
  $("btn-swap").addEventListener("click", function () {
    var big = document.body.classList.toggle("big-map");
    $("btn-swap").textContent = big ? "Bigger photo" : "Bigger map";
    setTimeout(function () { S.viewer.redraw(); S.map.reset(); }, 50);
  });

  KG.on("timeup", function () {
    $("done-title").textContent = "Time's up";
    $("done-summary").textContent = "You ran out of time.";
    $("rounds").querySelector("tbody").innerHTML = "";
    $("done-standing").textContent = "";
    $("board").hidden = true;
    show("done");
  });

  // ------------------------------------------------------------------ start up

  KG.ready().then(function (info) {
    S.info = info;
    if (info.preview) {
      $("intro-rule").textContent = "BeaconHunt needs Kolibri Games to play, because the server keeps the answers.";
      $("btn-start").disabled = true;
      return;
    }
    var settings = info.settings || {}, c = info.challenge;
    var bits = [];
    if (c) bits.push("Challenge: " + c.title + ".");
    bits.push((settings.rounds || 5) + " photos from " + mapTitle(settings.map) + ".");
    bits.push(settings.mode === "location"
      ? "Put a pin where you think each photo was taken: the closer, the more points."
      : "Find the country each photo was taken in.");
    if (info.rules && info.rules.time_limit) bits.push("You have " + Math.round(info.rules.time_limit / 60) + " minutes.");
    $("intro-rule").textContent = bits.join(" ");
  }).catch(function (err) { error("intro", err.message); });
})();
