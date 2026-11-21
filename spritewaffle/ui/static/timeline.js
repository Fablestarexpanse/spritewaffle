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
          <img class="pix" id="tlPreview" alt="">
          <div class="row">
            <button id="tlPlay" type="button">Play</button>
            <input id="tlRange" type="range" min="0" step="1" aria-label="Scrub frames">
            <span class="muted" id="tlPosition"></span>
          </div>
          <div id="tlStrip" role="group" aria-label="Animation frames"></div>
        </div>
        <div class="tl-pane">
          <h3 id="tlFrameLabel"></h3>
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
          <p id="tlQaNote" class="warn" hidden>Run QA to review the changed artwork before character export.</p>
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
  let clip, selected = 0, timer, playing = false;

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
  };
  dialog.addEventListener("close", stop, {once: true});

  function select(index) {
    selected = index;
    const frame = clip.frames[index];
    preview.src = frame.url;
    preview.alt = "Frame " + frame.name;
    scrub.value = index;
    find("#tlPosition").textContent = `${index + 1} / ${clip.frames.length}`;
    find("#tlFrameLabel").textContent = "Frame " + frame.name;
    duration.value = frame.duration_ms;
    find("#tlReset").disabled = !frame.timing_edited;
    find("#tlRestore").disabled = !frame.replaced && !frame.conflict;
    find("#tlFrameNote").textContent = frame.conflict ? "Source changed. The saved replacement is inactive." :
      frame.replaced ? "Using the saved replacement." : "";
    for (const button of strip.children) button.setAttribute("aria-pressed", String(Number(button.dataset.tlIndex) === index));
    const active = strip.children[index];
    const frameBox = active.getBoundingClientRect(), stripBox = strip.getBoundingClientRect();
    if (frameBox.right > stripBox.right) strip.scrollLeft += frameBox.right - stripBox.right;
    if (frameBox.left < stripBox.left) strip.scrollLeft -= stripBox.left - frameBox.left;
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
    strip.innerHTML = data.frames.map((frame, i) => `
      <button type="button" data-tl-index="${i}" aria-label="Frame ${esc(frame.name)}, ${frame.duration_ms} ms">
        <img class="pix" src="${esc(frame.url)}" alt="">
        ${esc(frame.name.replace(/\.png$/, ""))} · ${frame.duration_ms} ms
      </button>`).join("");
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
    message("Saving frame…");
    try {
      const body = {operation, frame: clip.frames[selected].name};
      if (operation === "duration") body.duration_ms = value;
      if (operation === "replace") body.png = await new Promise((resolve, reject) => {
        if (value.size > clip.max_image_bytes) return reject(new Error("Choose a PNG no larger than 32 MiB."));
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(",")[1]);
        reader.onerror = () => reject(new Error("The PNG could not be read."));
        reader.readAsDataURL(value);
      });
      const data = await api(endpoint + query(), body);
      if (!open()) return;
      display(data, selected);
      message("Saved.");
    } catch (error) {
      if (open()) message(error.message, true);
    } finally {
      if (open()) busy(false);
    }
  }

  function advance() {
    timer = setTimeout(() => {
      if (!open() || !playing) return stop();
      if (selected === clip.frames.length - 1 && !clip.loop) return stop();
      select((selected + 1) % clip.frames.length);
      advance();
    }, clip.frames[selected].duration_ms);
  }
  play.onclick = () => {
    if (playing) return stop();
    if (!clip.loop && selected === clip.frames.length - 1) select(0);
    playing = true;
    play.textContent = "Pause";
    advance();
  };
  set.onchange = load;
  scrub.oninput = () => { stop(); select(Number(scrub.value)); };
  strip.onclick = event => {
    const button = event.target.closest("[data-tl-index]");
    if (button) { stop(); select(Number(button.dataset.tlIndex)); }
  };
  find("#tlTiming").onsubmit = event => { event.preventDefault(); save("duration", duration.valueAsNumber); };
  find("#tlReset").onclick = () => save("duration", null);
  upload.onchange = () => { replace.disabled = !upload.files.length; };
  find("#tlReplacement").onsubmit = event => { event.preventDefault(); save("replace", upload.files[0]); };
  find("#tlRestore").onclick = () => save("restore");
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
