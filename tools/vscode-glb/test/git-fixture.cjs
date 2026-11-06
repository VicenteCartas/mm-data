const fs = require('node:fs/promises');
const path = require('node:path');
const { promisify } = require('node:util');
const { execFile } = require('node:child_process');
const { deflateSync } = require('node:zlib');
const execute = promisify(execFile);
function png(rgb) {
  const chunk = (name, data) => {
    const body = Buffer.concat([Buffer.from(name), data]), out = Buffer.alloc(body.length + 8);
    out.writeUInt32BE(data.length); body.copy(out, 4); let crc = 0xffffffff;
    for (const byte of body) { crc ^= byte; for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0); }
    out.writeUInt32BE((crc ^ 0xffffffff) >>> 0, out.length - 4); return out;
  };
  const header = Buffer.alloc(13); header.writeUInt32BE(1); header.writeUInt32BE(1, 4); header[8] = 8; header[9] = 2;
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', header), chunk('IDAT', deflateSync(Buffer.from([0, ...rgb]))), chunk('IEND', Buffer.alloc(0))]);
}
function mesh(size) {
  const document = { asset: { version: '2.0' }, scene: 0, scenes: [{ nodes: [0, 1] }],
    nodes: [0, 1].map(lod => ({ name: 'review-lod' + lod, mesh: 0, scale: [size / (lod + 1), size / (lod + 1), 1] })),
    meshes: [{ primitives: [{ attributes: { POSITION: 0 }, material: 0 }] }],
    materials: [{ name: 'review', extras: { mmSnow: { colourScale: [.5, .5, .5, 1] } }, pbrMetallicRoughness: { baseColorTexture: { index: 0 }, metallicFactor: 0 } }],
    textures: [{ source: 0 }], images: [{ uri: '../board/textures/review_albedo.png' }],
    buffers: [{ byteLength: 36 }], bufferViews: [{ buffer: 0, byteLength: 36 }], accessors: [{ bufferView: 0, componentType: 5126, count: 3, type: 'VEC3', min: [0, 0, 0], max: [1, 1, 0] }] };
  const raw = JSON.stringify(document), json = Buffer.from(raw.padEnd(Math.ceil(raw.length / 4) * 4));
  const file = Buffer.alloc(64 + json.length); file.writeUInt32LE(0x46546c67); file.writeUInt32LE(2, 4); file.writeUInt32LE(file.length, 8); file.writeUInt32LE(json.length, 12); file.writeUInt32LE(0x4e4f534a, 16); json.copy(file, 20); file.writeUInt32LE(36, 20 + json.length); file.writeUInt32LE(0x004e4942, 24 + json.length);
  [0, 0, 0, 1, 0, 0, 0, 1, 0].forEach((value, i) => file.writeFloatLE(value, 28 + json.length + i * 4)); return file;
}
async function gitFixture(parent) {
  await fs.mkdir(parent, { recursive: true }); const root = await fs.mkdtemp(path.join(parent, 'git-review-'));
  const git = async (...args) => execute('git', ['-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=.no-hooks', '-C', root, ...args], { windowsHide: true });
  const file = path.join(root, 'data/models/fixture/review.glb'), textures = path.join(root, 'data/models/board/textures');
  await fs.mkdir(path.dirname(file), { recursive: true }); await fs.mkdir(textures, { recursive: true }); await fs.writeFile(path.join(textures, 'materials.json'), '{}');
  const write = async (size, roughness, rgb) => {
    await fs.writeFile(file, mesh(size)); await fs.writeFile(path.join(textures, 'review_albedo.png'), png(rgb));
    await fs.writeFile(path.join(textures, 'review.tres'), `[gd_resource type="StandardMaterial3D" format=3]\n[resource]\nroughness = ${roughness}\n`);
    await fs.writeFile(path.join(path.dirname(file), 'review.json'), JSON.stringify({ mesh: 'review.glb', revisionSize: size }));
  };
  await git('init', '-q'); await write(10, .2, [255, 0, 0]); await git('add', '.');
  await git('-c', 'user.name=Viewer test', '-c', 'user.email=viewer-test@example.invalid', 'commit', '--no-gpg-sign', '-qm', 'Fixture');
  await write(20, .4, [0, 0, 255]); await git('add', '.'); await write(30, .8, [0, 255, 0]);
  return { root, file, textures, git, write, dispose: async () => {
    const relative = path.relative(path.resolve(parent), path.resolve(root));
    if (relative.startsWith('..') || path.isAbsolute(relative) || !path.basename(root).startsWith('git-review-')) throw Error('Unsafe test cleanup');
    await fs.rm(root, { recursive: true, force: true, maxRetries: 4, retryDelay: 200 });
  } };
}
module.exports = { gitFixture, png };
