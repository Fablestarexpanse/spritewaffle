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
    </div>`;
  const find = selector => panel.querySelector(selector);
  const form = find("#moduleForm"), fields = form.elements, canvas = find("#modulePreview");
  const status = find("#moduleStatus"), error = find("#moduleError");
  let state;

  function draw() {
    if (!state?.tileset) return;
    const {grid, empty_tiles} = state.tileset;
    const {columns, tile_width: tw, tile_height: th} = grid;
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
    const scale = Math.min(5, 288 / Math.max(width * tw, height * th));
    const w = Math.max(1, Math.round(tw * scale)), h = Math.max(1, Math.round(th * scale));
    canvas.width = width * w;
    canvas.height = height * h;
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    canvas.hidden = !state.preview || !image.complete || !image.naturalWidth;
    if (!canvas.hidden) {
      for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
          const id = (row + y) * columns + col + x;
          if (!empty.has(id)) drawTilesetCell(ctx, image, grid, id, x * w, y * h, w, h);
        }
      }
    }
    size.textContent = `${width} × ${height} tiles`;
  }

  panel.querySelectorAll("[data-module-corner]").forEach(button => button.onclick = () => {
    fields[button.dataset.moduleCorner].value = selectedTile();
    draw();
  });
  fields.start.oninput = fields.end.oninput = draw;
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
    draw,
    sync(result) {
      const atlasChanged = result.atlas_revision !== state?.atlas_revision;
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
      draw();
    },
  };
}
