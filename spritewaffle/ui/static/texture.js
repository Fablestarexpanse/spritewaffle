"use strict";
// Seamless texture jobs (core/texture.py): settings, variants with a tiled preview, approve, export,
// and "send to tileset". Uses the page's helpers ($, esc, api, jobPath, run, approve, toast).

const TEX_STYLES = {pixel: "Pixel art", painted: "Hand-painted", anime: "Anime cel", comic: "Comic ink"};

function texScoreClass(s) { return s == null ? "" : s <= 1.3 ? "drift-ok" : s <= 1.8 ? "drift-warn" : "drift-bad"; }

// Draw a tile repeated n x n on a canvas, nearest-neighbour; optionally offset by half a tile so the
// wrap seams meet in the middle of the view (where a seam is easiest to spot).
function texDrawTiled(canvas, src, n, offset) {
  const im = new Image();
  im.onload = () => {
    const ctx = canvas.getContext("2d"), t = im.naturalWidth, k = canvas.width / (t * n);
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const o = offset ? -t * k / 2 : 0;
    for (let y = -1; y <= n; y++) for (let x = -1; x <= n; x++) ctx.drawImage(im, o + x * t * k, o + y * t * k, t * k, t * k);
  };
  im.src = src;
}

function paneTexture(j, st) {
  const tx = j.texture || {settings: {}, variants: [], exports: [], tile_sizes: [32]};
  const s = tx.settings, have = tx.variants.length > 0, approved = st("texture") === "approved";
  const view = paneTexture.view || {n: 3, offset: false};
  $("#pane").innerHTML = `<section>
    <h2>Texture ${badge(st("texture"))} <span class="muted">seamless tiles: generate, check the wrap, approve, export</span></h2>
    <div class="tileset-form" style="grid-template-columns:repeat(auto-fill,minmax(150px,1fr))">
      <label class="field full"><span>What it is</span><textarea id="txDesc" placeholder="e.g. mossy cobblestone ground, dry cracked desert earth, shallow ocean water">${esc(s.description || "")}</textarea></label>
      <label class="field"><span>Tile size (px)</span><select id="txSize">${tx.tile_sizes.map(n => `<option ${n === s.tile_size ? "selected" : ""}>${n}</option>`).join("")}</select></label>
      <label class="field"><span>Style</span><select id="txStyle">${Object.entries(TEX_STYLES).map(([k, l]) => `<option value="${k}" ${k === s.style ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <label class="field"><span>Variants</span><input id="txVar" type="number" min="1" max="16" value="${s.variants || 4}"></label>
      <label class="field" ${s.style === "pixel" ? "" : "hidden"}><span>Colours</span><input id="txCol" type="number" min="2" max="256" value="${s.colours || 16}"></label>
      <label class="field" title="How far to zoom into the generated swatch: higher = fewer, bigger features per tile"><span>Detail zoom</span>
        <select id="txZoom"><option value="0" ${s.zoom_auto ? "selected" : ""}>Auto (${s.zoom}×)</option>${[1, 2, 3, 4, 5, 6].map(z => `<option value="${z}" ${!s.zoom_auto && z === s.zoom ? "selected" : ""}>${z}×</option>`).join("")}</select></label>
    </div>
    <div class="row">
      <button class="primary" id="txGen" title="Render every variant (GPU), make it seamless, cut the tiles">${have ? "Re-generate all" : "Generate"}</button>
      ${have ? `<button id="txRetile" title="Seam and cut every variant again from its saved render: new size, zoom or colours, no new render">Re-cut tiles</button>` : ""}
      ${have && !approved ? `<button class="primary" id="txApprove">Approve</button>` : ""}
      ${approved ? `<button id="txExport">Export</button><button class="primary" id="txTileset" title="Export, then open the variants as a new tileset (terrain, maps, Tiled)">Send to tileset</button>
        <button id="txTransition" title="Blend this texture with another approved one into the 16 corner transition tiles, with terrain rules filled in">Make transition…</button>` : ""}
    </div>
    <p class="hint">Each variant is generated seen from straight above, then joined edge to edge along the least visible cut,
      so it wraps exactly. <b>Wrap score</b>: how visible the seam is, about 1.0 = seamless (green ≤ 1.3).</p>
  </section>
  ${have ? `<section><h2>Variants <span class="spacer"></span>
      <label>Repeat <select id="txN">${[2, 3, 4, 8].map(n => `<option ${n === view.n ? "selected" : ""}>${n}</option>`).join("")}</select></label>
      <label title="Shift the view by half a tile so the wrap edges meet in the middle"><input type="checkbox" id="txOff" ${view.offset ? "checked" : ""}> Offset by half</label></h2>
    <div class="grid4">${tx.variants.map(v => `<div class="card">
      <canvas width="240" height="240" data-tile="${esc(v.tile)}" style="width:100%;border-radius:4px"></canvas>
      <div class="row" style="margin:0;justify-content:space-between"><b>#${v.index + 1}</b>
        <span class="muted ${texScoreClass(v.wrap_tile)}" title="tile ${v.wrap_tile}, seamless master ${v.wrap_master}, as generated ${v.wrap_raw}">wrap ${v.wrap_tile ?? "?"}</span></div>
      <div class="row" style="margin:0"><button data-txroll="${v.index}">Re-roll</button>
        <a href="${esc(v.master)}" data-view="Seamless master #${v.index + 1}"><button class="ghost">Master</button></a>
        <a href="${esc(v.raw)}" data-view="As generated #${v.index + 1}"><button class="ghost">Raw</button></a></div></div>`).join("")}</div></section>` : ""}
  ${tx.exports.length ? `<section><h2>Files</h2>${tx.exports.map(f => `<p><a href="${esc(f.url)}">${esc(f.name)}</a> <span class="muted">${kb(f.size)}</span></p>`).join("")}</section>` : ""}`;

  $$("[data-tile]").forEach(c => texDrawTiled(c, c.dataset.tile, view.n, view.offset));
  const save = () => api(jobPath() + "/texture", {description: $("#txDesc").value.trim(), tile_size: +$("#txSize").value,
    style: $("#txStyle").value, variants: +$("#txVar").value, colours: +($("#txCol")?.value || 16), zoom: +$("#txZoom").value});
  $("#txStyle").onchange = async () => { await save(); lastSig = ""; refreshAll(); };
  $("#txGen").onclick = async () => {
    if (!$("#txDesc").value.trim()) return toast("Describe the texture first", true);
    await save(); run("texture", {}, "Texture variants queued");
  };
  if ($("#txRetile")) $("#txRetile").onclick = async () => { await save(); run("texture_retile", {}, "Re-cutting tiles"); };
  if ($("#txApprove")) $("#txApprove").onclick = () => approve("texture");
  if ($("#txExport")) $("#txExport").onclick = async () => { const r = await api(jobPath() + "/texture/export", {}); toast(`Exported ${r.variants} tiles (${r.tile_size} px)`); lastSig = ""; refreshAll(); };
  if ($("#txTileset")) $("#txTileset").onclick = async () => {
    const r = await api(jobPath() + "/texture/tileset", {});
    toast(`Tileset made: ${r.tiles} tiles`); location.hash = `${r.character}/${r.job_id}/tileset`;
  };
  if ($("#txTransition")) $("#txTransition").onclick = () => texTransitionDialog(j);
  $$("[data-txroll]").forEach(b => b.onclick = () => run("texture", {only: [+b.dataset.txroll]}, `Variant ${+b.dataset.txroll + 1} re-roll queued`));
  if ($("#txN")) $("#txN").onchange = e => { paneTexture.view = {...view, n: +e.target.value}; renderJob(); };
  if ($("#txOff")) $("#txOff").onchange = e => { paneTexture.view = {...view, offset: e.target.checked}; renderJob(); };
}

// Terrain transition: this texture + another approved one -> the 16 corner tiles as a tileset with
// its terrain rules filled in (core/transition.py). Opens the new tileset's workspace.
function texTransitionDialog(j) {
  const d = $("#dlg"), others = j.textures || [], s = j.texture.settings;
  d.innerHTML = `<h2>Terrain transition <span class="spacer"></span><button class="ghost" id="trClose">Close</button></h2>
    ${others.length ? `<p class="hint" style="margin-top:0">Blends <b>${esc(j.character)}</b> with another approved texture into the 16 tiles a corner
      terrain needs (every mix of the four corners). The tileset gets its terrain rules, so the map preview and Tiled export work right away.</p>
    <div class="tileset-form" style="grid-template-columns:repeat(auto-fill,minmax(160px,1fr))">
      <label class="field"><span>Other texture</span><select id="trOther">${others.map(o => `<option value="${esc(o.character)}/${esc(o.job_id)}">${esc(o.character)} / ${esc(o.job_id)}</option>`).join("")}</select></label>
      <label class="field"><span>Name for ${esc(j.character)}</span><input id="trNameA" value="${esc(j.character)}"></label>
      <label class="field"><span>Name for the other</span><input id="trNameB" value="${esc(others[0].character)}"></label>
      <label class="field"><span>Tile size (px)</span><input id="trSize" type="number" value="${s.tile_size}"></label>
      <label class="field"><span>Border: straight ↔ ragged</span><input id="trRough" type="range" min="0" max="1" step="0.05" value="0.5"></label>
      <label class="field"><span>Border shape (seed)</span><input id="trSeed" type="number" value="0"></label>
      <label class="field"><span>Variant of ${esc(j.character)}</span><input id="trVa" type="number" min="1" value="1"></label>
      <label class="field"><span>Variant of the other</span><input id="trVb" type="number" min="1" value="1"></label>
      <label class="field" title="Corner: 16 tiles, painted in SpriteWaffle's map preview, Tiled and Godot. Blob: 47 + plain tiles with rounded inner corners, painted in Tiled or Godot"><span>Set</span>
        <select id="trKind"><option value="corner">Corner (16 tiles)</option><option value="blob">Blob (47 + plain)</option></select></label>
      <label class="field" title="A darker lip on the lower terrain along the border"><span>Edge lip (px)</span><input id="trBand" type="number" min="0" max="16" step="0.5" placeholder="auto"></label>
    </div>
    <div class="row"><button class="primary" id="trGo">Make transition tileset</button></div>`
    : `<p class="warn">Approve a second seamless texture first (e.g. dirt next to grass), then come back.</p>`}`;
  $("#trClose").onclick = () => d.close();
  if ($("#trOther")) $("#trOther").onchange = e => { $("#trNameB").value = e.target.value.split("/")[0]; };
  if ($("#trGo")) $("#trGo").onclick = async () => {
    $("#trGo").disabled = true;
    try {
      const r = await api(jobPath() + "/texture/transition", {other: $("#trOther").value, names: [$("#trNameA").value.trim(), $("#trNameB").value.trim()],
        tile_size: +$("#trSize").value, roughness: +$("#trRough").value, seed: +$("#trSeed").value,
        variant_a: +$("#trVa").value - 1, variant_b: +$("#trVb").value - 1, kind: $("#trKind").value,
        ...($("#trBand").value !== "" ? {band: +$("#trBand").value} : {})});
      d.close(); toast(`Transition tileset made: ${r.names.join(" / ")}`);
      location.hash = `${r.character}/${r.job_id}/tileset`;
    } finally { if ($("#trGo")) $("#trGo").disabled = false; }
  };
  d.showModal();
}
