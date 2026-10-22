// Projects database: loads project folders, link health, and discovered repos,
// then renders Notion-style gallery, table, and board views plus a page peek.
(function () {
    const BASE = "content/projects/";
    const view = document.getElementById("db-view");
    const foot = document.getElementById("db-foot");
    const search = document.getElementById("db-search");
    const tabs = Array.from(document.querySelectorAll(".db-tab"));
    const peek = document.getElementById("peek");

    let projects = [];
    let current = "now";
    let query = "";

    const STATUS_COLOR = {
        "Live": "green",
        "Launching": "yellow",
        "In progress": "blue",
        "Shipped": "gray",
        "Offline": "red"
    };
    const STATUS_ORDER = ["Live", "Launching", "In progress", "Shipped", "Offline"];
    const TAG_COLORS = ["blue", "purple", "pink", "orange", "green", "yellow", "brown", "red", "gray"];

    const ICONS = {
        status: '<svg viewBox="0 0 16 16"><path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 2a5 5 0 110 10A5 5 0 018 3z"/><circle cx="8" cy="8" r="2.5"/></svg>',
        select: '<svg viewBox="0 0 16 16"><path d="M8 1a7 7 0 100 14A7 7 0 008 1zm-2.5 5.5L8 9l2.5-2.5 1 1L8 11 4.5 7.5z"/></svg>',
        date: '<svg viewBox="0 0 16 16"><path d="M4 1h1.5v1.5h5V1H12v1.5h2V15H2V2.5h2zm-.5 5V13.5h9V6.5z"/></svg>',
        person: '<svg viewBox="0 0 16 16"><path d="M8 8a3 3 0 100-6 3 3 0 000 6zm0 1.5c-3 0-5.5 1.5-5.5 3.5V14h11v-1c0-2-2.5-3.5-5.5-3.5z"/></svg>',
        client: '<svg viewBox="0 0 16 16"><path d="M2 14V3l6-2v4l6 2v7zm2-9v1.5h1.5V5zm0 3v1.5h1.5V8zm0 3v1.5h1.5V11zm6-1v1.5h1.5V10z"/></svg>',
        url: '<svg viewBox="0 0 16 16"><path d="M6.4 9.6a3 3 0 004.2 0l3-3a3 3 0 00-4.2-4.2l-.9.9 1 1 .9-.9a1.6 1.6 0 112.2 2.2l-3 3a1.6 1.6 0 01-2.2 0l-1 1zm3.2-3.2a3 3 0 00-4.2 0l-3 3a3 3 0 004.2 4.2l.9-.9-1-1-.9.9a1.6 1.6 0 11-2.2-2.2l3-3a1.6 1.6 0 012.2 0l1-1z"/></svg>',
        tags: '<svg viewBox="0 0 16 16"><path d="M2 2h6l7 7-6 6-7-7zm3 2a1 1 0 100 2 1 1 0 000-2z"/></svg>',
        title: '<svg viewBox="0 0 16 16"><path d="M2 3h12v2H9v8H7V5H2z"/></svg>',
        code: '<svg viewBox="0 0 16 16"><path d="M5.3 4.3L1.6 8l3.7 3.7-1 1L-.1 8l4.4-4.7zm5.4 0l1-1L16.1 8l-4.4 4.7-1-1L14.4 8z"/></svg>'
    };

    async function getJSON(path, optional) {
        try {
            const res = await fetch(path, { cache: "no-store" });
            if (!res.ok) throw new Error(path + " " + res.status);
            return await res.json();
        } catch (err) {
            if (optional) return null;
            throw err;
        }
    }

    async function load() {
        try {
            const manifest = await getJSON(BASE + "index.json");
            const folders = Array.isArray(manifest.projects) ? manifest.projects : [];
            const [list, health, discovered] = await Promise.all([
                Promise.all(folders.map(async (folder) => {
                    const p = await getJSON(BASE + folder + "/project.json", true);
                    if (!p) return null;
                    return Object.assign({}, p, {
                        slug: p.slug || folder,
                        image: resolve(folder, p.image),
                        thumb: resolve(folder, p.thumb)
                    });
                })),
                getJSON(BASE + "status.json", true),
                getJSON(BASE + "discovered.json", true)
            ]);

            const known = new Set();
            projects = list.filter(Boolean).filter((p) => p.featured !== false);
            projects.forEach((p) => known.add(p.slug));

            if (discovered && Array.isArray(discovered.projects)) {
                discovered.projects.forEach((p, i) => {
                    if (!p.slug || known.has(p.slug)) return;
                    projects.push(Object.assign({ group: "Selected work", status: "In progress", order: 500 + i, discovered: true }, p));
                    known.add(p.slug);
                });
            }

            const checks = (health && health.projects) || {};
            projects.forEach((p) => {
                p.health = checks[p.slug] || null;
                p.displayStatus = displayStatus(p);
            });

            projects.sort((a, b) => (a.order ?? 999) - (b.order ?? 999));

            if (health && health.checked) {
                const when = formatDate(health.checked);
                const note = document.getElementById("scan-note");
                if (note) note.textContent = "Project links checked " + when;
                const edited = document.getElementById("edited");
                if (edited) edited.textContent = "Edited " + when;
            }

            render();
            openFromHash();
        } catch (err) {
            console.error(err);
            view.innerHTML = '<p class="muted">Projects could not load. Open the site through a web server or GitHub Pages.</p>';
        }
    }

    function displayStatus(p) {
        const declared = p.status || "In progress";
        if (!p.health || typeof p.health.ok !== "boolean" || !p.projectUrl) return declared;
        if (p.health.ok && ["Launching", "In progress", "Live"].includes(declared)) return "Live";
        if (!p.health.ok && declared === "Live") return "Offline";
        return declared;
    }

    function resolve(folder, path) {
        if (!path) return "";
        if (/^https?:\/\//.test(path) || path.startsWith("/")) return path;
        return BASE + folder + "/" + path;
    }

    function esc(value) {
        return String(value == null ? "" : value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    }

    function hashColor(text) {
        let h = 0;
        for (const ch of String(text)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
        return TAG_COLORS[h % TAG_COLORS.length];
    }

    function tag(text) { return '<span class="tag ' + hashColor(text) + '">' + esc(text) + "</span>"; }

    function statusPill(status) {
        return '<span class="status-pill ' + (STATUS_COLOR[status] || "gray") + '">' + esc(status) + "</span>";
    }

    function host(url) {
        try {
            const h = new URL(url).hostname.replace(/^www\./, "");
            if (h === "play.google.com") return "Google Play";
            if (h === "apps.apple.com") return "App Store";
            if (h.endsWith("youtube.com") || h === "youtu.be") return "YouTube";
            return h;
        } catch (e) { return url; }
    }

    function formatDate(iso) {
        const d = new Date(iso);
        if (isNaN(d)) return "";
        return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
    }

    function matches(p) {
        if (!query) return true;
        const hay = [p.name, p.category, p.description, p.client && p.client.name, (p.tags || []).join(" "), p.displayStatus].join(" ").toLowerCase();
        return hay.includes(query);
    }

    function visible() {
        let list = projects.filter(matches);
        if (current === "now") list = list.filter((p) => p.group === "Now building");
        return list;
    }

    function render() {
        tabs.forEach((t) => t.setAttribute("aria-selected", String(t.dataset.view === current)));
        const list = visible();
        if (!list.length) {
            view.innerHTML = '<p class="muted">No projects match.</p>';
        } else if (current === "table") {
            view.innerHTML = tableView(list);
        } else if (current === "board") {
            view.innerHTML = boardView(list);
        } else {
            view.innerHTML = '<div class="gallery">' + list.map(cardHTML).join("") + "</div>";
        }
        foot.textContent = list.length ? "Count " + list.length : "";
        view.querySelectorAll("[data-slug]").forEach((el) => {
            el.addEventListener("click", (e) => {
                if (e.target.closest("a")) return;
                openPeek(el.dataset.slug);
            });
            el.addEventListener("keydown", (e) => {
                if (el.tagName === "TR" && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openPeek(el.dataset.slug); }
            });
        });
    }

    function coverHTML(p, cls) {
        const src = p.thumb || p.image;
        if (src) return '<div class="' + cls + '"><img src="' + esc(src) + '" alt="' + esc(p.imageAlt || p.name) + '" loading="lazy" decoding="async" width="640" height="400"></div>';
        return '<div class="' + cls + ' empty" aria-hidden="true">' + esc(p.icon || "📄") + "</div>";
    }

    function cardHTML(p) {
        return '<button class="card" type="button" data-slug="' + esc(p.slug) + '">' +
            coverHTML(p, "card-cover") +
            '<div class="card-body">' +
            '<div class="card-title"><span class="ic" aria-hidden="true">' + esc(p.icon || "📄") + "</span>" + esc(p.name) + "</div>" +
            (p.description ? '<div class="card-text">' + esc(p.description) + "</div>" : "") +
            '<div class="card-props">' + statusPill(p.displayStatus) + (p.category ? tag(p.category) : "") + (p.year ? '<span class="tag">' + esc(p.year) + "</span>" : "") + "</div>" +
            "</div></button>";
    }

    function tableView(list) {
        const th = (icon, label) => '<th><span>' + ICONS[icon] + esc(label) + "</span></th>";
        const rows = list.map((p) => '<tr class="row" tabindex="0" data-slug="' + esc(p.slug) + '">' +
            '<td class="name-cell"><span class="ic" aria-hidden="true">' + esc(p.icon || "📄") + '</span><span class="t">' + esc(p.name) + "</span></td>" +
            "<td>" + statusPill(p.displayStatus) + "</td>" +
            "<td>" + (p.category ? tag(p.category) : "") + "</td>" +
            "<td>" + esc(p.year || "") + "</td>" +
            "<td>" + esc(p.role || (p.client && p.client.name) || "") + "</td>" +
            '<td class="url-cell">' + (p.projectUrl ? '<a href="' + esc(p.projectUrl) + '" target="_blank" rel="noreferrer">' + esc(host(p.projectUrl)) + "</a>" : "") + "</td>" +
            "</tr>").join("");
        return '<div class="table-wrap"><table class="db-table"><thead><tr>' +
            th("title", "Name") + th("status", "Status") + th("select", "Category") + th("date", "Year") + th("person", "Role / Client") + th("url", "Link") +
            "</tr></thead><tbody>" + rows + "</tbody></table></div>";
    }

    function boardView(list) {
        const groups = {};
        list.forEach((p) => { (groups[p.displayStatus] = groups[p.displayStatus] || []).push(p); });
        const keys = STATUS_ORDER.filter((k) => groups[k]).concat(Object.keys(groups).filter((k) => !STATUS_ORDER.includes(k)));
        return '<div class="board">' + keys.map((k) => '<div class="board-col"><div class="board-head">' + statusPill(k) + "<span>" + groups[k].length + "</span></div>" + groups[k].map(cardHTML).join("") + "</div>").join("") + "</div>";
    }

    // ---------- Peek ----------
    function prop(icon, name, valueHTML) {
        if (!valueHTML) return "";
        return '<div class="prop"><div class="prop-name">' + ICONS[icon] + esc(name) + '</div><div class="prop-value">' + valueHTML + "</div></div>";
    }

    function linkValue(p) {
        if (!p.projectUrl) return '<span class="muted">Link coming soon</span>';
        let health = "";
        if (p.health && typeof p.health.ok === "boolean") {
            health = p.health.ok
                ? ' <span class="status-pill green">Online</span>'
                : ' <span class="status-pill red">Not responding</span>';
        }
        return '<a href="' + esc(p.projectUrl) + '" target="_blank" rel="noreferrer">' + esc(host(p.projectUrl)) + "</a>" + health;
    }

    function openPeek(slug, fromHash) {
        const p = projects.find((x) => x.slug === slug);
        if (!p) return;

        document.getElementById("peek-cover").innerHTML = p.image ? '<img src="' + esc(p.image) + '" alt="' + esc(p.imageAlt || p.name) + '" decoding="async">' : "";
        document.getElementById("peek-cover").style.display = p.image ? "" : "none";
        document.getElementById("peek-icon").textContent = p.icon || "📄";
        document.getElementById("peek-title").textContent = p.name;
        document.getElementById("peek-crumb").textContent = "Projects / " + p.name;

        document.getElementById("peek-props").innerHTML =
            prop("status", "Status", statusPill(p.displayStatus)) +
            prop("select", "Category", p.category ? tag(p.category) : "") +
            prop("date", "Year", esc(p.year || "")) +
            prop("person", "Role", esc(p.role || "")) +
            prop("client", "Client", p.client && p.client.name ? (p.client.url ? '<a href="' + esc(p.client.url) + '" target="_blank" rel="noreferrer">' + esc(p.client.name) + "</a>" : esc(p.client.name)) : "") +
            prop("url", "Link", linkValue(p)) +
            prop("code", "Repository", p.repoUrl ? '<a href="' + esc(p.repoUrl) + '" target="_blank" rel="noreferrer">' + esc(p.repoUrl.replace(/^https:\/\/github\.com\//, "")) + "</a>" : "") +
            prop("tags", "Tags", (p.tags || []).map(tag).join(""));

        const paragraphs = String(p.longDescription || p.description || "").split(/\n\s*\n/).filter(Boolean);
        document.getElementById("peek-body").innerHTML =
            paragraphs.map((t) => "<p>" + esc(t) + "</p>").join("") +
            (p.projectUrl ? '<p></p><a class="page-link" href="' + esc(p.projectUrl) + '" target="_blank" rel="noreferrer"><span class="pl-icon">🔗</span><span class="pl-title">' + esc(p.ctaLabel || "Open project") + '</span><span class="pl-meta">' + esc(host(p.projectUrl)) + "</span></a>" : "");

        const open = document.getElementById("peek-open");
        if (p.projectUrl) { open.href = p.projectUrl; open.style.display = ""; } else { open.style.display = "none"; }

        peek.classList.add("open");
        document.body.classList.add("locked");
        peek.querySelector(".peek-panel").scrollTop = 0;
        if (!fromHash) history.replaceState(null, "", "#" + encodeURIComponent(p.slug));
        document.getElementById("peek-close").focus();
    }

    function closePeek() {
        if (!peek.classList.contains("open")) return;
        peek.classList.remove("open");
        document.body.classList.remove("locked");
        history.replaceState(null, "", location.pathname + location.search);
    }

    function openFromHash() {
        const slug = decodeURIComponent(location.hash.replace(/^#/, ""));
        if (slug && projects.some((p) => p.slug === slug)) openPeek(slug, true);
    }

    document.getElementById("peek-close").addEventListener("click", closePeek);
    peek.addEventListener("click", (e) => { if (e.target === peek) closePeek(); });
    window.addEventListener("keydown", (e) => { if (e.key === "Escape") closePeek(); });
    window.addEventListener("hashchange", openFromHash);

    document.getElementById("peek-copy").addEventListener("click", async (e) => {
        const btn = e.currentTarget;
        try {
            await navigator.clipboard.writeText(location.href);
            btn.textContent = "Copied";
        } catch (err) {
            btn.textContent = "Copy failed";
        }
        setTimeout(() => { btn.textContent = "Copy link"; }, 1400);
    });

    tabs.forEach((t) => t.addEventListener("click", () => { current = t.dataset.view; render(); }));
    search.addEventListener("input", () => { query = search.value.trim().toLowerCase(); render(); });

    load();
})();
