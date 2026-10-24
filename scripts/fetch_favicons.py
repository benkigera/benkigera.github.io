#!/usr/bin/env python3
"""Fetch the real favicon of each live project site and save it as a tiny WebP.

For every project with a website in "projectUrl" (YouTube links are skipped),
the script opens the site in Chromium, finds the best icon the site declares
(<link rel="icon">, apple-touch-icon, or /favicon.ico), draws it at 96x96 with
a transparent background, and saves content/projects/<slug>/favicon.webp
(usually 1-4 KB). For a Google Play link it uses the app's store icon.
project.json then gets "favicon": "favicon.webp", and the page shows it in
place of the emoji.

Existing favicons are kept unless --refresh is passed.

Needs Playwright and Pillow. Run from the repository root:
    python3 scripts/fetch_favicons.py [--refresh]
"""

import asyncio
import base64
import io
import json
import os
import sys
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "content" / "projects"
SIZE = 96
SKIP_HOSTS = ("youtube.com", "youtu.be")

FIND_ICONS = """() => {
    const out = [];
    for (const link of document.querySelectorAll('link[rel]')) {
        const rel = link.rel.toLowerCase();
        if (!/(^|\\s)(icon|apple-touch-icon|apple-touch-icon-precomposed|shortcut)(\\s|$)/.test(rel)) continue;
        if (link.media && !matchMedia(link.media).matches) continue;
        let size = 0;
        const sizes = (link.getAttribute('sizes') || '').toLowerCase();
        if (sizes === 'any') size = 512;
        else for (const s of sizes.split(/\\s+/)) { const n = parseInt(s, 10); if (n > size) size = n; }
        const svg = /\\.svg(\\?|$)/i.test(link.href) || (link.type || '').includes('svg');
        if (svg) size = Math.max(size, 512);
        if (!size && rel.includes('apple-touch-icon')) size = 180;
        out.push({ href: link.href, size: size || 32 });
    }
    return out;
}"""

PLAY_ICON = """() => {
    const imgs = Array.from(document.querySelectorAll('img'))
        .filter(e => /play-lh\\.googleusercontent\\.com/.test(e.currentSrc || e.src || ''));
    const icon = imgs.find(e => /icon/i.test(e.alt || '')) || imgs.find(e => {
        const r = e.getBoundingClientRect(); return r.width >= 64 && Math.abs(r.width - r.height) < 4;
    });
    return icon ? (icon.currentSrc || icon.src).split('=')[0] + '=s192' : null;
}"""

RENDER = """<!doctype html><html><head><style>
html,body{margin:0;background:transparent}
img{display:block;width:%dpx;height:%dpx;object-fit:contain}
</style></head><body><img id="i" src="%s"></body></html>"""


def note(message):
    """Print a message and also show it as a warning on the GitHub Actions run."""
    print(f"  {message}", file=sys.stderr)
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::warning title=fetch_favicons::{message}")


def load_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


async def find_icon_urls(page, url):
    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    if "play.google.com/store/apps" in url:
        icon = await page.evaluate(PLAY_ICON)
        return [icon] if icon else []
    icons = await page.evaluate(FIND_ICONS)
    icons.sort(key=lambda i: -i["size"])
    origin = await page.evaluate("location.origin")
    urls = [i["href"] for i in icons] + [origin + "/favicon.ico"]
    return list(dict.fromkeys(urls))


async def icon_source(context, icon_url):
    """Download the icon with the browser's network stack and return a data: URL.

    Downloading first avoids sites that refuse icons loaded from another page.
    Falls back to the plain URL when the download fails.
    """
    try:
        res = await context.request.get(icon_url, timeout=20000, headers={"Accept": "image/*,*/*"})
        if not res.ok:
            return None, f"HTTP {res.status}"
        body = await res.body()
        if not body:
            return None, "empty file"
        ctype = (res.headers.get("content-type") or "").split(";")[0].strip()
        if not ctype.startswith("image/"):
            head = body[:200].lstrip().lower()
            if head.startswith(b"<svg") or b"<svg" in head:
                ctype = "image/svg+xml"
            elif body[:4] == b"\x00\x00\x01\x00":
                ctype = "image/x-icon"
            elif body[:8] == b"\x89PNG\r\n\x1a\n":
                ctype = "image/png"
            else:
                return None, f"not an image ({ctype or 'unknown type'})"
        return f"data:{ctype};base64," + base64.b64encode(body).decode("ascii"), ""
    except Exception as err:
        return icon_url, f"download failed ({type(err).__name__}), trying direct load"


async def render_icon(page, src):
    """Draw the icon at SIZE x SIZE in the browser (handles SVG and ICO) and return PNG bytes."""
    await page.set_content(RENDER % (SIZE, SIZE, src.replace('"', "%22")), wait_until="load", timeout=20000)
    ok = await page.evaluate("() => { const i = document.getElementById('i'); return i.complete && i.naturalWidth > 0; }")
    if not ok:
        return None
    return await page.locator("#i").screenshot(omit_background=True)


def check_icon(im):
    """Return a reason to reject the icon, or '' when it is usable at small sizes."""
    box = im.getbbox()
    if box is None:
        return "fully transparent"
    w, h = box[2] - box[0], box[3] - box[1]
    if w < 8 or h < 8:
        return "nearly empty"
    if w / h > 1.8 or h / w > 1.8:
        return "wide text logo, unreadable at icon size"
    return ""


async def fetch(browser, url, out_path):
    context = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        device_scale_factor=1,
        locale="en-US",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    )
    page = await context.new_page()
    try:
        candidates = await find_icon_urls(page, url)
        if not candidates:
            note(f"{url}: page lists no icons")
        reasons = []
        for icon_url in candidates:
            src, why = await icon_source(context, icon_url)
            if not src:
                reasons.append(f"{icon_url} ({why})")
                continue
            png = await render_icon(page, src)
            if not png:
                reasons.append(f"{icon_url} (browser could not draw it)")
                continue
            im = Image.open(io.BytesIO(png)).convert("RGBA")
            bad = check_icon(im)
            if bad:
                reasons.append(f"{icon_url} ({bad})")
                continue
            im.save(out_path, "WEBP", quality=82, method=6)
            print(f"  {out_path.stat().st_size} bytes from {icon_url}")
            return True
        note(f"{url}: no usable icon. Tried: " + "; ".join(reasons)[:900])
        return False
    except Exception as err:
        note(f"{url}: failed: {err}")
        return False
    finally:
        await context.close()


async def main(refresh):
    manifest = load_json(PROJECTS / "index.json", {"projects": []})
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for folder in manifest.get("projects", []):
            json_path = PROJECTS / folder / "project.json"
            project = load_json(json_path)
            if not project:
                continue
            url = (project.get("projectUrl") or "").strip()
            out_path = PROJECTS / folder / "favicon.webp"
            if not url or any(h in url for h in SKIP_HOSTS):
                continue
            if out_path.exists() and not refresh:
                ok = True
            else:
                print(f"icon  {folder}: {url}")
                ok = await fetch(browser, url, out_path)
            if ok and project.get("favicon") != "favicon.webp":
                project["favicon"] = "favicon.webp"
                write_json(json_path, project)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main("--refresh" in sys.argv))
