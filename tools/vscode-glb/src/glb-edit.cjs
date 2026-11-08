const path = require('node:path');
const { readGlb } = require('./assets.cjs');
const { editAttributes, sampling } = require('./surface-edit.cjs');

// JSON edits retain binary chunks verbatim; attribute edits supply an extended BIN with its original bytes intact.
function writeGlb(bytes, json, binary) {
  readGlb(bytes);
  const raw = Buffer.from(JSON.stringify(json)), padded = Buffer.alloc(Math.ceil(raw.length / 4) * 4, 0x20); raw.copy(padded);
  const chunks = [];
  for (let at = 12; at < bytes.length;) {
    const size = bytes.readUInt32LE(at), type = bytes.readUInt32LE(at + 4);
    if (type === 0x4e4f534a) { const header = Buffer.alloc(8); header.writeUInt32LE(padded.length); header.writeUInt32LE(type, 4); chunks.push(header, padded); }
    else if (type === 0x004e4942 && binary) { const header = Buffer.alloc(8); header.writeUInt32LE(binary.length); header.writeUInt32LE(type, 4); chunks.push(header, binary); }
    else chunks.push(bytes.subarray(at, at + 8 + size));
    at += size + 8;
  }
  const header = Buffer.from(bytes.subarray(0, 12)); header.writeUInt32LE(12 + chunks.reduce((sum, chunk) => sum + chunk.length, 0), 8);
  return Buffer.concat([header, ...chunks]);
}
function relativeUri(from, to) {
  const relative = path.relative(path.dirname(from), to);
  if (path.isAbsolute(relative)) throw Error('GLB and external textures must be on the same drive');
  return relative.split(path.sep).map(encodeURIComponent).join('/');
}
function rebaseGlb(bytes, from, to) {
  if (path.dirname(from) === path.dirname(to)) return bytes;
  const { json } = readGlb(bytes);
  const uri = value => /^[a-z][a-z\d+.-]*:/i.test(value) ? value : relativeUri(to, path.resolve(path.dirname(from), decodeURIComponent(value)));
  for (const item of [...(json.images || []), ...(json.buffers || [])]) if (item.uri) item.uri = uri(item.uri);
  for (const material of json.materials || []) {
    const textures = material.extras?.mmSnow?.textures || {};
    for (const [role, value] of Object.entries(textures)) textures[role] = uri(value);
  }
  return writeGlb(bytes, json);
}
function uniqueName(items, base) {
  const names = new Set(items.map(item => item.name)); let name = base, number = 2;
  while (names.has(name)) name = `${base}-${number++}`;
  return name;
}
function properties(material, changes, managed) {
  if (!changes || typeof changes !== 'object' || Array.isArray(changes)) throw Error('Invalid material properties');
  const allowed = ['baseColorFactor', 'emissiveFactor', 'emissionMode', 'roughnessFactor', 'metallicFactor', 'alphaMode', 'alphaCutoff', 'doubleSided'];
  if (Object.keys(changes).some(key => !allowed.includes(key))) throw Error('Unsupported material property');
  const factor = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1;
  for (const [key, value] of Object.entries(changes)) {
    if (key === 'emissionMode') {
      if (!['inherit', 'always', 'night', 'off'].includes(value)) throw Error('Invalid emissionMode');
      if (value !== 'inherit') (material.extras ||= {}).mmEmission = value;
      else if (material.extras) { delete material.extras.mmEmission; if (!Object.keys(material.extras).length) delete material.extras; }
      continue;
    }
    if (key === 'doubleSided' ? typeof value !== 'boolean' : key === 'alphaMode' ? !['OPAQUE', 'MASK', 'BLEND'].includes(value)
      : key.endsWith('ColorFactor') || key === 'emissiveFactor' ? !Array.isArray(value) || value.length !== (key === 'baseColorFactor' ? 4 : 3) || !value.every(factor) : !factor(value)) throw Error(`Invalid ${key}`);
    if (managed && ['roughnessFactor', 'metallicFactor'].includes(key)) throw Error('Shared roughness and metallic are controlled by the .tres material');
    if (['baseColorFactor', 'roughnessFactor', 'metallicFactor'].includes(key)) (material.pbrMetallicRoughness ||= {})[key] = value;
    else material[key] = value;
  }
}
function editTargets(json, edit) {
  const { node, primitive } = edit.target;
  if (edit.scope !== 'material') return [{ node, primitive }];
  const material = json.meshes[json.nodes[node].mesh].primitives[primitive].material;
  if (!Number.isInteger(material)) throw Error('This surface has no assigned material; choose This surface');
  return (json.nodes || []).flatMap((n, ni) => (json.meshes?.[n.mesh]?.primitives || []).flatMap((p, pi) => p.material === material ? [{ node: ni, primitive: pi }] : []));
}
function editGlb(bytes, edit, file, shared, managed = false) {
  const { json, binary } = readGlb(bytes);
  const { node: nodeIndex, primitive: primitiveIndex } = edit.target || {};
  if (!Number.isInteger(nodeIndex) || !Number.isInteger(primitiveIndex) || nodeIndex < 0 || primitiveIndex < 0 || !['surface', 'material'].includes(edit.scope)) throw Error('Select a valid GLB surface');
  const node = json.nodes?.[nodeIndex], mesh = json.meshes?.[node?.mesh], primitive = mesh?.primitives?.[primitiveIndex];
  if (!primitive) throw Error('Selected surface no longer exists');
  const previous = primitive.material, materials = json.materials ||= [], source = materials[previous] || {};
  const targets = editTargets(json, edit);
  let index;
  const attributesEdit = ['placement', 'vertexTint'].includes(edit.kind);
  if (attributesEdit) index = previous;
  else if (edit.kind === 'existing') {
    if (!Number.isInteger(edit.material) || !materials[edit.material]) throw Error('Select a material from this GLB');
    index = edit.material;
  } else {
    const material = structuredClone(source);
    if (edit.kind === 'shared') {
      if (!shared?.spec?.maps.albedo) throw Error('Select an available material from the palette');
      for (const target of targets) if (json.meshes[json.nodes[target.node].mesh].primitives[target.primitive].attributes?.TEXCOORD_0 === undefined) throw Error('This surface has no UV coordinates. Unwrap it in Blender before assigning a texture.');
      const images = json.images ||= [], textures = json.textures ||= [], uri = relativeUri(file, shared.spec.maps.albedo.file);
      let image = images.findIndex(item => item.uri === uri);
      if (image < 0) { image = images.length; images.push({ uri }); }
      const oldInfo = source.pbrMetallicRoughness?.baseColorTexture, sampler = textures[oldInfo?.index]?.sampler;
      let texture = textures.findIndex(item => item.source === image && item.sampler === sampler && !item.extensions);
      if (texture < 0) { texture = textures.length; textures.push({ source: image, ...(sampler === undefined ? {} : { sampler }) }); }
      material.pbrMetallicRoughness = { baseColorFactor: source.pbrMetallicRoughness?.baseColorFactor || [1, 1, 1, 1], baseColorTexture: { ...oldInfo, index: texture }, roughnessFactor: 1, metallicFactor: 0 };
      delete material.normalTexture; delete material.occlusionTexture;
      if (material.extras) { delete material.extras.mmPaintMask; if (!Object.keys(material.extras).length) delete material.extras; } // The .tres says.
      if (edit.keepEmission === false) { delete material.emissiveTexture; delete material.emissiveFactor; if (material.extensions) delete material.extensions.KHR_materials_emissive_strength; }
      material.alphaMode = shared.spec.paintMask ? 'OPAQUE' : shared.spec.transparent ? 'MASK' : 'OPAQUE';
      if (material.alphaMode === 'MASK') material.alphaCutoff = shared.spec.alphaCutoff; else delete material.alphaCutoff;
      material.doubleSided = source.doubleSided ?? shared.spec.doubleSided;
    } else if (edit.kind === 'properties') properties(material, edit.changes, managed);
    else if (edit.kind === 'sampling') sampling(json, material, edit.sampling);
    else throw Error('Unknown material edit');
    if (edit.kind !== 'shared' && JSON.stringify(material) === JSON.stringify(source)) return bytes;
    const users = (json.nodes || []).reduce((count, n) => count + (json.meshes?.[n.mesh]?.primitives || []).filter(p => p.material === previous).length, 0);
    if (Number.isInteger(previous) && users === targets.length) { index = previous; materials[index] = material; }
    else { index = materials.length; material.name = uniqueName(materials, managed ? `${source.name}#surface` : source.name || shared?.name || 'Material'); materials.push(material); }
    if (edit.kind === 'shared') {
      const others = materials.filter((_, i) => i !== index);
      material.name = others.some(item => item.name === shared.id) ? uniqueName(others, `${shared.id}#surface`) : shared.id;
    }
  }
  if (index === previous && edit.kind === 'existing') return bytes;
  for (const target of targets) {
    const n = json.nodes[target.node];
    // Changing one instance must not silently reassign other nodes which share its mesh.
    if (edit.scope === 'surface' && json.nodes.some((other, ni) => ni !== target.node && other.mesh === n.mesh)) {
      const copy = structuredClone(json.meshes[n.mesh]); copy.name = uniqueName(json.meshes, copy.name || 'Mesh');
      n.mesh = json.meshes.length; json.meshes.push(copy);
    }
    if (!attributesEdit) json.meshes[n.mesh].primitives[target.primitive].material = index;
  }
  return writeGlb(bytes, json, attributesEdit ? editAttributes(json, binary, targets, edit) : undefined);
}
module.exports = { writeGlb, rebaseGlb, editGlb, editTargets };
