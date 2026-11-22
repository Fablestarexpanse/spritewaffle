function bindTilesetTerrain(panel, route, request, image, apply) {
  panel.innerHTML = `<h2>Terrain transitions</h2>
    <div class="tileset-workspace">
      <div>
        <div class="field"><label for="terrainNames">Terrain names, one per line</label>
          <textarea id="terrainNames" rows="3" placeholder="Grass&#10;Water"></textarea></div>
        <button id="terrainSaveNames" type="button">Save terrain names</button>
        <div id="terrainCorners" hidden>
          <h3 id="terrainTileHeading">Tile corners</h3>
          <div class="tileset-form">${["Top left", "Top right", "Bottom right", "Bottom left"].map((label, i) =>
            `<label class="field">${label}<select data-corner="${i}"></select></label>`).join("")}</div>
          <div class="row"><button id="terrainSaveTile" type="button">Save tile corners</button></div>
        </div>
        <p id="terrainError" class="warn" role="alert" hidden></p>
      </div>
      <div id="terrainPreview" hidden>
        <h3>Map preview</h3>
        <canvas id="terrainCanvas" aria-label="Eight by six terrain map preview"></canvas>
        <p id="terrainStats" class="muted" role="status"></p>
        <p class="hint">Paint sets all four corners of a cell. Dashed cells need a matching tile.</p>
        <div class="row">
          <label>Terrain <select id="terrainBrush"></select></label>
          <button type="button" id="terrainFill">Fill preview</button>
          <button type="button" id="terrainClear">Clear</button>
        </div>
        <div class="row">
          <label>Cell <input type="number" id="terrainCell" min="0" max="47" value="0" step="1"></label>
          <button type="button" id="terrainPaint">Paint cell</button>
        </div>
      </div>
    </div>`;
  const find = selector => panel.querySelector(selector);
  const names = find("#terrainNames"), brush = find("#terrainBrush"), canvas = find("#terrainCanvas");
  const corners = [...panel.querySelectorAll("[data-corner]")], cellInput = find("#terrainCell");
  const cols = 8, rows = 6;
  const lattice = (name = null) => Array.from({length: rows + 1}, () => Array(cols + 1).fill(name));
  let state, tile = 0, rules = {colors: [], tiles: {}}, vertices = lattice(), result, storage, revision = 0;

  function error(message = "") {
    const notice = find("#terrainError");
    notice.textContent = message;
    notice.hidden = !message;
  }

  async function save(button, draft) {
    button.disabled = true;
    error();
    try { apply(await request("/terrain", {terrain: draft, revision: state.revision})); }
    catch (cause) { error(cause.message); }
    finally { button.disabled = false; }
  }

  function draw() {
    if (!state?.tileset || !result) return;
    const grid = state.tileset.grid, tw = grid.tile_width, th = grid.tile_height;
    const size = 40 / Math.max(tw, th);
    const w = Math.max(1, Math.round(tw * size)), h = Math.max(1, Math.round(th * size));
    canvas.width = cols * w;
    canvas.height = rows * h;
    const ctx = canvas.getContext("2d"), style = getComputedStyle(canvas);
    const missing = new Set(result.missing.map(([x, y]) => y * cols + x));
    ctx.imageSmoothingEnabled = false;
    result.tiles.forEach((row, y) => row.forEach((id, x) => {
      if (id !== null && image.complete && image.naturalWidth) {
        const sx = grid.margin + id % grid.columns * (tw + grid.spacing);
        const sy = grid.margin + Math.floor(id / grid.columns) * (th + grid.spacing);
        ctx.drawImage(image, sx, sy, tw, th, x * w, y * h, w, h);
      }
      ctx.strokeStyle = style.getPropertyValue(missing.has(y * cols + x) ? "--warn" : "--line").trim();
      ctx.setLineDash(missing.has(y * cols + x) ? [3, 2] : []);
      ctx.strokeRect(x * w + .5, y * h + .5, w - 1, h - 1);
    }));
  }

  async function resolveMap() {
    const id = ++revision;
    if (!rules.colors.length) return;
    try { sessionStorage.setItem(storage, JSON.stringify(vertices)); } catch {}
    try {
      const resolved = await request("/preview", {vertices, revision: state.revision});
      if (id !== revision) return;
      result = resolved;
      const count = result.tiles.flat().filter(id => id !== null).length;
      find("#terrainStats").textContent = `${count} placed · ${result.missing.length} missing transition${result.missing.length === 1 ? "" : "s"}`;
      draw();
    } catch (cause) {
      if (id === revision) error(cause.message);
    }
  }

  function paint(id) {
    if (!Number.isInteger(id) || id < 0 || id >= cols * rows || !brush.value) return;
    const x = id % cols, y = Math.floor(id / cols);
    cellInput.value = id;
    vertices[y][x] = vertices[y][x + 1] = vertices[y + 1][x] = vertices[y + 1][x + 1] = brush.value;
    error();
    resolveMap();
  }

  function selectTile(id, reset = false) {
    if (id === tile && !reset) return;
    tile = id;
    find("#terrainTileHeading").textContent = `Tile ${id} corners`;
    const saved = rules.tiles[id] || [null, null, null, null];
    corners.forEach((select, i) => select.value = saved[i] ?? "");
  }

  function sync(next) {
    const changed = next.revision !== state?.revision;
    state = next;
    panel.hidden = !next.tileset;
    if (!next.tileset || !changed) return;
    const nextStorage = route + "/preview/" + next.tileset.digest + "/" + JSON.stringify(next.tileset.grid);
    if (nextStorage !== storage) {
      storage = nextStorage;
      vertices = lattice();
      try {
        const stored = JSON.parse(sessionStorage.getItem(storage));
        if (stored?.length === rows + 1 && stored.every(row => row.length === cols + 1)) vertices = stored;
      } catch {}
    }
    const before = rules.colors;
    rules = next.tileset.terrain || {colors: [], tiles: {}};
    if (JSON.stringify(before) !== JSON.stringify(rules.colors)) names.value = rules.colors.join("\n");
    find("#terrainCorners").hidden = find("#terrainPreview").hidden = !rules.colors.length;
    const options = rules.colors.map(name => `<option value="${esc(name)}">${esc(name)}</option>`).join("");
    for (const select of corners) select.innerHTML = '<option value="">Unassigned</option>' + options;
    const previousBrush = brush.value;
    brush.innerHTML = options;
    brush.value = rules.colors.includes(previousBrush) ? previousBrush : rules.colors[0] || "";
    vertices = vertices.map(row => row.map(name => rules.colors.includes(name) ? name : null));
    selectTile(tile, true);
    resolveMap();
  }

  find("#terrainSaveNames").onclick = event => {
    const colors = names.value.split(/\r?\n/).map(name => name.trim()).filter(Boolean);
    save(event.currentTarget, {colors, tiles: rules.tiles});
  };
  find("#terrainSaveTile").onclick = event => {
    const tiles = {...rules.tiles, [tile]: corners.map(select => select.value || null)};
    save(event.currentTarget, {colors: rules.colors, tiles});
  };
  find("#terrainFill").onclick = () => { error(); vertices = lattice(brush.value); resolveMap(); };
  find("#terrainClear").onclick = () => { error(); vertices = lattice(); resolveMap(); };
  find("#terrainPaint").onclick = () => paint(cellInput.valueAsNumber);
  canvas.onclick = event => {
    const box = canvas.getBoundingClientRect();
    const x = Math.floor((event.clientX - box.left) * cols / box.width);
    const y = Math.floor((event.clientY - box.top) * rows / box.height);
    if (x >= 0 && x < cols && y >= 0 && y < rows) paint(y * cols + x);
  };
  return {sync, selectTile, draw};
}
