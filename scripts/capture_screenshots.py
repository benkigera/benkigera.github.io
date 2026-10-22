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
import os
import shutil
import sys
import tempfile
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


def note(message):
    """Print a message and also show it as a warning on the GitHub Actions run."""
    print(f"  {message}", file=sys.stderr)
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::warning title=capture_screenshots::{message}")


def compose_strip(parts, out_path):
    """Lay phone screenshots side by side on a light background, 1440x900."""
    from PIL import Image, ImageDraw

    width, height, gap, pad = 1440, 900, 28, 64
    shots = [Image.open(p).convert("RGB") for p in parts][:4]
    # Pick one height so that every screenshot fits on a single row.
    ratio_sum = sum(im.width / im.height for im in shots)
    fit_h = (width - 2 * 48 - gap * (len(shots) - 1)) / ratio_sum
    target_h = int(min(height - 2 * pad, fit_h))
    scaled = [im.resize((round(im.width * target_h / im.height), target_h), Image.LANCZOS) for im in shots]
    total = sum(im.width for im in scaled) + gap * (len(scaled) - 1)
    top = (height - target_h) // 2
    canvas = Image.new("RGB", (width, height), (238, 240, 243))
    x = (width - total) // 2
    for im in scaled:
        mask = Image.new("L", im.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.width - 1, im.height - 1], radius=26, fill=255)
        canvas.paste(im, (x, top), mask)
        x += im.width + gap
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "JPEG", quality=86)


async def capture_play_store(browser, url, out_path):
    """Build a cover from the app's own screenshots on its Google Play listing."""
    context = await browser.new_context(viewport=VIEWPORT, device_scale_factor=3, locale="en-US")
    page = await context.new_page()
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        await page.goto(url + ("&" if "?" in url else "?") + "hl=en&gl=US", wait_until="domcontentloaded", timeout=45000)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        await page.wait_for_timeout(2500)
        # The app's screenshots are the tall portrait images in the listing.
        # Find them by their size on the page, not by Play's internal markup.
        found = []
        images = await page.query_selector_all("img")
        for img in images:
            box = await img.bounding_box()
            if not box:
                continue
            if 180 <= box["height"] <= 700 and box["height"] > box["width"] * 1.3 and box["y"] < 1600:
                found.append((box["y"], box["x"], img))
        found.sort(key=lambda item: (round(item[0] / 50), item[1]))
        note(f"{url}: {len(images)} images on page, {len(found)} portrait screenshots found")
        if not found:
            return False
        parts = []
        for i, (_, _, img) in enumerate(found[:5]):
            path = tmp_dir / f"shot{i}.png"
            await img.screenshot(path=str(path))
            parts.append(path)
        compose_strip(parts, out_path)
        return True
    except Exception as err:
        note(f"store capture failed for {url}: {err}")
        return False
    finally:
        await context.close()
        shutil.rmtree(tmp_dir, ignore_errors=True)


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
