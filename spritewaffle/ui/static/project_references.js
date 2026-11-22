(() => {
  "use strict";
  const route = "/api/project/references";
  const dialog = $("#projectReferenceDialog");
  const form = $("#projectReferenceForm");
  const fields = form.elements;
  const filter = $("#referenceFilter");
  const archived = $("#referenceArchived");
  const list = $("#projectReferenceList");
  const save = $("#referenceSave");
  const add = $("#referenceAdd");
  let entries = [];
  let editing = null;
  let loading = false;

  function status(message) {
    const output = $("#referenceStatus");
    output.textContent = message;
    output.hidden = !message;
  }

  function render() {
    const visible = entries.filter(entry => archived.checked || !entry.archived);
    const collections = [...new Set(visible.map(entry => entry.collection))].sort((a, b) => a.localeCompare(b));
    const selected = filter.value;
    filter.innerHTML = '<option value="">All collections</option>' + collections.map(name => `<option value="${esc(name)}">${esc(name)}</option>`).join("");
    if (collections.includes(selected)) filter.value = selected;
    $("#referenceCollections").innerHTML = collections.map(name => `<option value="${esc(name)}">`).join("");
    const matching = visible.filter(entry => !filter.value || entry.collection === filter.value);
    list.innerHTML = matching.map(entry => {
      const url = `${route}/${encodeURIComponent(entry.id)}/image`;
      return `<article class="reference-card" data-reference="${esc(entry.id)}">
        ${entry.available ? `<a class="reference-preview" href="${url}" data-view="${esc(entry.name)}" aria-label="View ${esc(entry.name)}">
          <img src="${url}?thumbnail=true" loading="lazy" alt=""></a>` : '<div class="reference-preview muted">Image missing</div>'}
        <strong>${esc(entry.name)}</strong>
        <span class="muted">${esc(entry.collection)} · ${esc(entry.width)} × ${esc(entry.height)}${entry.archived ? " · Archived" : ""}</span>
        ${entry.notes ? `<p>${esc(entry.notes)}</p>` : ""}
        <div class="row"><button type="button" data-edit>Edit</button>
          <button type="button" class="ghost" data-archive>${entry.archived ? "Restore" : "Archive"}</button></div>
      </article>`;
    }).join("") || '<p class="muted">No references here. Add an image or show archived references.</p>';
  }

  function openForm(entry) {
    editing = entry?.id ?? null;
    form.reset();
    form.hidden = false;
    $("#referenceFileField").hidden = !!entry;
    fields.image.disabled = !!entry;
    fields.image.required = !entry;
    fields.name.required = !!entry;
    fields.name.value = entry?.name || "";
    fields.collection.value = entry?.collection || filter.value;
    fields.notes.value = entry?.notes || "";
    save.textContent = entry ? "Save changes" : "Add reference";
    status("");
    (entry ? fields.name : fields.image).focus();
  }

  function closeForm() {
    form.hidden = true;
    form.reset();
    editing = null;
  }

  function saved(entry) {
    const index = entries.findIndex(item => item.id === entry.id);
    if (index === -1) entries.push(entry);
    else entries[index] = entry;
    render();
  }

  function encode(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.split(",", 2)[1]);
      reader.onerror = () => reject(new Error("Could not read the selected image"));
      reader.readAsDataURL(file);
    });
  }

  $("#btnProjectReferences").onclick = async () => {
    if (loading || dialog.open) return;
    closeForm();
    entries = [];
    render();
    dialog.showModal();
    loading = true;
    add.disabled = true;
    list.replaceChildren();
    status("Loading references…");
    try {
      entries = await api(route + "?include_archived=true");
      status("");
      render();
    } catch (error) {
      status(error.message);
    } finally {
      add.disabled = false;
      loading = false;
    }
  };
  $("#referenceClose").onclick = () => dialog.close();
  $("#referenceCancel").onclick = () => { closeForm(); add.focus(); };
  add.onclick = () => openForm();
  filter.onchange = archived.onchange = () => { if (!loading) render(); };

  form.onsubmit = async event => {
    event.preventDefault();
    const id = editing;
    const file = fields.image.files[0];
    const payload = {name: fields.name.value, collection: fields.collection.value, notes: fields.notes.value};
    if (!id && (!file || file.size > 16 * 1024 * 1024)) {
      status("Choose an image no larger than 16 MiB.");
      return;
    }
    save.disabled = true;
    status("Saving reference…");
    try {
      if (!id) Object.assign(payload, {filename: file.name, data: await encode(file)});
      const entry = await api(id ? `${route}/${encodeURIComponent(id)}` : route, payload);
      if (filter.value && filter.value !== entry.collection) filter.value = "";
      saved(entry);
      closeForm();
      status(id ? "Reference updated." : "Reference added.");
      add.focus();
    } catch (error) {
      status(error.message);
    } finally {
      save.disabled = false;
    }
  };

  list.onclick = async event => {
    const button = event.target.closest("button"), card = button?.closest("[data-reference]");
    if (!card || save.disabled) return;
    const entry = entries.find(item => item.id === card.dataset.reference);
    if (button.hasAttribute("data-edit")) { openForm(entry); return; }
    button.disabled = true;
    try {
      saved(await api(`${route}/${encodeURIComponent(entry.id)}`, {archived: !entry.archived}));
      status(entry.archived ? "Reference restored." : "Reference archived. Use Show archived to restore it.");
      const next = list.querySelector(`[data-reference="${entry.id}"] [data-archive]`);
      (next || archived).focus();
    } catch (error) {
      status(error.message);
    } finally {
      button.disabled = false;
    }
  };
})();
