import { Color } from 'three';

export function materialEditor({ send, selectSurface, inspectMaterial, showTab, paintSwatches, previewMode }) {
  const $ = id => document.getElementById(id), pageSize = 8;
  let asset, generation, editable = false, dirty = false, busy = false, variant = '', activeTab = 'view';
  let target = null, library = { entries: [] }, page = 0, request = 0, selectedId = '', cache = new Map(), rendered = false;
  const key = value => `${value.node}:${value.primitive}`;
  const primitive = () => target && asset?.metadata.meshes?.[asset.metadata.nodes[target.node]?.mesh]?.primitives[target.primitive];
  const surface = () => asset?.surfaces[primitive()?.material];
  const hex = values => '#' + new Color().fromArray(values).getHexString();
  const color = id => new Color($(id).value).toArray();
  let repeat = [1, 1], gesture = 1;
  const endGesture = () => { gesture++; send('endMaterialEdit'); };
  const currentMapping = () => ({ offset: [Number($('uvOffsetU').value), Number($('uvOffsetV').value)], scale: [Number($('uvScaleU').value), Number($('uvScaleV').value)], pivot: [Number($('uvPivotU').value), Number($('uvPivotV').value)], rotation: Number($('uvRotation').value) });
  const textureInfo = material => material?.pbrMetallicRoughness?.baseColorTexture || material?.pbrMetallicRoughness?.metallicRoughnessTexture || material?.normalTexture || material?.occlusionTexture || material?.emissiveTexture;
  function notice(error) {
    $('editNotice').textContent = error || (!editable ? 'Git revision is read-only. Open the working copy to edit.' : variant ? 'Choose Default in View → Season / variant to edit the base material.' : dirty ? 'Unsaved material edits · Ctrl+S to save' : 'Material changes are saved with the GLB.');
    $('editNotice').classList.toggle('warning', !!error);
  }
  function controls() {
    const canEdit = editable && !variant && !busy && !!primitive();
    $('saveGlb').disabled = !editable || !dirty || busy;
    $('saveGlbAs').disabled = $('undoEdit').disabled = $('redoEdit').disabled = !editable || busy;
    $('assignExisting').disabled = !canEdit || !asset?.surfaces.length;
    $('propertyFields').disabled = !canEdit;
    $('assignPalette').disabled = !canEdit || !cache.get(selectedId)?.spec;
    $('placementFields').disabled = $('uvFit').disabled = !canEdit || primitive()?.attributes.TEXCOORD_0 === undefined;
    $('uvReset').disabled = !canEdit || !primitive()?.extras?.mmTexturePlacement;
    $('vertexPaintFields').disabled = !canEdit; $('restoreVertexPaint').disabled = !canEdit || !primitive()?.extras?.mmVertexPaint;
    $('paintColor').disabled = $('paintMode').value === 'white';
    $('paintMatchColor').disabled = $('paintTolerance').disabled = !$('paintMatch').checked;
    $('samplingFields').disabled = !canEdit || !textureInfo(surface()?.gltf);
    $('surfaceTools').hidden = !['materials', 'palette'].includes(activeTab);
    $('editPlacement').hidden = activeTab !== 'palette';
  }
  function select(value, highlight = true) {
    if (JSON.stringify(value) !== JSON.stringify(target)) { endGesture(); $('tab-materials').scrollTop = 0; }
    target = value;
    $('surfaceTarget').value = target ? key(target) : '';
    const current = surface(), pbr = current?.gltf.pbrMetallicRoughness || {};
    $('surfaceInfo').textContent = target ? `Assigned: ${current?.name || 'Default material'}${current?.managed ? ' · shared' : ''}` : 'Pick a surface, or choose one from the list.';
    $('existingMaterial').value = primitive()?.material === undefined ? '' : String(primitive().material);
    $('editTint').value = $('editTintHex').value = hex(pbr.baseColorFactor || [1, 1, 1]); $('editOpacity').value = pbr.baseColorFactor?.[3] ?? 1;
    $('editEmission').value = hex(current?.gltf.emissiveFactor || [0, 0, 0]);
    $('editEmissionMode').value = current?.gltf.extras?.mmEmission === 'off' ? 'off' : 'inherit';
    $('editRoughness').value = current?.managed?.roughness ?? pbr.roughnessFactor ?? 1;
    $('editMetallic').value = current?.managed?.metallic ?? pbr.metallicFactor ?? 1;
    $('editRoughness').disabled = $('editMetallic').disabled = !!current?.managed; $('sharedFinish').hidden = !current?.managed;
    $('editAlpha').value = current?.gltf.alphaMode || 'OPAQUE'; $('editCutoff').value = current?.gltf.alphaCutoff ?? .5; $('editDoubleSided').checked = !!current?.gltf.doubleSided;
    const mapping = primitive()?.extras?.mmTexturePlacement || { offset: [0, 0], scale: [1, 1], rotation: 0, pivot: [.5, .5] };
    for (const [key, ids] of [['offset', ['uvOffsetU', 'uvOffsetV']], ['scale', ['uvScaleU', 'uvScaleV']], ['pivot', ['uvPivotU', 'uvPivotV']]]) ids.forEach((id, i) => $(id).value = mapping[key][i]);
    $('uvRotation').value = mapping.rotation; repeat = [...mapping.scale];
    const texture = asset?.metadata.textures?.[textureInfo(current?.gltf)?.index], sampler = asset?.metadata.samplers?.[texture?.sampler] || {};
    $('wrapU').value = sampler.wrapS ?? 10497; $('wrapV').value = sampler.wrapT ?? 10497; $('minFilter').value = sampler.minFilter ?? 9987; $('magFilter').value = sampler.magFilter ?? 9729;
    $('vertexSwatches').replaceChildren();
    const painted = primitive()?.attributes.COLOR_0 !== undefined && primitive()?.extras?.mmVertexPaint?.source !== null;
    if (!painted) $('paintMatch').checked = false;
    $('vertexPaintInfo').textContent = painted ? 'Authored vertex colours also tint this surface. Recolour them here to retain the material texture and shading.' : 'This surface has no authored vertex paint. You can add it here.';
    for (const rgb of target && painted ? paintSwatches(target) : []) {
      const value = hex(rgb), button = document.createElement('button'), swatch = document.createElement('input');
      button.className = 'swatch'; button.type = 'button'; button.title = value; button.setAttribute('aria-label', `Match paint ${value}`);
      swatch.type = 'color'; swatch.value = value; swatch.tabIndex = -1; button.append(swatch);
      button.onclick = () => { endGesture(); $('paintMatch').checked = true; $('paintMatchColor').value = value; controls(); }; $('vertexSwatches').append(button);
    }
    if (target && highlight) selectSurface(target);
    if (current) inspectMaterial(current.index);
    notice(); controls();
  }
  function edit(action) {
    if (!editable || variant || busy || !primitive()) return;
    busy = true; notice(); controls();
    send('materialEdit', { generation, edit: { ...action, target, scope: $('editScope').value } });
  }
  function live(action) {
    if (!editable || variant || busy || !primitive()) return;
    dirty = true; notice(); controls();
    send('materialEdit', { generation, live: true, gesture, edit: { ...action, target, scope: $('editScope').value } });
  }
  function livePlacement() {
    if ($('placementFields').disabled) return;
    const fields = [...$('placementFields').querySelectorAll('input[type=number]')], value = currentMapping();
    if (fields.some(input => input.value === '' || !input.validity.valid) || value.scale.some(n => Math.abs(n) < .00001)) { notice('Enter valid numbers and a non-zero scale. The last valid preview is kept.'); return; }
    live({ kind: 'placement', mapping: value });
  }
  function liveProperties() {
    if ($('propertyFields').disabled || !$('materialForm').checkValidity() || [...$('propertyFields').querySelectorAll('input[type=number]')].some(input => input.value === '')) return;
    const original = surface()?.gltf || {}, pbr = original.pbrMetallicRoughness || {};
    // Keep untouched linear factors exact instead of round-tripping them through an sRGB colour picker.
    const rgb = $('editTint').value === hex(pbr.baseColorFactor || [1, 1, 1]) ? (pbr.baseColorFactor || [1, 1, 1]).slice(0, 3) : color('editTint');
    const emission = $('editEmission').value === hex(original.emissiveFactor || [0, 0, 0]) ? original.emissiveFactor || [0, 0, 0] : color('editEmission');
    const changes = { baseColorFactor: [...rgb, Number($('editOpacity').value)], emissiveFactor: emission, emissionMode: $('editEmissionMode').value, alphaMode: $('editAlpha').value, alphaCutoff: Number($('editCutoff').value), doubleSided: $('editDoubleSided').checked };
    if (!surface()?.managed) { changes.roughnessFactor = Number($('editRoughness').value); changes.metallicFactor = Number($('editMetallic').value); }
    live({ kind: 'properties', changes });
  }
  function livePaint() {
    if ($('vertexPaintFields').disabled) return;
    const matching = $('paintMatch').checked, tolerance = Number($('paintTolerance').value);
    if (matching && ($('paintTolerance').value === '' || !$('paintTolerance').validity.valid)) { notice('Enter a tolerance from 0 to 2. The last valid preview is kept.'); return; }
    live({ kind: 'vertexTint', mode: $('paintMode').value, color: color('paintColor'), match: matching ? { color: color('paintMatchColor'), tolerance } : null });
  }
  function liveSampling() {
    if ($('samplingFields').disabled) return;
    live({ kind: 'sampling', sampling: { wrapS: Number($('wrapU').value), wrapT: Number($('wrapV').value), minFilter: Number($('minFilter').value), magFilter: Number($('magFilter').value) } });
  }
  function chooseEntry(id) {
    selectedId = id;
    for (const button of $('paletteGrid').querySelectorAll('button')) button.setAttribute('aria-pressed', String(button.dataset.material === id));
    const entry = cache.get(id);
    $('paletteSelection').textContent = entry?.error || (entry ? `${id} · ${entry.spec.shader ? 'Shader preview' : 'Shared PBR'} · roughness ${entry.spec.roughness} · metallic ${entry.spec.metallic}${entry.metres ? ` · ${entry.metres} m repeat at ${entry.pixels}px` : ''}` : 'Albedo previews · Select a material to assign.');
    controls();
  }
  function paintEntry(button, entry) {
    button.replaceChildren();
    const image = document.createElement('img'); image.alt = ''; image.loading = 'lazy';
    if (entry.spec?.maps.albedo) image.src = entry.spec.maps.albedo.url;
    const caption = document.createElement('span'); caption.textContent = entry.name;
    const folder = document.createElement('small'); folder.textContent = entry.error ? 'Unavailable — see details' : entry.folder || entry.category;
    button.append(image, caption, folder); button.title = entry.error ? `${entry.id}\n${entry.error}` : `${entry.id}\n${entry.category}`;
    button.classList.toggle('unavailable', !!entry.error);
  }
  function renderPalette() {
    if (!asset || activeTab !== 'palette') return;
    rendered = true;
    const query = $('paletteSearch').value.trim().toLowerCase(), folder = $('paletteFolder').value, category = $('paletteCategory').value;
    const filtered = library.entries.filter(item => (!query || item.id.toLowerCase().includes(query)) && (!folder || item.folder === folder) && (!category || item.category === category));
    const pages = Math.max(1, Math.ceil(filtered.length / pageSize)); page = Math.min(page, pages - 1);
    $('paletteCount').textContent = library.error || `${filtered.length} of ${library.entries.length} materials · albedo previews`;
    $('palettePage').textContent = `${page + 1} / ${pages}`; $('palettePrevious').disabled = page === 0; $('paletteNext').disabled = page + 1 === pages;
    const entries = filtered.slice(page * pageSize, (page + 1) * pageSize); $('paletteGrid').replaceChildren();
    for (const entry of entries) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'palette-card'; button.dataset.material = entry.id;
      button.setAttribute('aria-label', entry.id); button.setAttribute('aria-pressed', String(selectedId === entry.id));
      paintEntry(button, cache.get(entry.id) || entry); button.onclick = () => chooseEntry(entry.id); $('paletteGrid').append(button);
    }
    request++;
    const missing = entries.filter(entry => !cache.has(entry.id)).map(entry => entry.id);
    if (missing.length) send('palettePage', { ids: missing, generation, request });
  }
  $('surfaceTarget').onchange = () => { const [node, primitive] = $('surfaceTarget').value.split(':').map(Number); select($('surfaceTarget').value ? { node, primitive } : null); };
  $('browsePalette').onclick = () => showTab('palette');
  $('editPlacement').onclick = () => { showTab('materials'); $('tab-materials').scrollTop = 0; };
  $('editScope').onchange = endGesture;
  $('assignExisting').onclick = () => edit({ kind: 'existing', material: Number($('existingMaterial').value) });
  $('assignPalette').onclick = () => edit({ kind: 'shared', id: selectedId, keepEmission: $('keepEmission').checked });
  $('editTint').oninput = () => $('editTintHex').value = $('editTint').value;
  $('editTintHex').oninput = () => { if (/^#[0-9a-f]{6}$/i.test($('editTintHex').value)) $('editTint').value = $('editTintHex').value; };
  $('resetTint').onclick = () => { endGesture(); $('editTint').value = $('editTintHex').value = '#ffffff'; liveProperties(); };
  $('placementForm').oninput = event => { if (event.target.type === 'number') livePlacement(); };
  $('placementForm').onsubmit = event => { event.preventDefault(); livePlacement(); };
  $('uvReset').onclick = () => edit({ kind: 'placement', reset: true });
  $('uvFit').onclick = () => edit({ kind: 'placement', fit: true, mapping: { offset: [0, 0], scale: [1, 1], pivot: [0, 0], rotation: 0 } });
  for (const [id, amount] of [['uvTurnLeft', -90], ['uvTurnRight', 90]]) $(id).onclick = () => { endGesture(); $('uvRotation').value = Number($('uvRotation').value) + amount; livePlacement(); };
  for (const [id, input] of [['uvFlipU', 'uvScaleU'], ['uvFlipV', 'uvScaleV']]) $(id).onclick = () => { endGesture(); $(input).value = -Number($(input).value); repeat = currentMapping().scale; livePlacement(); };
  for (const [i, id] of ['uvScaleU', 'uvScaleV'].entries()) $(id).oninput = () => {
    const value = Number($(id).value);
    if ($('uvLinkScale').checked && repeat[i] && value) $('uvScale' + (i ? 'U' : 'V')).value = Number((repeat[1 - i] * value / repeat[i]).toPrecision(8));
    repeat = currentMapping().scale;
  };
  $('vertexPaintForm').oninput = livePaint;
  $('vertexPaintForm').onsubmit = event => { event.preventDefault(); livePaint(); };
  // Colour, mode and tolerance form one adjustment; a new swatch starts the next paint group.
  $('vertexPaintForm').addEventListener('focusout', event => { if (!$('vertexPaint').contains(event.relatedTarget)) endGesture(); });
  $('restoreVertexPaint').onclick = () => edit({ kind: 'vertexTint', mode: 'restore' });
  $('samplingForm').oninput = liveSampling;
  $('samplingForm').onsubmit = event => { event.preventDefault(); liveSampling(); };
  $('samplingForm').addEventListener('focusout', event => { if (!$('textureSampling').contains(event.relatedTarget)) endGesture(); });
  $('previewChecker').onclick = () => previewMode('checker'); $('previewMaterial').onclick = () => previewMode('pbr');
  $('materialForm').oninput = liveProperties;
  $('materialForm').onsubmit = event => { event.preventDefault(); liveProperties(); };
  for (const id of ['placementForm', 'materialForm']) $(id).addEventListener('focusout', endGesture);
  for (const id of ['paletteSearch', 'paletteFolder', 'paletteCategory']) $(id).addEventListener('input', () => { page = 0; renderPalette(); });
  $('palettePrevious').onclick = () => { page--; renderPalette(); }; $('paletteNext').onclick = () => { page++; renderPalette(); };
  $('paletteRefresh').onclick = () => send('reload');
  for (const [id, type] of [['saveGlb', 'saveGlb'], ['saveGlbAs', 'saveGlbAs'], ['undoEdit', 'undo'], ['redoEdit', 'redo']]) $(id).onclick = () => { endGesture(); send(type); };
  document.addEventListener('keydown', event => {
    if (!editable || !(event.ctrlKey || event.metaKey) || event.altKey) return;
    const key = event.key.toLowerCase(), typing = event.target.matches('input, textarea, [contenteditable="true"]');
    const type = key === 's' ? event.shiftKey ? 'saveGlbAs' : 'saveGlb' : !typing && key === 'z' ? event.shiftKey ? 'redo' : 'undo' : !typing && key === 'y' ? 'redo' : null;
    if (type) { event.preventDefault(); event.stopPropagation(); endGesture(); send(type); }
  });
  return {
    selected: () => target,
    pick: value => { if (JSON.stringify(value) !== JSON.stringify(target)) select(value, false); },
    tab(name) { activeTab = name; controls(); if (!rendered) renderPalette(); },
    loading() { busy = true; controls(); },
    status(message) { dirty = !!message.dirty; busy = false; notice(message.error); controls(); },
    preview(message) {
      if (message.generation !== generation) return;
      asset.metadata = message.metadata; asset.surfaces = message.surfaces; dirty = !!message.dirty;
      $('existingMaterial').replaceChildren(...asset.surfaces.map(item => new Option(item.name, item.index)));
      $('existingMaterial').value = String(primitive()?.material ?? '');
      const current = surface();
      $('surfaceInfo').textContent = target ? `Assigned: ${current?.name || 'Default material'}${current?.managed ? ' · shared' : ''}` : 'Pick a surface, or choose one from the list.';
      notice(); controls();
    },
    loaded(message) {
      asset = message.asset; generation = message.generation; editable = !message.revision; dirty = !!message.dirty; variant = message.variant || ''; busy = false;
      library = message.library || { entries: [] }; cache.clear(); rendered = false;
      const folder = $('paletteFolder').value;
      $('paletteFolder').replaceChildren(new Option('All folders', ''), ...[...new Set(library.entries.map(item => item.folder))].filter(Boolean).sort().map(value => new Option(value, value)));
      if ([...$('paletteFolder').options].some(option => option.value === folder)) $('paletteFolder').value = folder;
      const parents = new Map(); asset.metadata.nodes?.forEach((n, ni) => n.children?.forEach(child => parents.set(child, ni)));
      const label = (node, ni) => {
        const names = [node.name || `Node ${ni}`], visited = new Set([ni]);
        while (parents.has(ni) && !visited.has(parents.get(ni))) { ni = parents.get(ni); visited.add(ni); const name = asset.metadata.nodes[ni]?.name; if (name && /-lod[0-3]$/.test(name)) { names.unshift(name); break; } }
        return names.join(' / ');
      };
      $('surfaceTarget').replaceChildren(new Option('Click a surface in the viewport', ''));
      asset.metadata.nodes?.forEach((node, ni) => asset.metadata.meshes?.[node.mesh]?.primitives?.forEach((p, pi) => $('surfaceTarget').add(new Option(`${label(node, ni)} · surface ${pi + 1}`, `${ni}:${pi}`))));
      $('existingMaterial').replaceChildren(...asset.surfaces.map(item => new Option(item.name, item.index)));
      if (target && !primitive()) target = null;
      select(target); renderPalette(); chooseEntry(selectedId);
    },
    palette(message) {
      if (message.generation !== generation || message.request !== request) return;
      for (const entry of message.entries) cache.set(entry.id, entry);
      for (const button of $('paletteGrid').querySelectorAll('button')) { const entry = cache.get(button.dataset.material); if (entry) paintEntry(button, entry); }
      chooseEntry(selectedId);
    }
  };
}
