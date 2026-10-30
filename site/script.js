// plot2data-ml showcase site. Dark/light toggle + gallery renderer, no framework.

(() => {
  const root = document.documentElement;
  const toggle = document.getElementById("theme-toggle");

  // Theme: respect saved choice, else OS.
  const saved = localStorage.getItem("p2d-theme");
  if (saved === "light" || saved === "dark") {
    root.setAttribute("data-theme", saved);
  }
  toggle?.addEventListener("click", () => {
    const cur = root.getAttribute("data-theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const effective = cur || (prefersDark ? "dark" : "light");
    const next = effective === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    localStorage.setItem("p2d-theme", next);
  });

  // Smooth scroll from in-page nav links.
  document.querySelectorAll('a[href^="#"]').forEach(a => {
    a.addEventListener("click", (e) => {
      const id = a.getAttribute("href").slice(1);
      const el = document.getElementById(id);
      if (!el) return;
      e.preventDefault();
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      history.replaceState(null, "", "#" + id);
    });
  });

  // Gallery.
  const grid = document.getElementById("gallery-grid");
  if (!grid) return;

  fetch("examples/gallery.json")
    .then(r => {
      if (!r.ok) throw new Error("could not load gallery.json");
      return r.json();
    })
    .then(data => renderGallery(data, grid))
    .catch(err => {
      grid.innerHTML = `<div class="placeholder">Gallery unavailable: ${escapeHtml(err.message)}. Rebuild it with <code>python site/_build.py</code>.</div>`;
    });

  function renderGallery(data, grid) {
    const entries = data.entries || [];
    const chips = document.querySelectorAll(".filter .chip");
    let activeKind = "all";

    const draw = () => {
      const filtered = activeKind === "all"
        ? entries
        : entries.filter(e => e.kind === activeKind);
      grid.innerHTML = filtered.map(cardHtml).join("");
    };

    chips.forEach(c => c.addEventListener("click", () => {
      chips.forEach(x => x.classList.remove("active"));
      c.classList.add("active");
      activeKind = c.dataset.filter;
      draw();
    }));

    draw();
  }

  function cardHtml(e) {
    const series = e.series || [];
    const seriesCount = series.length;
    const points = series.reduce((a, s) => a + (s.points || 0), 0);
    const warnings = (e.warnings || []).filter(Boolean);
    const xaxis = e.x_axis
      ? `${e.x_axis.scale}${e.x_axis.date ? " dates" : ""} (${(e.x_axis.ticks || []).length} ticks)`
      : "none";
    const yaxis = e.y_axis
      ? `${e.y_axis.scale}${e.y_axis.date ? " dates" : ""} (${(e.y_axis.ticks || []).length} ticks)`
      : "none";

    const preview = (e.preview || []).map(block => {
      const header = block.header || [];
      const rows = block.rows || [];
      return `
        <div class="preview">
          <div class="preview-cap">${escapeHtml(block.caption)}</div>
          <table>
            <thead><tr>${header.map(h => `<th>${escapeHtml(h)}</th>`).join("")}</tr></thead>
            <tbody>
              ${rows.map(r => `<tr>${r.map(c => `<td>${escapeHtml(c)}</td>`).join("")}</tr>`).join("")}
              ${rows.length ? `<tr><td colspan="${header.length}" style="color:var(--ink-dim)">...</td></tr>` : ""}
            </tbody>
          </table>
        </div>`;
    }).join("");

    const warn = warnings.length
      ? `<div class="warn">${warnings.map(escapeHtml).join("<br>")}</div>` : "";

    const tags = (e.tags || []).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join("");

    return `
      <article class="card" data-kind="${escapeHtml(e.kind)}">
        <header class="card-head">
          <div class="card-title">${escapeHtml(e.label)}</div>
          <div class="card-sub">${escapeHtml(e.kind)} &middot; ${escapeHtml(e.name)}.png</div>
          <div class="card-tags">${tags}</div>
        </header>
        <div class="cmp">
          <figure>
            <img src="${e.src}" alt="${escapeHtml(e.label)} source image" loading="lazy">
            <figcaption>source</figcaption>
          </figure>
          <figure>
            <img src="${e.overlay}" alt="${escapeHtml(e.label)} extraction overlay" loading="lazy">
            <figcaption>extraction</figcaption>
          </figure>
        </div>
        <div class="card-body">
          <div class="badge-row">
            <div><b>${seriesCount}</b> series</div>
            <div><b>${points}</b> points</div>
            <div><b>x:</b> ${escapeHtml(xaxis)}</div>
            <div><b>y:</b> ${escapeHtml(yaxis)}</div>
            <div><b>${(e.elapsed_s || 0).toFixed(2)}s</b></div>
          </div>
          ${preview}
          ${warn}
          <div class="card-foot">
            <a href="${e.csv}" download>download CSV</a>
            <a href="${e.overlay}" target="_blank" rel="noopener">overlay</a>
            <a href="${e.src}" target="_blank" rel="noopener">source</a>
          </div>
        </div>
      </article>`;
  }

  function escapeHtml(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
})();
