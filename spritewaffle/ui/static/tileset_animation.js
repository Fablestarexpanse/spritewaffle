function tileFrameAt(frames, elapsed) {
  const duration = frames.reduce((total, frame) => total + frame.duration_ms, 0);
  let remaining = Math.max(0, elapsed) % duration;
  for (const frame of frames) {
    if (remaining < frame.duration_ms) return frame.tile;
    remaining -= frame.duration_ms;
  }
  return null;
}

function drawTilesetCell(ctx, image, grid, id, x, y, width, height) {
  const {tile_width: w, tile_height: h, margin, spacing, columns} = grid;
  const sx = margin + id % columns * (w + spacing);
  const sy = margin + Math.floor(id / columns) * (h + spacing);
  ctx.drawImage(image, sx, sy, w, h, x, y, width, height);
}

function bindTilesetAnimation(panel, request, image, apply, drawMap) {
  panel.innerHTML = `
    <h2>Tile animation</h2>
    <p class="hint">Select a tile, then add atlas tile IDs in playback order. Save to update both previews.</p>
    <div class="tile-animation-layout">
      <div>
        <canvas id="tileAnimationCanvas" aria-label="Selected tile animation preview"></canvas>
        <p id="tileAnimationSample" class="muted"></p>
        <button id="tileAnimationPlay" type="button" disabled>Play previews</button>
      </div>
      <form id="tileAnimationForm">
        <fieldset class="tile-animation-fields" aria-label="Tile animation frames">
          <ol id="tileAnimationFrames"></ol>
          <div class="row">
            <button id="tileAnimationAdd" type="button">Add frame</button>
            <button id="tileAnimationSave" type="submit">Save animation</button>
            <button id="tileAnimationClear" type="button">Clear animation</button>
          </div>
        </fieldset>
        <p id="tileAnimationError" class="warn" role="alert" hidden></p>
      </form>
    </div>`;
  const find = selector => panel.querySelector(selector);
  const canvas = find("#tileAnimationCanvas"), fields = find("fieldset"), form = find("form");
  const frameList = find("#tileAnimationFrames"), play = find("#tileAnimationPlay");
  const add = find("#tileAnimationAdd"), save = find("#tileAnimationSave"), clear = find("#tileAnimationClear");
  let state, active = 0, draft = [], editorKey, elapsed = 0, started = null, animationId;

  function frameFor(id) {
    const frames = state?.tileset?.animations?.[id];
    return frames ? tileFrameAt(frames, elapsed) : id;
  }

  function draw() {
    if (!state?.tileset) return;
    const {grid} = state.tileset;
    const scale = 96 / Math.max(grid.tile_width, grid.tile_height);
    const width = Math.max(1, Math.round(grid.tile_width * scale));
    const height = Math.max(1, Math.round(grid.tile_height * scale));
    if (canvas.width !== width) canvas.width = width;
    if (canvas.height !== height) canvas.height = height;
    const id = frameFor(active);
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, width, height);
    ctx.imageSmoothingEnabled = false;
    if (state.preview && image.complete && image.naturalWidth) drawTilesetCell(ctx, image, grid, id, 0, 0, width, height);
    const sample = find("#tileAnimationSample");
    const label = "Tile " + active + " · Preview frame " + id;
    if (sample.textContent !== label) sample.textContent = label;
  }

  function animate(now) {
    if (!panel.isConnected) return pause();
    const previous = elapsed;
    elapsed = now - started;
    const animations = Object.values(state.tileset.animations || {});
    if (animations.some(frames => tileFrameAt(frames, previous) !== tileFrameAt(frames, elapsed))) {
      draw();
      drawMap();
    }
    animationId = requestAnimationFrame(animate);
  }

  function pause() {
    cancelAnimationFrame(animationId);
    started = null;
    play.textContent = "Play previews";
  }

  function error(message = "") {
    const notice = find("#tileAnimationError");
    notice.textContent = message;
    notice.hidden = !message;
  }

  function rows() {
    const {rows, columns} = state.tileset.grid;
    frameList.innerHTML = draft.map((frame, index) => `
      <li class="tile-animation-frame" data-index="${index}">
        <label>Frame ${index + 1} tile ID
          <input type="number" data-key="tile" min="0" max="${rows * columns - 1}" required value="${frame.tile ?? ""}">
        </label>
        <label>Duration (ms)
          <input type="number" data-key="duration_ms" min="1" max="60000" required value="${frame.duration_ms ?? ""}">
        </label>
        <div class="row">
          <button type="button" data-change="up" aria-label="Move frame ${index + 1} up" ${index === 0 ? "disabled" : ""}>↑</button>
          <button type="button" data-change="down" aria-label="Move frame ${index + 1} down" ${index === draft.length - 1 ? "disabled" : ""}>↓</button>
          <button type="button" data-change="remove" aria-label="Remove frame ${index + 1}">Remove</button>
        </div>
      </li>`).join("");
    add.disabled = draft.length >= 64;
    save.disabled = draft.length < 2;
    clear.disabled = !state.tileset.animations?.[active];
  }

  function selectTile(id) {
    active = id;
    const {digest, grid, animations = {}} = state.tileset;
    const saved = animations[id] || [];
    const key = JSON.stringify([digest, grid, id, saved]);
    if (editorKey !== key) {
      editorKey = key;
      draft = saved.map(frame => ({...frame}));
      rows();
      error();
    }
    draw();
  }

  async function submit(frames) {
    fields.disabled = true;
    error();
    try {
      const result = await request("/animation", {tile: active, frames, revision: state.revision});
      editorKey = null;
      apply(result);
    } catch (cause) {
      error(cause.message);
    } finally {
      fields.disabled = false;
    }
  }

  play.onclick = () => {
    if (started !== null) return pause();
    started = performance.now() - elapsed;
    play.textContent = "Pause previews";
    animationId = requestAnimationFrame(animate);
  };
  add.onclick = () => {
    draft.push({tile: active, duration_ms: 100});
    rows();
    frameList.lastElementChild.querySelector("input").focus();
  };
  frameList.oninput = event => {
    const input = event.target;
    if (!input.dataset.key) return;
    const index = Number(input.closest("li").dataset.index);
    draft[index][input.dataset.key] = Number.isNaN(input.valueAsNumber) ? null : input.valueAsNumber;
  };
  frameList.onclick = event => {
    const {change} = event.target.dataset;
    if (!change) return;
    const index = Number(event.target.closest("li").dataset.index);
    const [frame] = draft.splice(index, 1);
    const destination = index + (change === "up" ? -1 : 1);
    if (change !== "remove") draft.splice(destination, 0, frame);
    rows();
    const next = frameList.children[change === "remove" ? Math.min(index, draft.length - 1) : destination];
    if (next) next.querySelector("input").focus();
    else add.focus();
  };
  form.onsubmit = event => {
    event.preventDefault();
    submit(draft);
  };
  clear.onclick = () => submit([]);

  return {
    draw, frameFor, selectTile,
    sync(result) {
      const old = state?.tileset;
      state = result;
      panel.hidden = !state.tileset;
      play.disabled = !state.preview || !Object.keys(state.tileset?.animations || {}).length;
      if (play.disabled || old?.digest !== state.tileset?.digest ||
          JSON.stringify(old?.grid) !== JSON.stringify(state.tileset?.grid)) {
        pause();
        elapsed = 0;
      }
    }
  };
}

if (typeof module !== "undefined") module.exports = {tileFrameAt};
