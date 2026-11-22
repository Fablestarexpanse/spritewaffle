"use strict";

function pixelRectangle([x1, y1], [x2, y2]) {
  return {left: Math.min(x1, x2), top: Math.min(y1, y2),
          right: Math.max(x1, x2), bottom: Math.max(y1, y2)};
}

function insidePixelRectangle({left, top, right, bottom}, x, y) {
  return left <= x && x <= right && top <= y && y <= bottom;
}

function pixelFillOffsets(pixels, width, bounds, [x, y], paint) {
  if (!insidePixelRectangle(bounds, x, y)) return [];
  const target = pixels.getUint32(4 * (y * width + x));
  if (target === paint) return [];
  const {left, top, right, bottom} = bounds;
  const stride = right - left + 1;
  const area = stride * (bottom - top + 1);
  const visited = new Uint8Array(area);
  const offsets = new Uint32Array(area);
  let count = 0;
  function visit(column, row) {
    if (!insidePixelRectangle(bounds, column, row)) return;
    const cell = (row - top) * stride + column - left;
    if (visited[cell]) return;
    visited[cell] = 1;
    const offset = 4 * (row * width + column);
    if (pixels.getUint32(offset) === target) offsets[count++] = offset;
  }
  // The queue holds only matching pixels, with at most one entry per cell in bounds.
  visit(x, y);
  for (let head = 0; head < count; head++) {
    const index = offsets[head] / 4;
    const column = index % width, row = Math.floor(index / width);
    visit(column - 1, row);
    visit(column + 1, row);
    visit(column, row - 1);
    visit(column, row + 1);
  }
  return offsets.subarray(0, count);
}

function showPixelEditor(readUrl, saveUrl, frame, label, onSave) {
  const dialog = document.querySelector("#pixelEditor");
  if (dialog.open) return;
  dialog.innerHTML = `
    <div class="row" style="margin:0">
      <h2 id="pxTitle" style="margin:0">Edit pixels</h2>
      <span class="spacer"></span><button id="pxClose" type="button" autofocus>Close</button>
    </div>
    <p id="pxFrame" class="muted"></p>
    <p id="pxStatus" class="muted" role="status">Loading frame…</p>
    <fieldset id="pxControls" disabled hidden>
      <div class="row" id="pxTools" role="group" aria-label="Drawing tools">
        <button type="button" data-tool="pencil" aria-pressed="true">Pencil</button>
        <button type="button" data-tool="eraser" aria-pressed="false">Eraser</button>
        <button type="button" data-tool="fill" aria-pressed="false">Fill</button>
        <button type="button" data-tool="picker" aria-pressed="false">Pick color</button>
        <button type="button" data-tool="select" aria-pressed="false">Select</button>
        <label>Color <input id="pxColor" type="color" value="#542073"></label>
        <label>Alpha <input id="pxAlpha" type="number" min="0" max="255" step="1" value="255" required></label>
      </div>
      <div id="pxPalette" class="row" role="group" aria-label="Job palette" hidden></div>
      <div class="row">
        <button id="pxOut" type="button" aria-label="Zoom out">−</button>
        <output id="pxZoom" aria-label="Zoom"></output>
        <button id="pxIn" type="button" aria-label="Zoom in">+</button>
        <label><input id="pxShowGrid" type="checkbox" checked> Pixel grid</label>
      </div>
      <div id="pxViewport">
        <div id="pxStage">
          <canvas id="pxCanvas" tabindex="0" aria-label="Sprite canvas" aria-describedby="pxKeys"></canvas>
          <div id="pxGrid" aria-hidden="true"></div>
          <div id="pxSelection" aria-hidden="true" hidden></div>
          <div id="pxCursor" aria-hidden="true"></div>
        </div>
      </div>
      <p id="pxKeys" class="muted">With the canvas focused, move with the arrow keys and apply the tool with Enter or Space.</p>
      <div class="row" role="group" aria-label="Rectangular selection">
        <span id="pxSelectionInfo" class="muted" role="status">No selection</span>
        <button id="pxClear" type="button" disabled>Erase selected pixels</button>
        <button id="pxDeselect" type="button" disabled>Deselect</button>
      </div>
      <div class="row">
        <button id="pxUndo" type="button">Undo edit</button>
        <button id="pxRedo" type="button">Redo edit</button>
        <span class="spacer"></span><button id="pxSave" class="primary" type="button">Save pixel edit</button>
      </div>
    </fieldset>`;
  const get = id => dialog.querySelector("#px" + id);
  const status = get("Status"), close = get("Close"), controls = get("Controls");
  const canvas = get("Canvas"), stage = get("Stage"), cursor = get("Cursor"), viewport = get("Viewport");
  const palette = get("Palette"), color = get("Color"), alpha = get("Alpha");
  const undo = get("Undo"), redo = get("Redo"), save = get("Save");
  const box = get("Selection"), info = get("SelectionInfo"), clear = get("Clear"), deselect = get("Deselect");
  const context = canvas.getContext("2d");
  const modified = new Set(), past = [], future = [];
  const tools = [...get("Tools").querySelectorAll("[data-tool]")];
  const maxZoom = 32;
  let width, height, fingerprint, original, image, pixels, fullFrame;
  let zoom = 1, tool = "pencil", point = [0, 0], gesture = null, pending = false;
  let selection = null, selecting = null;
  const offset = ([x, y]) => 4 * (y * width + x);
  const rgba = index => image.data.subarray(index, index + 4);
  const paintCanvas = () => context.putImageData(image, 0, 0);
  const message = (text, error = false) => {
    status.textContent = text;
    status.className = error ? "err" : "muted";
  };
  const sync = () => {
    const busy = !!(gesture || selecting);
    undo.disabled = !past.length || busy;
    redo.disabled = !future.length || busy;
    save.disabled = !modified.size || busy;
    clear.disabled = deselect.disabled = !selection || busy;
    if (modified.size || status.textContent.startsWith("Draft")) {
      message(modified.size ? `Draft · ${modified.size} changed ${modified.size === 1 ? "pixel" : "pixels"}` : "");
    }
  };

  function selectTool(next) {
    if (selecting) finishSelection(true);
    tool = next;
    tools.forEach(button => button.setAttribute("aria-pressed", String(button.dataset.tool === tool)));
    get("Keys").textContent = tool === "select"
      ? "Drag a rectangle, or press Enter to set a corner, move with the arrow keys, then press Enter again."
      : "With the canvas focused, move with the arrow keys and apply the tool with Enter or Space.";
  }

  function moveCursor(next, scroll = false) {
    point = next;
    cursor.style.left = point[0] * zoom + "px";
    cursor.style.top = point[1] * zoom + "px";
    if (scroll) cursor.scrollIntoView({block: "nearest", inline: "nearest"});
  }

  function setZoom(level) {
    zoom = level;
    canvas.style.width = width * zoom + "px";
    canvas.style.height = height * zoom + "px";
    stage.style.setProperty("--px-step", zoom + "px");
    get("Zoom").value = zoom + "×";
    get("Out").disabled = zoom === 1;
    get("In").disabled = zoom === maxZoom;
    get("Grid").hidden = !get("ShowGrid").checked || zoom < 4;
    moveCursor(point);
    renderSelection();
  }

  function setPixel(index, value) {
    pixels.setUint32(index, value);
    if (value === original.getUint32(index)) modified.delete(index);
    else modified.add(index);
  }

  function changePixel(changes, index, value) {
    const before = pixels.getUint32(index);
    if (before === value) return;
    if (!changes.has(index)) changes.set(index, before);
    setPixel(index, value);
  }

  function remember(changes, value) {
    if (!changes.size) return;
    past.push({changes, value});
    future.length = 0;
  }

  function editRegion(offsets, value) {
    const changes = new Map();
    for (const index of offsets) changePixel(changes, index, value);
    if (!changes.size) return;
    remember(changes, value);
    paintCanvas();
    sync();
  }

  function* selectedOffsets({left, top, right, bottom}) {
    for (let y = top; y <= bottom; y++) {
      for (let x = left; x <= right; x++) yield 4 * (y * width + x);
    }
  }

  function renderSelection() {
    box.hidden = !selection;
    if (!selection) { info.textContent = "No selection"; return; }
    const {left, top, right, bottom} = selection;
    const columns = right - left + 1, rows = bottom - top + 1;
    box.style.left = left * zoom + "px";
    box.style.top = top * zoom + "px";
    box.style.width = columns * zoom + "px";
    box.style.height = rows * zoom + "px";
    info.textContent = `Selected ${columns} × ${rows} px`;
  }

  function selectTo(at) {
    selection = pixelRectangle(selecting.anchor, at);
    renderSelection();
  }

  function finishSelection(cancel = false) {
    if (cancel) selection = selecting.previous;
    selecting = null;
    renderSelection();
    sync();
  }

  function brush() {
    if (tool === "eraser") return 0;
    if (!alpha.reportValidity()) return null;
    return Number.parseInt(color.value.slice(1), 16) * 256 + alpha.valueAsNumber;
  }

  function pick(index) {
    const [r, g, b, a] = rgba(index);
    color.value = "#" + [r, g, b].map(channel => channel.toString(16).padStart(2, "0")).join("");
    alpha.value = a;
    selectTool("pencil");
  }

  function draw(to) {
    moveCursor(to);
    const {changes, value, last} = gesture;
    let [x, y] = last || to;
    const [endX, endY] = to;
    const dx = Math.abs(endX - x), dy = -Math.abs(endY - y);
    const stepX = x < endX ? 1 : -1, stepY = y < endY ? 1 : -1;
    let error = dx + dy;
    // Bresenham connects pointer samples without gaps when the brush moves quickly.
    for (;;) {
      if (!selection || insidePixelRectangle(selection, x, y)) changePixel(changes, offset([x, y]), value);
      if (x === endX && y === endY) break;
      const twice = 2 * error;
      if (twice >= dy) { error += dy; x += stepX; }
      if (twice <= dx) { error += dx; y += stepY; }
    }
    gesture.last = to;
    paintCanvas();
  }

  function begin(at, pointerId) {
    moveCursor(at);
    if (tool === "picker") { pick(offset(at)); return; }
    if (tool === "select") {
      selecting = {anchor: at, pointerId, previous: selection};
      selectTo(at);
      sync();
      return;
    }
    const value = brush();
    if (value === null) return;
    if (tool === "fill") {
      editRegion(pixelFillOffsets(pixels, width, selection || fullFrame, at, value), value);
      return;
    }
    gesture = {changes: new Map(), value, last: null, pointerId};
    draw(at);
    sync();
  }

  function finish() {
    if (!gesture) return;
    remember(gesture.changes, gesture.value);
    gesture = null;
    sync();
  }

  function step(back) {
    const entry = (back ? past : future).pop();
    if (!entry) return;
    for (const [index, before] of entry.changes) setPixel(index, back ? before : entry.value);
    (back ? future : past).push(entry);
    paintCanvas();
    sync();
  }

  function locate(event) {
    const bounds = canvas.getBoundingClientRect();
    const x = Math.floor((event.clientX - bounds.left) * width / bounds.width);
    const y = Math.floor((event.clientY - bounds.top) * height / bounds.height);
    return [x, y];
  }

  function clampPoint([x, y]) {
    return [Math.max(0, Math.min(width - 1, x)), Math.max(0, Math.min(height - 1, y))];
  }

  canvas.onpointerdown = event => {
    const at = locate(event);
    if (pending || gesture || selecting || event.button !== 0 || !insidePixelRectangle(fullFrame, ...at)) return;
    canvas.focus({preventScroll: true});
    begin(at, event.pointerId);
    if (gesture || selecting) canvas.setPointerCapture(event.pointerId);
  };
  canvas.onpointermove = event => {
    if (selecting?.pointerId === event.pointerId) {
      const at = clampPoint(locate(event));
      moveCursor(at);
      selectTo(at);
      return;
    }
    if (gesture?.pointerId !== event.pointerId) return;
    const at = locate(event);
    if (insidePixelRectangle(fullFrame, ...at)) draw(at);
    else gesture.last = null;
  };
  canvas.onpointerup = event => {
    if (selecting?.pointerId === event.pointerId) {
      const at = clampPoint(locate(event));
      moveCursor(at);
      selectTo(at);
      finishSelection();
    }
    if (gesture?.pointerId === event.pointerId) finish();
  };
  canvas.onpointercancel = canvas.onlostpointercapture = event => {
    if (selecting?.pointerId === event.pointerId) finishSelection(true);
    if (gesture?.pointerId === event.pointerId) finish();
  };
  canvas.onkeydown = event => {
    if (pending || gesture || selecting?.pointerId !== undefined) return;
    const deltas = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]};
    const delta = deltas[event.key];
    if (delta) {
      event.preventDefault();
      moveCursor(clampPoint([point[0] + delta[0], point[1] + delta[1]]), true);
      if (selecting) selectTo(point);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (event.repeat) return;
      if (selecting) finishSelection();
      else { begin(point); finish(); }
    }
  };

  tools.forEach(button => { button.onclick = () => selectTool(button.dataset.tool); });
  get("Out").onclick = () => setZoom(Math.max(1, Math.floor(zoom / 2)));
  get("In").onclick = () => setZoom(Math.min(maxZoom, zoom * 2));
  get("ShowGrid").onchange = () => setZoom(zoom);
  clear.onclick = () => editRegion(selectedOffsets(selection), 0);
  deselect.onclick = () => { selection = null; renderSelection(); sync(); };
  undo.onclick = () => step(true);
  redo.onclick = () => step(false);
  const canClose = () => !pending && (!modified.size || window.confirm("Discard unsaved pixel edits?"));
  close.onclick = () => { if (canClose()) dialog.close(); };
  dialog.oncancel = event => {
    if (selecting) { finishSelection(true); event.preventDefault(); }
    else if (!canClose()) event.preventDefault();
  };

  save.onclick = async () => {
    const pixels = Array.from(modified, index => {
      const position = index / 4;
      return [position % width, Math.floor(position / width), ...rgba(index)];
    });
    pending = controls.disabled = close.disabled = true;
    message("Saving pixel edit…");
    try {
      const result = await api(saveUrl, {operation: "paint", frame, fingerprint, pixels});
      close.disabled = false;
      dialog.close();
      onSave(result);
    } catch (error) {
      message(error.message, true);
    } finally {
      pending = controls.disabled = close.disabled = false;
    }
  };

  dialog.showModal();
  // The title node belongs to this opening, even if a pending load is closed and reopened.
  const heading = get("Title");
  api(readUrl).then(data => {
    if (!dialog.open || !heading.isConnected) return;
    ({width, height, fingerprint} = data);
    const bytes = Uint8ClampedArray.from(atob(data.rgba), byte => byte.charCodeAt(0));
    original = new DataView(bytes.buffer);
    image = new ImageData(bytes.slice(), width, height);
    pixels = new DataView(image.data.buffer);
    fullFrame = pixelRectangle([0, 0], [width - 1, height - 1]);
    canvas.width = width;
    canvas.height = height;
    const colors = data.palette.filter(value => /^#[0-9a-f]{6}$/i.test(value));
    palette.replaceChildren(...colors.map(value => {
      const swatch = document.createElement("button");
      swatch.type = "button";
      swatch.style.backgroundColor = value;
      swatch.title = value;
      swatch.setAttribute("aria-label", `Use ${value}`);
      swatch.onclick = () => { color.value = value; if (tool !== "fill") selectTool("pencil"); };
      return swatch;
    }));
    palette.hidden = !colors.length;
    if (colors.length) color.value = colors[0];
    get("Frame").textContent = `${label} · ${width} × ${height} px`;
    controls.hidden = controls.disabled = false;
    const fit = Math.floor(Math.min((viewport.clientWidth - 20) / width, (window.innerHeight * .42 - 20) / height));
    setZoom(Math.max(1, Math.min(maxZoom, fit)));
    paintCanvas();
    message("");
    sync();
  }).catch(error => { if (dialog.open && heading.isConnected) message(error.message, true); });
}
