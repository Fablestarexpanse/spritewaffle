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
      <section id="tlUnavailable" hidden>
        <p class="warn" role="status">Restore or remove unavailable inserted frames before playback, QA, or export.</p>
        <ul id="tlUnavailableList"></ul>
      </section>
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
            <button id="tlBlank" type="button">Insert blank after</button>
            <button id="tlRemove" type="button">Remove frame</button>
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
          <details id="tlTags">
            <summary>Animation tags <span id="tlTagCount" class="muted"></span></summary>
            <div class="row"><label class="field">Tag <select id="tlTagPick"></select></label></div>
            <form id="tlTagForm">
              <div class="row">
                <label class="field">Name <input id="tlTagName" type="text" required></label>
                <label><input type="checkbox" id="tlTagLoop"> Loop tag</label>
              </div>
              <div class="row">
                <label>First frame <select id="tlTagFirst"></select></label>
                <label>Last frame <select id="tlTagLast"></select></label>
              </div>
              <p id="tlTagError" class="warn" role="status" hidden></p>
              <div class="row">
                <button id="tlTagSave" type="submit">Save tag</button>
                <button id="tlTagPreview" type="button">Preview tag</button>
                <button id="tlTagRemove" type="button">Remove tag</button>
              </div>
            </form>
          </details>
        </div>
        <div class="tl-pane" id="tlEditor">
          <h3 id="tlFrameLabel"></h3>
          <div class="row">
            <button id="tlPixels" type="button">Edit pixels</button>
            <button id="tlReposition" type="button">Reposition frame</button>
            <button id="tlReprocess" type="button">Reprocess frame</button>
          </div>
          <form id="tlTiming">
            <label>Duration (ms) <input id="tlDuration" type="number" min="1" step="1" required></label>
            <div class="row">
              <button type="submit">Save duration</button>
              <button id="tlReset" type="button">Reset duration</button>
            </div>
          </form>
          <details id="tlPoses">
            <summary>Pose markers <span id="tlPoseSummary" class="muted"></span></summary>
            <form id="tlPoseForm">
              <div id="tlPoseChecks" role="group" aria-label="Pose marker types"></div>
              <div class="row">
                <button id="tlPoseSave" type="submit">Save markers</button>
                <button id="tlPosePrev" type="button" aria-label="Previous marked frame">Previous marker</button>
                <button id="tlPoseNext" type="button" aria-label="Next marked frame">Next marker</button>
              </div>
            </form>
          </details>
          <form id="tlReplacement">
            <div class="row"><label class="field">Same-size PNG <input id="tlFile" type="file" accept="image/png,.png" required></label></div>
            <div class="row">
              <button type="submit" id="tlReplace">Replace frame</button>
              <button type="button" id="tlInsert">Insert PNG after</button>
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
  const insert = find("#tlInsert"), remove = find("#tlRemove");
  const onion = find("#tlOnion"), onionKey = find("#tlOnionKey");
  const previousGhost = find("#tlPrevGhost"), nextGhost = find("#tlNextGhost");
  const history = find("#tlHistory"), version = find("#tlVersion");
  const historyPreview = find("#tlHistoryPreview"), useVersion = find("#tlUseVersion");
  const mode = find("#tlMode"), limited = find("#tlLimit"), first = find("#tlFirst"), last = find("#tlLast");
  const tagPick = find("#tlTagPick"), tagName = find("#tlTagName"), tagLoop = find("#tlTagLoop");
  const tagFirst = find("#tlTagFirst"), tagLast = find("#tlTagLast"), tagPreview = find("#tlTagPreview");
  const poseChecks = find("#tlPoseChecks"), poseSave = find("#tlPoseSave");
  const posePrev = find("#tlPosePrev"), poseNext = find("#tlPoseNext");
  let clip, selected = 0, timer, playing = false, playingTag = null;
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
    playingTag = null;
    play.textContent = "Play";
    tagPreview.textContent = "Preview tag";
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

  function poseLabels(frame) {
    return frame.pose_markers.map(marker => clip.pose_marker_types[marker]).join(", ");
  }

  function showPoses(frame) {
    const labels = poseLabels(frame);
    find("#tlPoseSummary").textContent = labels ? `· ${labels}` : "";
    for (const input of poseChecks.querySelectorAll("input")) input.checked = frame.pose_markers.includes(input.value);
    poseSave.disabled = true;
    posePrev.disabled = poseNext.disabled = !clip.frames.some(item => item.id !== frame.id && item.pose_markers.length);
  }

  function checkedPoses() {
    return [...poseChecks.querySelectorAll("input:checked")].map(input => input.value);
  }

  function jumpToPose(direction) {
    const count = clip.frames.length;
    for (let step = 1; step < count; step++) {
      const index = (selected + direction * step + count) % count;
      if (clip.frames[index].pose_markers.length) {
        stop();
        select(index);
        return;
      }
    }
  }

  function select(index) {
    selected = index;
    const frame = clip.frames[index];
    preview.src = frame.url;
    const label = frame.id !== frame.name ? "Copy of " + frame.name :
      frame.inserted ? "Inserted " + frame.id : "Frame " + frame.name;
    preview.alt = label;
    scrub.value = index;
    find("#tlPosition").textContent = `${index + 1} / ${clip.frames.length}`;
    find("#tlFrameLabel").textContent = label;
    find("#tlReprocess").disabled = frame.inserted;
    find("#tlReprocess").title = frame.inserted ? "An inserted frame has no retained animation master." : "";
    find("#tlEarlier").disabled = index === 0;
    find("#tlLater").disabled = index === clip.frames.length - 1;
    duration.value = frame.duration_ms;
    find("#tlReset").disabled = !frame.timing_edited;
    find("#tlRestore").disabled = !frame.replaced && !frame.conflict;
    find("#tlFrameNote").textContent = frame.conflict ? "The saved replacement is inactive. Its source or PNG changed." :
      frame.replaced ? "Using the saved replacement." : "";
    showPoses(frame);
    showHistory(frame);
    paintOnion();
    for (const button of strip.children) button.setAttribute("aria-pressed", String(Number(button.dataset.tlIndex) === index));
    const active = strip.children[index];
    const frameBox = active.getBoundingClientRect(), stripBox = strip.getBoundingClientRect();
    if (frameBox.right > stripBox.right) strip.scrollLeft += frameBox.right - stripBox.right;
    if (frameBox.left < stripBox.left) strip.scrollLeft -= stripBox.left - frameBox.left;
  }

  function frameOptions(input, current, fallback) {
    input.replaceChildren(...clip.frames.map((frame, i) => new Option(`${i + 1} · ${frame.id}`, frame.id)));
    if (current && !clip.frames.some(frame => frame.id === current)) {
      input.add(new Option(`Missing · ${current}`, current));
    }
    input.value = current || fallback || "";
  }

  function displayPlayback(data) {
    const playback = data.playback;
    mode.value = playback.mode;
    limited.checked = !!playback.start_frame;
    for (const [input, current, fallback] of [[first, playback.start_frame, data.frames[0]?.id],
                                              [last, playback.end_frame, data.frames.at(-1)?.id]]) {
      frameOptions(input, current, fallback);
      input.disabled = !limited.checked;
    }
    find("#tlWindow").textContent = playback.error ? "· Range needs repair" : limited.checked
      ? `· Frames ${playback.start + 1}–${playback.end + 1}` : "· Full clip";
    const error = find("#tlPlaybackError");
    error.textContent = playback.error || "";
    error.hidden = !playback.error;
    if (playback.error) find("#tlPlayback").open = true;
    const blocked = !data.frames.length || !!playback.error || Object.keys(data.unavailable).length > 0;
    play.disabled = blocked;
    find("#tlQa").disabled = find("#tlExport").disabled = blocked || data.tags.some(tag => tag.error);
  }

  function showTagForm() {
    const tag = clip.tags.find(item => item.id === tagPick.value);
    const {start, end, loop} = clip.playback;
    tagName.value = tag?.name || "";
    tagLoop.checked = tag?.loop ?? loop;
    frameOptions(tagFirst, tag?.start_frame, clip.frames[start]?.id);
    frameOptions(tagLast, tag?.end_frame, clip.frames[end]?.id);
    const empty = !clip.frames.length;
    tagName.disabled = tagLoop.disabled = tagFirst.disabled = tagLast.disabled = find("#tlTagSave").disabled = empty;
    tagPreview.disabled = !tag || !!tag.error || Object.keys(clip.unavailable).length > 0;
    find("#tlTagRemove").disabled = !tag;
    const error = find("#tlTagError");
    error.textContent = tag?.error || "";
    error.hidden = !tag?.error;
  }

  function displayTags(selectedTag) {
    const issue = clip.tags.find(tag => tag.error);
    const count = clip.tags.length;
    find("#tlTagCount").textContent = issue ? "· Needs repair" : count ? `· ${count}` : "";
    tagPick.replaceChildren(new Option("New tag", ""), ...clip.tags.map(tag =>
      new Option(tag.error ? `Needs repair · ${tag.name}` : tag.name, tag.id)));
    tagPick.value = selectedTag ?? issue?.id ?? "";
    if (tagPick.selectedIndex < 0) tagPick.value = issue?.id || "";
    if (issue) find("#tlTags").open = true;
    showTagForm();
  }

  function displayUnavailable(data) {
    const entries = Object.entries(data.unavailable);
    find("#tlUnavailable").hidden = !entries.length;
    find("#tlUnavailableList").replaceChildren(...entries.map(([id, issue]) => {
      const item = document.createElement("li"), button = document.createElement("button");
      button.type = "button";
      button.textContent = `Remove ${id}`;
      button.onclick = () => save("remove", null, id);
      item.append(`${id} · ${issue} `, button);
      return item;
    }));
  }

  function display(data, index = 0, selectedTag = tagPick.value || null) {
    clip = data;
    controls.hidden = false;
    const noFrames = !data.frames.length;
    scrub.max = Math.max(0, data.frames.length - 1);
    scrub.disabled = preview.hidden = find("#tlEditor").hidden = find("#tlPlayback").hidden = noFrames;
    find("#tlDuplicate").disabled = find("#tlBlank").disabled = noFrames;
    remove.disabled = data.frames.length < 2;
    duration.max = data.max_duration_ms;
    upload.value = "";
    replace.disabled = insert.disabled = true;
    find("#tlClipInfo").textContent = noFrames ? "No available frames" :
      `${data.cell.join(" × ")} px · ${data.loop ? "Loop" : "One shot"} · Default ${data.default_ms} ms`;
    find("#tlQaNote").hidden = !data.qa_needs_review;
    find("#tlUndo").disabled = !data.can_undo;
    find("#tlRedo").disabled = !data.can_redo;
    displayUnavailable(data);
    displayPlayback(data);
    displayTags(selectedTag);
    poseChecks.innerHTML = Object.entries(data.pose_marker_types).map(([marker, label]) =>
      `<label><input type="checkbox" value="${esc(marker)}"> ${esc(label)}</label>`).join("");
    const {start, end, start_frame, error} = data.playback;
    strip.innerHTML = data.frames.map((frame, i) => {
      const inPlayback = start_frame && !error && start <= i && i <= end;
      const kind = frame.id !== frame.name ? "copy of" : frame.inserted ? "inserted" : "frame";
      const caption = frame.id !== frame.name ? "Copy " : frame.inserted ? "New " : "";
      const poses = poseLabels(frame);
      return `
      <button type="button" data-tl-index="${i}" data-frame-id="${esc(frame.id)}"
        ${inPlayback ? 'data-in-playback="true"' : ""}
        ${poses ? `data-marked title="${esc(poses)}"` : ""}
        aria-label="${i + 1}, ${kind} ${esc(frame.name)}, ${frame.duration_ms} ms${inPlayback ? ", in playback range" : ""}${poses ? `, ${esc(poses)}` : ""}">
        <img class="pix" src="${esc(frame.url)}" alt="">
        ${caption}${esc(frame.name.replace(/\.png$/, "").replace(/^insert-/, ""))} · ${frame.duration_ms} ms
      </button>`;
    }).join("");
    if (noFrames) {
      selected = 0;
      find("#tlEarlier").disabled = find("#tlLater").disabled = true;
      find("#tlPosition").textContent = "";
      paintOnion();
    } else {
      select(Math.min(index, data.frames.length - 1));
    }
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

  async function save(operation, value, target = clip.frames[selected]?.id) {
    stop();
    busy(true);
    const tagOperation = operation === "save_tag" || operation === "remove_tag";
    message(tagOperation ? "Saving tags…" : operation === "playback" ? "Saving playback…" : "Saving frame…");
    try {
      const body = {operation, frame: target};
      if (operation === "duration") body.duration_ms = value;
      if (operation === "pose") body.pose_markers = value;
      if (operation === "activate") body.version = value;
      if (operation === "move") body.position = value;
      if (operation === "playback") body.playback = value;
      if (tagOperation) {
        body.tag_id = tagPick.value || null;
        if (operation === "save_tag") body.tag = value;
      }
      if (operation === "replace" || operation === "insert") body.png = await new Promise((resolve, reject) => {
        if (value.size > clip.max_image_bytes) return reject(new Error("Choose a PNG no larger than 32 MiB."));
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(",")[1]);
        reader.onerror = () => reject(new Error("The PNG could not be read."));
        reader.readAsDataURL(value);
      });
      const data = await api(endpoint + query(), body);
      if (!open()) return;
      const next = data.frames.findIndex(frame => frame.id === (data.selected_frame || body.frame));
      display(data, next >= 0 ? next : selected, tagOperation ? data.selected_tag || "" : tagPick.value || null);
      const labels = {activate: `Version ${value} applied.`, duplicate: "Frame duplicated.", move: "Frame moved.",
                      insert: "PNG frame inserted.", insert_blank: "Blank frame inserted.", remove: "Frame removed from the sequence.",
                      undo: "Frame order change undone.", redo: "Frame order change redone.", playback: "Playback saved.",
                      save_tag: "Tag saved.", remove_tag: "Tag removed.", pose: value?.length ? "Pose markers saved." : "Pose markers cleared."};
      message(labels[operation] || "Saved.");
    } catch (error) {
      if (open()) message(error.message, true);
    } finally {
      if (open()) busy(false);
    }
  }

  function advance(bounds) {
    const {start, end, loop} = bounds;
    timer = setTimeout(() => {
      if (!open() || !playing) return stop();
      if (selected === end && !loop) return stop();
      select(selected === end ? start : selected + 1);
      advance(bounds);
    }, clip.frames[selected].duration_ms);
  }
  function startPlayback(bounds, tagId = null) {
    stop();
    const {start, end, loop} = bounds;
    if (tagId || selected < start || selected > end || (!loop && selected === end)) select(start);
    playing = true;
    playingTag = tagId;
    play.textContent = "Pause";
    if (tagId) tagPreview.textContent = "Pause tag";
    paintOnion();
    advance(bounds);
  }
  play.onclick = () => playing ? stop() : startPlayback(clip.playback);
  set.onchange = load;
  tagPick.onchange = () => { if (playingTag) stop(); showTagForm(); };
  find("#tlTagForm").onsubmit = event => {
    event.preventDefault();
    save("save_tag", {name: tagName.value, start_frame: tagFirst.value, end_frame: tagLast.value, loop: tagLoop.checked});
  };
  find("#tlTagRemove").onclick = () => save("remove_tag");
  tagPreview.onclick = () => {
    const tag = clip.tags.find(item => item.id === tagPick.value);
    if (tag && !tag.error) {
      if (playingTag === tag.id) stop();
      else startPlayback(tag, tag.id);
    }
  };
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
  find("#tlPoseForm").onsubmit = event => { event.preventDefault(); save("pose", checkedPoses()); };
  poseChecks.onchange = () => {
    poseSave.disabled = checkedPoses().join(",") === clip.frames[selected].pose_markers.join(",");
  };
  posePrev.onclick = () => jumpToPose(-1);
  poseNext.onclick = () => jumpToPose(1);
  function savedArtwork(data, id, label) {
    if (!open()) return;
    const index = data.frames.findIndex(item => item.id === id);
    display(data, index >= 0 ? index : selected);
    message(label);
  }
  find("#tlPixels").onclick = () => {
    stop();
    const frame = clip.frames[selected];
    const label = find("#tlFrameLabel").textContent;
    const saveUrl = endpoint + query();
    const readUrl = endpoint + "/pixels" + query() + "&frame=" + encodeURIComponent(frame.id);
    showPixelEditor(readUrl, saveUrl, frame.id, label, data => savedArtwork(data, frame.id, "Pixel edit saved to replacement history."));
  };
  find("#tlReprocess").onclick = () => {
    stop();
    const frame = clip.frames[selected];
    const label = find("#tlFrameLabel").textContent;
    const saveUrl = endpoint + query();
    const readUrl = endpoint + "/reprocess" + query() + "&frame=" + encodeURIComponent(frame.id);
    showFrameRepair(readUrl, saveUrl, frame.id, label, data => savedArtwork(data, frame.id, "Reprocessed frame saved to replacement history."));
  };
  find("#tlReposition").onclick = () => {
    stop();
    const frame = clip.frames[selected];
    const label = find("#tlFrameLabel").textContent;
    const saveUrl = endpoint + query();
    const readUrl = endpoint + "/reposition" + query() + "&frame=" + encodeURIComponent(frame.id);
    const references = clip.frames.map((item, i) => ({id: item.id, label: `${i + 1} · ${item.id}`})).filter(item => item.id !== frame.id);
    showFrameRepair(readUrl, saveUrl, frame.id, label,
                    data => savedArtwork(data, frame.id, "Repositioned frame saved to replacement history."), references);
  };
  upload.onchange = () => { replace.disabled = insert.disabled = !upload.files.length; };
  find("#tlReplacement").onsubmit = event => { event.preventDefault(); save("replace", upload.files[0]); };
  insert.onclick = () => save("insert", upload.files[0]);
  find("#tlRestore").onclick = () => save("restore");
  find("#tlDuplicate").onclick = () => save("duplicate");
  find("#tlBlank").onclick = () => save("insert_blank");
  remove.onclick = () => save("remove");
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
