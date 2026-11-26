/* The local tileset workspace uses the same validated grid and export operation as the CLI. */
function paneTileset() {
  const route = jobPath() + "/tileset";
  const request = (path = "", body) => api(route + path, body, {announceErrors: false});
  const pane = $("#pane");
  pane.innerHTML = `<section id="tileWorkspace">
    <h2 id="tileSheetHeading">Tile sheet</h2>
    <nav class="row tileset-navigation" id="tileNavigation" aria-label="Tileset tools" hidden>
      <button type="button" data-tile-jump="sheet">Tile sheet</button>
      <button type="button" data-tile-jump="animation">Tile animation</button>
      <button type="button" data-tile-jump="modules">Tile modules</button>
      <button type="button" data-tile-jump="terrain">Terrain rules</button>
      <button type="button" data-tile-jump="map">Map preview</button>
      <button type="button" data-tile-jump="objects">Map objects</button>
      <button type="button" data-tile-jump="maps">Saved maps &amp; export</button>
    </nav>
    <div class="tileset-workspace">
      <div>
        <p id="tileSummary" class="muted">Loading tileset…</p>
        <canvas id="tileCanvas" aria-label="Tile sheet preview" hidden></canvas>
        <div class="row" id="tileControls" hidden>
          <label>Tile ID <input id="tileSelection" type="number" value="0" min="0" step="1"></label>
          <label><input id="tileSolid" type="checkbox"> Collision</label>
          <label>Shape <select id="tileShape">
            <option value="full">Full square</option><option value="half_bottom">Half (bottom)</option>
            <option value="half_top">Half (top)</option><option value="slope_up">Slope up ◢</option>
            <option value="slope_down">Slope down ◣</option><option value="slope_up_low">Gentle slope up, low half</option>
            <option value="slope_up_high">Gentle slope up, high half</option><option value="slope_down_high">Gentle slope down, high half</option>
            <option value="slope_down_low">Gentle slope down, low half</option><option value="custom">Custom polygon…</option></select></label>
          <label title="Jump-through platform: solid from above only"><input id="tileOneWay" type="checkbox"> One-way</label>
          <label id="tilePointsField" hidden title="Tile pixels, top-left origin, e.g. 0,16 16,8 16,16">Points
            <input id="tilePoints" size="22" placeholder="0,16 16,8 16,16"></label>
          <span id="tileEmpty" class="muted" role="status"></span>
        </div>
        <div class="row" id="tilePropsRow" hidden>
          <label title="Custom data for the game: name=value, comma separated. Numbers and true/false keep their type.">Properties
            <input id="tileProps" size="30" placeholder="damage=5, water=true"></label>
          <button type="button" id="tilePropsSave">Save properties</button>
        </div>
      </div>
      <div>
        <form id="tileImport" class="tileset-form">
          <label class="field full">PNG sheet <input name="image" type="file" accept=".png,image/png" required></label>
          <label class="field">Tile width (px) <input name="tile_width" type="number" min="1" max="4096" value="16" required></label>
          <label class="field">Tile height (px) <input name="tile_height" type="number" min="1" max="4096" value="16" required></label>
          <label class="field">Margin (px) <input name="margin" type="number" min="0" max="4096" value="0" required></label>
          <label class="field">Spacing (px) <input name="spacing" type="number" min="0" max="4096" value="0" required></label>
          <button class="primary full" id="tileImportSave" type="submit">Import PNG</button>
        </form>
        <p id="tileImportHint" class="hint" hidden>A different sheet or grid starts a new tile layout. Earlier sources and layouts are retained.</p>
        <div class="row" id="tileExportRow" hidden><button id="tileExport" type="button">Export tileset</button>
          <span class="muted" id="tileExportStatus" role="status"></span></div>
        <div class="row" id="tileDownloads"></div>
        <p class="warn" id="tileError" role="alert" hidden></p>
      </div>
    </div>
    <div id="tileAnimationPanel" hidden></div>
    <div id="tileModulePanel" hidden></div>
    <div id="terrainPanel" hidden></div>
  </section>`;
  const root = pane.querySelector("#tileWorkspace");
  const find = selector => root.querySelector(selector);
  const form = find("#tileImport"), canvas = find("#tileCanvas"), summary = find("#tileSummary");
  const solid = find("#tileSolid"), selection = find("#tileSelection"), exportButton = find("#tileExport");
  const shapeSelect = find("#tileShape"), oneWay = find("#tileOneWay"), pointsInput = find("#tilePoints");
  const propsInput = find("#tileProps");
  const SHAPES = {full: [[0, 0], [1, 0], [1, 1], [0, 1]], half_bottom: [[0, .5], [1, .5], [1, 1], [0, 1]],
    half_top: [[0, 0], [1, 0], [1, .5], [0, .5]], slope_up: [[0, 1], [1, 0], [1, 1]], slope_down: [[0, 0], [1, 1], [0, 1]],
    slope_up_low: [[0, 1], [1, .5], [1, 1]], slope_up_high: [[0, .5], [1, 0], [1, 1], [0, 1]],
    slope_down_high: [[0, 0], [1, .5], [1, 1], [0, 1]], slope_down_low: [[0, .5], [1, 1], [0, 1]]};
  const shapeOf = id => (state.tileset.tile_shapes || {})[id] || {};
  function polygonOf(id, w, h) {
    const s = shapeOf(id);
    return s.points ? s.points : SHAPES[s.shape || "full"].map(([x, y]) => [x * w, y * h]);
  }
  const propsText = values => Object.entries(values || {}).map(([k, v]) => `${k}=${v}`).join(", ");
  function parseProps(text) {
    const out = {};
    for (const part of text.split(",").map(p => p.trim()).filter(Boolean)) {
      const at = part.indexOf("=");
      if (at < 1) throw new Error(`Write properties as name=value, not "${part}".`);
      const k = part.slice(0, at).trim(), v = part.slice(at + 1).trim();
      out[k] = /^(true|false)$/i.test(v) ? v.toLowerCase() === "true" : /^-?\d+$/.test(v) ? parseInt(v, 10)
        : /^-?\d*\.\d+$/.test(v) ? parseFloat(v) : v;
    }
    return out;
  }
  const image = new Image();
  let state, active = 0, scale = 1;
  const animation = bindTilesetAnimation(find("#tileAnimationPanel"), request, image, result => render(result),
    () => terrain.draw());
  const modules = bindTilesetModules(find("#tileModulePanel"), request, image, result => render(result), () => active);
  const terrain = bindTilesetTerrain(find("#terrainPanel"), route, request, image, result => render(result),
    animation.frameFor);
  const keys = ["tile_width", "tile_height", "margin", "spacing"];
  const names = {"tiles.png": "PNG", "tileset.json": "SpriteWaffle JSON", "tileset.tsj": "Tiled TSJ"};
  const states = {current: "Export current", stale: "Export stale", incomplete: "Export incomplete", untracked: "Export untracked"};

  function error(message = "") {
    const notice = find("#tileError");
    notice.textContent = message;
    notice.hidden = !message;
  }

  function redraw() {
    if (!state?.tileset || !image.complete || !image.naturalWidth) return;
    const {grid, solid_tiles} = state.tileset;
    const {tile_width: w, tile_height: h, margin: m, spacing: s, columns, rows} = grid;
    const context = canvas.getContext("2d");
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.imageSmoothingEnabled = false;
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const filled = new Set(solid_tiles);
    const style = getComputedStyle(canvas);
    for (let i = 0; i < rows * columns; i++) {
      const x = (m + (i % columns) * (w + s)) * scale;
      const y = (m + Math.floor(i / columns) * (h + s)) * scale;
      if (filled.has(i)) {
        context.fillStyle = style.getPropertyValue("--warn").trim();
        context.globalAlpha = .35;
        context.beginPath();
        polygonOf(String(i), w, h).forEach(([px, py], n) => context[n ? "lineTo" : "moveTo"](x + px * scale, y + py * scale));
        context.closePath();
        context.fill();
        context.globalAlpha = 1;
        if (shapeOf(String(i)).one_way) {
          context.strokeStyle = style.getPropertyValue("--warn").trim();
          context.setLineDash([4, 3]); context.strokeRect(x + 2, y + 2, w * scale - 4, 2); context.setLineDash([]);
        }
      }
      context.strokeStyle = style.getPropertyValue(i === active ? "--accent" : "--line").trim();
      context.lineWidth = i === active ? 2 : 1;
      context.strokeRect(x + .5, y + .5, Math.max(0, w * scale - 1), Math.max(0, h * scale - 1));
    }
  }

  function select(id) {
    if (!state?.tileset || !Number.isInteger(id) || id < 0 || id > Number(selection.max)) {
      selection.value = active;
      return;
    }
    active = id;
    selection.value = id;
    solid.checked = state.tileset.solid_tiles.includes(id);
    const s = shapeOf(String(id));
    shapeSelect.value = s.points ? "custom" : s.shape || "full";
    oneWay.checked = !!s.one_way;
    pointsInput.value = s.points ? s.points.map(p => p.join(",")).join(" ") : "";
    find("#tilePointsField").hidden = shapeSelect.value !== "custom";
    shapeSelect.disabled = oneWay.disabled = !solid.checked;
    propsInput.value = propsText((state.tileset.tile_properties || {})[String(id)]);
    find("#tileEmpty").textContent = state.tileset.empty_tiles.includes(id) ? "Transparent tile" : "";
    terrain.selectTile(id);
    animation.selectTile(id);
    redraw();
  }

  function render(result, loadGrid = false) {
    state = result;
    const record = result.tileset;
    if (result.preview && image.getAttribute("src") !== result.preview) image.src = result.preview;
    animation.sync(result);
    modules.sync(result);
    terrain.sync(result);
    find("#tileControls").hidden = !record;
    find("#tilePropsRow").hidden = !record;
    find("#tileNavigation").hidden = !record;
    find("#tileExportRow").hidden = !record;
    find("#tileImportHint").hidden = !record;
    canvas.hidden = !result.preview;
    if (record) {
      const {grid, empty_tiles, filename} = record;
      selection.max = grid.columns * grid.rows - 1;
      summary.textContent = `${filename} · ${grid.columns} × ${grid.rows} tiles · ${empty_tiles.length} transparent${result.preview ? "" : " · Source PNG missing"}`;
      if (loadGrid) keys.forEach(key => form.elements[key].value = grid[key]);
      select(Math.min(active, Number(selection.max)));
    } else summary.textContent = "Import a PNG tile sheet and enter its grid dimensions.";
    exportButton.disabled = !result.preview;
    find("#tileExportStatus").textContent = states[result.export.status] || "";
    find("#tileDownloads").innerHTML = Object.entries(result.files).map(([name, link]) =>
      `<a href="${esc(link)}">${esc(names[name] || name)}</a>`).join("");
  }

  async function perform(button, operation, ready) {
    button.disabled = true;
    error();
    try { ready(await operation()); }
    catch (cause) { error(cause.message); }
    finally { button.disabled = false; }
  }

  image.onload = () => {
    const {width, height} = state.tileset.grid;
    const longest = Math.max(width, height);
    scale = Math.min(1280 / longest, Math.max(1, Math.min(12, 360 / longest)));
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    redraw();
    animation.draw();
    modules.draw();
    terrain.draw();
  };
  image.onerror = () => error("The retained PNG could not be displayed. Import it again.");
  canvas.onclick = event => {
    const {grid} = state.tileset;
    const bounds = canvas.getBoundingClientRect();
    const x = (event.clientX - bounds.left) * grid.width / bounds.width - grid.margin;
    const y = (event.clientY - bounds.top) * grid.height / bounds.height - grid.margin;
    const col = Math.floor(x / (grid.tile_width + grid.spacing)), row = Math.floor(y / (grid.tile_height + grid.spacing));
    if (x >= 0 && y >= 0 && col < grid.columns && row < grid.rows &&
        x % (grid.tile_width + grid.spacing) < grid.tile_width && y % (grid.tile_height + grid.spacing) < grid.tile_height) {
      select(row * grid.columns + col);
    }
  };
  selection.onchange = () => select(selection.valueAsNumber);
  const sections = {sheet: "#tileSheetHeading", animation: "#tileAnimationPanel h2", modules: "#tileModulePanel h2", terrain: "#terrainPanel h2",
    map: "#terrainPreview h3", objects: "#terrainObjectPanel summary", maps: "#terrainMapsHeading"};
  root.querySelectorAll("[data-tile-jump]").forEach(button => {
    button.onclick = () => {
      const target = find(sections[button.dataset.tileJump]);
      if (button.dataset.tileJump === "objects") target.parentElement.open = true;
      if (target.tagName !== "SUMMARY") target.tabIndex = -1;
      target.scrollIntoView({block: "start"});
      target.focus({preventScroll: true});
    };
  });
  function shapeBody() {
    if (shapeSelect.value === "custom") {
      const points = pointsInput.value.trim().split(/\s+/).filter(Boolean).map(p => p.split(",").map(Number));
      if (points.length < 3 || points.some(p => p.length !== 2 || p.some(Number.isNaN))) return null;
      return {points, one_way: oneWay.checked};
    }
    return {shape: shapeSelect.value, one_way: oneWay.checked};
  }
  async function saveCollision(control) {
    const shape = solid.checked ? shapeBody() : null;
    if (solid.checked && !shape) {
      find("#tilePointsField").hidden = false;
      return error("Enter at least three x,y points, separated by spaces.");
    }
    await perform(control, () => request("/collision", {tile: active, solid: solid.checked, shape, revision: state.revision}), render);
    select(active);
  }
  solid.onchange = () => saveCollision(solid);
  oneWay.onchange = () => saveCollision(oneWay);
  shapeSelect.onchange = () => {
    find("#tilePointsField").hidden = shapeSelect.value !== "custom";
    if (shapeSelect.value !== "custom" || shapeBody()) saveCollision(shapeSelect);
  };
  pointsInput.onchange = () => saveCollision(pointsInput);
  find("#tilePropsSave").onclick = () => {
    let values;
    try { values = parseProps(propsInput.value); } catch (cause) { return error(cause.message); }
    perform(find("#tilePropsSave"), () => request("/properties", {tile: active, properties: values, revision: state.revision}), render);
  };
  exportButton.onclick = () => perform(exportButton, () => request("/export", {}), render);
  form.onsubmit = event => {
    event.preventDefault();
    const file = form.elements.image.files[0];
    if (file.size > 16 * 1024 * 1024) return error("Choose a PNG no larger than 16 MiB.");
    const grid = Object.fromEntries(keys.map(key => [key, form.elements[key].valueAsNumber]));
    perform(find("#tileImportSave"), async () => {
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(",")[1]);
        reader.onerror = () => reject(new Error("The selected file could not be read."));
        reader.readAsDataURL(file);
      });
      return request("/import", {data, filename: file.name, grid});
    }, result => {
      form.elements.image.value = "";
      active = 0;
      render(result, true);
    });
  };
  request().then(result => render(result, true)).catch(cause => {
    summary.textContent = "Tileset unavailable.";
    error(cause.message);
  });
}
