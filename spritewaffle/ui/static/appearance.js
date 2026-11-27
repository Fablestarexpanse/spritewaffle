(() => {
  "use strict";

  const key = "sw.appearance.v1";
  const root = document.documentElement;
  const systemTheme = matchMedia("(prefers-color-scheme: dark)");
  const narrow = matchMedia("(max-width: 760px)");
  let narrowSidebar = false;
  const accents = {gold: "#ffcb42", violet: "#b786ef", blue: "#78bcff", mint: "#69dcb1"};
  const defaults = {
    theme: "midnight", accent: "default", customAccent: "#ffcb42",
    fontSize: "100", density: "comfortable", motion: true, preview: "checker", sidebar: true, sidebarWidth: null
  };
  const MIN_SIDEBAR = 200, MAX_SIDEBAR = 640;          // px; null = the responsive default
  const choices = {
    theme: ["midnight", "slate", "forest", "light", "oled", "system"],
    accent: ["default", ...Object.keys(accents), "custom"],
    fontSize: ["90", "100", "115", "130", "150"],
    density: ["compact", "comfortable", "spacious"],
    preview: ["checker", "dark", "light", "neutral"]
  };
  const isHex = value => typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value);

  let saved;
  try { saved = JSON.parse(localStorage.getItem(key)); } catch {}
  let prefs = {...defaults};
  for (const [name, values] of Object.entries(choices)) {
    if (values.includes(saved?.[name])) prefs[name] = saved[name];
  }
  if (isHex(saved?.customAccent)) prefs.customAccent = saved.customAccent;
  for (const name of ["motion", "sidebar"]) {
    if (typeof saved?.[name] === "boolean") prefs[name] = saved[name];
  }
  if (Number.isInteger(saved?.sidebarWidth) && saved.sidebarWidth >= MIN_SIDEBAR && saved.sidebarWidth <= MAX_SIDEBAR)
    prefs.sidebarWidth = saved.sidebarWidth;

  function accentInk(hex) {
    const channels = hex.slice(1).match(/../g).map(pair => parseInt(pair, 16) / 255);
    const [r, g, b] = channels.map(c => c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
    return r * 0.2126 + g * 0.7152 + b * 0.0722 > 0.179 ? "#000000" : "#ffffff";
  }

  function apply() {
    const theme = prefs.theme === "system" ? (systemTheme.matches ? "midnight" : "light") : prefs.theme;
    Object.assign(root.dataset, {
      theme, density: prefs.density, motion: String(prefs.motion), preview: prefs.preview,
      sidebar: String(narrow.matches ? narrowSidebar : prefs.sidebar)
    });
    root.style.fontSize = `${Number(prefs.fontSize) * 0.875}%`;
    if (prefs.sidebarWidth && !narrow.matches) root.style.setProperty("--sidebar-width", `${prefs.sidebarWidth}px`);
    else root.style.removeProperty("--sidebar-width");
    const accent = prefs.accent === "custom" ? prefs.customAccent : accents[prefs.accent];
    if (accent) {
      root.style.setProperty("--accent", accent);
      root.style.setProperty("--accent-ink", accentInk(accent));
    } else {
      root.style.removeProperty("--accent");
      root.style.removeProperty("--accent-ink");
    }
  }

  function update() {
    apply();
    try { localStorage.setItem(key, JSON.stringify(prefs)); } catch {}
  }

  apply();
  systemTheme.addEventListener("change", apply);

  document.addEventListener("DOMContentLoaded", () => {
    const dialog = document.querySelector("#appearanceSettings");
    const fields = dialog.querySelector("#appearanceFields");
    const sidebar = document.querySelector("#btnJobs");
    const sync = () => {
      for (const field of fields.elements) {
        if (field.type === "checkbox") field.checked = prefs[field.name];
        else field.value = prefs[field.name];
      }
      fields.elements.customAccent.disabled = prefs.accent !== "custom";
      sidebar.setAttribute("aria-expanded", root.dataset.sidebar);
    };
    const change = ({target}) => {
      const {name, type, checked, value} = target;
      if (name === "motion") prefs.motion = checked;
      else if (name === "customAccent" && isHex(value)) prefs.customAccent = value;
      else if (choices[name]?.includes(value)) prefs[name] = value;
      else return;
      update();
      sync();
    };
    fields.addEventListener("change", change);
    fields.elements.customAccent.addEventListener("input", change);
    document.querySelector("#btnSettings").onclick = () => dialog.showModal();
    document.querySelector("#appearanceReset").onclick = () => {
      prefs = {...defaults, sidebar: prefs.sidebar};
      update();
      sync();
    };
    sidebar.onclick = () => {
      if (narrow.matches) {
        narrowSidebar = !narrowSidebar;
        apply();
      } else {
        prefs.sidebar = !prefs.sidebar;
        update();
      }
      sync();
    };
    narrow.addEventListener("change", () => { apply(); sync(); });
    // resizable sidebar: drag its edge (or focus it and use the arrow keys); double-click resets
    const aside = document.querySelector("#jobBrowser");
    const handle = document.createElement("div");
    handle.className = "sidebar-resize";
    handle.tabIndex = 0;
    handle.setAttribute("role", "separator");
    handle.setAttribute("aria-orientation", "vertical");
    handle.setAttribute("aria-label", "Resize the job list (arrow keys; double-click resets)");
    handle.title = "Drag to resize · double-click to reset";
    aside.after(handle);                             // a grid sibling, so it doesn't scroll with the job list
    const setWidth = px => {
      prefs.sidebarWidth = px === null ? null : Math.round(Math.min(MAX_SIDEBAR, Math.max(MIN_SIDEBAR, px)));
      update();
    };
    handle.addEventListener("pointerdown", event => {
      if (narrow.matches) return;
      event.preventDefault();
      handle.setPointerCapture(event.pointerId);
      const left = aside.getBoundingClientRect().left;
      const move = e => {
        prefs.sidebarWidth = Math.round(Math.min(MAX_SIDEBAR, Math.max(MIN_SIDEBAR, e.clientX - left)));
        apply();
      };
      const up = () => { handle.removeEventListener("pointermove", move); update(); };
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", up, {once: true});
    });
    handle.addEventListener("dblclick", () => setWidth(null));
    handle.addEventListener("keydown", event => {
      const step = event.shiftKey ? 64 : 16;
      const now = aside.getBoundingClientRect().width;
      if (event.key === "ArrowLeft") setWidth(now - step);
      else if (event.key === "ArrowRight") setWidth(now + step);
      else if (event.key === "Home") setWidth(null);
      else return;
      event.preventDefault();
    });
    document.querySelector("#jobBrowser").addEventListener("click", event => {
      if (!narrow.matches || !event.target.closest("a.job") || event.ctrlKey || event.metaKey || event.shiftKey) return;
      narrowSidebar = false;
      apply();
      sync();
      document.querySelector("#main").focus({preventScroll: true});
    });
    document.addEventListener("keydown", event => {
      if (event.key !== "/" || event.altKey || event.ctrlKey || event.metaKey ||
          event.target.closest("input, textarea, select, [contenteditable]") || document.querySelector("dialog[open]")) return;
      event.preventDefault();
      if (root.dataset.sidebar === "false") sidebar.click();
      document.querySelector("#search").focus();
    });
    sync();
  });
})();
