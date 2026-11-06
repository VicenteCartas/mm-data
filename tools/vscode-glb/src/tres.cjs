// Read only the documented Godot material subset. No shader source is executed.
const fs = require('node:fs/promises');
const path = require('node:path');

function properties(text) {
  const resources = new Map(), props = {}; let section = '', kind;
  for (const line of text.replace(/^\uFEFF/, '').split(/\r?\n/).map(s => s.trim())) {
    if (!line || line.startsWith(';')) continue;
    if (line.startsWith('[')) {
      section = line.slice(1).split(/[\s\]]/)[0];
      const attrs = Object.fromEntries([...line.matchAll(/(\w+)=("(?:[^"\\]|\\.)*"|[^\s\]]+)/g)].map(([, k, v]) => [k, v.startsWith('"') ? JSON.parse(v) : v]));
      if (section === 'gd_resource') kind = attrs.type;
      if (section === 'ext_resource') resources.set(attrs.id, attrs.path);
    } else if (section === 'resource') {
      const at = line.indexOf('=');
      if (at >= 0) props[line.slice(0, at).trim()] = line.slice(at + 1).trim();
    }
  }
  return { resources, props, kind };
}

async function readTres(file, root, resolve, io = fs) {
  let { resources, props, kind } = properties(await io.readFile(file, 'utf8'));
  if (!['StandardMaterial3D', 'ShaderMaterial'].includes(kind)) throw Error(`Unsupported material type: ${kind}`);
  const dependency = async key => {
    if (!(key in props)) return null;
    const match = props[key].match(/^ExtResource\(\s*("[^"]+"|\d+)\s*\)$/);
    const uri = match && resources.get(match[1].replaceAll('"', ''));
    if (!uri) throw Error(`Invalid texture reference ${key} in ${file}`);
    return resolve(uri.startsWith('res://') ? root : path.dirname(file), uri.replace(/^res:\/\//, ''), [root]);
  };
  const shader = kind === 'ShaderMaterial';
  if (shader) {
    const shaderFile = await dependency('shader');
    if (!shaderFile) throw Error(`Missing shader in ${file}`);
    const code = (await io.readFile(shaderFile, 'utf8')).replace(/\/\/[^\n]*|\/\*[\s\S]*?\*\//g, '');
    const uniforms = Object.fromEntries([...code.matchAll(/\buniform\s+\w+\s+(\w+)\s*(?::[^=;]*)?(?:=([^;]*))?;/g)].map(m => [m[1], m[2]?.trim()]));
    props = { ...Object.fromEntries(Object.entries(uniforms).filter(([, v]) => v)), ...Object.fromEntries(Object.entries(props).filter(([k]) => k.startsWith('shader_parameter/') && k.slice(17) in uniforms).map(([k, v]) => [k.slice(17), v])) };
  }
  const num = (key, fallback) => {
    const n = Number(props[key] ?? fallback);
    if (!Number.isFinite(n)) throw Error(`Invalid ${key} in ${file}`);
    return n;
  };
  const color = (key, fallback) => {
    if (!props[key]) return fallback;
    const m = props[key].match(/^(?:Color|vec4)\(([^)]+)\)$/);
    if (!m) throw Error(`Invalid ${key} in ${file}`);
    let v = m[1].split(',').map(Number); if (v.length === 1) v = Array(4).fill(v[0]);
    if (v.length !== 4 || !v.every(Number.isFinite)) throw Error(`Invalid ${key} in ${file}`);
    return v;
  };
  const on = key => props[key] === 'true';
  const result = { file, shader, tint: color(shader ? 'albedo' : 'albedo_color', [1, 1, 1, 1]), roughness: num('roughness', 1), metallic: num('metallic', 0), normalScale: num('normal_scale', 1), maps: {},
    emissionColor: !shader && on('emission_enabled') ? color('emission', [0, 0, 0, 1]) : [0, 0, 0, 1], emissionEnergy: num('emission_energy_multiplier', num('emission_energy', 1)), emissionOperator: num('emission_operator', 0),
    nightEmission: props['metadata/mmEmission'] === '"night"', paintMask: on('metadata/mmPaintMask'),
    heightScale: num('heightmap_scale', 5), heightFlip: on('heightmap_flip_texture'), scatter: num(shader ? 'subsurface_scattering_strength' : 'subsurf_scatter_strength', 0),
    transparent: !shader && num('transparency', 0) !== 0, alphaCutoff: num('alpha_scissor_threshold', .5), doubleSided: !shader && num('cull_mode', 0) === 2 };
  const roles = {
    albedo: shader ? 'texture_albedo' : 'albedo_texture',
    normal: shader ? 'texture_normal' : on('normal_enabled') ? 'normal_texture' : null,
    ao: shader ? 'texture_orm' : on('ao_enabled') ? 'ao_texture' : null,
    roughness: shader ? 'texture_orm' : 'roughness_texture', metallic: shader ? 'texture_orm' : 'metallic_texture',
    emission: shader ? 'texture_emission' : on('emission_enabled') ? 'emission_texture' : null,
    height: shader ? 'texture_height' : on('heightmap_enabled') ? (props.heightmap_texture ? 'heightmap_texture' : 'depth_texture') : null,
    scatter: shader ? 'texture_subsurface_scattering' : on('subsurf_scatter_enabled') ? 'subsurf_scatter_texture' : null
  };
  for (const [role, key] of Object.entries(roles)) {
    if (key) result.maps[role] = await dependency(key);
  }
  result.channels = {};
  for (const [role, channel] of [['ao', 0], ['roughness', 1], ['metallic', 2]]) {
    const n = shader ? channel : num(`${role}_texture_channel`, 0);
    if (!Number.isInteger(n) || n < 0 || n > 4) throw Error(`Invalid ${role} channel in ${file}`);
    result.channels[role] = n;
  }
  return result;
}
module.exports = { properties, readTres };
