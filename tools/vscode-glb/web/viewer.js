import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { prepareMaterials, materialFactors, materialSampling, modifyGeometry, applyColors, applyLabel } from './materials.js';
import { displayKeys, viewState } from '../src/view-state.cjs';
import { isHelperGroup } from '../src/stats.cjs';
import { materialEditor } from './editor.js';

const api = typeof acquireVsCodeApi === 'function' ? acquireVsCodeApi() : globalThis.__MM_TEST__?.api;
const $ = id => document.getElementById(id), send = (type, extra = {}) => api.postMessage({ type, ...extra });
const state = { lod: '0', variant: '', projection: 'ortho', shading: 'pbr', wire: false, grid: true, helpers: false, bounds: false, exposure: '1', environment: '1', bloom: false, background: '#202a35', label: '', tab: 'view', syncViews: true, ...api.getState() };
let renderer, composer, camera, controls, asset, gltf, assembly, selected, mixer, editor, playing = false, generation = 0, loadSerial = 0, engineBusy = false, documentDirty = false;
let receivingView = false, viewLoading = false, linkedView, syncPending = false, lastShared = '', lastSharedAt = 0, engineAllowed = false;
const scene = new THREE.Scene(), owned = new Set(), hidden = new Set(), nodes = new Map(), alternate = new Map();
const perspective = new THREE.PerspectiveCamera(40, 1, .1, 1000), ortho = new THREE.OrthographicCamera(-50, 50, 50, -50, .1, 1000);
const selectionBox = new THREE.BoxHelper(undefined, 0x82bdff); selectionBox.visible = false; scene.add(selectionBox);
const modelBox = new THREE.Box3Helper(new THREE.Box3(), 0xadb5c6); modelBox.visible = false; scene.add(modelBox);
const measureLine = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: 0xffcf65, depthTest: false })); measureLine.visible = false; scene.add(measureLine);
let measuring = false, measurePoints = [];
const gridGroup = new THREE.Group(); scene.add(gridGroup);
const grid = new THREE.GridHelper(180, 10, 0x596b83, 0x354455); gridGroup.add(grid);
grid.geometry.computeBoundingSphere();
const hex = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(Array.from({ length: 6 }, (_, i) => new THREE.Vector3(Math.cos(i * Math.PI / 3) * 41.5625, .02, Math.sin(i * Math.PI / 3) * 41.5625))), new THREE.LineBasicMaterial({ color: 0xa0abb9 })); gridGroup.add(hex);
const helperGroup = new THREE.Group(); scene.add(helperGroup);
const hemi = new THREE.HemisphereLight(0xc7ddff, 0x687052, .6); scene.add(hemi);
const sun = new THREE.DirectionalLight(0xfff2dd, 2); sun.position.set(60, 100, 80); scene.add(sun);
let renderPass, bloomPass;
function cameraState() { return { position: camera.position.toArray(), target: controls.target.toArray(), zoom: camera.zoom, span: ortho.userData.span || 50 }; }
function publishView() {
  if (!gltf || viewLoading || receivingView || !state.syncViews) return;
  const shared = viewState({ ...state, camera: cameraState() }); if (!shared) return;
  const text = JSON.stringify(shared); syncPending = false; lastSharedAt = performance.now();
  if (text !== lastShared) { lastShared = text; send('viewState', { state: shared }); }
}
function save(share = true) {
  api.setState(state);
  if (share && !receivingView && !viewLoading) { linkedView = null; $('comparisonNote').hidden = true; publishView(); }
}
function applyLinked(value) {
  const next = viewState(value); if (!next || !state.syncViews) return;
  linkedView = next;
  if (!gltf || viewLoading) return;
  receivingView = true;
  try {
    const projection = state.projection, lod = state.lod, notes = [];
    for (const key of displayKeys) {
      if (key === 'lod' && ![...$('lod').options].some(option => option.value === next.lod)) { notes.push(`LOD ${next.lod} is absent here; keeping LOD ${state.lod}.`); continue; }
      state[key] = next[key]; const control = $(key); if (control.type === 'checkbox') control.checked = next[key]; else control.value = next[key];
    }
    if (state.projection !== projection) switchCamera();
    // Flush local damping before applying a peer's exact pose; peer updates never echo back.
    controls.enableDamping = false; controls.update();
    camera.position.fromArray(next.camera.position); controls.target.fromArray(next.camera.target);
    camera.zoom = next.camera.zoom; ortho.userData.span = next.camera.span; resize(); controls.update(); controls.enableDamping = true;
    if (next.colors?.length === (asset.metadata.extras?.mmColourSlots || []).length) { state.colors = next.colors.slice(); renderColors(); }
    if (state.lod !== lod) clearAssembly();
    applyVisibility(); applyDisplay(); applyLabel(gltf.scene, state.label);
    if (next.variant !== state.variant) {
      if (!next.variant || asset.variants.includes(next.variant)) { state.variant = next.variant; $('variant').value = next.variant; send('variant', { value: next.variant }); }
      else notes.push(`Variant ${next.variant} is absent here; keeping ${state.variant || 'Default'}.`);
    }
    $('comparisonNote').textContent = notes.join(' '); $('comparisonNote').hidden = !notes.length;
    state.camera = cameraState(); save(false); lastShared = JSON.stringify(next); syncPending = false;
  } finally { receivingView = false; }
}
function setStatus(text) { $('status').textContent = text; }
function diagnostic(text) { const p = document.createElement('p'); p.className = 'warning'; p.textContent = text; $('diagnostics').append(p); }
function escapeError(error) { return error?.message || String(error); }
function visible(object) { for (let p = object; p; p = p.parent) if (!p.visible) return false; return true; }
function bounds(root = assembly || gltf?.scene, includeHelpers = false) {
  const box = new THREE.Box3();
  root?.updateWorldMatrix(true, true);
  root?.traverseVisible(object => { if (object.isMesh && (includeHelpers || !object.userData.mmHelper)) { const source = object.isSkinnedMesh || object.isInstancedMesh ? object : object.geometry; source.computeBoundingBox(); box.union(source.boundingBox.clone().applyMatrix4(object.matrixWorld)); } });
  if (box.isEmpty()) box.setFromCenterAndSize(new THREE.Vector3(), new THREE.Vector3(20, 20, 20));
  return box;
}
const clipPoint = new THREE.Vector3(), clipSize = new THREE.Vector3(), clipBox = new THREE.Box3();
function updateBounds() {
  modelBox.box.copy(bounds());
  clipBox.copy(state.helpers ? bounds(undefined, true) : modelBox.box);
  if (helperGroup.visible) clipBox.expandByObject(helperGroup);
}
function updateClipping() {
  if (!gltf) return;
  // Keep depth precision around visible geometry, including when the camera is restored or zoomed.
  // The grid may extend the far plane, but must never pull the near plane towards the camera.
  camera.updateMatrixWorld();
  let closest = Infinity, furthest = -Infinity;
  for (const x of [clipBox.min.x, clipBox.max.x]) for (const y of [clipBox.min.y, clipBox.max.y]) for (const z of [clipBox.min.z, clipBox.max.z]) {
    const depth = -clipPoint.set(x, y, z).applyMatrix4(camera.matrixWorldInverse).z;
    closest = Math.min(closest, depth); furthest = Math.max(furthest, depth);
  }
  const size = clipBox.getSize(clipSize).length(), margin = Math.max(size * .05, .0001);
  const near = Math.max(size * .0001, .00001, closest - margin);
  const far = Math.max(near + margin, furthest + margin, state.grid ? camera.position.length() + grid.geometry.boundingSphere.radius + margin : 0);
  if (camera.near !== near || camera.far !== far) { camera.near = near; camera.far = far; camera.updateProjectionMatrix(); }
}
function fit(root) {
  const box = bounds(root), center = box.getCenter(new THREE.Vector3()), size = box.getSize(new THREE.Vector3());
  const radius = Math.max(size.length() / 2, 1), aspect = camera.aspect || $('viewport').clientWidth / Math.max(1, $('viewport').clientHeight);
  const direction = camera.position.clone().sub(controls.target).normalize(); if (!direction.lengthSq()) direction.set(1, .8, 1).normalize();
  const distance = radius / Math.sin(THREE.MathUtils.degToRad(20)) / Math.min(aspect, 1) * 1.12;
  camera.position.copy(center).addScaledVector(direction, distance); controls.target.copy(center);
  ortho.userData.span = radius * 1.3 / Math.min(aspect, 1); camera.zoom = 1;
  resize(); controls.update();
}
function resize() {
  if (!renderer) return;
  const width = Math.max(1, $('viewport').clientWidth), height = Math.max(1, $('viewport').clientHeight), aspect = width / height;
  perspective.aspect = aspect;
  const span = ortho.userData.span || 50; ortho.left = -span * aspect; ortho.right = span * aspect; ortho.top = span; ortho.bottom = -span;
  perspective.updateProjectionMatrix(); ortho.updateProjectionMatrix(); renderer.setSize(width, height, false); composer?.setSize(width, height);
}
function switchCamera() {
  const old = camera; camera = state.projection === 'ortho' ? ortho : perspective;
  if (old) camera.position.copy(old.position);
  const target = controls?.target.clone() || new THREE.Vector3(); controls?.dispose();
  controls = new OrbitControls(camera, renderer.domElement); controls.target.copy(target); controls.enableDamping = true;
  controls.addEventListener('change', () => { if (!receivingView && !viewLoading) { linkedView = null; syncPending = true; } });
  controls.addEventListener('end', () => { state.camera = cameraState(); save(); });
  if (renderPass) renderPass.camera = camera;
  resize(); controls.update();
}
function disposeLoaded(value, extra = []) {
  const resources = new Set(extra);
  value?.scene.traverse(object => { if (object.geometry) resources.add(object.geometry); for (const m of [object.material, object.mmOriginalMaterial].flat().filter(Boolean)) { resources.add(m); for (const texture of Object.values(m)) if (texture?.isTexture) resources.add(texture); } });
  resources.forEach(item => item.dispose?.());
}
function disposeAsset() {
  mixer?.stopAllAction(); mixer = null; playing = false; clearAssembly();
  if (gltf) { disposeLoaded(gltf, [...owned, ...alternate.values()]); scene.remove(gltf.scene); gltf = null; }
  owned.clear(); alternate.clear(); nodes.clear(); hidden.clear(); selected = null; selectionBox.visible = false;
  helperGroup.traverse(o => { o.geometry?.dispose(); o.material?.dispose(); }); helperGroup.clear();
  modelBox.visible = false; measureLine.visible = false; measurePoints = [];
}
function clearAssembly() { if (assembly) { scene.remove(assembly); assembly = null; } if (gltf) gltf.scene.visible = true; }
function originalName(object) { const index = gltf?.parser.associations.get(object)?.nodes; return asset?.metadata.nodes?.[index]?.name || object.name; }
function isHelper(object) { for (let p = object; p && p !== gltf?.scene; p = p.parent) if (isHelperGroup(originalName(p))) return true; return false; }
function buildNodes() {
  gltf.scene.updateMatrixWorld(true);
  gltf.scene.traverse(object => {
    const index = gltf.parser.associations.get(object)?.nodes;
    if (index !== undefined) nodes.set(index, object);
    if (object.isMesh) {
      let parent = object, node;
      while (parent && node === undefined) { node = gltf.parser.associations.get(parent)?.nodes; parent = parent.parent; }
      const primitive = gltf.parser.associations.get(object)?.primitives ?? 0;
      if (node !== undefined && asset.metadata.meshes?.[asset.metadata.nodes[node]?.mesh]?.primitives[primitive]) object.userData.mmSurface = { node, primitive };
    }
    object.userData.mmHelper = isHelper(object);
    if (object.userData.mmHelper && object.isMesh) {
      const material = new THREE.MeshBasicMaterial({ color: 0x58d8ca, wireframe: true, transparent: true, opacity: .7, depthTest: false }); owned.add(material); object.material = material;
    }
    if (index !== undefined && /^(stand|vehicle|hide)-\d+$/.test(originalName(object))) {
      const arrow = new THREE.ArrowHelper(new THREE.Vector3(0, 0, -1).transformDirection(object.matrixWorld), object.getWorldPosition(new THREE.Vector3()), 6, 0xffbf72, 1.5, .8); helperGroup.add(arrow);
    }
  });
  renderParts();
}
function applyVisibility() {
  if (!gltf) return;
  gltf.scene.traverse(object => {
    if (object === gltf.scene) return;
    const lod = originalName(object)?.match(/-lod([0-3])$/);
    object.visible = !hidden.has(object.uuid) && (!lod || state.lod === 'all' || lod[1] === state.lod) && (!object.userData.mmHelper || state.helpers);
  });
  helperGroup.visible = state.helpers && !assembly; gridGroup.visible = state.grid;
  if (selected) selectionBox.visible = visible(selected);
  updateStats();
}
function updateStats() {
  if (!gltf) return;
  let meshes = 0, triangles = 0;
  (assembly || gltf.scene).traverseVisible(object => { if (object.isMesh && !object.userData.mmHelper) { meshes++; triangles += (object.geometry.index?.count || object.geometry.attributes.position.count) / 3; } });
  updateBounds(); const size = modelBox.box.getSize(new THREE.Vector3()); modelBox.visible = state.bounds;
  $('summary').textContent = `${Math.round(triangles).toLocaleString()} triangles · ${meshes} meshes`;
  setStatus(`${assembly ? 'Engine assembly' : 'Authored GLB'} · ${size.x.toFixed(1)} × ${size.z.toFixed(1)} × ${size.y.toFixed(1)} (E–W × N–S × height) · ${asset.surfaces.length} materials`);
  if (globalThis.__MM_TEST__) globalThis.__MM_TEST__.stats = { meshes, triangles, size: size.toArray(), assembled: !!assembly, nodes: nodes.size, loaded: true, materials: gltf.parser, scene: gltf.scene };
}
function applyDisplay() {
  if (!gltf) return;
  const materialFor = object => {
    if (object.userData.mmHelper) return object.material;
    const source = object.mmOriginalMaterial;
    if (state.shading === 'pbr') { source.wireframe = state.wire; return source; }
    const key = `${source.uuid}:${state.shading}`;
    if (!alternate.has(key)) {
      const options = { side: source.side, alphaTest: source.alphaTest, map: source.map };
      const mat = state.shading === 'normal' ? new THREE.MeshNormalMaterial({ side: source.side }) : state.shading === 'clay' ? new THREE.MeshStandardMaterial({ ...options, color: 0xadb9c8, map: null, roughness: .7, metalness: 0 }) : new THREE.ShaderMaterial({ side: source.side, vertexShader: 'varying vec2 mmUv; void main(){ mmUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }', fragmentShader: state.shading === 'checker' ? 'varying vec2 mmUv; void main(){ vec2 tile=fract(mmUv), cell=floor(mmUv*8.); vec3 c=mix(vec3(.16),vec3(.8),mod(cell.x+cell.y,2.)); c*=vec3(.7+.3*tile.x,.7+.3*tile.y,1.); if(min(min(tile.x,1.-tile.x),min(tile.y,1.-tile.y))<.015)c=vec3(.9,.2,.06); gl_FragColor=vec4(c,1.); }' : 'varying vec2 mmUv; void main(){ gl_FragColor=vec4(fract(mmUv),0.3,1.); }' });
      alternate.set(key, mat);
    }
    const material = alternate.get(key); material.wireframe = state.wire; return material;
  };
  for (const root of [gltf.scene, assembly].filter(Boolean)) root.traverse(o => { if (o.isMesh) o.material = materialFor(o); });
  scene.background = new THREE.Color(state.background); scene.environmentIntensity = Number(state.environment); renderer.toneMappingExposure = Number(state.exposure); bloomPass.enabled = state.bloom;
}
function selectObject(object) {
  selected = object; selectionBox.visible = !!object && visible(object);
  editor?.pick(!assembly ? object?.userData.mmSurface || null : null);
  if (object) {
    selectionBox.setFromObject(object);
    const index = gltf.parser.associations.get(object)?.nodes;
    let vertices = 0, triangles = 0, primitives = 0; const geometries = new Set();
    object.traverse(o => { if (o.isMesh) { primitives++; triangles += (o.geometry.index?.count || o.geometry.attributes.position.count) / 3; if (!geometries.has(o.geometry)) { vertices += o.geometry.index ? new Set(o.geometry.index.array).size : o.geometry.attributes.position.count; geometries.add(o.geometry); } } });
    $('selectionInfo').textContent = JSON.stringify({ vertices, triangles, primitives, node: index === undefined ? originalName(object) : asset.metadata.nodes[index] }, null, 2);
  } else $('selectionInfo').textContent = '';
  renderParts();
}
function previewMaterial(message) {
  if (!gltf || message.generation !== generation) return;
  asset.metadata = message.metadata; asset.surfaces = message.surfaces;
  const updates = new Map(message.updates.map(update => [`${update.node}:${update.primitive}`, update]));
  gltf.scene.traverse(object => {
    const target = object.userData.mmSurface, update = target && updates.get(`${target.node}:${target.primitive}`);
    if (!update) return;
    object.userData.mmMaterial = update.material;
    if (!object.userData.mmLiveMaterial) {
      const source = object.mmOriginalMaterial, material = source.clone();
      material.onBeforeCompile = source.onBeforeCompile; material.customProgramCacheKey = source.customProgramCacheKey;
      owned.add(material); object.mmOriginalMaterial = material; object.userData.mmLiveMaterial = true;
    }
    materialFactors(object.mmOriginalMaterial, asset.surfaces[update.material]);
    if (update.sampling) materialSampling(object.mmOriginalMaterial, update.sampling, owned);
    if (update.uv) {
      const values = new Float32Array(Uint8Array.from(atob(update.uv), char => char.charCodeAt(0)).buffer);
      const uv = object.geometry.attributes.uv;
      if (uv && !uv.isInterleavedBufferAttribute && uv.array instanceof Float32Array && !uv.normalized && uv.array.length === values.length) { uv.array.set(values); uv.needsUpdate = true; }
      else object.geometry.setAttribute('uv', new THREE.Float32BufferAttribute(values, 2));
      object.geometry.deleteAttribute('tangent');
    }
    if (update.color !== undefined) {
      const width = update.color?.width || 3;
      const values = update.color ? new Float32Array(Uint8Array.from(atob(update.color.data), char => char.charCodeAt(0)).buffer) : new Float32Array(object.geometry.attributes.position.count * width).fill(1);
      const color = object.geometry.attributes.color;
      if (color && color.itemSize === width && color.array.length === values.length) { color.array.set(values); color.needsUpdate = true; }
      else object.geometry.setAttribute('color', new THREE.Float32BufferAttribute(values, width));
      object.geometry.userData.originalColors = values.slice();
      object.mmOriginalMaterial.vertexColors = !!update.color; object.mmOriginalMaterial.needsUpdate = true;
    }
    for (const [key, material] of alternate) if (key.startsWith(object.mmOriginalMaterial.uuid + ':')) { material.dispose(); alternate.delete(key); }
  });
  applyColors(gltf.scene, asset.metadata.extras?.mmColourSlots || [], state.colors || []);
  clearAssembly(); applyVisibility(); applyDisplay(); renderMaterials();
  documentDirty = !!message.dirty; editor.preview(message);
  $('build').disabled = $('test').disabled = !engineAllowed || engineBusy || documentDirty;
  $('engineStatus').textContent = 'Material edited; save the GLB before testing in the engine.';
}
function renderParts() {
  $('partList').replaceChildren(); const filter = $('partSearch').value.toLowerCase();
  for (const [index, object] of nodes) {
    const name = originalName(object) || `Node ${index}`; if (!name.toLowerCase().includes(filter)) continue;
    const row = document.createElement('div'); row.className = `node${selected === object ? ' selected' : ''}`;
    const check = document.createElement('input'); check.type = 'checkbox'; check.checked = !hidden.has(object.uuid); check.setAttribute('aria-label', `Show ${name}`);
    check.onchange = () => { check.checked ? hidden.delete(object.uuid) : hidden.add(object.uuid); clearAssembly(); applyVisibility(); };
    const button = document.createElement('button'); button.textContent = name; button.title = name; button.onclick = () => selectObject(object); button.ondblclick = () => fit(object);
    const solo = document.createElement('button'); solo.textContent = 'Solo'; solo.className = 'solo'; solo.onclick = () => { clearAssembly(); gltf.scene.traverse(o => { if (o.isMesh) { let related = false; for (let p = o; p; p = p.parent) if (p === object) related = true; related ? hidden.delete(o.uuid) : hidden.add(o.uuid); } }); applyVisibility(); fit(object); renderParts(); };
    row.append(check, button, solo); $('partList').append(row);
  }
}
function renderMaterials() {
  const list = $('materialList'), chosen = list.value, query = $('materialSearch').value.toLowerCase(); list.replaceChildren();
  for (const surface of asset.surfaces) if (surface.name.toLowerCase().includes(query)) { const option = new Option(`${surface.name}${surface.managed ? ' · shared' : ''}`, surface.index); list.add(option); }
  if ([...list.options].some(o => o.value === chosen)) list.value = chosen; else list.selectedIndex = 0;
  showMaterial();
}
function openButton(file, title) { const b = document.createElement('button'); b.textContent = title || file; b.title = file; b.onclick = () => send('openDependency', { file }); return b; }
function showMaterial() {
  const host = $('materialDetail'); host.replaceChildren(); const surface = asset?.surfaces[Number($('materialList').value)]; if (!surface) return;
  const title = document.createElement('h3'); title.textContent = surface.name; host.append(title);
  const description = document.createElement('p'); description.className = 'muted'; description.textContent = surface.managed ? 'Shared Material Maker / Godot material' : 'GLB material (embedded or ordinary external textures)'; host.append(description);
  if (surface.managed) host.append(openButton(surface.managed.file, 'Open .tres'));
  const maps = document.createElement('div'); maps.className = 'maps'; host.append(maps);
  const entries = surface.managed ? Object.entries(surface.managed.maps) : [];
  for (const [role, map] of entries) { const card = document.createElement('div'); card.className = 'map'; const label = document.createElement('p'); label.textContent = role; const img = document.createElement('img'); img.src = map.url; img.alt = `${role} map`; card.append(label, img, openButton(map.file, 'Open map')); maps.append(card); }
  // Embedded maps are also inspectable, without extracting or writing them to the repository.
  const material = [...nodes.values()].flatMap(n => { const found = []; n.traverse(o => { if (o.isMesh && o.userData.mmMaterial === surface.index) found.push(o.mmOriginalMaterial); }); return found; })[0];
  for (const [role, key] of [['GLB albedo', 'map'], ['GLB normal', 'normalMap'], ['GLB emission', 'emissiveMap']]) {
    if (surface.managed) break;
    const image = material?.[key]?.image; if (!image) continue;
    const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
    try { canvas.getContext('2d').drawImage(image, 0, 0); const card = document.createElement('div'); card.className = 'map'; const img = document.createElement('img'); img.src = canvas.toDataURL(); img.alt = role; const label = document.createElement('p'); label.textContent = role; card.append(label, img); maps.append(card); } catch { /* Diagnostics already list missing images. */ }
  }
  const details = document.createElement('pre'); details.textContent = JSON.stringify(surface.managed ? { roughness: surface.managed.roughness, metallic: surface.managed.metallic, normalScale: surface.managed.normalScale, emissionEnergy: surface.managed.emissionEnergy, channels: surface.managed.channels, gltf: surface.gltf } : surface.gltf, null, 2); host.append(details);
}
function renderColors() {
  const slots = asset.metadata.extras?.mmColourSlots || []; $('colours').replaceChildren();
  if (!slots.length) return;
  const heading = document.createElement('h2'); heading.textContent = 'Colour slots'; $('colours').append(heading);
  state.colors = state.colors?.length === slots.length ? state.colors : slots.map(s => s.colour);
  slots.forEach((slot, index) => {
    const label = document.createElement('label'); label.textContent = slot.name; const input = document.createElement('input'); input.type = 'color'; input.value = state.colors[index]; input.setAttribute('aria-label', slot.name);
    const change = value => { input.value = value; state.colors[index] = value; applyColors(gltf.scene, slots, state.colors); save(); };
    input.oninput = () => change(input.value); label.append(input); $('colours').append(label);
    const presets = document.createElement('div'); presets.className = 'swatches';
    for (const [name, color] of [['Default', slot.colour], ...(slot.presets || [])]) { const button = document.createElement('button'); button.title = name; button.className = 'swatch'; button.setAttribute('aria-label', `${slot.name}: ${name}`); const swatch = document.createElement('input'); swatch.type = 'color'; swatch.value = color; swatch.tabIndex = -1; button.append(swatch); button.onclick = () => change(color); presets.append(button); }
    $('colours').append(presets);
  });
  applyColors(gltf.scene, slots, state.colors);
}
function renderStats() {
  const table = document.createElement('table'); table.innerHTML = '<thead><tr><th>LOD</th><th>Vertices</th><th>Tris</th><th>Prims</th></tr></thead>';
  const body = document.createElement('tbody'); table.append(body);
  for (const row of asset.statistics.rows) {
    const tr = document.createElement('tr'); tr.title = `${row.meshes} mesh instances · ${row.materials} materials · ${row.nodes} nodes`;
    for (const value of [row.name, row.vertices, row.triangles, row.primitives]) { const td = document.createElement('td'); td.textContent = typeof value === 'number' ? value.toLocaleString() : value; tr.append(td); }
    if (row.name.startsWith('LOD ')) { tr.tabIndex = 0; tr.setAttribute('role', 'button'); const choose = () => { state.lod = row.name.slice(4); $('lod').value = state.lod; clearAssembly(); applyVisibility(); fit(); save(); }; tr.onclick = choose; tr.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choose(); } }; }
    body.append(tr);
  }
  const info = document.createElement('p'); info.className = 'muted'; info.textContent = `${(asset.statistics.fileBytes / 1024).toFixed(1)} KiB · ${asset.statistics.images} images (${asset.statistics.embeddedImages} embedded)`;
  $('lodStats').replaceChildren(table, info);
}
async function load(message) {
  viewLoading = true;
  const serial = ++loadSerial; generation = message.generation;
  const oldCamera = gltf ? { position: camera.position.clone(), target: controls.target.clone(), zoom: camera.zoom } : null;
  disposeAsset(); const nextAsset = message.asset; asset = nextAsset; state.variant = message.variant || ''; $('diagnostics').replaceChildren(); $('filename').textContent = asset.name;
  $('revision').textContent = asset.revision || 'Working copy'; $('workingCopy').hidden = !message.revision;
  $('metadata').textContent = JSON.stringify({ extras: asset.metadata.extras, descriptors: asset.descriptors, extensions: asset.metadata.extensionsUsed }, null, 2);
  $('dependencies').replaceChildren(...asset.dependencies.map(file => openButton(file)));
  asset.diagnostics.forEach(diagnostic); $('enginePath').textContent = message.engine || 'Engine checkout not found. Use Settings to choose one.';
  engineAllowed = message.trusted && !message.revision; documentDirty = !!message.dirty;
  $('build').disabled = $('test').disabled = !engineAllowed || engineBusy || documentDirty;
  if (!message.trusted) $('engineStatus').textContent = 'Trust the workspace to run engine tests. Viewing remains available.';
  let loaded; const resources = new Set();
  try {
    const loader = new GLTFLoader();
    loaded = await loader.parseAsync(JSON.stringify(nextAsset.document), '');
    if (serial !== loadSerial) { disposeLoaded(loaded); return; }
    await prepareMaterials(loaded, nextAsset, resources, text => { if (serial === loadSerial) diagnostic(text); });
    if (serial !== loadSerial) { disposeLoaded(loaded, resources); return; }
    await modifyGeometry(loaded, nextAsset, resources);
    if (serial !== loadSerial) { disposeLoaded(loaded, resources); return; }
    gltf = loaded; resources.forEach(r => owned.add(r));
    scene.add(gltf.scene); buildNodes();
    const lods = [...new Set([...nodes.values()].map(o => originalName(o)?.match(/-lod([0-3])$/)?.[1]).filter(Boolean))].sort();
    $('lod').replaceChildren(...lods.map(level => new Option(`LOD ${level}`, level)), new Option('All authored groups', 'all'));
    if (!lods.includes(state.lod)) state.lod = lods[0] || 'all'; $('lod').value = state.lod;
    $('variant').replaceChildren(new Option('Default', ''), ...asset.variants.map(v => new Option(v, v))); $('variant').value = state.variant;
    $('labelSection').hidden = !asset.surfaces.some(s => s.gltf.extras?.mmLabel);
    renderColors(); renderStats(); applyLabel(gltf.scene, state.label); applyVisibility(); applyDisplay(); renderMaterials();
    $('animationSection').hidden = !gltf.animations.length;
    $('animation').replaceChildren(...gltf.animations.map((clip, i) => new Option(clip.name || `Animation ${i + 1}`, i)));
    if (gltf.animations.length) mixer = new THREE.AnimationMixer(gltf.scene);
    if (oldCamera) { camera.position.copy(oldCamera.position); controls.target.copy(oldCamera.target); camera.zoom = oldCamera.zoom; camera.updateProjectionMatrix(); }
    else if (state.camera) { camera.position.fromArray(state.camera.position); controls.target.fromArray(state.camera.target); camera.zoom = state.camera.zoom; ortho.userData.span = state.camera.span; resize(); }
    else fit();
    controls.update(); $('overlay').textContent = ''; $('engineStatus').textContent = message.revision ? 'Open the working copy to run engine tests. This view shows the Git revision and its materials.' : !message.trusted ? 'Trust the workspace to run engine tests.' : 'No engine test run for this version.';
    viewLoading = false; save(false); updateStats(); editor.loaded(message);
    if (documentDirty) $('engineStatus').textContent = 'Save the GLB before running engine tests.';
    if (linkedView) applyLinked(linkedView); else publishView();
    globalThis.__MM_TEST__?.loaded?.();
  } catch (error) { if (gltf === loaded) disposeAsset(); else disposeLoaded(loaded, resources); if (serial === loadSerial) { viewLoading = false; $('overlay').textContent = `Cannot display this GLB\n${escapeError(error)}`; diagnostic(escapeError(error)); setStatus('Load failed — see Info'); globalThis.__MM_TEST__?.failed?.(escapeError(error)); } }
}
function showAssembly(message) {
  clearAssembly(); $('engineStatus').textContent = `PASS: ${message.result.summary}`;
  if (message.kind === 'RIGID') { state.lod = String(message.result.lod); $('lod').value = state.lod; applyVisibility(); fit(); return; }
  const group = new THREE.Group(), toY = new THREE.Matrix4().makeRotationX(-Math.PI / 2), toZ = toY.clone().invert();
  gltf.scene.updateMatrixWorld(true);
  for (const placement of message.result.instances) {
    const source = [...nodes.values()].find(node => originalName(node) === placement.node);
    if (!source) throw Error(`Engine returned an unknown node: ${placement.node}`);
    const copy = source.clone(true), originals = [], copies = [];
    source.traverse(o => originals.push(o)); copy.traverse(o => copies.push(o));
    copies.forEach((o, i) => { o.mmOriginalMaterial = originals[i].mmOriginalMaterial; });
    copy.visible = true; copy.matrixAutoUpdate = false;
    copy.matrix.copy(toY).multiply(new THREE.Matrix4().fromArray(placement.matrix)).multiply(toZ).multiply(source.matrixWorld); group.add(copy);
  }
  assembly = group; scene.add(group); gltf.scene.visible = false; selectObject(null); helperGroup.visible = false; applyDisplay(); fit(); updateStats();
}
function tab(name) { state.tab = name; document.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === name)); document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.id === `tab-${name}`)); editor?.tab(name); save(); }
function bind() {
  $('syncViews').checked = state.syncViews;
  $('syncViews').onchange = () => { state.syncViews = $('syncViews').checked; lastShared = ''; save(); };
  $('workingCopy').onclick = () => send('workingCopy');
  for (const id of ['lod', 'projection', 'shading', 'wire', 'grid', 'helpers', 'bounds', 'exposure', 'environment', 'bloom', 'background', 'label']) {
    const control = $(id); if (control.type === 'checkbox') control.checked = state[id]; else control.value = state[id];
    control.addEventListener('input', () => {
      state[id] = control.type === 'checkbox' ? control.checked : control.value; save();
      if (id === 'projection') { switchCamera(); fit(); }
      else if (id === 'lod') { clearAssembly(); applyVisibility(); }
      else if (['helpers', 'grid'].includes(id)) applyVisibility();
      else if (id === 'bounds') updateStats();
      else if (id === 'label') { if (gltf) applyLabel(gltf.scene, state.label); }
      else applyDisplay();
    });
  }
  $('variant').onchange = () => { state.variant = $('variant').value; save(); send('variant', { value: state.variant }); };
  document.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => tab(b.dataset.tab)); tab(state.tab);
  $('fit').onclick = () => fit(); $('reload').onclick = () => send('reload'); $('settings').onclick = () => send('settings'); $('logs').onclick = () => send('logs'); $('build').onclick = () => send('build');
  $('inspectorToggle').onclick = () => { $('inspector').hidden = !$('inspector').hidden; $('inspectorToggle').setAttribute('aria-expanded', !$('inspector').hidden); resize(); };
  document.querySelectorAll('[data-camera]').forEach(b => b.onclick = () => { const directions = { iso: [1, .8, 1], front: [0, 0, -1], side: [1, 0, 0], top: [0, 1, .00001] }; camera.position.copy(controls.target).add(new THREE.Vector3(...directions[b.dataset.camera])); fit(); });
  $('partSearch').oninput = renderParts; $('materialSearch').oninput = renderMaterials; $('materialList').onchange = showMaterial;
  $('showAll').onclick = () => { hidden.clear(); clearAssembly(); applyVisibility(); renderParts(); }; $('clearSelection').onclick = () => selectObject(null);
  $('authored').onclick = () => { clearAssembly(); applyVisibility(); fit(); };
  $('measure').onclick = () => { measuring = !measuring; measurePoints = []; measureLine.visible = false; $('measure').textContent = measuring ? 'Cancel measurement' : 'Measure two points'; $('measurement').textContent = measuring ? 'Click two points on the visible model.' : ''; };
  $('screenshot').onclick = () => { updateClipping(); composer.render(); send('screenshot', { data: renderer.domElement.toDataURL('image/png') }); };
  document.querySelectorAll('[data-preset]').forEach(b => b.onclick = () => { const enabled = ({ none: [], straight: [0, 3], corner: [0, 1], all: [0, 1, 2, 3, 4, 5] })[b.dataset.preset]; document.querySelectorAll('[data-reach]').forEach((input, i) => input.value = enabled.includes(i) ? $('height').value : 0); });
  $('test').onclick = () => send('test', { generation, settings: { kind: $('kind').value, lod: Number(state.lod === 'all' ? 0 : state.lod), height: Number($('height').value), reach: [...document.querySelectorAll('[data-reach]')].map(i => Number(i.value)), rotation: Number($('rotation').value), seed: Number($('seed').value) } });
  $('play').onclick = () => { if (!mixer) return; playing = !playing; if (playing) { mixer.stopAllAction(); mixer.clipAction(gltf.animations[Number($('animation').value)]).play(); } };
  $('animation').onchange = () => { if (mixer) { mixer.stopAllAction(); if (playing) mixer.clipAction(gltf.animations[Number($('animation').value)]).play(); } };
  $('canvas').onkeydown = event => { if (event.key.toLowerCase() === 'f') fit(); };
  let down;
  $('canvas').addEventListener('pointerdown', e => down = [e.clientX, e.clientY]);
  $('canvas').addEventListener('pointerup', e => {
    if (!gltf || e.button !== 0 || !down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;
    const rect = $('canvas').getBoundingClientRect(), pointer = new THREE.Vector2((e.clientX - rect.left) / rect.width * 2 - 1, 1 - (e.clientY - rect.top) / rect.height * 2), ray = new THREE.Raycaster(); ray.setFromCamera(pointer, camera);
    const hit = ray.intersectObject(assembly || gltf.scene, true).find(i => i.object.isMesh && visible(i.object));
    if (hit && measuring) {
      measurePoints.push(hit.point.clone());
      if (measurePoints.length === 2) { const delta = measurePoints[1].clone().sub(measurePoints[0]); measureLine.geometry.dispose(); measureLine.geometry = new THREE.BufferGeometry().setFromPoints(measurePoints); measureLine.visible = true; $('measurement').textContent = `${delta.length().toFixed(3)} model units · ΔE ${delta.x.toFixed(2)}, ΔN ${(-delta.z).toFixed(2)}, Δheight ${delta.y.toFixed(2)}`; measuring = false; $('measure').textContent = 'Measure two points'; }
      else $('measurement').textContent = 'Choose the second point.';
    } else if (hit) {
      if (state.tab !== 'parts' && !assembly) { selectObject(hit.object); if (state.tab !== 'palette') tab('materials'); }
      else { let object = hit.object; while (object.parent && gltf.parser.associations.get(object)?.nodes === undefined && object.parent !== gltf.scene) object = object.parent; selectObject(object); tab('parts'); }
    }
  });
}
try {
  renderer = new THREE.WebGLRenderer({ canvas: $('canvas'), antialias: true, alpha: false }); renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); renderer.toneMapping = THREE.ACESFilmicToneMapping;
  const environment = new RoomEnvironment(); const pmrem = new THREE.PMREMGenerator(renderer); const target = pmrem.fromScene(environment, .04); scene.environment = target.texture; pmrem.dispose(); environment.dispose();
  perspective.position.set(120, 90, 120); ortho.position.copy(perspective.position); switchCamera();
  composer = new EffectComposer(renderer); renderPass = new RenderPass(scene, camera); bloomPass = new UnrealBloomPass(new THREE.Vector2(1, 1), .3, .4, 1); composer.addPass(renderPass); composer.addPass(bloomPass); composer.addPass(new OutputPass());
  editor = materialEditor({ send, showTab: tab,
    previewMode: mode => { state.shading = mode; $('shading').value = mode; applyDisplay(); save(); },
    paintSwatches: target => {
      let object; gltf?.scene.traverse(o => { if (o.userData.mmSurface?.node === target.node && o.userData.mmSurface?.primitive === target.primitive) object = o; });
      if (!object) return [];
      const colors = object.geometry.userData.authoredPaint, groups = new Map();
      const used = object.geometry.index ? new Set(object.geometry.index.array) : Array.from({ length: colors.count }, (_, i) => i);
      for (const i of used) {
        const rgb = [0, 1, 2].map(c => colors.getComponent(i, c)), peak = Math.max(...rgb, .000001), key = rgb.map(n => Math.round(n / peak * 8)).join(':');
        const group = groups.get(key) || { count: 0, peak: -1 }; group.count++; if (peak > group.peak) { group.rgb = rgb; group.peak = peak; } groups.set(key, group);
      }
      return [...groups.values()].sort((a, b) => b.count - a.count).slice(0, 12).map(group => group.rgb);
    },
    inspectMaterial: index => { $('materialSearch').value = ''; renderMaterials(); $('materialList').value = String(index); showMaterial(); },
    selectSurface: target => {
      let object; gltf?.scene.traverse(o => { if (o.userData.mmSurface?.node === target.node && o.userData.mmSurface?.primitive === target.primitive) object = o; });
      if (!object) return;
      clearAssembly();
      for (let parent = object; parent; parent = parent.parent) { hidden.delete(parent.uuid); const lod = originalName(parent)?.match(/-lod([0-3])$/); if (lod && state.lod !== 'all') { state.lod = lod[1]; $('lod').value = state.lod; } }
      applyVisibility(); selectObject(object);
    }
  });
  // Composer is initialized after controls; now size both.
  resize(); bind(); new ResizeObserver(resize).observe($('viewport'));
  let previous = performance.now(); renderer.setAnimationLoop(now => { const delta = Math.min((now - previous) / 1000, .1); previous = now; controls.update(); if (playing) { mixer?.update(delta); updateBounds(); } if (selected && selectionBox.visible) selectionBox.setFromObject(selected); updateClipping(); composer.render(); if (syncPending && now - lastSharedAt >= 50) publishView(); });
  window.addEventListener('message', event => {
    const message = event.data;
    if (message.type === 'asset') load(message);
    else if (message.type === 'linkedView') applyLinked(message.state);
    else if (message.type === 'loading') { editor.loading(); viewLoading = true; loadSerial++; clearAssembly(); $('overlay').textContent = 'Reading model and materials…'; $('engineStatus').textContent = 'Asset changed; previous engine test invalidated.'; }
    else if (message.type === 'palettePage') editor.palette(message);
    else if (message.type === 'materialPreview') previewMaterial(message);
    else if (message.type === 'editStatus') { documentDirty = !!message.dirty; editor.status(message); $('build').disabled = $('test').disabled = !engineAllowed || engineBusy || documentDirty; }
    else if (message.type === 'error') { loadSerial++; disposeAsset(); $('overlay').textContent = message.message; setStatus('Load failed'); globalThis.__MM_TEST__?.failed?.(message.message); }
    else if (message.type === 'engineBusy') { engineBusy = true; clearAssembly(); applyVisibility(); $('build').disabled = $('test').disabled = true; $('engineStatus').textContent = message.message; }
    else if (message.type === 'engineIdle') { engineBusy = false; $('build').disabled = $('test').disabled = !engineAllowed || documentDirty; }
    else if (message.type === 'engineResult') { if (message.error) { clearAssembly(); applyVisibility(); } $('engineStatus').textContent = (message.error ? 'FAIL: ' : '') + message.message; }
    else if (message.type === 'assembly') { try { showAssembly(message); } catch (error) { clearAssembly(); applyVisibility(); $('engineStatus').textContent = 'FAIL: ' + escapeError(error); } }
  });
  send('ready', { variant: state.variant });
} catch (error) { $('overlay').textContent = `Viewer initialization failed: ${escapeError(error)}`; globalThis.__MM_TEST__?.failed?.(escapeError(error)); }
