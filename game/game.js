/* BeaconHunt: look at a street photo and guess which country it was taken in.
 *
 * The Kolibri Games server ("photo-guess" service) does the real work: it
 * picks the photos from the device's photo packs, sends one round at a time,
 * and only says where a photo was taken after the guess. This page shows the
 * photo and the map and passes on the learner's guess:
 *
 *   KolibriGames.start()                         the rounds and the first photo
 *   KolibriGames.move("guess", {country: "SLE"}) the answer, the points and the next photo
 *   KolibriGames.finish({})                      the server adds up the points
 */
(function () {
  "use strict";
  var KG = window.KolibriGames;
  var $ = function (id) { return document.getElementById(id); };

  // The UN sub-regions in each region's photo pack (the same as beacon_pack/regions.py).
  // The map zooms to the region and fades the rest of the world.
  var REGIONS = {
    "west-africa": ["Western Africa"],
    "north-africa": ["Northern Africa"],
    "east-africa": ["Eastern Africa"],
    "central-africa": ["Middle Africa"],
    "southern-africa": ["Southern Africa"],
    "northern-america": ["Northern America"],
    "central-america": ["Central America"],
    "caribbean": ["Caribbean"],
    "south-america": ["South America"],
    "northern-europe": ["Northern Europe"],
    "western-europe": ["Western Europe"],
    "southern-europe": ["Southern Europe"],
    "eastern-europe": ["Eastern Europe"],
    "western-asia": ["Western Asia"],
    "central-asia": ["Central Asia"],
    "southern-asia": ["Southern Asia"],
    "eastern-asia": ["Eastern Asia"],
    "south-eastern-asia": ["South-Eastern Asia"],
    "oceania": ["Australia and New Zealand"],
    "pacific-islands": ["Melanesia", "Micronesia", "Polynesia"]
  };

  var S = { info: null, state: null, guess: null, busy: false, map: null, viewer: null, region: "world" };

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

  // The countries of a region, as the pack tool picks them: territories only in
  // the island regions (the Caribbean and the Pacific). null: the whole world.
  function regionCountries(id) {
    var subs = REGIONS[id];
    if (!subs) return null;
    var islands = id === "caribbean" || id === "pacific-islands", countries = window.BEACON_MAP.countries;
    return Object.keys(countries).filter(function (k) {
      var c = countries[k];
      return subs.indexOf(c.sub) >= 0 && (islands || c.kind !== "territory");
    });
  }

  function regionTitle(id) {
    if (!id || id === "world") return "the whole world";
    return id.split("-").map(function (w) { return w.charAt(0).toUpperCase() + w.slice(1); }).join(" ");
  }

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
    $("pick-name").textContent = "Click a country on the map";
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

  function guess() {
    if (S.busy || !S.guess) return;
    S.busy = true;
    $("btn-guess").disabled = true;
    error("play", "");
    KG.move("guess", { country: S.guess }).then(function (reply) {
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
    $("result").className = "result " + (r.correct ? "right" : "wrong");
    $("result-title").textContent = r.correct ? "Right! It's " + r.answer_name + "." : "It's " + r.answer_name + ".";
    $("result-detail").textContent = r.correct ? "Well spotted." :
      "You guessed " + r.guess_name + ", about " + num(r.distance_km) + " km away.";
    $("result-points").textContent = "+" + num(r.points) + " points";
    var c = r.credit || {};
    $("credit").textContent = "Photo by " + (c.author || "unknown") + " on " + (c.source || "Mapillary") +
      (c.captured ? ", " + c.captured : "") + ". " + (c.license || "CC BY-SA 4.0") + ".";
    $("credit-url").textContent = (c.url || "").replace(/^https?:\/\/(www\.)?/, "");
    $("btn-next").textContent = done ? "See your score" : "Next photo";
    drawHud();
    $("hud-round").textContent = "Round " + r.round + " of " + S.state.rounds;
    S.map.reveal(r.answer, r.guess, r.lat, r.lon);
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
        S.map = BeaconMap.create($("map"), window.BEACON_MAP, { onPick: onPick });
        S.viewer = BeaconViewer.create($("photo"));
        window.BeaconHuntMap = S.map;   // for the browser test and for debugging in the console
      }
      S.map.focus(regionCountries(S.region));
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
      $("done-summary").textContent = "You found " + (d.correct || 0) + " of " + (d.rounds || []).length +
        " countries" + (a.seconds ? " in " + clock(a.seconds) : "") + ".";
      var body = $("rounds").querySelector("tbody");
      body.innerHTML = "";
      (d.rounds || []).forEach(function (r) {
        var tr = document.createElement("tr");
        tr.className = r.correct ? "right" : "wrong";
        [r.round, r.answer_name, r.correct ? "Right" : r.guess_name, r.correct ? "" : num(r.distance_km) + " km",
         num(r.points)].forEach(function (v, i) {
          var td = document.createElement("td");
          td.textContent = v;
          if (i === 0 || i >= 3) td.className = "num";
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
    S.region = settings.region || "world";
    var bits = [];
    if (c) bits.push("Challenge: " + c.title + ".");
    bits.push((settings.rounds || 5) + " photos from " + regionTitle(S.region) + ".");
    if (info.rules && info.rules.time_limit) bits.push("You have " + Math.round(info.rules.time_limit / 60) + " minutes.");
    $("intro-rule").textContent = bits.join(" ");
  }).catch(function (err) { error("intro", err.message); });
})();
