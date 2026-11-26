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
      ${approved ? `<button id="txExport">Export</button><button class="primary" id="txTileset" title="Export, then open the variants as a new tileset (terrain, maps, Tiled)">Send to tileset</button>` : ""}
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
  $$("[data-txroll]").forEach(b => b.onclick = () => run("texture", {only: [+b.dataset.txroll]}, `Variant ${+b.dataset.txroll + 1} re-roll queued`));
  if ($("#txN")) $("#txN").onchange = e => { paneTexture.view = {...view, n: +e.target.value}; renderJob(); };
  if ($("#txOff")) $("#txOff").onchange = e => { paneTexture.view = {...view, offset: e.target.checked}; renderJob(); };
}
