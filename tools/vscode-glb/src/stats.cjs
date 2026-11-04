// Count referenced glTF vertices, not an entire shared POSITION buffer for every LOD.
function isHelperGroup(name) { return ['cut', 'stands', 'building_volumes'].includes(name); }

function indices(document, binary, accessorIndex) {
  const accessor = document.accessors[accessorIndex], count = accessor.count;
  if (!Number.isSafeInteger(count) || count < 0 || count > 50_000_000) throw Error('Invalid index count');
  const read = (viewIndex, offset, type, n, stride) => {
    const size = { 5121: 1, 5123: 2, 5125: 4 }[type];
    if (!size) throw Error('Invalid index component type');
    const view = document.bufferViews[viewIndex];
    if (view.buffer !== 0 || !binary) throw Error('Geometry statistics require embedded GLB buffers');
    const start = (view.byteOffset || 0) + offset, step = stride || view.byteStride || size;
    if (n && (offset + (n - 1) * step + size > view.byteLength || start + (n - 1) * step + size > binary.length)) throw Error('Index accessor exceeds its buffer');
    return Array.from({ length: n }, (_, i) => size === 1 ? binary.readUInt8(start + i * step) : size === 2 ? binary.readUInt16LE(start + i * step) : binary.readUInt32LE(start + i * step));
  };
  const result = accessor.bufferView === undefined ? Array(count).fill(0) : read(accessor.bufferView, accessor.byteOffset || 0, accessor.componentType, count);
  if (accessor.sparse) {
    const { count: n, indices: offsets, values } = accessor.sparse;
    const targets = read(offsets.bufferView, offsets.byteOffset || 0, offsets.componentType, n);
    const replacements = read(values.bufferView, values.byteOffset || 0, accessor.componentType, n);
    targets.forEach((target, i) => { if (target >= count) throw Error('Sparse index outside accessor'); result[target] = replacements[i]; });
  }
  return result;
}
function summarize(document, binary, fileBytes) {
  const rows = new Map(), cached = new Map(), nodes = document.nodes || [];
  const children = new Set(nodes.flatMap(n => n.children || []));
  const roots = document.scenes?.[document.scene ?? 0]?.nodes || nodes.map((_, i) => i).filter(i => !children.has(i));
  function visit(index, group, ancestors) {
    if (ancestors.has(index)) throw Error('Cyclic node hierarchy');
    const node = nodes[index]; if (!node) throw Error('Invalid node reference');
    group = node.name?.match(/-lod([0-3])$/) ? `LOD ${node.name.match(/-lod([0-3])$/)[1]}` : isHelperGroup(node.name) ? 'Helpers' : group;
    if (!rows.has(group)) rows.set(group, { name: group, vertices: new Map(), triangles: 0, primitives: 0, meshes: 0, materials: new Set(), nodes: 0 });
    const row = rows.get(group); row.nodes++;
    if (node.mesh !== undefined) {
      row.meshes++;
      for (const primitive of document.meshes[node.mesh].primitives) {
        const position = primitive.attributes.POSITION, accessor = document.accessors[position];
        if (!row.vertices.has(position)) row.vertices.set(position, new Set());
        const references = row.vertices.get(position);
        let values;
        if (primitive.indices === undefined) values = Array.from({ length: accessor.count }, (_, i) => i);
        else { if (!cached.has(primitive.indices)) cached.set(primitive.indices, indices(document, binary, primitive.indices)); values = cached.get(primitive.indices); }
        values.forEach(i => { if (i >= accessor.count) throw Error('Vertex index outside POSITION accessor'); references.add(i); });
        const mode = primitive.mode ?? 4; row.triangles += mode === 4 ? values.length / 3 : mode === 5 || mode === 6 ? Math.max(0, values.length - 2) : 0;
        row.primitives++; if (primitive.material !== undefined) row.materials.add(primitive.material);
      }
    }
    const next = new Set(ancestors); next.add(index); for (const child of node.children || []) visit(child, group, next);
  }
  roots.forEach(root => visit(root, 'Scene', new Set()));
  return { fileBytes, images: (document.images || []).length, embeddedImages: (document.images || []).filter(i => i.bufferView !== undefined).length,
    rows: [...rows.values()].filter(r => r.meshes || r.name.startsWith('LOD')).map(r => ({ ...r, vertices: [...r.vertices.values()].reduce((n, v) => n + v.size, 0), materials: r.materials.size })) };
}
module.exports = { summarize, indices, isHelperGroup };
