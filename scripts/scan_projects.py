#!/usr/bin/env python3
"""Scan portfolio projects and update the site's data files.

1. Checks every project link in content/projects and records whether it
   responds, in content/projects/status.json. The page uses this to show
   "Live" or "Offline" and an "Online" marker next to each link.
2. Finds public GitHub repos that have the topic "portfolio" and lists any
   that are not yet a project folder in content/projects/discovered.json.
   The page shows them in the Projects database automatically.

Uses only the Python standard library. Run it from the repository root:
    python3 scripts/scan_projects.py
Set GITHUB_TOKEN to raise the GitHub API rate limit (the workflow does this).
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "content" / "projects"
GITHUB_USER = os.environ.get("PORTFOLIO_GITHUB_USER", "benkigera")
TOPIC = os.environ.get("PORTFOLIO_TOPIC", "portfolio")
UA = "Mozilla/5.0 (compatible; benkigera-portfolio-scanner/1.0; +https://benkigera.github.io/)"
TIMEOUT = 20


def load_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def check_url(url):
    """Return (ok, code). ok is None when the site blocks automated checks."""
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
                return True, res.status
        except urllib.error.HTTPError as err:
            if method == "HEAD" and err.code in (400, 403, 404, 405, 429, 501):
                continue  # some servers reject HEAD; retry with GET
            if err.code in (401, 403, 429):
                return None, err.code
            return False, err.code
        except Exception as err:  # DNS failure, timeout, TLS error
            if method == "HEAD":
                continue
            return False, type(err).__name__
    return False, "unknown"


def scan_links(folders):
    results = {}
    for folder in folders:
        project = load_json(PROJECTS / folder / "project.json")
        if not project:
            continue
        url = (project.get("projectUrl") or "").strip()
        if not url:
            continue
        ok, code = check_url(url)
        slug = project.get("slug") or folder
        entry = {"url": url, "code": code}
        if ok is not None:
            entry["ok"] = ok
        results[slug] = entry
        print(f"{'up  ' if ok else 'down' if ok is False else 'skip'}  {slug:28} {code}  {url}")
    return results


def github_get(url):
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as res:
        return json.loads(res.read().decode("utf-8"))


def title_from(name):
    return " ".join(part.capitalize() for part in name.replace("_", "-").split("-") if part)


def discover_repos(known_slugs, known_repos):
    found = []
    page = 1
    while True:
        repos = github_get(f"https://api.github.com/users/{GITHUB_USER}/repos?per_page=100&page={page}&sort=pushed")
        if not repos:
            break
        for repo in repos:
            topics = repo.get("topics") or []
            if TOPIC not in topics or repo.get("fork") or repo.get("archived"):
                continue
            slug = repo["name"].lower()
            if slug in known_slugs or repo["full_name"].lower() in known_repos:
                continue
            pushed = datetime.fromisoformat(repo["pushed_at"].replace("Z", "+00:00"))
            recent = datetime.now(timezone.utc) - pushed < timedelta(days=60)
            found.append({
                "slug": slug,
                "name": title_from(repo["name"]),
                "icon": "📦",
                "category": repo.get("language") or "Project",
                "year": repo["created_at"][:4],
                "status": "In progress",
                "group": "Now building" if recent else "Selected work",
                "description": repo.get("description") or "",
                "longDescription": repo.get("description") or "",
                "projectUrl": repo.get("homepage") or "",
                "repoUrl": repo["html_url"],
                "ctaLabel": "View Project",
                "tags": [t for t in topics if t != TOPIC][:4],
            })
        if len(repos) < 100:
            break
        page += 1
    return found


def main():
    manifest = load_json(PROJECTS / "index.json", {"projects": []})
    folders = manifest.get("projects", [])

    known_slugs, known_repos = set(), set()
    for folder in folders:
        project = load_json(PROJECTS / folder / "project.json", {}) or {}
        known_slugs.add((project.get("slug") or folder).lower())
        if project.get("repo"):
            known_repos.add(project["repo"].lower())

    try:
        discovered = discover_repos(known_slugs, known_repos)
        write_json(PROJECTS / "discovered.json", {"projects": discovered})
        print(f"discovered {len(discovered)} repo(s) tagged '{TOPIC}'")
    except Exception as err:
        print(f"GitHub discovery skipped: {err}", file=sys.stderr)
        discovered = (load_json(PROJECTS / "discovered.json", {}) or {}).get("projects", [])

    links = scan_links(folders)
    for project in discovered:
        if project.get("projectUrl"):
            ok, code = check_url(project["projectUrl"])
            entry = {"url": project["projectUrl"], "code": code}
            if ok is not None:
                entry["ok"] = ok
            links[project["slug"]] = entry

    write_json(PROJECTS / "status.json", {
        "checked": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "projects": links,
    })


if __name__ == "__main__":
    main()
