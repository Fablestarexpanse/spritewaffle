"use strict";

function showTimeline(action) {
  const dialog = document.querySelector("#timelineDialog");
  const endpoint = jobPath() + "/timeline";
  const runEndpoint = jobPath() + "/run";
  const sets = Object.entries(action.sets).filter(([, set]) => set.has_frames).map(([name]) => name);
  if (!sets.length || dialog.open) return;

  dialog.innerHTML = `
    <div class="row" style="margin:0">
      <h2 id="tlTitle" style="margin:0">${esc(action.facing)} · ${esc(action.action)} timeline</h2>
      <span class="spacer"></span><form method="dialog"><button>Close</button></form>
    </div>
    <div class="row">
      <label>Frame set <select id="tlSet">${sets.map(name => `<option>${esc(name)}</option>`).join("")}</select></label>
      <span class="muted" id="tlClipInfo"></span>
    </div>
    <p id="tlStatus" role="status" class="muted"></p>
    <fieldset id="timelineControls" disabled hidden>
      <div class="tl-workspace">
        <div class="tl-pane">
          <div class="tl-stage">
            <div id="tlPrevGhost" class="tl-ghost" aria-hidden="true" hidden></div>
            <div id="tlNextGhost" class="tl-ghost" aria-hidden="true" hidden></div>
            <img class="pix" id="tlPreview" alt="">
          </div>
          <div class="row">
            <button id="tlPlay" type="button">Play</button>
            <input id="tlRange" type="range" min="0" step="1" aria-label="Scrub frames">
            <span class="muted" id="tlPosition"></span>
          </div>
          <div class="row">
            <label><input id="tlOnion" type="checkbox"> Onion skin</label>
            <span id="tlOnionKey" class="muted" hidden><span>Previous frame</span><span>Next frame</span></span>
          </div>
          <div id="tlStrip" role="group" aria-label="Animation frames"></div>
          <div class="row" role="group" aria-label="Frame order">
            <button id="tlDuplicate" type="button">Duplicate</button>
            <button id="tlEarlier" type="button">Move earlier</button>
            <button id="tlLater" type="button">Move later</button>
            <button id="tlUndo" type="button">Undo order</button>
            <button id="tlRedo" type="button">Redo order</button>
          </div>
          <details id="tlPlayback">
            <summary>Playback settings <span id="tlWindow" class="muted"></span></summary>
            <form id="tlPlaybackForm">
              <div class="row">
                <label>Mode <select id="tlMode">
                  <option value="source">Use source</option>
                  <option value="loop">Loop</option>
                  <option value="once">Play once</option>
                </select></label>
                <label><input type="checkbox" id="tlLimit"> Limit playback range</label>
              </div>
              <div class="row">
                <label>First frame <select id="tlFirst"></select></label>
                <label>Last frame <select id="tlLast"></select></label>
              </div>
              <p id="tlPlaybackError" class="warn" role="status" hidden></p>
              <div class="row"><button type="submit">Save playback</button></div>
            </form>
          </details>
        </div>
        <div class="tl-pane" id="tlEditor">
          <h3 id="tlFrameLabel"></h3>
          <div class="row"><button id="tlPixels" type="button">Edit pixels</button></div>
          <form id="tlTiming">
            <label>Duration (ms) <input id="tlDuration" type="number" min="1" step="1" required></label>
            <div class="row">
              <button type="submit">Save duration</button>
              <button id="tlReset" type="button">Reset duration</button>
            </div>
          </form>
          <form id="tlReplacement">
            <div class="row"><label class="field">Replacement PNG <input id="tlFile" type="file" accept="image/png,.png" required></label></div>
            <div class="row">
              <button type="submit" id="tlReplace">Replace frame</button>
              <button id="tlRestore" type="button">Restore source</button>
            </div>
          </form>
          <p id="tlFrameNote" class="muted"></p>
          <p id="tlQaNote" class="warn" hidden>Run QA to review the edited timeline before character export.</p>
          <details id="tlHistory" hidden>
            <summary>Replacement history</summary>
            <div class="row"><label>Version <select id="tlVersion"></select></label></div>
            <div class="row">
              <img class="pix" id="tlHistoryPreview" alt="">
              <button id="tlUseVersion" type="button">Use version</button>
            </div>
          </details>
        </div>
      </div>
      <div class="row">
        <button id="tlQa" type="button">Run QA</button>
        <button id="tlExport" type="button">Re-export action</button>
      </div>
    </fieldset>`;
  const find = selector => dialog.querySelector(selector);
  const controls = find("#timelineControls"), set = find("#tlSet"), status = find("#tlStatus");
  const strip = find("#tlStrip"), preview = find("#tlPreview"), play = find("#tlPlay"), scrub = find("#tlRange");
  const duration = find("#tlDuration"), upload = find("#tlFile"), replace = find("#tlReplace");
  const onion = find("#tlOnion"), onionKey = find("#tlOnionKey");
  const previousGhost = find("#tlPrevGhost"), nextGhost = find("#tlNextGhost");
  const history = find("#tlHistory"), version = find("#tlVersion");
  const historyPreview = find("#tlHistoryPreview"), useVersion = find("#tlUseVersion");
  const mode = find("#tlMode"), limited = find("#tlLimit"), first = find("#tlFirst"), last = find("#tlLast");
  let clip, selected = 0, timer, playing = false;
  try { onion.checked = localStorage.getItem("sw.timeline.onion") === "true"; } catch {}

  const open = () => controls.isConnected && dialog.open;
  const query = () => "?" + new URLSearchParams({facing: action.facing, action: action.action, frame_set: set.value});
  const busy = value => { controls.disabled = value; set.disabled = value; };
  const message = (value, error = false) => {
    status.textContent = value;
    status.className = error ? "err" : "muted";
  };
  const stop = () => {
    clearTimeout(timer);
    playing = false;
    play.textContent = "Play";
    paintOnion();
  };
  dialog.addEventListener("close", stop, {once: true});

  function paintOnion() {
    const count = clip?.frames.length || 0;
    const playback = clip?.playback;
    const inside = playback && !playback.error && selected >= playback.start && selected <= playback.end;
    const start = inside ? playback.start : 0, end = inside ? playback.end : count - 1;
    const show = onion.checked && !playing && start < end;
    const wrap = inside && playback.loop;
    const previous = selected > start ? selected - 1 : wrap ? end : -1;
    const next = selected < end ? selected + 1 : wrap ? start : -1;
    for (const [layer, index] of [[previousGhost, previous], [nextGhost, next]]) {
      const url = show ? clip.frames[index]?.url : null;
      layer.hidden = !url;
      layer.style.maskImage = url ? `url(${JSON.stringify(url)})` : "none";
    }
    onionKey.hidden = previousGhost.hidden && nextGhost.hidden;
  }

  function showHistoryVersion() {
    const entry = clip.frames[selected].history.find(item => item.version === Number(version.value));
    historyPreview.hidden = !entry?.url;
    if (entry?.url) {
      historyPreview.src = entry.url;
      historyPreview.alt = `Replacement version ${entry.version}`;
    }
    useVersion.disabled = !entry?.available || entry.active;
    useVersion.textContent = entry && !entry.same_source ? "Apply to current source" : "Use version";
  }

  function showHistory(frame) {
    history.hidden = !frame.history.length;
    version.replaceChildren(...frame.history.map(item => {
      const suffix = item.active ? " · Current" : !item.available ? " · Missing PNG" :
        !item.same_source ? " · Earlier source" : "";
      return new Option(`Version ${item.version}${suffix}`, item.version);
    }));
    const preferred = frame.history.find(item => item.active) || frame.history.at(-1);
    if (preferred) version.value = preferred.version;
    showHistoryVersion();
  }

  function select(index) {
    selected = index;
    const frame = clip.frames[index];
    preview.src = frame.url;
    const label = frame.id === frame.name ? "Frame " + frame.name : "Copy of " + frame.name;
    preview.alt = label;
    scrub.value = index;
    find("#tlPosition").textContent = `${index + 1} / ${clip.frames.length}`;
    find("#tlFrameLabel").textContent = label;
    find("#tlEarlier").disabled = index === 0;
    find("#tlLater").disabled = index === clip.frames.length - 1;
    duration.value = frame.duration_ms;
    find("#tlReset").disabled = !frame.timing_edited;
    find("#tlRestore").disabled = !frame.replaced && !frame.conflict;
    find("#tlFrameNote").textContent = frame.conflict ? "The saved replacement is inactive. Its source or PNG changed." :
      frame.replaced ? "Using the saved replacement." : "";
    showHistory(frame);
    paintOnion();
    for (const button of strip.children) button.setAttribute("aria-pressed", String(Number(button.dataset.tlIndex) === index));
    const active = strip.children[index];
    const frameBox = active.getBoundingClientRect(), stripBox = strip.getBoundingClientRect();
    if (frameBox.right > stripBox.right) strip.scrollLeft += frameBox.right - stripBox.right;
    if (frameBox.left < stripBox.left) strip.scrollLeft -= stripBox.left - frameBox.left;
  }

  function displayPlayback(data) {
    const playback = data.playback;
    mode.value = playback.mode;
    limited.checked = !!playback.start_frame;
    for (const [input, current, fallback] of [[first, playback.start_frame, data.frames[0].id],
                                              [last, playback.end_frame, data.frames.at(-1).id]]) {
      input.replaceChildren(...data.frames.map((frame, i) => new Option(`${i + 1} · ${frame.id}`, frame.id)));
      if (current && !data.frames.some(frame => frame.id === current)) {
        input.add(new Option(`Missing · ${current}`, current));
      }
      input.value = current || fallback;
      input.disabled = !limited.checked;
    }
    find("#tlWindow").textContent = playback.error ? "· Range needs repair" : limited.checked
      ? `· Frames ${playback.start + 1}–${playback.end + 1}` : "· Full clip";
    const error = find("#tlPlaybackError");
    error.textContent = playback.error || "";
    error.hidden = !playback.error;
    if (playback.error) find("#tlPlayback").open = true;
    play.disabled = find("#tlQa").disabled = find("#tlExport").disabled = !!playback.error;
  }

  function display(data, index = 0) {
    clip = data;
    controls.hidden = false;
    scrub.max = data.frames.length - 1;
    duration.max = data.max_duration_ms;
    upload.value = "";
    replace.disabled = true;
    find("#tlClipInfo").textContent = `${data.cell.join(" × ")} px · ${data.loop ? "Loop" : "One shot"} · Default ${data.default_ms} ms`;
    find("#tlQaNote").hidden = !data.qa_needs_review;
    find("#tlUndo").disabled = !data.can_undo;
    find("#tlRedo").disabled = !data.can_redo;
    displayPlayback(data);
    const {start, end, start_frame, error} = data.playback;
    strip.innerHTML = data.frames.map((frame, i) => {
      const inPlayback = start_frame && !error && start <= i && i <= end;
      return `
      <button type="button" data-tl-index="${i}" data-frame-id="${esc(frame.id)}"
        ${inPlayback ? 'data-in-playback="true"' : ""}
        aria-label="${i + 1}, ${frame.id === frame.name ? "frame" : "copy of"} ${esc(frame.name)}, ${frame.duration_ms} ms${inPlayback ? ", in playback range" : ""}">
        <img class="pix" src="${esc(frame.url)}" alt="">
        ${frame.id === frame.name ? "" : "Copy "}${esc(frame.name.replace(/\.png$/, ""))} · ${frame.duration_ms} ms
      </button>`;
    }).join("");
    select(Math.min(index, data.frames.length - 1));
  }

  async function load() {
    stop();
    busy(true);
    controls.hidden = true;
    message("Loading frames…");
    try {
      const data = await api(endpoint + query());
      if (!open()) return;
      display(data);
      message("");
    } catch (error) {
      if (open()) message(error.message, true);
    } finally {
      if (open()) busy(false);
    }
  }

  async function save(operation, value) {
    stop();
    busy(true);
    message(operation === "playback" ? "Saving playback…" : "Saving frame…");
    try {
      const body = {operation, frame: clip.frames[selected].id};
      if (operation === "duration") body.duration_ms = value;
      if (operation === "activate") body.version = value;
      if (operation === "move") body.position = value;
      if (operation === "playback") body.playback = value;
      if (operation === "replace") body.png = await new Promise((resolve, reject) => {
        if (value.size > clip.max_image_bytes) return reject(new Error("Choose a PNG no larger than 32 MiB."));
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(",")[1]);
        reader.onerror = () => reject(new Error("The PNG could not be read."));
        reader.readAsDataURL(value);
      });
      const data = await api(endpoint + query(), body);
      if (!open()) return;
      const next = data.frames.findIndex(frame => frame.id === (data.selected_frame || body.frame));
      display(data, next >= 0 ? next : selected);
      const labels = {activate: `Version ${value} applied.`, duplicate: "Frame duplicated.", move: "Frame moved.",
                      undo: "Frame order change undone.", redo: "Frame order change redone.", playback: "Playback saved."};
      message(labels[operation] || "Saved.");
    } catch (error) {
      if (open()) message(error.message, true);
    } finally {
      if (open()) busy(false);
    }
  }

  function advance() {
    timer = setTimeout(() => {
      if (!open() || !playing) return stop();
      const {start, end, loop} = clip.playback;
      if (selected === end && !loop) return stop();
      select(selected === end ? start : selected + 1);
      advance();
    }, clip.frames[selected].duration_ms);
  }
  play.onclick = () => {
    if (playing) return stop();
    const {start, end, loop} = clip.playback;
    if (selected < start || selected > end || (!loop && selected === end)) select(start);
    playing = true;
    play.textContent = "Pause";
    paintOnion();
    advance();
  };
  set.onchange = load;
  limited.onchange = () => { first.disabled = last.disabled = !limited.checked; };
  find("#tlPlaybackForm").onsubmit = event => {
    event.preventDefault();
    save("playback", {mode: mode.value, start_frame: limited.checked ? first.value : null,
                      end_frame: limited.checked ? last.value : null});
  };
  onion.onchange = () => {
    try { localStorage.setItem("sw.timeline.onion", String(onion.checked)); } catch {}
    paintOnion();
  };
  scrub.oninput = () => { stop(); select(Number(scrub.value)); };
  strip.onclick = event => {
    const button = event.target.closest("[data-tl-index]");
    if (button) { stop(); select(Number(button.dataset.tlIndex)); }
  };
  find("#tlTiming").onsubmit = event => { event.preventDefault(); save("duration", duration.valueAsNumber); };
  find("#tlReset").onclick = () => save("duration", null);
  find("#tlPixels").onclick = () => {
    stop();
    const frame = clip.frames[selected];
    const label = find("#tlFrameLabel").textContent;
    const saveUrl = endpoint + query();
    const readUrl = endpoint + "/pixels" + query() + "&frame=" + encodeURIComponent(frame.id);
    showPixelEditor(readUrl, saveUrl, frame.id, label, data => {
      if (!open()) return;
      const index = data.frames.findIndex(item => item.id === frame.id);
      display(data, index >= 0 ? index : selected);
      message("Pixel edit saved to replacement history.");
    });
  };
  upload.onchange = () => { replace.disabled = !upload.files.length; };
  find("#tlReplacement").onsubmit = event => { event.preventDefault(); save("replace", upload.files[0]); };
  find("#tlRestore").onclick = () => save("restore");
  find("#tlDuplicate").onclick = () => save("duplicate");
  find("#tlEarlier").onclick = () => save("move", selected - 1);
  find("#tlLater").onclick = () => save("move", selected + 1);
  find("#tlUndo").onclick = () => save("undo");
  find("#tlRedo").onclick = () => save("redo");
  find("#tlEditor").onfocusin = stop;
  version.onchange = showHistoryVersion;
  useVersion.onclick = () => save("activate", Number(version.value));
  const queue = async (stage, label) => {
    stop();
    busy(true);
    try {
      await api(runEndpoint, {stage, args: {facing: action.facing, action: action.action}});
      if (open()) message(label);
    } catch (error) {
      if (open()) message(error.message, true);
    } finally {
      if (open()) busy(false);
    }
  };
  find("#tlQa").onclick = () => queue("qa", "QA queued.");
  find("#tlExport").onclick = () => queue("export", "Action export queued.");
  dialog.showModal();
  load();
}
