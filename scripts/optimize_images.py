#!/usr/bin/env python3
"""Make light WebP images for every project so the page loads fast.

For each project with an "image":
  - cover.webp  max 1280 px wide, used when a project page is opened
  - thumb.webp  640 px wide, used on the gallery cards
project.json gets "image": "cover.webp" and "thumb": "thumb.webp".
The original file is removed once cover.webp exists, unless it is
screenshot.webp from capture_screenshots.py (that one is kept as the source).

Run from the repository root:
    python3 scripts/optimize_images.py
Needs Pillow (pip install pillow).
"""

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "content" / "projects"
COVER_W, COVER_Q = 1280, 70
THUMB_W, THUMB_Q = 640, 62
KEEP_SOURCES = {"screenshot.webp"}


def save_webp(src, dest, width, quality):
    with Image.open(src) as im:
        im = im.convert("RGB")
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        im.save(dest, "WEBP", quality=quality, method=6)


def optimize_folder(folder):
    path = folder / "project.json"
    project = json.loads(path.read_text(encoding="utf-8"))
    image = project.get("image") or ""
    cover, thumb = folder / "cover.webp", folder / "thumb.webp"
    shot = folder / "screenshot.webp"

    # Pick the source: a fresh screenshot, else a new original image, else the cover itself.
    if shot.exists():
        src = shot
    elif image and not image.startswith(("http://", "https://", "/")) and (folder / image).exists():
        src = folder / image
    else:
        return False

    rebuilt = False
    if src != cover and (not cover.exists() or src.stat().st_mtime > cover.stat().st_mtime or image != "cover.webp"):
        save_webp(src, cover, COVER_W, COVER_Q)
        rebuilt = True
    if rebuilt or not thumb.exists():
        save_webp(cover, thumb, THUMB_W, THUMB_Q)

    if project.get("image") != "cover.webp" or project.get("thumb") != "thumb.webp":
        project["image"], project["thumb"] = "cover.webp", "thumb.webp"
        path.write_text(json.dumps(project, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if src.name not in KEEP_SOURCES and src.name not in ("cover.webp", "thumb.webp"):
        src.unlink()
    kb = lambda p: p.stat().st_size // 1024
    print(f"{folder.name:26} cover {kb(cover):>3} KB  thumb {kb(thumb):>3} KB")
    return True


def main():
    for folder in sorted(p for p in PROJECTS.iterdir() if (p / "project.json").exists()):
        optimize_folder(folder)


if __name__ == "__main__":
    main()
