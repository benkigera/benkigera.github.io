// Shared behaviour for Notion-style pages: theme toggle and top bar shadow.
(function () {
    const root = document.documentElement;

    function readTheme() {
        try { return localStorage.getItem("bk-theme"); } catch (e) { return null; }
    }

    function writeTheme(value) {
        try { localStorage.setItem("bk-theme", value); } catch (e) { /* storage unavailable */ }
    }

    const saved = readTheme();
    if (saved === "light" || saved === "dark") root.setAttribute("data-theme", saved);

    function currentTheme() {
        const set = root.getAttribute("data-theme");
        if (set) return set;
        return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
            button.addEventListener("click", function () {
                const next = currentTheme() === "dark" ? "light" : "dark";
                root.setAttribute("data-theme", next);
                writeTheme(next);
            });
        });

        const bar = document.querySelector(".topbar");
        if (bar) {
            const onScroll = function () { bar.classList.toggle("is-scrolled", window.scrollY > 4); };
            window.addEventListener("scroll", onScroll, { passive: true });
            onScroll();
        }
    });
})();
