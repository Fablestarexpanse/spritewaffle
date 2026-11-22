"use strict";

function showFrameRepair(readUrl, saveUrl, frame, label, onApply, references = null) {
  const dialog = document.querySelector("#frameRepair");
  if (dialog.open) return;
  const reposition = references !== null;
  const operation = reposition ? "reposition" : "reprocess";
  const title = reposition ? "Reposition frame" : "Reprocess frame";
  const repairOptions = `
    <div class="row"><label>Green spill cleanup <select id="frMode">
      <option value="profile">Use profile</option>
      <option value="edge">Edges only</option>
      <option value="all">Whole sprite</option>
    </select></label></div>`;
  const shiftOptions = `
    <div class="row"><label>Method <select id="frMode">
      <option value="manual">Manual offset</option>
      <option value="reference" ${references?.length ? "" : "disabled"}>Align to reference foot</option>
    </select></label></div>
    <div class="row" id="frOffsets">
      <label>Right + / left − <input id="frDx" type="number" step="1" value="0" required aria-label="Horizontal offset in pixels"></label>
      <label>Down + / up − <input id="frDy" type="number" step="1" value="0" required aria-label="Vertical offset in pixels"></label>
    </div>
    <div class="row" id="frAlignment" hidden>
      <label>Reference frame <select id="frReference"></select></label>
      <label>Axes <select id="frAxes">
        <option value="vertical">Vertical</option>
        <option value="both">Horizontal and vertical</option>
      </select></label>
    </div>`;
  dialog.innerHTML = `
    <div class="row" style="margin:0">
      <h2 id="frTitle" style="margin:0">${title}</h2>
      <span class="spacer"></span><button id="frClose" type="button" autofocus>Close</button>
    </div>
    <p id="frSource" class="muted"></p>
    <form id="frOptions"><fieldset id="frFields">
      ${reposition ? shiftOptions : repairOptions}
      <div class="row">
        <button id="frRefresh" type="submit">Compare again</button>
        <label><input id="frHighlight" type="checkbox" disabled> Highlight changes</label>
      </div>
    </fieldset></form>
    <p id="frStatus" class="muted" role="status"></p>
    <p id="frFeet" class="muted" hidden></p>
    <div id="frImages" hidden>
      <figure><figcaption>Current</figcaption><div class="fr-canvas">
        <img id="frBefore" class="pix" alt="Current effective frame">
        <span id="frBeforeFoot" class="fr-foot" aria-hidden="true" hidden></span>
      </div></figure>
      <figure><figcaption>${reposition ? "Repositioned" : "Reprocessed"}</figcaption>
        <div class="fr-canvas">
          <img id="frAfter" class="pix" alt="Candidate frame">
          <div id="frMask" aria-hidden="true" hidden></div>
          <span id="frAfterFoot" class="fr-foot" aria-hidden="true" hidden></span>
        </div>
      </figure>
    </div>
    <div class="row"><span class="spacer"></span><button id="frApply" class="primary" type="button" disabled>Apply as replacement</button></div>`;
  const get = id => dialog.querySelector("#fr" + id);
  const mode = get("Mode"), close = get("Close"), apply = get("Apply"), refresh = get("Refresh");
  const images = get("Images"), status = get("Status"), source = get("Source");
  const highlight = get("Highlight"), mask = get("Mask");
  const dx = get("Dx"), dy = get("Dy"), reference = get("Reference"), axes = get("Axes");
  const form = get("Options"), fields = get("Fields"), feet = get("Feet");
  let request = 0, draft, saving = false;
  const open = () => dialog.open && close.isConnected;
  function message(text, error = false) {
    status.textContent = text;
    status.className = error ? "err" : "muted";
  }

  function clearComparison() {
    draft = null;
    apply.disabled = highlight.disabled = images.hidden = mask.hidden = feet.hidden = true;
    source.textContent = label;
  }

  function changeRepositionOptions() {
    const align = mode.value === "reference";
    get("Offsets").hidden = dx.disabled = dy.disabled = align;
    get("Alignment").hidden = reference.disabled = axes.disabled = !align;
    ++request;
    clearComparison();
    refresh.disabled = false;
    message("Compare the selected adjustment.");
  }

  function markFoot(element, point, data) {
    element.style.left = `${point[0] / data.width * 100}%`;
    element.style.top = `${point[1] / data.height * 100}%`;
    element.hidden = false;
  }

  async function compare() {
    if (!form.reportValidity()) return;
    const query = ++request;
    clearComparison();
    refresh.disabled = true;
    const parameters = !reposition ? {despill: mode.value} : mode.value === "reference" ?
      {reference: reference.value, axes: axes.value} : {dx: dx.valueAsNumber, dy: dy.valueAsNumber};
    message(reposition ? "Repositioning frame…" : "Reprocessing retained frame…");
    try {
      const data = await api(readUrl + "&" + new URLSearchParams(parameters));
      if (!open() || query !== request) return;
      draft = {data, parameters};
      images.style.setProperty("--fr-aspect", data.width / data.height);
      get("Before").src = "data:image/png;base64," + data.before_png;
      get("After").src = "data:image/png;base64," + data.after_png;
      mask.style.maskImage = `url("data:image/png;base64,${data.change_mask_png}")`;
      source.textContent = `${label} · ${data.width} × ${data.height} px`;
      if (reposition) {
        markFoot(get("BeforeFoot"), data.foot_before, data);
        markFoot(get("AfterFoot"), data.foot_after, data);
        const point = value => `(${value[0]}, ${value[1]})`;
        feet.textContent = `Foot point ${point(data.foot_before)} → ${point(data.foot_after)} px` +
          (data.reference ? ` · Reference ${data.reference} ${point(data.foot_reference)}` : "");
        feet.hidden = false;
      } else {
        source.textContent += ` · ${data.source.split("/").at(-1)}`;
      }
      images.hidden = false;
      apply.disabled = highlight.disabled = !data.changed_pixels;
      mask.hidden = !highlight.checked || !data.changed_pixels;
      const changes = data.changed_pixels ? `${data.changed_pixels} changed ${data.changed_pixels === 1 ? "pixel" : "pixels"}.` :
        reposition ? "Same pixels." : "Reprocessing produced the same pixels.";
      const signed = offset => offset > 0 ? `+${offset}` : String(offset);
      message(reposition ? `Offset (${signed(data.dx)}, ${signed(data.dy)}) px · ${changes}` : changes);
    } catch (error) {
      if (open() && query === request) message(error.message, true);
    } finally {
      if (open() && query === request) refresh.disabled = false;
    }
  }

  apply.onclick = async () => {
    if (!draft?.data.changed_pixels) return;
    saving = fields.disabled = close.disabled = apply.disabled = refresh.disabled = true;
    message("Saving candidate frame…");
    try {
      const data = await api(saveUrl, {operation, frame, ...draft.parameters, fingerprint: draft.data.fingerprint});
      fields.disabled = close.disabled = false;
      dialog.close();
      onApply(data);
    } catch (error) {
      draft = null;
      message(error.message, true);
    } finally {
      saving = fields.disabled = close.disabled = refresh.disabled = false;
    }
  };
  if (reposition) {
    reference.replaceChildren(...references.map(item => new Option(item.label, item.id)));
    for (const field of [mode, dx, dy, reference, axes]) field.oninput = field.onchange = changeRepositionOptions;
    changeRepositionOptions();
  } else {
    mode.onchange = compare;
  }
  form.onsubmit = event => { event.preventDefault(); compare(); };
  highlight.onchange = () => { mask.hidden = !highlight.checked; };
  close.onclick = () => dialog.close();
  dialog.oncancel = event => { if (saving) event.preventDefault(); };
  dialog.showModal();
  compare();
}
