function bindTilemapObjects(panel, changed, selectedCell, request) {
  panel.innerHTML = `
    <summary>Map objects <span id="mapObjectCount" class="muted"></span></summary>
    <p class="hint">Place a tile above the ground layer. Give it named states, then apply it and save the map.</p>
    <fieldset id="mapObjectFields">
      <div class="row">
        <label>Template <select id="mapObjectTemplate"></select></label>
        <button id="mapObjectUseTemplate" type="button" disabled>Use template</button>
        <button id="mapObjectSaveTemplate" type="button" disabled>Save as template</button>
      </div>
      <p id="mapTemplateError" class="warn" role="alert" hidden></p>
      <div class="row">
        <label>Object <select id="mapObjectList"></select></label>
        <button id="mapObjectNew" type="button">New object</button>
      </div>
      <form id="mapObjectForm">
        <div class="tileset-form">
          <label class="field">Name <input id="mapObjectName" required maxlength="80" placeholder="Front door"></label>
          <label class="field">Type <input id="mapObjectKind" maxlength="40" placeholder="door"></label>
          <label class="field">Cell <input id="mapObjectCell" type="number" min="0" required></label>
          <label class="field">Active state <select id="mapObjectState"></select></label>
        </div>
        <p id="mapObjectAtlas" class="warn" hidden>Enter new tile IDs for every state to use the replacement atlas.</p>
        <div id="mapObjectStates"></div>
        <div class="row">
          <button id="mapObjectAddState" type="button">Add state</button>
          <button type="submit">Apply object</button>
          <button id="mapObjectRemove" type="button">Remove object</button>
        </div>
        <p id="mapObjectStatus" class="muted" role="status"></p>
        <p id="mapObjectError" class="warn" role="alert" hidden></p>
      </form>
    </fieldset>`;
  const find = selector => panel.querySelector(selector);
  const list = find("#mapObjectList"), name = find("#mapObjectName"), kind = find("#mapObjectKind");
  const cell = find("#mapObjectCell"), active = find("#mapObjectState"), states = find("#mapObjectStates");
  const templateList = find("#mapObjectTemplate"), useTemplate = find("#mapObjectUseTemplate");
  const saveTemplate = find("#mapObjectSaveTemplate");
  let objects = [], rows = [], context, lastTile = 0;
  let templates = [], templateLoaded = false, templateWorking = false, mapLocked = false, staged = null;
  let draftVersion = 0;

  function templateError(message = "") {
    const notice = find("#mapTemplateError");
    notice.textContent = message;
    notice.hidden = !message;
  }

  function templateControls() {
    const picked = templates.find(item => item.id === templateList.value);
    const applied = objects.find(item => item.id === list.value);
    useTemplate.disabled = !picked || picked.atlas !== context?.atlas_revision;
    saveTemplate.disabled = !templateLoaded || !applied || applied.atlas !== context?.atlas_revision;
  }

  function templateOptions(selected = templateList.value) {
    templateList.replaceChildren(new Option(templates.length ? "Select a template" : "No templates saved", ""),
      ...templates.map(item => new Option(item.name + (item.atlas === context?.atlas_revision ? "" : " (previous atlas)"),
        item.id)));
    templateList.value = selected;
    templateControls();
  }

  function lockEditor() {
    find("#mapObjectFields").disabled = mapLocked || templateWorking;
  }

  async function templateAction(action) {
    if (templateWorking || mapLocked) return;
    templateWorking = true;
    lockEditor();
    templateError();
    try { await action(); }
    catch (cause) { templateError(cause.message); }
    finally {
      templateWorking = false;
      lockEditor();
    }
  }

  function error(message = "") {
    find("#mapObjectError").textContent = message;
    find("#mapObjectError").hidden = !message;
  }

  function options(id = "") {
    list.replaceChildren(new Option("New object", ""), ...objects.map(item => new Option(item.name, item.id)));
    list.value = id;
    find("#mapObjectCount").textContent = objects.length ? "(" + objects.length + ")" : "";
  }

  function activeOptions(selected = 0) {
    active.replaceChildren(...rows.map((row, index) => new Option(row.name.trim() || "State " + (index + 1), index)));
    active.value = Math.min(selected, rows.length - 1);
  }

  function showRows(selected = 0) {
    states.replaceChildren(...rows.map((row, index) => {
      const fields = document.createElement("div");
      fields.className = "row map-object-state";
      fields.innerHTML = '<label>State name <input required maxlength="40"></label>' +
        '<label>Tile ID <input type="number" min="0" required></label>' +
        '<button type="button">Remove state</button>';
      const [stateName, tile] = fields.querySelectorAll("input");
      stateName.value = row.name;
      stateName.setAttribute("aria-label", "State " + (index + 1) + " name");
      tile.value = row.tile ?? "";
      tile.max = lastTile;
      tile.setAttribute("aria-label", "State " + (index + 1) + " tile ID");
      stateName.oninput = () => {
        row.name = stateName.value;
        activeOptions(Number(active.value));
      };
      tile.oninput = () => row.tile = Number.isNaN(tile.valueAsNumber) ? null : tile.valueAsNumber;
      const remove = fields.querySelector("button");
      remove.disabled = rows.length === 2;
      remove.setAttribute("aria-label", "Remove state " + (index + 1));
      remove.onclick = () => {
        const savedIndex = Number(active.value);
        rows.splice(index, 1);
        showRows(savedIndex > index ? savedIndex - 1 : savedIndex);
      };
      return fields;
    }));
    activeOptions(selected);
    find("#mapObjectAddState").disabled = rows.length >= 8;
  }

  function select() {
    const entry = staged || objects.find(item => item.id === list.value);
    const outdated = !!entry && entry.atlas !== context?.atlas_revision;
    name.value = entry?.name || "";
    kind.value = entry?.kind || "";
    cell.value = entry?.cell ?? selectedCell();
    rows = entry ? entry.states.map(row => ({...row, tile: outdated ? null : row.tile}))
      : [{name: "", tile: null}, {name: "", tile: null}];
    find("#mapObjectAtlas").hidden = !outdated;
    find("#mapObjectRemove").disabled = !list.value;
    find("#mapObjectStatus").textContent = "";
    error();
    showRows(Math.max(0, rows.findIndex(row => row.name === entry?.state)));
    templateControls();
  }

  panel.ontoggle = () => {
    if (!panel.open || templateLoaded) return;
    templateAction(async () => {
      templates = await request("/object-templates");
      templateLoaded = true;
      templateOptions();
    });
  };
  templateList.onchange = templateControls;
  useTemplate.onclick = () => templateAction(async () => {
    const version = draftVersion;
    const draft = await request("/object-templates/" + encodeURIComponent(templateList.value) + "/instantiate",
      {cell: selectedCell()});
    if (version !== draftVersion) return;
    staged = draft;
    list.value = "";
    select();
    find("#mapObjectStatus").textContent = "Template loaded · Apply to place it";
  });
  saveTemplate.onclick = () => templateAction(async () => {
    const applied = objects.find(item => item.id === list.value);
    const template = await request("/object-templates", {
      name: applied.name, kind: applied.kind, state: applied.state, states: applied.states, atlas: applied.atlas,
    });
    templates = [...templates, template].sort((a, b) => a.name.localeCompare(b.name));
    templateOptions(template.id);
    find("#mapObjectStatus").textContent = "Template saved to tileset";
  });

  list.onchange = () => {
    staged = null;
    select();
  };
  find("#mapObjectNew").onclick = () => {
    staged = null;
    list.value = "";
    select();
    name.focus();
  };
  find("#mapObjectAddState").onclick = () => {
    const before = Number(active.value);
    rows.push({name: "", tile: null});
    showRows(before);
    states.lastElementChild.querySelector("input").focus();
  };
  find("#mapObjectRemove").onclick = () => {
    objects = objects.filter(item => item.id !== list.value);
    options();
    select();
    changed();
    find("#mapObjectStatus").textContent = "Object removed from draft";
  };
  find("#mapObjectForm").onsubmit = event => {
    event.preventDefault();
    const stateNames = rows.map(row => row.name.trim());
    if (!name.value.trim() || stateNames.some(label => !label) ||
        new Set(stateNames.map(label => label.toLowerCase())).size !== rows.length) {
      return error("Enter an object name and distinct names for its states.");
    }
    if (objects.some(item => item.id !== list.value && item.cell === cell.valueAsNumber)) {
      return error("A different object already occupies this cell.");
    }
    if (!list.value && objects.length >= 64) return error("A map can hold up to 64 objects.");
    const key = list.value || staged?.id || Array.from(crypto.getRandomValues(new Uint8Array(12)),
      byte => byte.toString(16).padStart(2, "0")).join("");
    const draft = {id: key, name: name.value.trim(), kind: kind.value.trim() || "object", cell: cell.valueAsNumber,
      state: stateNames[Number(active.value)],
      states: rows.map((row, index) => ({name: stateNames[index], tile: row.tile})),
      atlas: context.atlas_revision};
    const source = staged?.template_id || objects.find(item => item.id === key)?.template_id;
    if (source) draft.template_id = source;
    objects = list.value ? objects.map(item => item.id === key ? draft : item) : [...objects, draft];
    staged = null;
    options(key);
    select();
    changed();
    find("#mapObjectStatus").textContent = "Applied to map draft";
  };

  return {
    entries: () => objects,
    outdated: () => objects.filter(item => item.atlas !== context?.atlas_revision).length,
    locked(working) {
      mapLocked = working;
      lockEditor();
    },
    load(entries) {
      draftVersion++;
      objects = entries || [];
      staged = null;
      options();
      select();
    },
    sync(next, count) {
      const changedAtlas = context?.atlas_revision !== next.atlas_revision;
      context = next;
      const grid = next.tileset.grid;
      lastTile = grid.columns * grid.rows - 1;
      cell.max = count - 1;
      if (changedAtlas) {
        templateOptions();
        select();
      }
    },
  };
}
