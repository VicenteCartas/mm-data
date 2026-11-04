import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import { createRequire } from 'node:module';
import { MirroredRepeatWrapping, ClampToEdgeWrapping, LinearMipmapNearestFilter, NearestFilter } from 'three';
const require = createRequire(import.meta.url);
const { html } = require('../src/html.cjs'), { loadAsset, findRoots } = require('../src/assets.cjs'), { findEngine, preview } = require('../src/engine.cjs');
const { depthFixture } = require('./depth-fixture.cjs');
const { GlbDocument } = require('../src/document.cjs'), { materialPreview } = require('../src/material-preview.cjs');
const { readGlb } = require('../src/assets.cjs'), { readAttribute } = require('../src/attributes.cjs');
const { gitFixture } = require('./git-fixture.cjs'), { gitSource } = require('../src/git-source.cjs');
const extension = path.resolve(import.meta.dirname, '..'), dataRoot = path.resolve(extension, '../..');
const output = path.join(extension, 'test-output'); await fs.mkdir(output, { recursive: true });
let origin, current = 'buildings/walls/medium/straight.glb', variant = '', page, generation = 0, peer, relay = false, comparison;
let editingDocument, editingAsset;
const resources = new Map(), errors = [], consoleErrors = [];
const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, origin);
    if (url.pathname === '/favicon.ico') { res.statusCode = 204; return res.end(); }
    if (url.pathname === '/') { res.setHeader('Content-Type', 'text/html'); return res.end(html({ cspSource: origin, nonce: 'browser-test', script: `${origin}/viewer.js`, style: `${origin}/viewer.css` })); }
    const file = url.pathname === '/viewer.js' ? path.join(extension, 'dist/viewer.js') : url.pathname === '/viewer.css' ? path.join(extension, 'dist/viewer.css') : resources.get(url.pathname);
    if (!file) { res.statusCode = 404; return res.end(); }
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : file.endsWith('.jpg') ? 'image/jpeg' : 'image/png'); res.setHeader('Cache-Control', 'no-store'); res.end(await fs.readFile(file));
  } catch (error) { res.statusCode = 500; res.end(error.message); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); origin = `http://127.0.0.1:${server.address().port}`;
const engine = await findEngine('', dataRoot);
async function deliver(bytes) {
  const file = path.join(dataRoot, 'data/models', current), roots = await findRoots(file);
  bytes ||= await fs.readFile(file);
  const asset = await loadAsset(file, roots, p => { const key = `/asset/${resources.size}`; resources.set(key, p); return origin + key; }, variant, undefined, bytes);
  editingDocument = new GlbDocument(file, bytes); editingAsset = asset;
  await page.evaluate(message => window.postMessage(message, '*'), { type: 'asset', asset, generation: ++generation, variant, engine, trusted: true });
  return asset;
}
const browser = await chromium.launch({ channel: 'msedge', headless: true, args: ['--disable-gpu-sandbox'] });
function mockApi() {
  let state;
  window.__MM_TEST__ = { count: 0, failures: [], sent: 0, api: {
    postMessage: m => {
      if (m.type === 'screenshot') window.__MM_TEST__.screenshot = m.data;
      if (m.type === 'viewState') { window.__MM_TEST__.shared = m.state; window.__MM_TEST__.sharedAt = Date.now(); window.__MM_TEST__.sent++; }
      return window.mmMessage(m);
    }, getState: () => state, setState: v => state = v
  }, loaded() { this.count++; }, failed(error) { this.failures.push(error); } };
}
try {
  page = await browser.newPage({ viewport: { width: 1280, height: 850 } });
  page.on('pageerror', error => errors.push(error.message)); page.on('console', message => { if (message.type() === 'error' && !message.text().includes('favicon')) consoleErrors.push(message.text()); });
  await page.exposeFunction('mmMessage', async message => {
    try {
      if (message.type === 'viewState' && relay) await peer.evaluate(state => window.postMessage({ type: 'linkedView', state }, '*'), message.state);
      if (['ready', 'reload'].includes(message.type)) await deliver();
      if (message.type === 'variant') { variant = message.value; await deliver(); }
      if (message.type === 'endMaterialEdit') editingDocument.endEdit();
      if (message.type === 'materialEdit' && message.live) {
        const primitive = editingAsset.metadata.meshes[editingAsset.metadata.nodes[message.edit.target.node].mesh].primitives[message.edit.target.primitive];
        editingDocument.edit(message.edit, { group: message.gesture, managed: !!editingAsset.surfaces[primitive.material]?.managed });
        const update = materialPreview(editingDocument.bytes, message.edit, editingAsset);
        editingAsset.metadata = update.metadata; editingAsset.surfaces = update.surfaces;
        await page.evaluate(message => window.postMessage(message, '*'), { type: 'materialPreview', ...update, generation, dirty: editingDocument.dirty });
      }
      if (message.type === 'test') {
        await page.evaluate(() => window.postMessage({ type: 'engineBusy', message: 'Testing…' }, '*'));
        const result = await preview(engine, { ...message.settings, model: path.join(dataRoot, 'data/models', current), modelsRoot: path.join(dataRoot, 'data/models') });
        await page.evaluate(msg => { window.postMessage(msg, '*'); window.postMessage({ type: 'engineIdle' }, '*'); }, { type: 'assembly', kind: message.settings.kind, result });
      }
      if (message.type === 'screenshot') await fs.writeFile(path.join(output, 'exported-preview.png'), Buffer.from(message.data.split(',')[1], 'base64'));
    } catch (error) { errors.push(error.message); }
  });
  await page.addInitScript(mockApi);
  async function ready(expected) { await page.waitForFunction(n => window.__MM_TEST__.count >= n || window.__MM_TEST__.failures.length, expected, { timeout: 45000 }); assert.deepEqual(await page.evaluate(() => window.__MM_TEST__.failures), []); }
  await page.goto(origin); await ready(1);
  assert(await page.locator('#lodStats tbody tr').count() >= 1);
  const liveCanvas = await page.locator('#canvas').boundingBox();
  await page.locator('#canvas').click({ position: { x: liveCanvas.width * .5, y: liveCanvas.height * .55 } });
  assert(await page.locator('#tab-materials').evaluate(element => element.classList.contains('active')), 'Picking a surface must reveal its material controls');
  await page.locator('#surfaceTarget').selectOption('0:0');
  const start = await page.evaluate(() => {
    const test = window.__MM_TEST__; test.liveMeshes = [];
    test.stats.scene.traverse(object => { if (object.isMesh) test.liveMeshes.push(object); });
    test.liveMesh = test.liveMeshes.find(object => object.userData.mmSurface?.node === 0 && object.userData.mmSurface?.primitive === 0);
    test.untouched = test.liveMeshes.filter(object => object !== test.liveMesh).map(object => ({ color: object.mmOriginalMaterial.color.toArray(), uv: Array.from(object.geometry.attributes.uv?.array || []) }));
    return { uv: Array.from(test.liveMesh.geometry.attributes.uv.array), camera: test.shared.camera };
  });
  await page.locator('#uvOffsetU').fill('.25'); await page.locator('#uvOffsetV').fill('-.5');
  await page.locator('#uvScaleU').fill('2'); await page.locator('#uvScaleV').fill('3'); await page.locator('#uvRotation').fill('90');
  const expected = [-3 * (start.uv[1] - .5) + .75, 2 * (start.uv[0] - .5)];
  await page.waitForFunction(expected => { const uv = window.__MM_TEST__.liveMesh.geometry.attributes.uv; return Math.abs(uv.getX(0) - expected[0]) < .00001 && Math.abs(uv.getY(0) - expected[1]) < .00001; }, expected);
  await page.locator('#editTintHex').fill('#55cc99');
  await page.waitForFunction(() => window.__MM_TEST__.liveMesh.mmOriginalMaterial.color.getHexString() !== 'ffffff');
  assert.equal(await page.evaluate(() => window.__MM_TEST__.count), 1, 'Live edits must preserve the loaded scene');
  assert.deepEqual(await page.evaluate(() => window.__MM_TEST__.shared.camera), start.camera, 'Live edits must preserve the camera');
  assert(await page.evaluate(() => { const test = window.__MM_TEST__; return test.liveMeshes.filter(object => object !== test.liveMesh).every((object, i) => JSON.stringify({ color: object.mmOriginalMaterial.color.toArray(), uv: Array.from(object.geometry.attributes.uv?.array || []) }) === JSON.stringify(test.untouched[i])); }), 'Surface edits must not leak into shared materials or other LODs');
  await page.locator('#uvScaleU').fill('0');
  assert.deepEqual(await page.evaluate(() => { const uv = window.__MM_TEST__.liveMesh.geometry.attributes.uv; return [uv.getX(0), uv.getY(0)]; }), expected, 'Invalid partial input must retain the last preview');
  await page.locator('#uvScaleU').fill('2');
  await page.screenshot({ path: path.join(output, 'live-material-controls.png') });
  await page.locator('#textureSampling summary').click(); assert.equal(await page.locator('#applySampling').count(), 0);
  await page.evaluate(() => {
    const test = window.__MM_TEST__, fields = ['wrapS', 'wrapT', 'minFilter', 'magFilter'];
    test.samplingRoles = ['map', 'normalMap', 'roughnessMap', 'metalnessMap', 'aoMap', 'emissiveMap', 'bumpMap'];
    test.samplingBefore = Object.fromEntries(test.samplingRoles.filter(role => test.liveMesh.mmOriginalMaterial[role]).map(role => [role, test.liveMesh.mmOriginalMaterial[role]]));
    test.samplingOthers = [];
    test.stats.scene.traverse(object => { if (!object.isMesh || object === test.liveMesh) return; for (const role of test.samplingRoles) { const texture = object.mmOriginalMaterial[role]; if (texture) test.samplingOthers.push({ texture, values: fields.map(key => texture[key]) }); } });
  });
  assert(await page.evaluate(() => Object.keys(window.__MM_TEST__.samplingBefore).length > 1), 'The sampler test must include shared material maps');
  await page.locator('#wrapU').selectOption('33648');
  await page.waitForFunction(value => Object.keys(window.__MM_TEST__.samplingBefore).every(role => window.__MM_TEST__.liveMesh.mmOriginalMaterial[role].wrapS === value), MirroredRepeatWrapping);
  await page.evaluate(() => { const test = window.__MM_TEST__; test.samplingCopies = Object.fromEntries(Object.keys(test.samplingBefore).map(role => { const texture = test.liveMesh.mmOriginalMaterial[role]; return [role, { texture, version: texture.version }]; })); });
  await page.locator('#wrapV').selectOption('33071');
  for (const value of ['9728', '9729', '9984', '9986', '9987', '9985']) await page.locator('#minFilter').selectOption(value);
  await page.locator('#magFilter').selectOption('9728');
  const samplerValues = [MirroredRepeatWrapping, ClampToEdgeWrapping, LinearMipmapNearestFilter, NearestFilter];
  await page.waitForFunction(expected => { const test = window.__MM_TEST__; return Object.keys(test.samplingBefore).every(role => ['wrapS', 'wrapT', 'minFilter', 'magFilter'].every((key, i) => test.liveMesh.mmOriginalMaterial[role][key] === expected[i])); }, samplerValues);
  assert(await page.evaluate(() => {
    const test = window.__MM_TEST__, material = test.liveMesh.mmOriginalMaterial;
    return Object.entries(test.samplingBefore).every(([role, original]) => material[role] !== original && material[role].source === original.source && material[role].colorSpace === original.colorSpace && material[role].flipY === original.flipY && material[role] === test.samplingCopies[role].texture && material[role].version > test.samplingCopies[role].version)
      && test.samplingOthers.every(({ texture, values }) => ['wrapS', 'wrapT', 'minFilter', 'magFilter'].every((key, i) => texture[key] === values[i]));
  }), 'Live sampling must reuse its texture copies and loaded images, update GPU texture state, and leave other surfaces untouched');
  assert.equal(await page.evaluate(() => window.__MM_TEST__.count), 1, 'Live sampling must not reload the scene');
  assert.deepEqual(await page.evaluate(() => window.__MM_TEST__.shared.camera), start.camera);
  await page.screenshot({ path: path.join(output, 'live-texture-sampling.png') });
  await deliver(); await ready(2);
  await page.locator('[data-tab="test"]').click(); await page.locator('#height').fill('3'); await page.locator('[data-preset="straight"]').click(); await page.locator('[data-reach="S"]').fill('1'); await page.locator('#rotation').selectOption('2'); await page.locator('#test').click();
  await page.waitForFunction(() => document.getElementById('engineStatus').textContent.startsWith('PASS:'), null, { timeout: 45000 });
  assert.equal(await page.evaluate(() => window.__MM_TEST__.stats.assembled), true);
  await page.evaluate(() => window.postMessage({ type: 'linkedView', state: window.__MM_TEST__.shared }, '*'));
  await page.evaluate(() => new Promise(requestAnimationFrame));
  assert.equal(await page.evaluate(() => window.__MM_TEST__.stats.assembled), true, 'Linked camera/display settings must not discard a local engine assembly');
  await page.screenshot({ path: path.join(output, 'wall-assembled.png') });
  await page.locator('#authored').click(); assert.equal(await page.evaluate(() => window.__MM_TEST__.stats.assembled), false);
  await page.locator('[data-tab="view"]').click(); await page.locator('#projection').selectOption('ortho'); await page.locator('[data-camera="top"]').click(); await page.locator('#wire').check(); await page.locator('#wire').uncheck();
  await page.locator('#shading').selectOption('normal'); await page.locator('#shading').selectOption('uv'); await page.locator('#shading').selectOption('pbr');
  await page.locator('#projection').selectOption('perspective'); await page.locator('[data-camera="iso"]').click();
  current = 'buildings/fuel_tanks/fuel_tank_light.glb';
  const beforePaintLoads = await page.evaluate(() => window.__MM_TEST__.count), tank = await deliver(); await ready(beforePaintLoads + 1);
  const paintNode = tank.metadata.nodes.findIndex(n => tank.metadata.meshes?.[n.mesh]?.primitives.some(p => tank.metadata.materials[p.material].name === 'paint'));
  const paintPrimitive = tank.metadata.meshes[tank.metadata.nodes[paintNode].mesh].primitives.findIndex(p => tank.metadata.materials[p.material].name === 'paint');
  await page.locator('[data-tab="materials"]').click(); await page.locator('#surfaceTarget').selectOption(`${paintNode}:${paintPrimitive}`); await page.locator('#vertexPaint summary').click();
  const authoredSwatches = await page.locator('#vertexSwatches input').evaluateAll(inputs => inputs.map(input => input.value));
  const red = authoredSwatches.findIndex(hex => { const rgb = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16)); return rgb[0] > rgb[1] * 2 && rgb[0] > rgb[2] * 2; }); assert(red >= 0);
  await page.locator('#vertexSwatches button').nth(red).click();
  await page.evaluate(target => {
    const test = window.__MM_TEST__; test.paintOthers = [];
    test.stats.scene.traverse(object => { if (!object.isMesh) return; if (object.userData.mmSurface?.node === target.node && object.userData.mmSurface?.primitive === target.primitive) test.paintMesh = object; else test.paintOthers.push({ object, color: Array.from(object.geometry.attributes.color.array) }); });
    test.paintBefore = Array.from(test.paintMesh.geometry.attributes.color.array); test.paintCamera = JSON.stringify(test.shared.camera);
  }, { node: paintNode, primitive: paintPrimitive });
  async function renderedPaint() {
    const { json, binary } = readGlb(editingDocument.bytes), primitive = json.meshes[json.nodes[paintNode].mesh].primitives[paintPrimitive];
    const expected = Array.from(readAttribute(json, binary, primitive.attributes.COLOR_0).values);
    await page.waitForFunction(expected => Array.from(window.__MM_TEST__.paintMesh.geometry.attributes.color.array).every((n, i) => n === expected[i]), expected);
  }
  await page.locator('#paintColor').fill('#2266dd');
  await page.waitForFunction(() => window.__MM_TEST__.paintMesh.geometry.attributes.color.array.some((n, i) => n !== window.__MM_TEST__.paintBefore[i])); await renderedPaint();
  await page.locator('#paintMode').selectOption('solid'); await page.locator('#paintMode').selectOption('recolour'); await page.locator('#paintColor').fill('#33dd66'); await renderedPaint();
  assert.equal(await page.evaluate(() => window.__MM_TEST__.count), beforePaintLoads + 1, 'Live paint keeps the same scene');
  assert(await page.evaluate(() => { const test = window.__MM_TEST__; return test.paintCamera === JSON.stringify(test.shared.camera) && test.paintOthers.every(({ object, color }) => object.geometry.attributes.color.array.every((n, i) => n === color[i])); }), 'Live paint preserves the camera, other surfaces and LODs');
  assert(await page.evaluate(() => { const test = window.__MM_TEST__, attr = test.paintMesh.geometry.attributes.color; return attr.itemSize === 4 && attr.array.every((n, i) => i % 4 !== 3 || n === test.paintBefore[i]) && attr.array.some((n, i) => i % 4 !== 3 && n === test.paintBefore[i]); }), 'Unmatched paint and alpha remain unchanged');
  await page.screenshot({ path: path.join(output, 'live-fuel-paint.png') });
  await deliver(editingDocument.bytes); await ready(beforePaintLoads + 2);
  await page.locator('#surfaceTarget').selectOption(`${paintNode}:${paintPrimitive}`);
  assert.deepEqual(await page.locator('#vertexSwatches input').evaluateAll(inputs => inputs.map(input => input.value)), authoredSwatches, 'Original swatches survive reopening a recoloured tank');
  await page.locator('#editScope').selectOption('material'); await page.locator('#paintColor').fill('#cc77ee');
  await page.waitForFunction(target => {
    let matches = false;
    window.__MM_TEST__.stats.scene.traverse(object => { if (object.userData.mmSurface?.node !== target.node || object.userData.mmSurface?.primitive !== target.primitive) return; const color = object.geometry.attributes.color; for (let i = 0; i < color.count; i++) if (color.getX(i) > .5 && color.getY(i) < .2 && color.getZ(i) > .8) matches = true; });
    return matches;
  }, { node: paintNode, primitive: paintPrimitive });
  const wholePaint = readGlb(editingDocument.bytes);
  const expectedPaint = wholePaint.json.nodes.flatMap((node, ni) => (wholePaint.json.meshes?.[node.mesh]?.primitives || []).flatMap((primitive, pi) => primitive.attributes.COLOR_0 === undefined ? [] : [{ key: `${ni}:${pi}`, values: Array.from(readAttribute(wholePaint.json, wholePaint.binary, primitive.attributes.COLOR_0).values) }]));
  assert(await page.evaluate(expected => {
    const bySurface = new Map(expected.map(item => [item.key, item.values])); let valid = true;
    window.__MM_TEST__.stats.scene.traverse(object => { const target = object.userData.mmSurface, values = target && bySurface.get(`${target.node}:${target.primitive}`); if (values && !object.geometry.attributes.color.array.every((n, i) => n === values[i])) valid = false; });
    return valid;
  }, expectedPaint), 'All using this material previews the saved colours on every part and LOD');
  await page.screenshot({ path: path.join(output, 'live-fuel-paint-all-lods.png') });
  await page.locator('[data-tab="view"]').click();
  for (const name of ['board/scenery/military/cargo-crate.glb', 'board/scenery/vehicles/car.glb', 'board/vegetation/pine.glb', 'board/scenery/military/fortification.glb']) {
    current = name; variant = ''; const count = await page.evaluate(() => window.__MM_TEST__.count); const asset = await deliver(); await ready(count + 1); await page.locator('#fit').click();
    if (name.includes('cargo-crate')) {
      await page.locator('#label').fill('MM'); await page.locator('#bounds').check(); await page.locator('#measure').click();
      await page.locator('#canvas').click({ position: { x: 430, y: 380 } }); await page.locator('#canvas').click({ position: { x: 520, y: 400 } });
      assert.match(await page.locator('#measurement').textContent(), /model units/);
      await page.locator('#screenshot').click();
      assert(asset.metadata.images.some(image => image.bufferView !== undefined), 'Use an actual embedded-texture model');
      const node = asset.metadata.nodes.findIndex(n => asset.metadata.meshes?.[n.mesh]?.primitives.some(p => asset.metadata.materials[p.material]?.pbrMetallicRoughness?.baseColorTexture));
      const primitive = asset.metadata.meshes[asset.metadata.nodes[node].mesh].primitives.findIndex(p => asset.metadata.materials[p.material]?.pbrMetallicRoughness?.baseColorTexture);
      await page.locator('[data-tab="materials"]').click(); await page.locator('#surfaceTarget').selectOption(`${node}:${primitive}`);
      if (!await page.locator('#textureSampling').evaluate(element => element.open)) await page.locator('#textureSampling summary').click();
      await page.evaluate(target => { const test = window.__MM_TEST__; test.stats.scene.traverse(object => { if (object.userData.mmSurface?.node === target.node && object.userData.mmSurface?.primitive === target.primitive) test.embeddedMesh = object; }); test.embeddedSource = test.embeddedMesh.mmOriginalMaterial.map.source; test.embeddedLoads = test.count; }, { node, primitive });
      await page.locator('#wrapU').selectOption('33648'); await page.locator('#magFilter').selectOption('9728');
      await page.waitForFunction(expected => { const map = window.__MM_TEST__.embeddedMesh.mmOriginalMaterial.map; return map.wrapS === expected[0] && map.magFilter === expected[1]; }, [MirroredRepeatWrapping, NearestFilter]);
      assert(await page.evaluate(() => { const test = window.__MM_TEST__; return test.embeddedMesh.mmOriginalMaterial.map.source === test.embeddedSource && test.count === test.embeddedLoads; }), 'Embedded maps preview live using their loaded image');
      await page.locator('[data-tab="view"]').click();
    }
    if (name.includes('/car.')) { const picker = page.locator('#colours input[type=color]').first(); await picker.fill('#00ff88'); assert.equal(await picker.inputValue(), '#00ff88'); }
    if (name.includes('/pine.')) { const n = await page.evaluate(() => window.__MM_TEST__.count); await page.locator('#variant').selectOption('snow'); await ready(n + 1); }
    if (name.includes('fortification')) await page.locator('#helpers').check();
    assert(asset.statistics.rows.every(r => Number.isFinite(r.vertices) && Number.isFinite(r.triangles)));
    await page.screenshot({ path: path.join(output, path.basename(name, '.glb') + '.png') });
    await page.locator('[data-tab="materials"]').click(); assert(await page.locator('#materialList option').count() > 0); await page.locator('[data-tab="view"]').click();
  }
  await page.setViewportSize({ width: 640, height: 720 }); await page.screenshot({ path: path.join(output, 'narrow-viewer.png') });
  assert.equal(await page.locator('body').evaluate(el => el.scrollWidth <= innerWidth), true);
  await page.setViewportSize({ width: 1280, height: 850 });
  current = 'buildings/authored/hpg-headquarters.glb'; variant = '';
  const hpgLoads = await page.evaluate(() => window.__MM_TEST__.count);
  const hpg = await deliver(); await ready(hpgLoads + 1);
  const volumeCount = hpg.metadata.nodes.filter(node => node.name?.startsWith('building_volume-')).length;
  assert(volumeCount > 0);
  assert(hpg.statistics.rows.some(row => row.name === 'Helpers' && row.meshes === volumeCount));
  const visibleHelpers = () => page.evaluate(() => {
    const meshes = [];
    window.__MM_TEST__.stats.scene.traverseVisible(object => { if (object.isMesh && object.userData.mmHelper) meshes.push(object); });
    return { count: meshes.length, wire: meshes.every(object => object.material.wireframe) };
  });
  for (const lod of ['0', '1']) {
    await page.locator('#lod').selectOption(lod);
    await page.locator('#helpers').uncheck(); assert.equal((await visibleHelpers()).count, 0);
    await page.locator('#helpers').check(); assert.deepEqual(await visibleHelpers(), { count: volumeCount, wire: true });
  }
  await page.locator('#helpers').uncheck();
  // Compare the actual exported layered reflector under the same camera and lighting.
  const dishView = { ...await page.evaluate(() => window.__MM_TEST__.shared), lod: '0', projection: 'ortho',
    shading: 'pbr', grid: false, helpers: false, bounds: false, wire: false, bloom: false,
    camera: { position: [-930, 907, 110], target: [-110, 342, 10], span: 390, zoom: 1 } };
  await page.evaluate(state => window.postMessage({ type: 'linkedView', state }, '*'), dishView);
  for (const lod of ['0', '1']) {
    await page.locator('#lod').selectOption(lod);
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.locator('#screenshot').click();
    const error = await page.evaluate(async lod => {
      const image = new Image(); image.src = window.__MM_TEST__.screenshot; await image.decode();
      const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
      const context = canvas.getContext('2d'); context.drawImage(image, 0, 0);
      const values = context.getImageData(0, 0, canvas.width, canvas.height).data;
      if (lod === '0') { window.__MM_TEST__.dishPixels = values; return 0; }
      const near = window.__MM_TEST__.dishPixels, radius = canvas.height / 780 * 290;
      let difference = 0, count = 0;
      for (let y = 0; y < canvas.height; y++) for (let x = 0; x < canvas.width; x++) {
        if ((x - canvas.width / 2) ** 2 + (y - canvas.height / 2) ** 2 >= radius ** 2) continue;
        const i = (y * canvas.width + x) * 4;
        for (let c = 0; c < 3; c++) difference += Math.abs(values[i + c] - near[i + c]);
        count += 3;
      }
      return difference / count;
    }, lod);
    assert(error < 1, `HPG reflector colour/shading changes across LODs: mean RGB error ${error}/255`);
  }
  const fixture = path.join(output, 'depth-fixture.glb'); await fs.writeFile(fixture, depthFixture());
  const depth = await loadAsset(fixture, await findRoots(fixture));
  editingAsset = structuredClone(depth); editingDocument = new GlbDocument(fixture, await fs.readFile(fixture));
  const count = await page.evaluate(() => window.__MM_TEST__.count);
  await page.evaluate(message => window.postMessage(message, '*'), { type: 'asset', asset: depth, generation: ++generation, trusted: true }); await ready(count + 1);
  await page.locator('[data-tab="materials"]').click(); await page.locator('#surfaceTarget').selectOption('1:0');
  assert(await page.locator('#wrapU').isDisabled(), 'A surface without textures has no sampling controls');
  if (!await page.locator('#vertexPaint').evaluate(element => element.open)) await page.locator('#vertexPaint summary').click();
  await page.locator('#paintMatch').uncheck(); await page.locator('#paintColor').fill('#ff33ff');
  await page.waitForFunction(() => { let painted = false; window.__MM_TEST__.stats.scene.traverse(object => { if (object.userData.mmSurface?.node === 1) painted = object.mmOriginalMaterial.vertexColors && object.geometry.attributes.color.itemSize === 4; }); return painted; });
  // Restore the unpainted fixture for the independent depth-precision checks.
  await page.evaluate(message => window.postMessage(message, '*'), { type: 'asset', asset: depth, generation: ++generation, trusted: true }); await ready(count + 2);
  await page.locator('[data-tab="view"]').click();
  for (const id of ['grid', 'helpers', 'bounds', 'bloom']) await page.locator('#' + id).uncheck();
  for (const projection of ['perspective', 'ortho']) {
    await page.locator('#projection').selectOption(projection); await page.locator('[data-camera="iso"]').click();
    for (const view of ['fitted', 'orbit', 'zoom out', 'zoom in']) {
      const rect = await page.locator('#canvas').boundingBox(), x = rect.x + rect.width / 2, y = rect.y + rect.height / 2;
      if (view === 'orbit') { await page.mouse.move(x, y); await page.mouse.down(); await page.mouse.move(x + 85, y, { steps: 8 }); await page.mouse.up(); }
      if (view.startsWith('zoom')) { await page.mouse.move(x, y); await page.mouse.wheel(0, view === 'zoom out' ? 400 : -800); }
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      await page.evaluate(() => { window.__MM_TEST__.screenshot = null; }); await page.locator('#screenshot').click();
      const pixels = await page.evaluate(async () => {
        const image = new Image(); image.src = window.__MM_TEST__.screenshot; await image.decode(); const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
        const context = canvas.getContext('2d'); context.drawImage(image, 0, 0); const values = context.getImageData(0, 0, canvas.width, canvas.height).data;
        // Tone mapping mixes colour channels, so detect dominant colours rather than exact RGB.
        let red = 0, green = 0; for (let i = 0; i < values.length; i += 4) { if (values[i] > 80 && values[i] > values[i + 1] * 1.25) red++; if (values[i + 1] > 80 && values[i + 1] > values[i] * 1.25) green++; }
        return { red, green };
      });
      console.log(`Depth precision (${projection}, ${view}): ${JSON.stringify(pixels)}`);
      assert(pixels.green > 1000, 'The front surface must be visible');
      // A thin exposed rim is valid because the planes have slightly different projected edges.
      assert(pixels.red < (pixels.green + pixels.red) * .001 + 5, 'The rear surface must not bleed through a nearer surface');
    }
  }
  await fs.rm(fixture);
  comparison = await gitFixture(output);
  const snapshot = await gitSource(comparison.file, '');
  const staged = await loadAsset(comparison.file, await findRoots(comparison.file, '', [], snapshot.io), snapshot.urlFor, '', snapshot.io); staged.revision = 'Staged';
  const working = await loadAsset(comparison.file, await findRoots(comparison.file), p => { const key = `/asset/${resources.size}`; resources.set(key, p); return origin + key; }); working.revision = 'Working copy';
  const beforeComparison = await page.evaluate(() => window.__MM_TEST__.count);
  await page.evaluate(message => window.postMessage(message, '*'), { type: 'asset', asset: working, generation: ++generation, trusted: true }); await ready(beforeComparison + 1);
  peer = await browser.newPage({ viewport: { width: 1280, height: 850 } }); peer.on('pageerror', error => errors.push(error.message));
  await peer.exposeFunction('mmMessage', async message => {
    if (message.type === 'ready') await peer.evaluate(asset => window.postMessage({ type: 'asset', asset, generation: 1, trusted: true, revision: true }, '*'), staged);
    if (message.type === 'viewState' && relay) await page.evaluate(state => window.postMessage({ type: 'linkedView', state }, '*'), message.state);
  });
  await peer.addInitScript(mockApi); await peer.goto(origin);
  await peer.waitForFunction(() => window.__MM_TEST__.count === 1 || window.__MM_TEST__.failures.length); assert.deepEqual(await peer.evaluate(() => window.__MM_TEST__.failures), []);
  relay = true;
  await page.locator('#projection').selectOption('perspective'); await page.locator('#lod').selectOption('1');
  await peer.waitForFunction(() => document.getElementById('lod').value === '1');
  assert.match(await page.locator('#status').textContent(), /15\.0/); assert.match(await peer.locator('#status').textContent(), /10\.0/);
  await page.locator('#wire').check(); await peer.waitForFunction(() => document.getElementById('wire').checked);
  await peer.locator('#shading').selectOption('normal'); await page.waitForFunction(() => document.getElementById('shading').value === 'normal');
  await page.locator('#shading').selectOption('checker'); await peer.waitForFunction(() => document.getElementById('shading').value === 'checker');
  async function sameCamera(source, target) {
    await source.waitForFunction(() => Date.now() - window.__MM_TEST__.sharedAt > 180);
    const pose = await source.evaluate(() => window.__MM_TEST__.shared.camera);
    await target.waitForFunction(expected => {
      const actual = window.__MM_TEST__.api.getState().camera;
      return actual && ['position', 'target'].every(key => actual[key].every((n, i) => Math.abs(n - expected[key][i]) < 1e-6)) && Math.abs(actual.zoom - expected.zoom) < 1e-6;
    }, pose);
  }
  const viewport = await page.locator('#canvas').boundingBox(), cx = viewport.x + viewport.width / 2, cy = viewport.y + viewport.height / 2;
  await page.mouse.move(cx, cy); await page.mouse.down(); await page.mouse.move(cx + 120, cy + 25, { steps: 10 }); await page.mouse.up(); await sameCamera(page, peer);
  await page.mouse.move(cx, cy); await page.mouse.down({ button: 'right' }); await page.mouse.move(cx + 35, cy - 20, { steps: 6 }); await page.mouse.up({ button: 'right' }); await sameCamera(page, peer);
  const peerViewport = await peer.locator('#canvas').boundingBox(); await peer.mouse.move(peerViewport.x + peerViewport.width / 2, peerViewport.y + peerViewport.height / 2); await peer.mouse.wheel(0, 300); await sameCamera(peer, page);
  await peer.locator('#projection').selectOption('ortho'); await page.waitForFunction(() => document.getElementById('projection').value === 'ortho'); await sameCamera(peer, page);
  await peer.locator('#syncViews').uncheck(); await page.locator('#wire').uncheck(); await page.waitForTimeout(150); assert.equal(await peer.locator('#wire').isChecked(), true);
  await peer.locator('#syncViews').check(); await page.waitForFunction(() => document.getElementById('wire').checked);
  await sameCamera(peer, page); const sent = await page.evaluate(() => window.__MM_TEST__.sent); await page.waitForTimeout(250); assert.equal(await page.evaluate(() => window.__MM_TEST__.sent), sent, 'Linked updates must not echo forever');
  await page.screenshot({ path: path.join(output, 'working-comparison.png') }); await peer.screenshot({ path: path.join(output, 'staged-comparison.png') });
  await peer.setViewportSize({ width: 420, height: 720 }); await peer.locator('#inspectorToggle').click();
  assert.equal(await peer.locator('#inspector').isVisible(), false, 'The inspector must not cover toolbar controls in a narrow comparison pane');
  assert.equal(await peer.locator('body').evaluate(el => el.scrollWidth <= innerWidth), true);
  await peer.screenshot({ path: path.join(output, 'narrow-comparison.png') });
  assert.deepEqual(errors, []); assert.deepEqual(consoleErrors, []);
  console.log('Browser PASS: live sampling for managed and embedded maps, sampler isolation and reuse, live vertex paint, depth precision and linked Git comparisons.');
} finally { relay = false; await browser.close(); await new Promise(resolve => server.close(resolve)); await comparison?.dispose(); }
