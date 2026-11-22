"use strict";

function showFrameRepair(readUrl, saveUrl, frame, label, onApply) {
  const dialog = document.querySelector("#frameRepair");
  if (dialog.open) return;
  dialog.innerHTML = `
    <div class="row" style="margin:0">
      <h2 id="frTitle" style="margin:0">Reprocess frame</h2>
      <span class="spacer"></span><button id="frClose" type="button" autofocus>Close</button>
    </div>
    <p id="frSource" class="muted"></p>
    <div class="row">
      <label>Green spill cleanup <select id="frMode">
        <option value="profile">Use profile</option>
        <option value="edge">Edges only</option>
        <option value="all">Whole sprite</option>
      </select></label>
      <button id="frRefresh" type="button">Compare again</button>
      <label><input id="frHighlight" type="checkbox" disabled> Highlight changes</label>
    </div>
    <p id="frStatus" class="muted" role="status"></p>
    <div id="frImages" hidden>
      <figure><figcaption>Current</figcaption><img id="frBefore" class="pix" alt="Current effective frame"></figure>
      <figure><figcaption>Reprocessed</figcaption>
        <div id="frCandidate">
          <img id="frAfter" class="pix" alt="Frame reprocessed from the retained master">
          <div id="frMask" aria-hidden="true" hidden></div>
        </div>
      </figure>
    </div>
    <div class="row"><span class="spacer"></span><button id="frApply" class="primary" type="button" disabled>Apply as replacement</button></div>`;
  const get = id => dialog.querySelector("#fr" + id);
  const mode = get("Mode"), close = get("Close"), apply = get("Apply"), refresh = get("Refresh");
  const images = get("Images"), status = get("Status"), source = get("Source");
  const highlight = get("Highlight"), mask = get("Mask");
  let request = 0, draft, saving = false;
  const open = () => dialog.open && close.isConnected;
  function message(text, error = false) {
    status.textContent = text;
    status.className = error ? "err" : "muted";
  }

  async function compare() {
    const query = ++request;
    draft = null;
    apply.disabled = refresh.disabled = highlight.disabled = images.hidden = mask.hidden = true;
    source.textContent = label;
    message("Reprocessing retained frame…");
    try {
      const data = await api(readUrl + "&despill=" + encodeURIComponent(mode.value));
      if (!open() || query !== request) return;
      draft = data;
      get("Before").src = "data:image/png;base64," + data.before_png;
      get("After").src = "data:image/png;base64," + data.after_png;
      mask.style.maskImage = `url("data:image/png;base64,${data.change_mask_png}")`;
      source.textContent = `${label} · ${data.width} × ${data.height} px · ${data.source.split("/").at(-1)}`;
      images.hidden = false;
      apply.disabled = highlight.disabled = !data.changed_pixels;
      mask.hidden = !highlight.checked || !data.changed_pixels;
      message(data.changed_pixels ? `${data.changed_pixels} changed ${data.changed_pixels === 1 ? "pixel" : "pixels"}.` :
        "Reprocessing produced the same pixels.");
    } catch (error) {
      if (open() && query === request) message(error.message, true);
    } finally {
      if (open() && query === request) refresh.disabled = false;
    }
  }

  apply.onclick = async () => {
    if (!draft?.changed_pixels) return;
    saving = mode.disabled = close.disabled = apply.disabled = refresh.disabled = true;
    message("Saving reprocessed frame…");
    try {
      const data = await api(saveUrl, {operation: "reprocess", frame, despill: draft.despill, fingerprint: draft.fingerprint});
      mode.disabled = close.disabled = false;
      dialog.close();
      onApply(data);
    } catch (error) {
      draft = null;
      message(error.message, true);
    } finally {
      saving = mode.disabled = close.disabled = refresh.disabled = false;
    }
  };
  mode.onchange = refresh.onclick = compare;
  highlight.onchange = () => { mask.hidden = !highlight.checked; };
  close.onclick = () => dialog.close();
  dialog.oncancel = event => { if (saving) event.preventDefault(); };
  dialog.showModal();
  compare();
}
