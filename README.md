# benkigera.github.io

Personal portfolio, styled as a Notion page. Plain HTML, CSS and JavaScript, served by GitHub Pages.

## Add or change a project

Each project is a folder in `content/projects/<slug>/` with a `project.json` and an optional cover image.

1. Create the folder and `project.json` (copy an existing one).
2. Add the slug to `content/projects/index.json`. The order in that list is the order on the page.
3. Set `"group": "Now building"` to show it in the first view. Anything else appears under "All work".

Useful fields: `name`, `icon` (an emoji), `category`, `year`, `status` (`Live`, `Launching`, `In progress`, `Shipped`), `role`, `client`, `projectUrl`, `repo` (`owner/name`), `description`, `longDescription`, `tags`, `image`.

## Automatic project scan

`.github/workflows/scan-projects.yml` runs every day at 06:17 Nairobi time, on each push that changes project data, and on demand from the Actions tab. It does three things:

- **Checks every project link.** Results go to `content/projects/status.json`. If a link responds, a project marked `Launching` or `In progress` shows as `Live`. If a `Live` project's link stops responding, it shows as `Offline`.
- **Finds new repos.** Any public repo on github.com/benkigera with the topic `portfolio` that is not already a project folder appears on the page automatically, using the repo's name, description, homepage and topics. Repos pushed in the last 60 days go into "Now building". To give one a proper page, create a project folder for it and set `"repo": "benkigera/<name>"` so the scan stops listing it twice.

- **Takes real screenshots.** For every project with `"screenshot": true`, `scripts/capture_screenshots.py` opens the website in Chromium and saves `screenshot.jpg` in the project folder, then uses it as the cover. Set `screenshotUrl` to capture a different page than `projectUrl`. Screenshots are retaken every Monday, or when you run the workflow with "Retake every screenshot" checked. YouTube links are skipped. For a mobile app with no website, put your own phone screenshot in the folder and set `"image"` to its file name.

Run the scan locally with `python3 scripts/scan_projects.py`.
