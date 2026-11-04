const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { readGlb, loadAsset, findRoots } = require('../src/assets.cjs');
const { summarize } = require('../src/stats.cjs');
const { readTres } = require('../src/tres.cjs');
const { findEngine, preview } = require('../src/engine.cjs');
const root = path.resolve(__dirname, '../../..');
const model = relative => path.join(root, 'data/models', relative);
function glb(json, binary = Buffer.alloc(0)) {
  const text = Buffer.from(JSON.stringify(json).padEnd(Math.ceil(Buffer.byteLength(JSON.stringify(json)) / 4) * 4));
  const result = Buffer.alloc(20 + text.length + (binary.length ? 8 + binary.length : 0));
  result.writeUInt32LE(0x46546c67); result.writeUInt32LE(2, 4); result.writeUInt32LE(result.length, 8); result.writeUInt32LE(text.length, 12); result.writeUInt32LE(0x4e4f534a, 16); text.copy(result, 20);
  if (binary.length) { result.writeUInt32LE(binary.length, 20 + text.length); result.writeUInt32LE(0x004e4942, 24 + text.length); binary.copy(result, 28 + text.length); }
  return result;
}
test('rejects incomplete and malformed GLBs', () => {
  assert.throws(() => readGlb(Buffer.alloc(19)), /complete/);
  const file = glb({ asset: { version: '2.0' } }); assert.equal(readGlb(file).json.asset.version, '2.0');
  file.writeUInt32LE(10000, 12); assert.throws(() => readGlb(file), /chunk/);
});
test('LOD counts use referenced vertices, separate helpers, and count repeated draws', () => {
  const binary = Buffer.from([0, 1, 2, 4, 5, 6, 0, 0]);
  const doc = { scene: 0, scenes: [{ nodes: [0, 3, 5] }], nodes: [{ name: 'piece-lod0', children: [1, 2] }, { mesh: 0 }, { mesh: 0 }, { name: 'piece-lod1', children: [4] }, { mesh: 1 }, { name: 'cut', mesh: 0 }],
    meshes: [{ primitives: [{ attributes: { POSITION: 0 }, indices: 1, material: 0 }] }, { primitives: [{ attributes: { POSITION: 0 }, indices: 2, material: 1 }] }],
    accessors: [{ count: 1000 }, { bufferView: 0, count: 3, componentType: 5121 }, { bufferView: 0, byteOffset: 3, count: 3, componentType: 5121 }], bufferViews: [{ buffer: 0, byteLength: 8 }] };
  const rows = summarize(doc, binary, 1234).rows;
  assert.deepEqual(rows.map(r => [r.name, r.vertices, r.triangles, r.primitives, r.materials]), [['LOD 0', 3, 2, 2, 1], ['LOD 1', 3, 1, 1, 1], ['Helpers', 3, 1, 1, 1]]);
  doc.scenes[0].nodes.push(6);
  doc.nodes.push({ name: 'building_volumes', children: [7] }, { name: 'building_volume-0', mesh: 1 });
  const withVolumes = summarize(doc, binary, 1234).rows;
  assert.deepEqual(withVolumes.map(r => [r.name, r.vertices, r.triangles, r.primitives, r.materials]), [['LOD 0', 3, 2, 2, 1], ['LOD 1', 3, 1, 1, 1], ['Helpers', 6, 2, 2, 2]]);
  doc.nodes[1].children = [0]; assert.throws(() => summarize(doc, binary, 1234), /Cyclic/);
});
test('shared materials resolve .tres and their map channels alongside GLB lamps', async () => {
  const file = model('buildings/walls/medium/straight.glb');
  const asset = await loadAsset(file, await findRoots(file), p => `local:${p}`);
  assert(asset.surfaces.some(s => s.managed));
  const mapped = asset.surfaces.find(s => s.managed?.maps.roughness);
  assert(mapped); assert.equal(mapped.managed.channels.roughness, 1); assert.equal(mapped.managed.channels.metallic, 2);
  assert(asset.surfaces.some(s => s.gltf.emissiveFactor?.some(v => v > 0)));
  assert(asset.statistics.rows.some(r => r.name === 'LOD 0' && r.triangles > 0));
});
test('embedded images, colour slots, labels and snow variants survive preparation', async () => {
  const crate = model('board/scenery/military/cargo-crate.glb');
  const loaded = await loadAsset(crate, await findRoots(crate));
  assert(loaded.statistics.embeddedImages > 0); assert(loaded.metadata.extras.mmColourSlots.length);
  assert(loaded.surfaces.some(s => s.gltf.extras?.mmPaintMask)); assert(loaded.surfaces.some(s => s.gltf.extras?.mmLabel));
  const tree = model('board/vegetation/pine.glb'), roots = await findRoots(tree);
  const normal = await loadAsset(tree, roots), snow = await loadAsset(tree, roots, p => p, 'snow');
  assert(normal.variants.includes('snow')); assert(snow.surfaces.some(s => s.changes));
  assert.notDeepEqual(normal.document.images, snow.document.images);
});
test('rejects external paths escaping model roots and network dependencies', async t => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'mm-glb-test-')); t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const file = path.join(dir, 'test.glb'), roots = { models: dir, textures: path.join(dir, 'textures') };
  for (const uri of ['../secret.png', 'https://example.com/image.png', '%2e%2e/secret.png', 'file:///secret.png', '//host/a.png']) {
    await fs.writeFile(file, glb({ asset: { version: '2.0' }, images: [{ uri }] }));
    await assert.rejects(loadAsset(file, roots), /relative|allowed/);
  }
});
test('Godot format 3, res paths, disabled maps and emission operators', async t => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'mm-tres-test-')); t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const file = path.join(dir, 'metal.tres');
  await fs.writeFile(file, '[gd_resource type="StandardMaterial3D" format=3]\n[ext_resource type="Texture2D" path="res://metal.png" id="1_img"]\n[resource]\nalbedo_texture = ExtResource("1_img")\nroughness = 0.3\nemission_enabled = true\nemission = Color(1,0.2,0.1,1)\nemission_operator = 1\nemission_energy_multiplier = 5\n');
  const spec = await readTres(file, dir, async (base, uri) => path.join(base, uri));
  assert.equal(spec.maps.albedo, path.join(dir, 'metal.png')); assert.equal(spec.maps.normal, undefined); assert.equal(spec.roughness, .3); assert.equal(spec.emissionOperator, 1); assert.equal(spec.emissionEnergy, 5);
});
test('existing engine bridge assembles symmetric links, end caps, heights and LODs', async t => {
  const engine = await findEngine('', root, [root]);
  assert.notEqual(engine, root, 'The mm-data Gradle project is not the MegaMek engine checkout');
  if (!engine) return t.skip('Sibling engine unavailable');
  const request = { model: model('buildings/walls/medium/straight.glb'), modelsRoot: model(''), kind: 'KIT', lod: 0, height: 3, reach: [3, 0, 0, 1, 0, 0], rotation: 2, seed: 12 };
  const result = await preview(engine, request);
  assert(result.ok); assert(result.instances.length > 3); assert(result.instances.every(i => i.matrix.length === 16));
  const fallback = await preview(engine, { ...request, kind: 'RIGID', lod: 3 }); assert(fallback.lod <= 3);
  await assert.rejects(preview(engine, { ...request, height: 0 }), /height/);
});
