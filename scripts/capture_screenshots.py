#!/usr/bin/env python3
"""Take real screenshots of project websites and use them as card covers.

A project gets a screenshot when its project.json has "screenshot": true and a
link in "screenshotUrl" or "projectUrl". The picture is saved as
content/projects/<slug>/screenshot.jpg and project.json "image" is pointed at
it. Repos found by scan_projects.py (discovered.json) that have a homepage get
a screenshot in content/projects/_shots/<slug>.jpg.

Existing screenshots are kept unless --refresh is passed, so the repo does not
gain a new image every day.

Needs Playwright:
    pip install playwright && python -m playwright install --with-deps chromium
Run from the repository root:
    python3 scripts/capture_screenshots.py [--refresh]
"""

import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "content" / "projects"
SHOTS = PROJECTS / "_shots"
VIEWPORT = {"width": 1440, "height": 900}
SKIP_HOSTS = ("youtube.com", "youtu.be")  # consent walls and video players make poor covers


def load_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


STORE_STRIP = """<!doctype html><html><head><style>
html,body{margin:0;height:100%}
body{display:flex;align-items:center;justify-content:center;gap:28px;background:#eef0f3;padding:56px 48px;box-sizing:border-box}
img{height:100%;max-height:788px;border-radius:22px;box-shadow:0 12px 32px rgba(0,0,0,.18);object-fit:contain}
</style></head><body>{imgs}</body></html>"""


async def capture_play_store(browser, url, out_path):
    """Build a cover from the app's own screenshots on its Google Play listing."""
    context = await browser.new_context(viewport=VIEWPORT, locale="en-US")
    page = await context.new_page()
    try:
        await page.goto(url + ("&" if "?" in url else "?") + "hl=en&gl=US", wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3000)
        # The app's screenshots are the large portrait images hosted on play-lh;
        # the icon and small related-app images are left out.
        srcs = await page.evaluate("""() => Array.from(document.querySelectorAll('img'))
            .filter(e => /play-lh\\.googleusercontent\\.com/.test(e.currentSrc || e.src || ''))
            .filter(e => !/icon/i.test(e.alt || ''))
            .filter(e => { const r = e.getBoundingClientRect(); return r.height >= 200 && r.height > r.width; })
            .map(e => e.currentSrc || e.src)""")
        srcs = [s.split("=")[0] + "=h1000" if "googleusercontent" in s else s for s in dict.fromkeys(srcs)]
        if not srcs:
            print("  no store screenshots found; taking a page screenshot", file=sys.stderr)
            return False
        imgs = "".join(f'<img src="{s}">' for s in srcs[:4])
        await page.set_content(STORE_STRIP.replace("{imgs}", imgs), wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(1000)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(out_path), type="jpeg", quality=85)
        return True
    except Exception as err:
        print(f"  store capture failed: {err}", file=sys.stderr)
        return False
    finally:
        await context.close()


async def capture(browser, url, out_path):
    if "play.google.com/store/apps" in url and await capture_play_store(browser, url, out_path):
        return True
    context = await browser.new_context(
        viewport=VIEWPORT,
        device_scale_factor=1,
        color_scheme="light",
        locale="en-US",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    )
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass  # some sites keep long-lived connections open
        await page.wait_for_timeout(2500)  # let fonts, images and animations settle
        out_path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(out_path), type="jpeg", quality=82, full_page=False)
        return True
    except Exception as err:
        print(f"  failed: {err}", file=sys.stderr)
        return False
    finally:
        await context.close()


async def main(refresh):
    manifest = load_json(PROJECTS / "index.json", {"projects": []})
    jobs = []

    for folder in manifest.get("projects", []):
        path = PROJECTS / folder / "project.json"
        project = load_json(path)
        if not project or not project.get("screenshot"):
            continue
        url = project.get("screenshotUrl") or project.get("projectUrl")
        if not url or any(h in url for h in SKIP_HOSTS):
            print(f"skip  {folder}: no website link")
            continue
        jobs.append(("project", folder, url, PROJECTS / folder / "screenshot.jpg", path))

    discovered_path = PROJECTS / "discovered.json"
    discovered = load_json(discovered_path, {"projects": []}) or {"projects": []}
    for item in discovered.get("projects", []):
        url = item.get("projectUrl")
        if url and not any(h in url for h in SKIP_HOSTS):
            jobs.append(("discovered", item["slug"], url, SHOTS / f"{item['slug']}.jpg", None))

    changed_discovered = False
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for kind, slug, url, out_path, json_path in jobs:
            if out_path.exists() and not refresh:
                print(f"keep  {slug}: screenshot exists")
                ok = True
            else:
                print(f"shoot {slug}: {url}")
                ok = await capture(browser, url, out_path)
            if not ok:
                continue
            if kind == "project":
                project = load_json(json_path)
                if project.get("image") != "screenshot.jpg":
                    project["image"] = "screenshot.jpg"
                    project["imageAlt"] = f"Screenshot of {project.get('name', slug)} website"
                    write_json(json_path, project)
            else:
                rel = out_path.relative_to(ROOT).as_posix()
                for item in discovered["projects"]:
                    if item["slug"] == slug and item.get("image") != rel:
                        item["image"] = rel
                        item["imageAlt"] = f"Screenshot of {item.get('name', slug)} website"
                        changed_discovered = True
        await browser.close()

    if changed_discovered:
        write_json(discovered_path, discovered)


if __name__ == "__main__":
    asyncio.run(main("--refresh" in sys.argv))
