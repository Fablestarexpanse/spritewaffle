function bindTilesetTerrain(panel, route, request, image, apply, frameFor) {
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
        <canvas id="terrainCanvas" aria-label="Terrain map preview"></canvas>
        <p id="terrainStats" class="muted" role="status"></p>
        <p class="hint">Paint sets all four corners of a cell. Dashed cells need a matching tile.</p>
        <div class="row">
          <label>Terrain <select id="terrainBrush"></select></label>
          <button type="button" id="terrainFill">Fill preview</button>
          <button type="button" id="terrainClear">Clear draft</button>
        </div>
        <div class="row">
          <label>Cell <input type="number" id="terrainCell" min="0" max="47" value="0" step="1"></label>
          <button type="button" id="terrainPaint">Paint cell</button>
        </div>
        <h3>Saved maps</h3>
        <fieldset id="terrainMapControls" aria-label="Map files">
          <div class="row">
            <label>Saved map <select id="terrainMapList"><option value="">Select a map</option></select></label>
            <button type="button" id="terrainMapOpen" disabled>Open</button>
            <button type="button" id="terrainMapNew">New draft</button>
          </div>
          <form id="terrainMapForm" class="row">
            <label>Map name <input id="terrainMapName" required maxlength="80"></label>
            <button type="submit">Save map</button>
            <button type="button" id="terrainMapExport" disabled>Prepare map ZIP</button>
            <a id="terrainMapDownload" hidden>Download map ZIP</a>
          </form>
        </fieldset>
        <p id="terrainMapStatus" class="muted" role="status"></p>
        <p id="terrainMapError" class="warn" role="alert" hidden></p>
      </div>
    </div>`;
  const find = selector => panel.querySelector(selector);
  const names = find("#terrainNames"), brush = find("#terrainBrush"), canvas = find("#terrainCanvas");
  const corners = [...panel.querySelectorAll("[data-corner]")], cellInput = find("#terrainCell");
  const mapList = find("#terrainMapList"), mapName = find("#terrainMapName");
  let cols = 8, rows = 6;
  const lattice = (name = null, width = cols, height = rows) =>
    Array.from({length: height + 1}, () => Array(width + 1).fill(name));
  let state, tile = 0, rules = {colors: [], tiles: {}}, vertices = lattice(), result, storage, revision = 0;
  let savedMap = null, maps = [], mapsLoaded = false, mapWorking = false;

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

  function mapError(message = "") {
    const notice = find("#terrainMapError");
    notice.textContent = message;
    notice.hidden = !message;
  }

  function dirtyMap() {
    if (!savedMap) return !!mapName.value.trim() || vertices.some(row => row.some(name => name !== null));
    return mapName.value.trim() !== savedMap.name ||
      JSON.stringify(vertices) !== JSON.stringify(savedMap.vertices);
  }

  function mapControls() {
    const dirty = dirtyMap();
    find("#terrainMapOpen").disabled = !mapList.value;
    find("#terrainMapExport").disabled = !savedMap || dirty || !result || !!result.missing.length;
    find("#terrainMapStatus").textContent = savedMap
      ? (dirty ? "Unsaved map changes" : "Saved to the project") : "Draft · Save to add it to the project";
  }

  function mapOptions(selected) {
    mapList.replaceChildren(new Option("Select a map", ""), ...maps.map(({id, name}) => new Option(name, id)));
    mapList.value = selected || "";
    mapControls();
  }

  async function mapAction(action) {
    if (mapWorking) return;
    mapWorking = true;
    find("#terrainMapControls").disabled = true;
    mapError();
    try { await action(); }
    catch (cause) { mapError(cause.message); }
    finally {
      find("#terrainMapControls").disabled = false;
      mapWorking = false;
    }
  }

  function forgetDraft() {
    try { sessionStorage.removeItem(storage); } catch {}
  }

  function editMap(draft) {
    vertices = draft;
    rows = vertices.length - 1;
    cols = vertices[0].length - 1;
    cellInput.max = cols * rows - 1;
    if (cellInput.valueAsNumber > Number(cellInput.max)) cellInput.value = 0;
    find("#terrainMapDownload").hidden = true;
    result = null;
    mapControls();
    resolveMap();
  }

  function draw() {
    if (!state?.tileset || !result) return;
    const grid = state.tileset.grid, tw = grid.tile_width, th = grid.tile_height;
    const size = 40 / Math.max(tw, th);
    const w = Math.max(1, Math.round(tw * size)), h = Math.max(1, Math.round(th * size));
    if (canvas.width !== cols * w) canvas.width = cols * w;
    if (canvas.height !== rows * h) canvas.height = rows * h;
    const ctx = canvas.getContext("2d"), style = getComputedStyle(canvas);
    const missing = new Set(result.missing.map(([x, y]) => y * cols + x));
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.imageSmoothingEnabled = false;
    result.tiles.forEach((row, y) => row.forEach((id, x) => {
      if (id !== null && state.preview && image.complete && image.naturalWidth) {
        drawTilesetCell(ctx, image, grid, frameFor(id), x * w, y * h, w, h);
      }
      ctx.strokeStyle = style.getPropertyValue(missing.has(y * cols + x) ? "--warn" : "--line").trim();
      ctx.setLineDash(missing.has(y * cols + x) ? [3, 2] : []);
      ctx.strokeRect(x * w + .5, y * h + .5, w - 1, h - 1);
    }));
  }

  async function resolveMap() {
    const id = ++revision;
    if (!savedMap) {
      try { sessionStorage.setItem(storage, JSON.stringify(vertices)); } catch {}
    }
    try {
      const resolved = await request("/preview", {vertices, revision: state.revision, allow_unknown: true});
      if (id !== revision) return;
      result = resolved;
      const count = result.tiles.flat().filter(id => id !== null).length;
      find("#terrainStats").textContent = `${count} placed · ${result.missing.length} missing transition${result.missing.length === 1 ? "" : "s"}`;
      mapControls();
      draw();
    } catch (cause) {
      if (id === revision) error(cause.message);
    }
  }

  function paint(id) {
    if (mapWorking || !Number.isInteger(id) || id < 0 || id >= cols * rows || !brush.value) return;
    const x = id % cols, y = Math.floor(id / cols);
    cellInput.value = id;
    vertices[y][x] = vertices[y][x + 1] = vertices[y + 1][x] = vertices[y + 1][x + 1] = brush.value;
    error();
    editMap(vertices);
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
    if (!mapsLoaded) {
      mapsLoaded = true;
      request("/maps").then(entries => {
        maps = entries;
        mapOptions(savedMap?.id);
      }).catch(cause => {
        mapsLoaded = false;
        mapError(cause.message);
      });
    }
    const nextStorage = route + "/preview/" + next.tileset.digest + "/" + JSON.stringify(next.tileset.grid);
    if (nextStorage !== storage) {
      storage = nextStorage;
      if (!savedMap) {
        vertices = lattice(null, 8, 6);
        try {
          const stored = JSON.parse(sessionStorage.getItem(storage));
          if (stored?.length === 7 && stored.every(row => Array.isArray(row) && row.length === 9)) vertices = stored;
        } catch {}
      }
    }
    const before = rules.colors;
    rules = next.tileset.terrain || {colors: [], tiles: {}};
    if (JSON.stringify(before) !== JSON.stringify(rules.colors)) names.value = rules.colors.join("\n");
    find("#terrainCorners").hidden = !rules.colors.length;
    find("#terrainPreview").hidden = false;
    const options = rules.colors.map(name => `<option value="${esc(name)}">${esc(name)}</option>`).join("");
    for (const select of corners) select.innerHTML = '<option value="">Unassigned</option>' + options;
    const previousBrush = brush.value;
    brush.innerHTML = options;
    brush.value = rules.colors.includes(previousBrush) ? previousBrush : rules.colors[0] || "";
    brush.disabled = find("#terrainFill").disabled = find("#terrainPaint").disabled = !rules.colors.length;
    selectTile(tile, true);
    editMap(vertices);
  }

  find("#terrainSaveNames").onclick = event => {
    const colors = names.value.split(/\r?\n/).map(name => name.trim()).filter(Boolean);
    save(event.currentTarget, {colors, tiles: rules.tiles});
  };
  find("#terrainSaveTile").onclick = event => {
    const tiles = {...rules.tiles, [tile]: corners.map(select => select.value || null)};
    save(event.currentTarget, {colors: rules.colors, tiles});
  };
  find("#terrainFill").onclick = () => { if (!mapWorking) { error(); editMap(lattice(brush.value)); } };
  find("#terrainClear").onclick = () => { if (!mapWorking) { error(); editMap(lattice()); } };
  find("#terrainPaint").onclick = () => paint(cellInput.valueAsNumber);
  mapList.onchange = mapControls;
  mapName.oninput = () => {
    find("#terrainMapDownload").hidden = true;
    mapControls();
  };
  const maySwitch = () => !dirtyMap() || confirm("Discard unsaved map changes?");
  find("#terrainMapNew").onclick = () => {
    if (!maySwitch()) return;
    mapError();
    savedMap = null;
    mapName.value = "";
    mapList.value = "";
    editMap(lattice(null, 8, 6));
  };
  find("#terrainMapOpen").onclick = () => {
    if (!mapList.value || !maySwitch()) return;
    mapAction(async () => {
      const opened = await request("/maps/" + encodeURIComponent(mapList.value));
      if (!savedMap) forgetDraft();
      savedMap = opened;
      mapName.value = savedMap.name;
      editMap(savedMap.vertices.map(row => row.slice()));
    });
  };
  find("#terrainMapForm").onsubmit = event => {
    event.preventDefault();
    mapAction(async () => {
      const updated = await request("/maps", {id: savedMap?.id, revision: savedMap?.revision,
        name: mapName.value, vertices, tileset_revision: state.revision});
      if (!savedMap) forgetDraft();
      savedMap = updated;
      mapName.value = savedMap.name;
      const entry = {id: savedMap.id, name: savedMap.name};
      maps = [...maps.filter(map => map.id !== entry.id), entry].sort((a, b) => a.name.localeCompare(b.name));
      mapOptions(entry.id);
    });
  };
  find("#terrainMapExport").onclick = () => mapAction(async () => {
    const exported = await request("/maps/" + encodeURIComponent(savedMap.id) + "/export",
      {revision: savedMap.revision, tileset_revision: state.revision});
    const download = find("#terrainMapDownload");
    download.href = exported.download;
    download.hidden = false;
    find("#terrainMapStatus").textContent = "Map package ready";
  });
  canvas.onclick = event => {
    const box = canvas.getBoundingClientRect();
    const x = Math.floor((event.clientX - box.left) * cols / box.width);
    const y = Math.floor((event.clientY - box.top) * rows / box.height);
    if (x >= 0 && x < cols && y >= 0 && y < rows) paint(y * cols + x);
  };
  return {sync, selectTile, draw};
}
