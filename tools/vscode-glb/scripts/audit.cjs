const fs = require('node:fs/promises');
const path = require('node:path');
const { readGlb, findRoots, loadAsset } = require('../src/assets.cjs');
async function files(dir) { const result = []; for (const e of await fs.readdir(dir, { withFileTypes: true })) { const p = path.join(dir, e.name); if (e.isDirectory()) result.push(...await files(p)); else if (e.name.endsWith('.glb')) result.push(p); } return result; }
async function main() {
  const dataRoot = path.resolve(__dirname, '../../..'), root = path.join(dataRoot, 'data/models');
  const all = await files(root), stats = { files: all.length, embedded: 0, external: 0, slots: [], variants: [], helpers: [], kits: 0, extensions: new Set(), warnings: [], errors: [] };
  for (const file of all) {
    const relative = path.relative(root, file);
    try {
      const { json } = readGlb(await fs.readFile(file));
      stats.embedded += (json.images || []).some(i => i.bufferView !== undefined) ? 1 : 0;
      stats.external += (json.images || []).some(i => i.uri) ? 1 : 0;
      if (json.extras?.mmColourSlots) stats.slots.push(relative);
      if (json.materials?.some(m => m.extras?.mmSnow)) stats.variants.push(relative);
      if (json.nodes?.some(n => ['cut', 'stands'].includes(n.name))) stats.helpers.push(relative);
      if (json.nodes?.some(n => /-base\d+/.test(n.name))) stats.kits++;
      (json.extensionsUsed || []).forEach(e => stats.extensions.add(e));
      const loaded = await loadAsset(file, await findRoots(file));
      if (loaded.diagnostics.length) stats.warnings.push({ file: relative, diagnostics: loaded.diagnostics });
    } catch (error) { stats.errors.push({ file: relative, error: error.message }); }
  }
  stats.extensions = [...stats.extensions];
  await fs.mkdir(path.join(__dirname, '../test-output'), { recursive: true });
  await fs.writeFile(path.join(__dirname, '../test-output/audit.json'), JSON.stringify(stats, null, 2));
  console.log(JSON.stringify({ ...stats, slots: stats.slots.length, variants: stats.variants.length, helpers: stats.helpers.length, warnings: stats.warnings.length, errors: stats.errors.length }));
}
if (require.main === module) main().catch(e => { console.error(e); process.exitCode = 1; });
module.exports = { files };
