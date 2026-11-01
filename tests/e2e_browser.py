"""
Browser test: plays BeaconHunt through Kolibri Games' preview server (the real
games page, SDK, sandbox and photo-guess service), with the demo photo pack.
Needs kolibri-games (0.2.0 or later), Playwright with Chromium, and Pillow.

    python -m tests.e2e_browser [--screenshots DIR]
"""
import argparse
import json
import os
import shutil
import tempfile
import threading
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = "f-org.togetherings.beacon-hunt"


def serve(port):
    work = tempfile.mkdtemp(prefix="beacon-hunt-e2e-")
    games = os.path.join(work, "games")
    os.makedirs(games)
    shutil.copytree(os.path.join(ROOT, "game"), os.path.join(games, "beacon-hunt"))
    from tests.make_demo_pack import make

    make(os.path.join(work, "packs"))
    os.environ["KOLIBRI_GAMES_PATH"] = games
    os.environ["KOLIBRI_HOME"] = os.path.join(work, "home")
    os.environ["KOLIBRI_GAMES_DATA_PHOTO_PACKS"] = os.path.join(work, "packs")
    os.environ["KOLIBRI_GAMES_DEV_QUIET"] = "1"
    from kolibri_games import devserver, registry

    registry.discover(refresh=True)
    server = ThreadingHTTPServer(("127.0.0.1", port), devserver.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, devserver, work


def answers(devserver, work):
    """The newest attempt's places (the test peeks at the server; a learner can't)."""
    attempt = devserver.store._attempts[-1]
    with open(os.path.join(work, "packs", "west-africa", "places.json")) as f:
        places = {p["id"]: p for p in json.load(f)}
    return [places[ref.split("/")[1]] for ref in attempt.state["places"]]


def click_map(page, frame, script, arg):
    inner = frame.locator("#map").element_handle().owner_frame()
    pos = inner.evaluate(script, arg)
    box = page.locator("iframe.game-frame").bounding_box()
    page.mouse.click(box["x"] + pos["x"], box["y"] + pos["y"])


def click_country(page, frame, code):
    """Click a country on the map at its point (where the game draws its circle if it's tiny)."""
    click_map(page, frame, "(code) => window.BeaconHuntMap.center(code)", code)


def click_spot(page, frame, lat, lon):
    click_map(page, frame, "(p) => window.BeaconHuntMap.pointAt(p[0], p[1])", [lat, lon])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshots", default=None)
    parser.add_argument("--port", type=int, default=8798)
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright

    shots = args.screenshots
    if shots:
        os.makedirs(shots, exist_ok=True)
    server, devserver, work = serve(args.port)
    base = "http://127.0.0.1:%d/" % args.port
    errors = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.on("pageerror", lambda e: errors.append("page: %s" % e))
            page.on("console", lambda m: m.type == "error" and errors.append("console: %s" % m.text))

            # The game is on the lobby, and playable (the photo pack was found).
            page.goto(base + "?as=amina")
            page.locator(".game", has_text="BeaconHunt").wait_for()

            # The coach sets it to 3 photos on the Africa map, finding the country.
            page.goto(base + "?as=coach#/settings/" + GAME)
            page.select_option("#f-g-map", label="Africa (10 photos)")
            page.locator("#f-g-rounds").fill("3")
            page.locator("button:has-text('Save settings')").click()
            page.locator("text=Settings saved.").first.wait_for()

            page.goto(base + "?as=amina#/play/" + GAME)
            frame = page.frame_locator("iframe.game-frame")
            frame.locator("#intro-rule:has-text('from Africa')").wait_for()
            if shots:
                page.screenshot(path=os.path.join(shots, "1-intro.png"))
            frame.locator("#btn-start").click()
            frame.locator("#play:not([hidden])").wait_for()
            frame.locator("#photo:not(.loading)").wait_for()
            frame.locator("#map path[data-key='SLE']").first.wait_for()

            want = [p["country"] for p in answers(devserver, work)]
            assert len(want) == 3, want
            for i, answer in enumerate(want):
                frame.locator("#photo:not(.loading)").wait_for()
                mode = frame.locator("#photo").get_attribute("data-mode")
                assert mode in ("pano", "flat"), mode
                if mode == "pano":   # drag to look around: the picture changes
                    canvas = frame.locator("canvas.pano")
                    before = canvas.screenshot()
                    b = canvas.bounding_box()
                    page.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
                    page.mouse.down()
                    page.mouse.move(b["x"] + b["width"] / 2 - 200, b["y"] + b["height"] / 2, steps=5)
                    page.mouse.up()
                    page.wait_for_timeout(100)
                    assert canvas.screenshot() != before, "dragging didn't turn the 360° photo"
                guess = answer if i > 0 else "KEN"   # Kenya: the same continent, nothing more
                click_country(page, frame, guess)
                frame.locator("#btn-guess:not([disabled])").wait_for()
                if shots and i == 0:
                    page.screenshot(path=os.path.join(shots, "2-guessing.png"))
                frame.locator("#btn-guess").press("Enter")   # (the preview server's bar covers the bottom of the page)
                frame.locator("#result:not([hidden])").wait_for()
                text = frame.locator("#result").inner_text()
                if i == 0:
                    assert "Same continent. You guessed Kenya." in text and "+100 points" in text, text
                    assert frame.locator("#map path.wrong").count() > 0
                    if shots:
                        page.screenshot(path=os.path.join(shots, "3-wrong-guess.png"))
                else:
                    assert text.startswith("Right!"), text
                assert "Mapillary" in text and "CC BY-SA 4.0" in text and "mapillary.com/app/?pKey=" in text
                assert frame.locator("#map .beacon").count() == 1
                frame.locator("#btn-next").press("Enter")

            frame.locator("#done:not([hidden])").wait_for()
            assert "found 2 of 3" in frame.locator("#done-summary").inner_text()
            assert frame.locator("#rounds tbody tr").count() == 3
            if shots:
                page.screenshot(path=os.path.join(shots, "4-score.png"))
            score = int(frame.locator("#done-title").inner_text().split()[0].replace(",", ""))
            assert score == 2100, score

            # A phone-sized screen: the photo is above the map.
            page.set_viewport_size({"width": 390, "height": 760})
            frame.locator("#btn-again").click()
            frame.locator("#play:not([hidden])").wait_for()
            frame.locator("#photo:not(.loading)").wait_for()
            photo = frame.locator("#photo").bounding_box()
            mapbox = frame.locator("#map").bounding_box()
            assert photo["y"] + photo["height"] <= mapbox["y"] + 1, (photo, mapbox)
            if shots:
                page.screenshot(path=os.path.join(shots, "5-phone.png"))

            # Location mode: put a pin on the photo's spot, then one about 300 km off.
            page.set_viewport_size({"width": 1280, "height": 800})
            page.goto(base + "?as=coach#/settings/" + GAME)
            page.select_option("#f-g-mode", label="The exact place (put a pin on the map)")
            page.select_option("#f-g-map", label="Africa (10 photos)")
            page.locator("#f-g-rounds").fill("2")
            page.locator("button:has-text('Save settings')").click()
            page.locator("text=Settings saved.").first.wait_for()
            page.goto(base + "?as=ben#/play/" + GAME)
            frame = page.frame_locator("iframe.game-frame")
            frame.locator("#intro-rule:has-text('Put a pin')").wait_for()
            frame.locator("#btn-start").click()
            frame.locator("#photo:not(.loading)").wait_for()
            spots = answers(devserver, work)
            for i, place in enumerate(spots):
                frame.locator("#photo:not(.loading)").wait_for()
                click_spot(page, frame, place["lat"] + (0 if i == 0 else 2.7), place["lon"])
                frame.locator("#map .pin").wait_for()
                frame.locator("#btn-guess:not([disabled])").wait_for()
                frame.locator("#btn-guess").press("Enter")
                frame.locator("#result:not([hidden])").wait_for()
                text = frame.locator("#result").inner_text()
                km = int(frame.locator("#result-title").inner_text().split(" km")[0].replace(",", "")) \
                    if " km away" in text else 0
                if i == 0:
                    assert km < 40, text
                    if shots:
                        page.screenshot(path=os.path.join(shots, "6-location.png"))
                else:
                    assert 250 < km < 350, text
                frame.locator("#btn-next").press("Enter")
            frame.locator("#done:not([hidden])").wait_for()
            assert "km away on average" in frame.locator("#done-summary").inner_text()
            browser.close()
    finally:
        server.shutdown()
        shutil.rmtree(work, ignore_errors=True)
    errors = [e for e in errors if "favicon" not in e]
    if errors:
        raise SystemExit("Browser errors:\n" + "\n".join(errors))
    print("BeaconHunt browser test passed.")


if __name__ == "__main__":
    main()
