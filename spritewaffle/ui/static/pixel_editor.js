"use strict";

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
        <button type="button" data-tool="picker" aria-pressed="false">Pick color</button>
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
          <div id="pxCursor" aria-hidden="true"></div>
        </div>
      </div>
      <p id="pxKeys" class="muted">With the canvas focused, move with the arrow keys and apply the tool with Enter or Space.</p>
      <div class="row">
        <button id="pxUndo" type="button">Undo stroke</button>
        <button id="pxRedo" type="button">Redo stroke</button>
        <span class="spacer"></span><button id="pxSave" class="primary" type="button">Save pixel edit</button>
      </div>
    </fieldset>`;
  const get = id => dialog.querySelector("#px" + id);
  const status = get("Status"), close = get("Close"), controls = get("Controls");
  const canvas = get("Canvas"), stage = get("Stage"), cursor = get("Cursor"), viewport = get("Viewport");
  const palette = get("Palette"), color = get("Color"), alpha = get("Alpha");
  const undo = get("Undo"), redo = get("Redo"), save = get("Save");
  const context = canvas.getContext("2d");
  const modified = new Set(), past = [], future = [];
  const tools = [...get("Tools").querySelectorAll("[data-tool]")];
  const maxZoom = 32;
  let width, height, fingerprint, original, image;
  let zoom = 1, tool = "pencil", point = [0, 0], gesture = null, pending = false;
  const equal = (a, b) => a.every((channel, i) => channel === b[i]);
  const offset = ([x, y]) => 4 * (y * width + x);
  const rgba = index => image.data.subarray(index, index + 4);
  const paintCanvas = () => context.putImageData(image, 0, 0);
  const message = (text, error = false) => {
    status.textContent = text;
    status.className = error ? "err" : "muted";
  };
  const sync = () => {
    undo.disabled = !past.length || !!gesture;
    redo.disabled = !future.length || !!gesture;
    save.disabled = !modified.size || !!gesture;
    if (modified.size || status.textContent.startsWith("Draft")) {
      message(modified.size ? `Draft · ${modified.size} changed ${modified.size === 1 ? "pixel" : "pixels"}` : "");
    }
  };

  function selectTool(next) {
    tool = next;
    tools.forEach(button => button.setAttribute("aria-pressed", String(button.dataset.tool === tool)));
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
  }

  function setPixel(index, value) {
    image.data.set(value, index);
    if (equal(value, original.subarray(index, index + 4))) modified.delete(index);
    else modified.add(index);
  }

  function brush() {
    if (tool === "eraser") return [0, 0, 0, 0];
    if (!alpha.reportValidity()) return null;
    const hex = Number.parseInt(color.value.slice(1), 16);
    return [(hex >> 16) & 255, (hex >> 8) & 255, hex & 255, alpha.valueAsNumber];
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
      const index = offset([x, y]);
      if (!equal(rgba(index), value)) {
        if (!changes.has(index)) changes.set(index, rgba(index).slice());
        setPixel(index, value);
      }
      if (x === endX && y === endY) break;
      const twice = 2 * error;
      if (twice >= dy) { error += dy; x += stepX; }
      if (twice <= dx) { error += dx; y += stepY; }
    }
    gesture.last = to;
    paintCanvas();
  }

  function begin(at, pointerId) {
    if (tool === "picker") { moveCursor(at); pick(offset(at)); return; }
    const value = brush();
    if (!value) return;
    gesture = {changes: new Map(), value, last: null, pointerId};
    draw(at);
    sync();
  }

  function finish() {
    if (!gesture) return;
    if (gesture.changes.size) {
      past.push(gesture);
      future.length = 0;
    }
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
    return x >= 0 && x < width && y >= 0 && y < height ? [x, y] : null;
  }

  canvas.onpointerdown = event => {
    const at = locate(event);
    if (!at || pending || gesture || event.button !== 0) return;
    canvas.focus({preventScroll: true});
    begin(at, event.pointerId);
    if (gesture) canvas.setPointerCapture(event.pointerId);
  };
  canvas.onpointermove = event => {
    if (gesture?.pointerId !== event.pointerId) return;
    const at = locate(event);
    if (at) draw(at);
    else gesture.last = null;
  };
  canvas.onpointerup = canvas.onpointercancel = canvas.onlostpointercapture = event => {
    if (gesture?.pointerId === event.pointerId) finish();
  };
  canvas.onkeydown = event => {
    if (pending || gesture) return;
    const deltas = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]};
    const delta = deltas[event.key];
    if (delta) {
      event.preventDefault();
      moveCursor([Math.max(0, Math.min(width - 1, point[0] + delta[0])),
                  Math.max(0, Math.min(height - 1, point[1] + delta[1]))], true);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      begin(point);
      finish();
    }
  };

  tools.forEach(button => { button.onclick = () => selectTool(button.dataset.tool); });
  get("Out").onclick = () => setZoom(Math.max(1, Math.floor(zoom / 2)));
  get("In").onclick = () => setZoom(Math.min(maxZoom, zoom * 2));
  get("ShowGrid").onchange = () => setZoom(zoom);
  undo.onclick = () => step(true);
  redo.onclick = () => step(false);
  const canClose = () => !pending && (!modified.size || window.confirm("Discard unsaved pixel edits?"));
  close.onclick = () => { if (canClose()) dialog.close(); };
  dialog.oncancel = event => { if (!canClose()) event.preventDefault(); };

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
    original = Uint8ClampedArray.from(atob(data.rgba), byte => byte.charCodeAt(0));
    image = new ImageData(original.slice(), width, height);
    canvas.width = width;
    canvas.height = height;
    const colors = data.palette.filter(value => /^#[0-9a-f]{6}$/i.test(value));
    palette.replaceChildren(...colors.map(value => {
      const swatch = document.createElement("button");
      swatch.type = "button";
      swatch.style.backgroundColor = value;
      swatch.title = value;
      swatch.setAttribute("aria-label", `Use ${value}`);
      swatch.onclick = () => { color.value = value; selectTool("pencil"); };
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
