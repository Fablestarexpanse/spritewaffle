function bindTilesetModules(panel, request, image, apply, selectedTile) {
  panel.innerHTML = `<h2>Tile modules</h2>
    <p class="hint">Save a rectangle from the atlas as a reusable section. Transparent tiles leave the map beneath them intact.</p>
    <div class="tileset-workspace">
      <div>
        <canvas id="modulePreview" class="module-preview" aria-label="Tile module preview" hidden></canvas>
        <p id="moduleSize" class="muted" role="status"></p>
        <p id="moduleCount" class="muted"></p>
      </div>
      <form id="moduleForm">
        <fieldset class="tile-animation-fields">
          <div class="tileset-form">
            <label class="field full">Module name <input name="name" required maxlength="64" placeholder="Doorway"></label>
            <label class="field">First corner tile <input name="start" type="number" value="0" min="0" required></label>
            <label class="field">Opposite corner tile <input name="end" type="number" value="0" min="0" required></label>
          </div>
          <div class="row">
            <button type="button" data-module-corner="start">Use selected as first</button>
            <button type="button" data-module-corner="end">Use selected as opposite</button>
          </div>
          <button type="submit" id="moduleSave">Save module</button>
        </fieldset>
        <p id="moduleStatus" class="muted" role="status"></p>
        <p id="moduleError" class="warn" role="alert" hidden></p>
      </form>
    </div>
    <div id="moduleExportPanel" hidden>
      <h3>Export a standalone module</h3>
      <form id="moduleExportForm" class="tileset-workspace">
        <div>
          <canvas id="moduleAssetPreview" class="module-preview" aria-label="Module preview with pivot and collision" hidden></canvas>
          <p id="moduleAssetSize" class="muted"></p>
        </div>
        <fieldset class="tile-animation-fields">
          <div class="tileset-form">
            <label class="field full">Saved module <select name="module"></select></label>
            <label class="field">Pivot X (px) <input type="number" name="pivotX" min="0" required></label>
            <label class="field">Pivot Y (px) <input type="number" name="pivotY" min="0" required></label>
          </div>
          <div class="row">
            <button type="button" id="modulePivotReset">Reset pivot</button>
            <button type="submit" id="moduleExport">Prepare asset ZIP</button>
          </div>
          <a id="moduleDownload" hidden>Download module ZIP</a>
          <p id="moduleExportError" class="warn" role="alert" hidden></p>
        </fieldset>
      </form>
    </div>`;
  const find = selector => panel.querySelector(selector);
  const form = find("#moduleForm"), fields = form.elements, canvas = find("#modulePreview");
  const status = find("#moduleStatus"), error = find("#moduleError");
  const exportForm = find("#moduleExportForm"), exportFields = exportForm.elements;
  const asset = find("#moduleAssetPreview"), download = find("#moduleDownload"), exportError = find("#moduleExportError");
  let state;

  function renderTiles(target, tiles, pivot, solid = new Set()) {
    const {grid} = state.tileset, {tile_width: tw, tile_height: th} = grid;
    const width = tiles[0].length, height = tiles.length;
    const scale = Math.min(5, 288 / Math.max(width * tw, height * th));
    const w = Math.max(1, Math.round(tw * scale)), h = Math.max(1, Math.round(th * scale));
    target.width = width * w;
    target.height = height * h;
    target.hidden = !state.preview || !image.complete || !image.naturalWidth;
    if (target.hidden) return;
    const ctx = target.getContext("2d"), style = getComputedStyle(target);
    ctx.imageSmoothingEnabled = false;
    ctx.strokeStyle = style.getPropertyValue("--warn").trim();
    ctx.setLineDash([3, 2]);
    tiles.forEach((line, y) => line.forEach((id, x) => {
      if (id === null) return;
      drawTilesetCell(ctx, image, grid, id, x * w, y * h, w, h);
      if (solid.has(id)) ctx.strokeRect(x * w + .5, y * h + .5, w - 1, h - 1);
    }));
    if (pivot) {
      const x = Math.min(target.width - 1, pivot[0] * w / tw);
      const y = Math.min(target.height - 1, pivot[1] * h / th);
      ctx.strokeStyle = style.getPropertyValue("--accent").trim();
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.moveTo(x - 5, y);
      ctx.lineTo(x + 5, y);
      ctx.moveTo(x, y - 5);
      ctx.lineTo(x, y + 5);
      ctx.stroke();
    }
  }

  function drawDraft() {
    const {grid: {columns}, empty_tiles} = state.tileset;
    const start = fields.start.valueAsNumber, end = fields.end.valueAsNumber;
    const size = find("#moduleSize");
    canvas.hidden = true;
    if (!fields.start.validity.valid || !fields.end.validity.valid) {
      size.textContent = "Choose two atlas tile IDs.";
      return;
    }
    const col = Math.min(start % columns, end % columns), row = Math.min(Math.floor(start / columns), Math.floor(end / columns));
    const width = Math.abs(start % columns - end % columns) + 1;
    const height = Math.abs(Math.floor(start / columns) - Math.floor(end / columns)) + 1;
    if (Math.max(width, height) > 16) {
      size.textContent = "Choose a region up to 16 × 16 tiles.";
      return;
    }
    const empty = new Set(empty_tiles);
    const tiles = Array.from({length: height}, (_, y) => Array.from({length: width}, (_, x) => {
      const id = (row + y) * columns + col + x;
      return empty.has(id) ? null : id;
    }));
    renderTiles(canvas, tiles);
    size.textContent = `${width} × ${height} tiles`;
  }

  function selectedModule() {
    return state?.tileset?.modules?.find(entry => entry.name === exportFields.module.value);
  }

  function drawAsset(reset = false) {
    const module = selectedModule();
    find("#moduleExportPanel").hidden = !module;
    if (!module) return;
    const {tile_width: tw, tile_height: th} = state.tileset.grid;
    const width = module.width * tw, height = module.height * th;
    exportFields.pivotX.max = width;
    exportFields.pivotY.max = height;
    if (reset) {
      exportFields.pivotX.value = Math.floor(width / 2);
      exportFields.pivotY.value = height;
    }
    const valid = exportFields.pivotX.validity.valid && exportFields.pivotY.validity.valid;
    find("#moduleExport").disabled = !valid || !state.preview;
    const pivot = valid ? [exportFields.pivotX.valueAsNumber, exportFields.pivotY.valueAsNumber] : null;
    const solids = new Set(state.tileset.solid_tiles);
    const count = module.tiles.flat().filter(id => solids.has(id)).length;
    find("#moduleAssetSize").textContent = `${width} × ${height} px · ${count} collision cell${count === 1 ? "" : "s"}`;
    renderTiles(asset, module.tiles, pivot, solids);
  }

  function clearExport() {
    download.hidden = exportError.hidden = true;
  }

  exportFields.module.onchange = find("#modulePivotReset").onclick = () => { clearExport(); drawAsset(true); };
  exportFields.pivotX.oninput = exportFields.pivotY.oninput = () => { clearExport(); drawAsset(); };
  exportForm.onsubmit = async event => {
    event.preventDefault();
    const fieldset = exportForm.querySelector("fieldset");
    const requestBody = {name: exportFields.module.value, revision: state.revision,
      pivot: [exportFields.pivotX.valueAsNumber, exportFields.pivotY.valueAsNumber]};
    fieldset.disabled = true;
    clearExport();
    try {
      const result = await request("/modules/export", requestBody);
      if (state.revision !== requestBody.revision) return;
      download.href = result.download;
      download.hidden = false;
      fieldset.disabled = false;
      download.focus();
    } catch (cause) {
      exportError.textContent = cause.message;
      exportError.hidden = false;
    } finally {
      fieldset.disabled = false;
    }
  };

  panel.querySelectorAll("[data-module-corner]").forEach(button => button.onclick = () => {
    fields[button.dataset.moduleCorner].value = selectedTile();
    drawDraft();
  });
  fields.start.oninput = fields.end.oninput = drawDraft;
  form.onsubmit = async event => {
    event.preventDefault();
    const name = fields.name.value;
    const fieldset = find("fieldset");
    fieldset.disabled = true;
    error.hidden = true;
    status.textContent = "";
    try {
      const result = await request("/modules", {name, start: fields.start.valueAsNumber, end: fields.end.valueAsNumber,
        revision: state.revision});
      apply(result);
      exportFields.module.value = name.trim();
      clearExport();
      drawAsset(true);
      fields.name.value = "";
      status.textContent = `Saved ${name.trim()}. Choose Place module in Map preview.`;
    } catch (cause) {
      error.textContent = cause.message;
      error.hidden = false;
    } finally {
      fieldset.disabled = false;
    }
  };
  return {
    draw() {
      if (!state?.tileset) return;
      drawDraft();
      drawAsset();
    },
    sync(result) {
      const atlasChanged = result.atlas_revision !== state?.atlas_revision;
      if (result.revision !== state?.revision) clearExport();
      state = result;
      panel.hidden = !result.tileset;
      if (!result.tileset) return;
      const {grid, modules = []} = result.tileset;
      fields.start.max = fields.end.max = grid.columns * grid.rows - 1;
      if (atlasChanged) {
        fields.start.value = fields.end.value = 0;
        fields.name.value = "";
        status.textContent = "";
        error.hidden = true;
      }
      find("#moduleCount").textContent = modules.length
        ? `${modules.length} saved · ${modules.map(module => module.name).join(", ")}` : "No modules saved.";
      const before = exportFields.module.value;
      exportFields.module.replaceChildren(...modules.map(module => new Option(module.name, module.name)));
      if (modules.some(module => module.name === before)) exportFields.module.value = before;
      drawDraft();
      drawAsset(atlasChanged || exportFields.module.value !== before);
    },
  };
}
