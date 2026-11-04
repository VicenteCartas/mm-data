const displayKeys = ['lod', 'projection', 'shading', 'wire', 'grid', 'helpers', 'bounds', 'exposure', 'environment', 'bloom', 'nightLights', 'background', 'label'];
function viewState(value) {
  if (!value || !['0', '1', '2', '3', 'all'].includes(value.lod) || !['perspective', 'ortho'].includes(value.projection)
    || !['pbr', 'clay', 'normal', 'uv', 'checker'].includes(value.shading) || !/^#[0-9a-f]{6}$/i.test(value.background)
    || typeof value.label !== 'string' || value.label.length > 64 || typeof value.variant !== 'string' || value.variant.length > 100) return null;
  for (const key of ['wire', 'grid', 'helpers', 'bounds', 'bloom']) if (typeof value[key] !== 'boolean') return null;
  if (value.nightLights !== undefined && typeof value.nightLights !== 'boolean') return null;
  for (const key of ['exposure', 'environment']) if (!Number.isFinite(Number(value[key])) || Number(value[key]) < 0 || Number(value[key]) > 3) return null;
  const camera = value.camera;
  if (!camera || !['position', 'target'].every(k => Array.isArray(camera[k]) && camera[k].length === 3 && camera[k].every(n => Number.isFinite(n) && Math.abs(n) <= 1e12))
    || !['zoom', 'span'].every(k => Number.isFinite(camera[k]) && camera[k] > 0 && camera[k] <= 1e12)) return null;
  if (value.colors !== undefined && (!Array.isArray(value.colors) || value.colors.length > 128 || value.colors.some(c => !/^#[0-9a-f]{6}$/i.test(c)))) return null;
  return { ...Object.fromEntries(displayKeys.map(k => [k, value[k]])), nightLights: value.nightLights ?? false, variant: value.variant, colors: value.colors, camera: structuredClone(camera) };
}
module.exports = { displayKeys, viewState };
