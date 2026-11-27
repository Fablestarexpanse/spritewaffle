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
        <p class="hint">Terrain paint sets all four corners of a cell. Dashed outlines mark unresolved cells.</p>
        <div class="row">
          <label>Terrain <select id="terrainBrush"></select></label>
          <button type="button" id="terrainFill">Fill preview</button>
          <button type="button" id="terrainClear">Clear ground</button>
        </div>
        <div class="row">
          <label>Cell <input type="number" id="terrainCell" min="0" max="47" value="0" step="1"></label>
          <label>Cell action
            <select id="terrainCellMode">
              <option value="terrain">Paint terrain</option>
              <option value="tile">Place selected tile</option>
              <option value="stamp" hidden>Place module</option>
              <option value="empty">Leave empty</option>
              <option value="restore">Restore terrain</option>
            </select>
          </label>
          <button type="button" id="terrainPaint">Paint cell</button>
        </div>
        <label class="field" id="terrainModuleField" hidden>Module <select id="terrainModule"></select></label>
        <p id="terrainStampError" class="warn" role="alert" hidden></p>
        <p id="terrainOverrideHint" class="hint" hidden></p>
        <details id="terrainObjectPanel"></details>
        <h3 id="terrainMapsHeading">Saved maps</h3>
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
            <label title="Cells no tile matches are left empty instead of stopping the export"><input type="checkbox" id="terrainMapEmpty"> allow empty cells</label>
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
  const cellMode = find("#terrainCellMode"), cellButton = find("#terrainPaint"), overrideHint = find("#terrainOverrideHint");
  const moduleSelect = find("#terrainModule");
  let cols = 8, rows = 6;
  const lattice = (name = null, width = cols, height = rows) =>
    Array.from({length: height + 1}, () => Array(width + 1).fill(name));
  let state, tile = 0, rules = {colors: [], tiles: {}}, vertices = lattice(), result, storage, revision = 0;
  let savedMap = null, maps = [], mapsLoaded = false, mapWorking = false;
  let overrides = {}, overrideAtlas;
  const objects = bindTilemapObjects(find("#terrainObjectPanel"), () => editMap(vertices), () => cellInput.valueAsNumber,
    request);

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
    if (!savedMap) return !!mapName.value.trim() || Object.keys(overrides).length > 0 || objects.entries().length > 0 ||
      vertices.some(row => row.some(name => name !== null));
    return mapName.value.trim() !== savedMap.name ||
      JSON.stringify(vertices) !== JSON.stringify(savedMap.vertices) ||
      JSON.stringify(overrides) !== JSON.stringify(savedMap.overrides || {}) ||
      overrideAtlas !== savedMap.override_atlas ||
      JSON.stringify(objects.entries()) !== JSON.stringify(savedMap.objects || []);
  }

  function updateCellTool() {
    const labels = {terrain: "Paint cell", tile: "Place tile " + tile, stamp: "Stamp module", empty: "Leave cell empty", restore: "Restore cell"};
    const stale = overrideAtlas && overrideAtlas !== state.atlas_revision;
    find("#terrainModuleField").hidden = cellMode.value !== "stamp";
    cellButton.textContent = labels[cellMode.value];
    cellButton.disabled = (cellMode.value === "terrain" && !brush.value) || (cellMode.value === "tile" && !!stale)
      || (cellMode.value === "stamp" && (!moduleSelect.value || !!stale));
    overrideHint.hidden = !stale;
    overrideHint.textContent = stale ? "The tile sheet changed. Restore the marked cells before placing tiles from this sheet." : "";
  }

  function mapControls() {
    const dirty = dirtyMap();
    find("#terrainMapOpen").disabled = !mapList.value;
    // unresolved cells block the export unless "allow empty cells" is ticked (they export as empty)
    find("#terrainMapExport").disabled = !savedMap || dirty || !result
      || (!!result.missing.length && !find("#terrainMapEmpty").checked) || !!objects.outdated();
    find("#terrainMapStatus").textContent = savedMap
      ? (dirty ? "Unsaved map changes" : "Saved to the project") : "Draft · Save to add it to the project";
  }

  function mapOptions(selected) {
    mapList.replaceChildren(new Option("Select a map", ""), ...maps.map(({id, name}) => new Option(name, id)));
    mapList.value = selected || "";
    mapControls();
  }

  async function mapAction(action, report = mapError) {
    if (mapWorking) return;
    mapWorking = true;
    find("#terrainMapControls").disabled = true;
    objects.locked(true);
    report();
    try { await action(); }
    catch (cause) { report(cause.message); }
    finally {
      find("#terrainMapControls").disabled = false;
      objects.locked(false);
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
    objects.sync(state, cols * rows);
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
    const byCell = new Map(objects.entries().map(entry => [entry.cell, entry]));
    const atlasReady = state.preview && image.complete && image.naturalWidth;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.imageSmoothingEnabled = false;
    result.tiles.forEach((row, y) => row.forEach((id, x) => {
      if (id !== null && atlasReady) {
        drawTilesetCell(ctx, image, grid, frameFor(id), x * w, y * h, w, h);
      }
      const cell = y * cols + x;
      const object = byCell.get(cell);
      const stale = object && object.atlas !== state.atlas_revision;
      if (object && !stale && atlasReady) {
        const stateTile = object.states.find(entry => entry.name === object.state)?.tile;
        if (Number.isInteger(stateTile)) drawTilesetCell(ctx, image, grid, frameFor(stateTile), x * w, y * h, w, h);
      }
      const unmatched = stale || missing.has(cell);
      const color = unmatched ? "--warn" : object || Object.hasOwn(overrides, cell) ? "--accent" : "--line";
      ctx.strokeStyle = style.getPropertyValue(color).trim();
      ctx.setLineDash(unmatched ? [3, 2] : []);
      ctx.strokeRect(x * w + .5, y * h + .5, w - 1, h - 1);
    }));
  }

  async function resolveMap() {
    const id = ++revision;
    if (!savedMap) {
      try { sessionStorage.setItem(storage, JSON.stringify({vertices, overrides, overrideAtlas, objects: objects.entries()})); } catch {}
    }
    try {
      const resolved = await request("/preview", {vertices, revision: state.revision, allow_unknown: true,
        overrides, override_atlas: overrideAtlas});
      if (id !== revision) return;
      result = resolved;
      const count = result.tiles.flat().filter(id => id !== null).length;
      const invalid = result.invalid_overrides?.length || 0;
      const missing = result.missing.length - invalid;
      const outdated = objects.outdated();
      find("#terrainStats").textContent = `${count} placed · ${missing} missing transition${missing === 1 ? "" : "s"}` +
        (invalid ? ` · ${invalid} outdated placement${invalid === 1 ? "" : "s"}` : "") +
        (outdated ? ` · ${outdated} outdated object${outdated === 1 ? "" : "s"}` : "");
      mapControls();
      draw();
    } catch (cause) {
      if (id === revision) error(cause.message);
    }
  }

  function paint(id) {
    if (mapWorking || cellButton.disabled || !Number.isInteger(id) || id < 0 || id >= cols * rows) return;
    cellInput.value = id;
    if (cellMode.value === "stamp") {
      cellButton.disabled = true;
      mapAction(async () => {
        const placed = await request("/stamp", {name: moduleSelect.value, cell: id, vertices, overrides,
          override_atlas: overrideAtlas, revision: state.revision});
        overrides = placed.overrides;
        overrideAtlas = placed.override_atlas;
        editMap(vertices);
      }, stampError).finally(updateCellTool);
      return;
    }
    switch (cellMode.value) {
      case "terrain": {
        const x = id % cols, y = Math.floor(id / cols);
        vertices[y][x] = vertices[y][x + 1] = vertices[y + 1][x] = vertices[y + 1][x + 1] = brush.value;
        break;
      }
      case "tile":
        overrides[id] = tile;
        overrideAtlas = state.atlas_revision;
        break;
      case "empty":
        overrides[id] = null;
        break;
      case "restore":
        delete overrides[id];
        break;
    }
    if (!Object.values(overrides).some(value => value !== null)) overrideAtlas = undefined;
    error();
    updateCellTool();
    editMap(vertices);
  }

  function stampError(message = "") {
    const notice = find("#terrainStampError");
    notice.textContent = message;
    notice.hidden = !message;
  }

  function selectTile(id, reset = false) {
    if (id === tile && !reset) return;
    tile = id;
    updateCellTool();
    find("#terrainTileHeading").textContent = `Tile ${id} corners`;
    const saved = rules.tiles[id] || [null, null, null, null];
    corners.forEach((select, i) => select.value = saved[i] ?? "");
  }

  function sync(next) {
    const changed = next.revision !== state?.revision;
    state = next;
    panel.hidden = !next.tileset;
    if (!next.tileset || !changed) return;
    objects.sync(next, cols * rows);
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
        overrides = {};
        overrideAtlas = undefined;
        let storedObjects;
        try {
          const stored = JSON.parse(sessionStorage.getItem(storage));
          const draft = stored?.vertices || stored;
          if (draft?.length === 7 && draft.every(row => Array.isArray(row) && row.length === 9)) {
            vertices = draft;
            overrides = stored.overrides || {};
            overrideAtlas = stored.overrideAtlas;
            storedObjects = stored.objects;
          }
        } catch {}
        objects.load(storedObjects);
      }
    }
    const before = rules.colors;
    rules = next.tileset.terrain || {colors: [], tiles: {}};
    const modules = next.tileset.modules || [];
    const selection = moduleSelect.value;
    moduleSelect.replaceChildren(...modules.map(item => new Option(`${item.name} · ${item.width} × ${item.height}`, item.name)));
    if (modules.some(item => item.name === selection)) moduleSelect.value = selection;
    cellMode.querySelector('option[value="stamp"]').hidden = !modules.length;
    if (!modules.length && cellMode.value === "stamp") cellMode.value = "terrain";
    if (JSON.stringify(before) !== JSON.stringify(rules.colors)) names.value = rules.colors.join("\n");
    // blob (mixed) sets are painted in Tiled or Godot; the corner editor and preview don't apply
    const blob = rules.mode === "mixed";
    let note = find("#terrainBlobNote");
    if (!note) { note = document.createElement("p"); note.id = "terrainBlobNote"; note.className = "hint"; find("#terrainError").before(note); }
    note.hidden = !blob;
    note.innerHTML = blob ? `This is a <b>blob</b> set (${Object.keys(rules.centers || rules.tiles).length} tiles, edges and corners).
      Paint maps with it in <b>Tiled</b> (mixed Wang set) or <b>Godot</b> (Match Corners and Sides terrain): export the tileset.
      The corner editor and the map preview here work with corner sets.` : "";
    names.disabled = find("#terrainSaveNames").disabled = blob;
    find("#terrainCorners").hidden = !rules.colors.length || blob;
    find("#terrainPreview").hidden = blob;
    if (blob) { find("#terrainError").hidden = true; return; }      // no corner preview to request
    const options = rules.colors.map(name => `<option value="${esc(name)}">${esc(name)}</option>`).join("");
    for (const select of corners) select.innerHTML = '<option value="">Unassigned</option>' + options;
    const previousBrush = brush.value;
    brush.innerHTML = options;
    brush.value = rules.colors.includes(previousBrush) ? previousBrush : rules.colors[0] || "";
    brush.disabled = find("#terrainFill").disabled = !rules.colors.length;
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
  find("#terrainClear").onclick = () => {
    if (mapWorking) return;
    error();
    overrides = {};
    overrideAtlas = undefined;
    updateCellTool();
    editMap(lattice());
  };
  cellMode.onchange = () => { stampError(); updateCellTool(); };
  moduleSelect.onchange = () => { stampError(); updateCellTool(); };
  cellButton.onclick = () => paint(cellInput.valueAsNumber);
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
    overrides = {};
    overrideAtlas = undefined;
    mapName.value = "";
    mapList.value = "";
    objects.load();
    updateCellTool();
    editMap(lattice(null, 8, 6));
  };
  find("#terrainMapOpen").onclick = () => {
    if (!mapList.value || !maySwitch()) return;
    mapAction(async () => {
      const opened = await request("/maps/" + encodeURIComponent(mapList.value));
      if (!savedMap) forgetDraft();
      savedMap = opened;
      mapName.value = savedMap.name;
      overrides = {...savedMap.overrides};
      overrideAtlas = savedMap.override_atlas;
      objects.load(savedMap.objects);
      updateCellTool();
      editMap(savedMap.vertices.map(row => row.slice()));
    });
  };
  find("#terrainMapForm").onsubmit = event => {
    event.preventDefault();
    mapAction(async () => {
      const updated = await request("/maps", {id: savedMap?.id, revision: savedMap?.revision,
        name: mapName.value, vertices, tileset_revision: state.revision, overrides, override_atlas: overrideAtlas,
        objects: objects.entries()});
      if (!savedMap) forgetDraft();
      savedMap = updated;
      overrideAtlas = savedMap.override_atlas;
      mapName.value = savedMap.name;
      const entry = {id: savedMap.id, name: savedMap.name};
      maps = [...maps.filter(map => map.id !== entry.id), entry].sort((a, b) => a.name.localeCompare(b.name));
      mapOptions(entry.id);
    });
  };
  find("#terrainMapEmpty").onchange = () => mapControls();
  find("#terrainMapExport").onclick = () => mapAction(async () => {
    const exported = await request("/maps/" + encodeURIComponent(savedMap.id) + "/export",
      {revision: savedMap.revision, tileset_revision: state.revision, allow_empty: find("#terrainMapEmpty").checked});
    const download = find("#terrainMapDownload");
    download.href = exported.download;
    download.hidden = false;
    find("#terrainMapStatus").textContent = (exported.empty_cells
      ? `Map package ready · ${exported.empty_cells} empty cell${exported.empty_cells === 1 ? "" : "s"}` : "Map package ready")
      + (exported.ldtk_skipped ? ` · no LDtk file: ${exported.ldtk_skipped}` : " · Tiled + LDtk");
  });
  canvas.onclick = event => {
    const box = canvas.getBoundingClientRect();
    const x = Math.floor((event.clientX - box.left) * cols / box.width);
    const y = Math.floor((event.clientY - box.top) * rows / box.height);
    if (x >= 0 && x < cols && y >= 0 && y < rows) paint(y * cols + x);
  };
  return {sync, selectTile, draw};
}
