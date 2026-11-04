const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { readGlb, findRoots, loadAsset } = require('../src/assets.cjs');
const { readLibrary, libraryMaterial } = require('../src/library.cjs');
const { editGlb, writeGlb, rebaseGlb } = require('../src/glb-edit.cjs');
const { GlbDocument } = require('../src/document.cjs');
const { materialPreview } = require('../src/material-preview.cjs');
const { readAttribute } = require('../src/attributes.cjs');
const root = path.resolve(__dirname, '../../..'), output = path.resolve(__dirname, '../test-output');
const wall = path.join(root, 'data/models/buildings/walls/medium/straight.glb');
async function directory(t) {
  await fs.mkdir(output, { recursive: true }); const dir = await fs.mkdtemp(path.join(output, 'edit-'));
  t.after(async () => { assert.equal(path.dirname(dir), output); await fs.rm(dir, { recursive: true, force: true }); }); return dir;
}
async function fixture() {
  const original = await fs.readFile(wall), { json } = readGlb(original);
  const node = json.nodes.find(n => Number.isInteger(n.mesh));
  const first = json.nodes.indexOf(node), second = json.nodes.length;
  json.nodes.push({ ...structuredClone(node), name: 'second-instance', translation: [100, 0, 0] });
  json.scenes[json.scene || 0].nodes.push(second);
  json.nodes[first].extras = { ...(json.nodes[first].extras || {}), preserved: 'node metadata' };
  const source = json.meshes[node.mesh].primitives[0].material;
  json.materials[source].extras = { ...json.materials[source].extras, preserved: true, mmVariants: { snow: { textures: { baseColor: '../../../board/textures/vegetation/snow_albedo.png' }, colourScale: [.5, .5, .5, 1] } } };
  json.materials[source].emissiveFactor = [.1, .2, .3];
  const base = writeGlb(original, json), extra = Buffer.alloc(12); extra.writeUInt32LE(4); extra.writeUInt32LE(0x12345678, 4); extra.writeUInt32LE(1234, 8);
  const bytes = Buffer.concat([base, extra]); bytes.writeUInt32LE(bytes.length, 8);
  return { bytes, first, second, source };
}
test('palette contains both catalog categories and resolves shared maps within the material root', async () => {
  const roots = await findRoots(wall), catalog = JSON.parse(await fs.readFile(path.join(roots.textures, 'materials.json'))), library = await readLibrary(roots);
  assert.equal(library.entries.length, Object.keys(catalog.loose).length + catalog.constrained.length);
  const entry = library.entries.find(item => item.id === 'structures/common/rusted-steel');
  const result = await libraryMaterial(entry, roots);
  assert.equal(result.category, 'constrained'); assert(result.spec.maps.albedo.file.endsWith('rusted-steel_albedo.png')); assert(result.dependencies.includes(result.spec.file));
  await assert.rejects(libraryMaterial({ id: '../../escape' }, roots), /allowed/);
});
test('shared assignment isolates a primitive of an instanced mesh and preserves the binary and extras', async () => {
  const { bytes, first, second, source } = await fixture(), roots = await findRoots(wall);
  const shared = await libraryMaterial({ id: 'structures/common/rusted-steel', name: 'rusted-steel' }, roots);
  const edited = editGlb(bytes, { kind: 'shared', target: { node: first, primitive: 0 }, scope: 'surface', keepEmission: true }, wall, shared);
  const before = readGlb(bytes), after = readGlb(edited), newMesh = after.json.nodes[first].mesh;
  assert.notEqual(newMesh, after.json.nodes[second].mesh);
  assert.deepEqual(after.json.meshes[before.json.nodes[first].mesh], before.json.meshes[before.json.nodes[first].mesh]);
  const newIndex = after.json.meshes[newMesh].primitives[0].material, material = after.json.materials[newIndex];
  assert.notEqual(newIndex, source); assert.deepEqual(after.json.materials[source], before.json.materials[source]);
  assert.deepEqual(material.extras, before.json.materials[source].extras); assert.deepEqual(material.emissiveFactor, [.1, .2, .3]);
  assert.deepEqual(after.json.nodes[first].extras, before.json.nodes[first].extras);
  assert.deepEqual(after.binary, before.binary); assert.deepEqual(edited.subarray(-12), bytes.subarray(-12));
  assert.deepEqual(after.json.accessors, before.json.accessors); assert.deepEqual(after.json.bufferViews, before.json.bufferViews);
  const image = after.json.images[after.json.textures[material.pbrMetallicRoughness.baseColorTexture.index].source];
  assert.equal(path.resolve(path.dirname(wall), decodeURIComponent(image.uri)), shared.spec.maps.albedo.file);
});

test('live gestures replace UV data, keep the saved baseline and produce the exact preview to save', async t => {
  const { bytes, first, second } = await fixture(), dir = await directory(t), file = path.join(dir, 'live.glb');
  const initial = rebaseGlb(bytes, wall, file); await fs.writeFile(file, initial);
  const model = new GlbDocument(file, initial), asset = await loadAsset(file, await findRoots(file, root));
  const edit = { kind: 'placement', target: { node: first, primitive: 0 }, scope: 'surface', mapping: { offset: [0, 0], scale: [1, 1], pivot: [.5, .5], rotation: 0 } };
  let event, started = 0;
  for (let i = 1; i <= 50; i++) {
    edit.mapping.offset[0] = i / 10;
    const result = model.edit(edit, { group: 'offset' });
    if (result.started) { started++; event = result.change; }
    assert.strictEqual(result.change, event);
  }
  assert.equal(started, 1); assert.deepEqual(event.before, initial); assert.deepEqual(event.after, model.bytes);
  assert.deepEqual(model.bytes, editGlb(initial, edit, file), 'Fifty input events must store only the final UV attribute');
  assert.deepEqual(await fs.readFile(file), initial, 'Live preview must not write the file');
  const preview = materialPreview(model.bytes, edit, asset), after = readGlb(model.bytes);
  assert.equal(preview.updates.length, 1); assert.equal(preview.updates[0].node, first);
  const primitive = after.json.meshes[after.json.nodes[first].mesh].primitives[0];
  const uv = readAttribute(after.json, after.binary, primitive.attributes.TEXCOORD_0).values;
  assert.deepEqual(Buffer.from(preview.updates[0].uv, 'base64'), Buffer.from(uv.buffer));
  assert.equal(after.json.nodes[second].mesh, readGlb(initial).json.nodes[second].mesh);
  const current = model.bytes;
  assert.throws(() => model.edit({ ...edit, mapping: { ...edit.mapping, scale: [0, 1] } }, { group: 'offset' }), /non-zero/);
  assert.strictEqual(model.bytes, current, 'Invalid partial input retains the last valid document');
  await model.save(); assert.deepEqual(await fs.readFile(file), current); assert(!model.dirty);
  edit.mapping.offset[0] = 6;
  const next = model.edit(edit, { group: 'offset' });
  assert(next.started, 'Saving ends a gesture even when the same control stays focused');
  assert.deepEqual(next.change.before, current);
  assert.deepEqual(event.after, current, 'Later input must not alter the saved undo/redo entry');
});
test('surface emission can be disabled and restored without duplicating shared textures or changing other instances', async t => {
  const { bytes, first, second, source } = await fixture(), before = readGlb(bytes);
  const edit = { kind: 'properties', target: { node: first, primitive: 0 }, scope: 'surface', changes: { emissionMode: 'off' } };
  const off = editGlb(bytes, edit, wall, null, true), after = readGlb(off);
  const materialAt = (json, node) => json.materials[json.meshes[json.nodes[node].mesh].primitives[0].material];
  const dark = materialAt(after.json, first);
  assert.equal(dark.extras.mmEmission, 'off'); assert(dark.name.startsWith(before.json.materials[source].name + '#'));
  assert.deepEqual(materialAt(after.json, second), before.json.materials[source]);
  assert.deepEqual(dark.emissiveFactor, before.json.materials[source].emissiveFactor);
  assert.deepEqual(dark.pbrMetallicRoughness, before.json.materials[source].pbrMetallicRoughness);
  assert.deepEqual(after.json.images, before.json.images); assert.deepEqual(after.json.textures, before.json.textures);
  assert.deepEqual(after.binary, before.binary);
  const dir = await directory(t), file = path.join(dir, 'dark.glb');
  const rebased = rebaseGlb(off, wall, file); await fs.writeFile(file, rebased);
  const loaded = await loadAsset(file, await findRoots(file, root));
  assert(loaded.surfaces.find(s => s.name === dark.name).managed, 'The cloned name must still resolve its shared material');
  const restored = readGlb(editGlb(off, { ...edit, changes: { emissionMode: 'inherit' } }, wall, null, true));
  const lit = materialAt(restored.json, first);
  assert.deepEqual(lit.extras, before.json.materials[source].extras);
  assert.deepEqual(lit.emissiveFactor, dark.emissiveFactor); assert.deepEqual(restored.binary, before.binary);
  assert.throws(() => editGlb(bytes, { ...edit, changes: { emissionMode: 'disabled' } }, wall), /Invalid emissionMode/);
});

test('whole-material edits update every use without cloning geometry; existing embedded materials remain usable', async () => {
  const { bytes, first, source } = await fixture();
  const edited = editGlb(bytes, { kind: 'properties', target: { node: first, primitive: 0 }, scope: 'material', changes: { baseColorFactor: [.2, .4, .6, 1], emissiveFactor: [1, 0, 0] } }, wall);
  const before = readGlb(bytes), after = readGlb(edited);
  assert.deepEqual(after.json.meshes, before.json.meshes); assert.deepEqual(after.json.nodes, before.json.nodes);
  assert.deepEqual(after.json.materials[source].emissiveFactor, [1, 0, 0]);
  assert.throws(() => editGlb(bytes, { kind: 'properties', target: { node: first, primitive: 0 }, scope: 'surface', changes: { roughnessFactor: .2 } }, wall, null, true), /controlled by the .tres/);
  assert.throws(() => editGlb(bytes, { kind: 'properties', target: { node: first, primitive: 0 }, scope: 'surface', changes: { alphaCutoff: -1 } }, wall), /Invalid/);
  const crate = path.join(root, 'data/models/board/scenery/military/cargo-crate.glb'), original = await fs.readFile(crate), parsed = readGlb(original);
  const node = parsed.json.nodes.findIndex(n => n.mesh !== undefined), primitive = parsed.json.meshes[parsed.json.nodes[node].mesh].primitives[0];
  const index = (primitive.material + 1) % parsed.json.materials.length;
  const reassigned = readGlb(editGlb(original, { kind: 'existing', target: { node, primitive: 0 }, scope: 'surface', material: index }, crate));
  assert.equal(reassigned.json.meshes[reassigned.json.nodes[node].mesh].primitives[0].material, index);
  assert.deepEqual(reassigned.binary, parsed.binary); assert.deepEqual(reassigned.json.images, parsed.json.images); assert.deepEqual(reassigned.json.materials, parsed.json.materials);
});
test('save, backup/restore, Save As path rebasing, cancellation and conflict protection preserve edits', async t => {
  const dir = await directory(t), file = path.join(dir, 'copy.glb'), { bytes, first } = await fixture();
  const initial = rebaseGlb(bytes, wall, file); await fs.writeFile(file, initial);
  const model = new GlbDocument(file, initial);
  model.bytes = editGlb(initial, { kind: 'properties', target: { node: first, primitive: 0 }, scope: 'surface', changes: { doubleSided: true } }, file);
  const changed = model.bytes; assert(model.dirty);
  const restored = GlbDocument.restore(file, model.backup()); assert(restored.dirty); assert.deepEqual(restored.bytes, changed);
  await assert.rejects(model.save(undefined, { isCancellationRequested: true }), /cancelled/); assert.deepEqual(await fs.readFile(file), initial);
  await model.save(); assert(!model.dirty); assert.deepEqual(await fs.readFile(file), changed);
  assert.deepEqual(readGlb(await fs.readFile(file)).binary, readGlb(bytes).binary);
  const targetDir = path.join(dir, 'nested space'); await fs.mkdir(targetDir); const target = path.join(targetDir, 'copy.glb'); await model.save(target);
  const loaded = await loadAsset(target, await findRoots(target, root)); assert(loaded.surfaces.some(surface => surface.managed));
  const before = readGlb(changed).json, after = readGlb(await fs.readFile(target)).json;
  for (let i = 0; i < before.images.length; i++) if (before.images[i].uri && !before.images[i].uri.startsWith('data:')) assert.equal(path.resolve(path.dirname(file), decodeURIComponent(before.images[i].uri)), path.resolve(path.dirname(target), decodeURIComponent(after.images[i].uri)));
  model.bytes = initial; await fs.writeFile(file, bytes);
  await assert.rejects(model.save(), /changed on disk/); assert.deepEqual(model.bytes, initial); assert.deepEqual(await fs.readFile(file), bytes);
  await model.refresh(); assert.deepEqual(model.bytes, initial, 'Reload must preserve unsaved edits');
  await model.revert(); assert(!model.dirty); assert.deepEqual(model.bytes, bytes);
  assert(!(await fs.readdir(dir)).some(name => name.endsWith('.tmp')));
});
