"""Record a short demo GIF of the live City Reps site for the README.

Drives the site in a headless browser (Playwright), takes a screenshot after
each step, and stitches them into assets/demo.gif with Pillow.

The clock is pinned to a weekday morning in Chicago so the picks show places
that are open, whatever time the workflow runs. A few sample reps are put in
the browser's storage so the streak tracker has something to show; they
exist only in that throwaway browser.

Run from the repo root:
    pip install playwright pillow && playwright install chromium
    python scripts/record_demo.py https://npsubaric.github.io/city-reps/ assets/demo.gif
"""
import asyncio
import io
import json
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from PIL import Image
from playwright.async_api import async_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "https://npsubaric.github.io/city-reps/"
OUT = sys.argv[2] if len(sys.argv) > 2 else "assets/demo.gif"
WIDTH, HEIGHT = 400, 760
CHICAGO = ZoneInfo("America/Chicago")


def demo_morning():
    """The most recent Tuesday at 10:30 AM in Chicago (a gym day with a target)."""
    today = datetime.now(CHICAGO).date()
    tuesday = today - timedelta(days=(today.weekday() - 1) % 7)
    return datetime(tuesday.year, tuesday.month, tuesday.day, 10, 30, tzinfo=CHICAGO), tuesday


def sample_reps(day: date):
    """Three earlier reps this week and last, so the tracker isn't empty."""
    def rep(days_ago, spot, kind, score, rpe):
        d = (day - timedelta(days=days_ago)).isoformat()
        return {"id": f"{d}-demo{days_ago}", "date": d, "type": kind, "spotId": spot,
                "spotName": "", "note": "", "created": 0, "score": score, "rpe": rpe}
    return [rep(1, "wt-library", "library", 8, 2), rep(5, "prequel", "cafe", 9, 3),
            rep(7, "humboldt-park", "outdoors", 8, 5)]


class Recorder:
    def __init__(self, page):
        self.page = page
        self.frames = []  # (PIL image, milliseconds to show it)

    async def shot(self, ms):
        png = await self.page.screenshot()
        self.frames.append((Image.open(io.BytesIO(png)).convert("RGB"), ms))

    async def scroll_to(self, selector, offset=-12, steps=6):
        """Scroll in a few small steps so the GIF shows movement, not a jump."""
        target = await self.page.evaluate(
            f"(() => {{ const el = document.querySelector({json.dumps(selector)});"
            f" return el ? el.getBoundingClientRect().top + window.scrollY + ({offset}) : null; }})()")
        if target is None:
            return False
        start = await self.page.evaluate("window.scrollY")
        for i in range(1, steps + 1):
            y = start + (target - start) * i / steps
            await self.page.evaluate(f"window.scrollTo(0, {y})")
            await self.page.wait_for_timeout(30)
            await self.shot(70)
        return True

    async def click(self, selector, wait=250):
        await self.page.click(selector)
        await self.page.wait_for_timeout(wait)


async def record():
    now, day = demo_morning()
    async with async_playwright() as p:
        # CHROME_PATH: use an installed Chrome instead of Playwright's own
        browser = await p.chromium.launch(executable_path=os.environ.get("CHROME_PATH"))
        context = await browser.new_context(
            viewport={"width": WIDTH, "height": HEIGHT}, timezone_id="America/Chicago",
            reduced_motion="reduce")
        page = await context.new_page()
        await page.clock.set_fixed_time(now)
        await page.add_init_script(
            f"localStorage.setItem('cr-reps', {json.dumps(json.dumps(sample_reps(day)))});"
            f"localStorage.setItem('cr-start', '{(day - timedelta(days=14)).isoformat()}');")
        await page.goto(URL, wait_until="networkidle")
        await page.wait_for_timeout(1500)
        r = Recorder(page)

        # 1. Today: the plan and the streak
        await r.shot(2200)

        # 2. The picker: open the "Where should I go?" sheet and answer a few questions
        await r.click("#filterBtn", wait=300)
        await r.shot(900)
        # (the defaults are focus, normal energy, 1-2 hours, walk, free only)
        for label in ["q-feel-recharge", "q-time-quick", "q-spend-coffee"]:
            await r.click(f"label[for={label}]")
            await r.shot(700)
        await r.click("#sheetGo", wait=400)

        # 3. The picks, with hours, license and inspection lines
        await r.scroll_to("#results", offset=-8)
        await r.shot(2600)
        await r.click("#shuffle", wait=400)
        await r.shot(1800)

        # 4. New near you (only when there are newly licensed places nearby)
        if await page.is_visible("#newSec"):
            await r.scroll_to("#newSec")
            await r.shot(2400)

        # 5. A pick on the full-screen map, then back to Explore
        await r.scroll_to("#results", offset=-8)
        await r.click("#results [data-show]", wait=500)
        await r.shot(2400)
        await r.click("#mapClose", wait=300)

        # 6. The directory: open now, then one spot opened up
        await r.scroll_to("#dirH")
        await r.click("label[for=fOpen]", wait=400)
        await r.shot(1500)
        await r.click("#dlist .dhead", wait=400)
        await r.shot(2400)

        # 7. Where the data comes from
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(300)
        await r.shot(2600)

        await browser.close()

    images = [img.quantize(colors=128, method=Image.Quantize.MEDIANCUT) for img, _ in r.frames]
    durations = [ms for _, ms in r.frames]
    images[0].save(OUT, save_all=True, append_images=images[1:], duration=durations,
                   loop=0, optimize=True, disposal=1)
    print(f"Wrote {OUT}: {len(images)} frames, {sum(durations) / 1000:.1f} s")


if __name__ == "__main__":
    asyncio.run(record())
