const fs = require('node:fs/promises');
const path = require('node:path');
const { readTres } = require('./tres.cjs');
const { summarize } = require('./stats.cjs');

function readGlb(bytes) {
  if (bytes.length < 20 || bytes.readUInt32LE(0) !== 0x46546c67 || bytes.readUInt32LE(4) !== 2 || bytes.readUInt32LE(8) !== bytes.length) throw Error('Expected a complete binary glTF 2.0 file');
  let json, binary;
  for (let at = 12; at < bytes.length;) {
    if (at + 8 > bytes.length) throw Error('Truncated GLB chunk');
    const size = bytes.readUInt32LE(at), type = bytes.readUInt32LE(at + 4); at += 8;
    if (size % 4 || at + size > bytes.length) throw Error('Invalid GLB chunk length');
    if (type === 0x4e4f534a) { if (json) throw Error('Duplicate GLB JSON'); json = JSON.parse(bytes.subarray(at, at + size).toString('utf8').trim()); }
    if (type === 0x004e4942) { if (binary) throw Error('Duplicate GLB binary'); binary = bytes.subarray(at, at + size); }
    at += size;
  }
  if (!json || json.asset?.version !== '2.0') throw Error('Missing glTF 2.0 document');
  return { json, binary };
}
function inside(root, file) { const rel = path.relative(root, file); return !rel.startsWith('..' + path.sep) && rel !== '..' && !path.isAbsolute(rel); }
async function exists(file, io = fs) { try { return (await io.stat(file)).isFile(); } catch { return false; } }
async function findRoots(file, configured = '', folders = [], io = fs) {
  const candidates = [];
  for (let dir = path.dirname(file); dir !== path.dirname(dir); dir = path.dirname(dir)) candidates.push(dir);
  candidates.push(...folders, ...folders.map(p => path.join(path.dirname(p), 'mm-data')));
  const root = configured || await (async () => { for (const dir of candidates) if (await exists(path.join(dir, 'data/models/board/textures/materials.json'), io)) return dir; return null; })();
  if (configured && !await exists(path.join(root, 'data/models/board/textures/materials.json'), io)) throw Error('mmDataPath must point to mm-data (containing data/models/board/textures/materials.json)');
  const models = root ? await io.realpath(path.join(root, 'data/models')) : path.dirname(file);
  return { root, models, textures: path.join(models, 'board/textures') };
}

async function resolveLocal(base, uri, boundaries, dependencies, io = fs) {
  if (typeof uri !== 'string' || /[?#\x00]/.test(uri) || /^[a-z][a-z\d+.-]*:/i.test(uri) || /^[\\/]/.test(uri)) throw Error(`Only local relative asset paths are allowed: ${uri}`);
  const target = path.resolve(base, decodeURIComponent(uri));
  if (!boundaries.some(root => inside(root, target))) throw Error(`Asset path leaves its allowed folder: ${uri}`);
  dependencies.add(target);
  const real = await io.realpath(target);
  if (!boundaries.some(root => inside(root, real))) throw Error(`Asset link leaves its allowed folder: ${uri}`);
  return target;
}
async function materialSpec(file, roots, urlFor, dependencies, io = fs) {
  const resolve = (base, uri, boundaries) => resolveLocal(base, uri, boundaries, dependencies, io);
  dependencies.add(file);
  const spec = await readTres(file, roots.textures, resolve, io);
  return { ...spec, maps: Object.fromEntries(await Promise.all(Object.entries(spec.maps).filter(([, p]) => p).map(async ([role, p]) => [role, { file: p, url: await urlFor(p, (await io.stat(p)).mtimeMs) }]))) };
}

async function loadAsset(file, roots, urlFor = p => p, variant = '', io = fs, bytes) {
  bytes ||= await io.readFile(file);
  const { json, binary } = readGlb(bytes);
  const original = structuredClone(json), diagnostics = [], dependencies = new Set([file]);
  const allowed = [roots.models, path.dirname(file)];
  const resolve = (base, uri, boundaries = allowed) => resolveLocal(base, uri, boundaries, dependencies, io);
  const localUrl = async p => urlFor(p, (await io.stat(p)).mtimeMs);
  const imagePaths = new Map();
  for (const [index, image] of (json.images || []).entries()) {
    if (!image.uri || image.uri.startsWith('data:image/')) continue;
    const target = await resolve(path.dirname(file), image.uri);
    imagePaths.set(index, target); image.uri = await localUrl(target);
  }
  for (const [i, buffer] of (json.buffers || []).entries()) {
    if (buffer.uri) {
      if (!buffer.uri.startsWith('data:')) buffer.uri = await localUrl(await resolve(path.dirname(file), buffer.uri));
    } else if (i === 0 && binary) buffer.uri = `data:application/octet-stream;base64,${binary.toString('base64')}`;
    else throw Error('Missing GLB geometry buffer');
  }
  const variants = new Set(), surfaces = [];
  for (const [index, material] of (json.materials || []).entries()) {
    const changes = variant === 'snow' ? material.extras?.mmSnow : undefined;
    if (material.extras?.mmSnow) variants.add('snow');
    if (changes) {
      if (changes.name) material.name = changes.name;
      for (const [role, uri] of Object.entries(changes.textures || {})) {
        const target = await resolve(path.dirname(file), uri);
        const image = json.images.length; json.images.push({ uri: await localUrl(target) }); imagePaths.set(image, target);
        const slot = role === 'baseColor' ? material.pbrMetallicRoughness : material;
        const key = ({ baseColor: 'baseColorTexture', normal: 'normalTexture', occlusion: 'occlusionTexture', emissive: 'emissiveTexture' })[role];
        if (!key || !slot?.[key]) continue;
        const previous = json.textures[slot[key].index];
        const texture = json.textures.length; json.textures.push({ ...previous, source: image }); slot[key] = { ...slot[key], index: texture };
      }
    }
    const texture = json.textures?.[material.pbrMetallicRoughness?.baseColorTexture?.index];
    const albedo = imagePaths.get(texture?.source);
    const surface = { index, name: material.name || `Material ${index}`, changes, gltf: original.materials[index], managed: null };
    if (albedo && inside(roots.textures, albedo) && albedo.endsWith('_albedo.png')) {
      const resource = albedo.replace(/_albedo\.png$/, '.tres'); dependencies.add(resource);
      try {
        const spec = await materialSpec(resource, roots, urlFor, dependencies, io);
        surface.managed = spec;
        if (spec.shader) diagnostics.push(`${material.name}: Godot ShaderMaterial is shown as a PBR approximation; custom lava/ice shader behavior requires the game.`);
        if (spec.maps.height || spec.scatter) diagnostics.push(`${material.name}: height uses bump preview; subsurface scattering and game parallax require the game.`);
      } catch (error) { diagnostics.push(`${material.name}: ${error.message}`); }
    }
    surfaces.push(surface);
  }
  if (json.skins?.length || json.animations?.length) diagnostics.push('This GLB has skinning/animation. The viewer supports glTF playback; the MegaMek rigid loader does not.');
  if (json.extensionsRequired?.length) diagnostics.push(`Required extensions: ${json.extensionsRequired.join(', ')}. MegaMek rejects required glTF extensions.`);
  if (json.materials?.some(m => m.extensions?.KHR_materials_emissive_strength)) diagnostics.push('KHR_materials_emissive_strength displays here but is not supported by the engine.');
  const descriptors = [];
  for (const entry of await io.readdir(path.dirname(file), { withFileTypes: true })) {
    if (!entry.isFile() || !entry.name.endsWith('.json')) continue;
    const candidate = path.join(path.dirname(file), entry.name);
    if ((await io.stat(candidate)).size > 2_000_000) continue;
    try {
      const doc = JSON.parse(await io.readFile(candidate, 'utf8'));
      if (doc.mesh === path.basename(file)) { descriptors.push({ file: candidate, data: doc }); dependencies.add(candidate); }
    } catch { /* Unrelated JSON is not a GLB dependency. */ }
  }
  const statistics = summarize(original, binary, bytes.length);
  return { file, name: path.basename(file), roots, document: json, metadata: original, statistics, surfaces, variants: [...variants], diagnostics, dependencies: [...dependencies], descriptors };
}
module.exports = { readGlb, inside, exists, findRoots, loadAsset, resolveLocal, materialSpec };
