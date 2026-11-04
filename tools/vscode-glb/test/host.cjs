const vscode = require('vscode');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const { chromium } = require('playwright-core');
const { gitFixture } = require('./git-fixture.cjs');
const { readGlb } = require('../src/assets.cjs');
const { rebaseGlb } = require('../src/glb-edit.cjs');
const { readAttribute } = require('../src/attributes.cjs');
const root = path.resolve(__dirname, '..'), models = path.resolve(root, '../../data/models');
function triangle(size) {
  const document = { asset: { version: '2.0' }, scene: 0, scenes: [{ nodes: [0] }], nodes: [{ name: 'test-lod0', children: [1] }, { name: 'triangle', mesh: 0 }], meshes: [{ primitives: [{ attributes: { POSITION: 0 } }] }], buffers: [{ byteLength: 36 }], bufferViews: [{ buffer: 0, byteLength: 36 }], accessors: [{ bufferView: 0, componentType: 5126, count: 3, type: 'VEC3', min: [0, 0, 0], max: [size, size, 0] }] };
  const raw = JSON.stringify(document), json = Buffer.from(raw.padEnd(Math.ceil(raw.length / 4) * 4));
  const file = Buffer.alloc(28 + json.length + 36); file.writeUInt32LE(0x46546c67); file.writeUInt32LE(2, 4); file.writeUInt32LE(file.length, 8); file.writeUInt32LE(json.length, 12); file.writeUInt32LE(0x4e4f534a, 16); json.copy(file, 20); file.writeUInt32LE(36, 20 + json.length); file.writeUInt32LE(0x004e4942, 24 + json.length);
  [0, 0, 0, size, 0, 0, 0, size, 0].forEach((value, i) => file.writeFloatLE(value, 28 + json.length + i * 4)); return file;
}
exports.run = async () => {
  const extension = vscode.extensions.getExtension('megamek-local.megamek-glb-viewer'); assert(extension); await extension.activate();
  assert((await vscode.commands.getCommands()).includes('megamekGlb.open'));
  await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  await vscode.commands.executeCommand('vscode.openWith', vscode.Uri.file(path.join(models, 'buildings/walls/medium/straight.glb')), 'megamek.glb');
  assert(vscode.window.tabGroups.all.flatMap(group => group.tabs).some(tab => tab.input instanceof vscode.TabInputCustom && tab.input.viewType === 'megamek.glb'));
  const browser = await chromium.connectOverCDP(`http://127.0.0.1:${process.env.MM_CDP_PORT}`);
  const fixture = path.join(root, 'test-output/reload-fixture.glb');
  const editFixture = path.join(root, 'test-output/material-edit.glb');
  const paintFixture = path.join(root, 'test-output/paint-edit.glb');
  let frame, window, comparison;
  async function findEditor(name, revision) {
    frame = null;
    const until = Date.now() + 45000;
    while (!frame && Date.now() < until) {
      for (const page of browser.contexts().flatMap(c => c.pages())) {
        for (const candidate of page.frames()) {
          try {
            if (await candidate.locator('#filename').count() && (await candidate.locator('#filename').textContent()) === name && (!revision || await candidate.locator('#revision').textContent() === revision) && (await candidate.locator('#status').textContent()).startsWith('Authored GLB')) {
              // A restored editor can still be detaching while the new custom editor opens.
              await candidate.waitForTimeout(300);
              if (candidate.isDetached()) continue;
              frame = candidate; window = page; break;
            }
          } catch { /* Frame is navigating. */ }
        }
        if (frame) break;
      }
      if (!frame) await new Promise(resolve => setTimeout(resolve, 200));
    }
    assert(frame, 'Custom editor webview must exist');
  }
  try {
    await findEditor('straight.glb');
    await frame.waitForFunction(() => document.getElementById('status').textContent.startsWith('Authored GLB'), null, { timeout: 45000 });
    assert.equal(await frame.locator('#filename').textContent(), 'straight.glb');
    assert(await frame.locator('#lodStats tbody tr').count() >= 1);
    await frame.locator('[data-tab="materials"]').click(); assert(await frame.locator('#materialList option').count() > 0);
    await window.screenshot({ path: path.join(root, 'test-output/vscode-webview.png') });
    if (!process.env.MM_SKIP_ENGINE_TEST) {
      await frame.locator('[data-tab="test"]').click(); await frame.locator('[data-preset="straight"]').click(); await frame.locator('#test').click();
      await frame.waitForFunction(() => /^(PASS|FAIL):/.test(document.getElementById('engineStatus').textContent), null, { timeout: 45000 });
      assert.match(await frame.locator('#engineStatus').textContent(), /^PASS:/);
      await window.screenshot({ path: path.join(root, 'test-output/vscode-engine-test.png') });
    } else console.log('Engine invocation skipped for this editor-only run.');
    const wall = path.join(models, 'buildings/walls/medium/straight.glb'), original = rebaseGlb(await fs.readFile(wall), wall, editFixture);
    await fs.writeFile(editFixture, original);
    const editUri = vscode.Uri.file(editFixture);
    await vscode.commands.executeCommand('vscode.openWith', editUri, 'megamek.glb'); await findEditor('material-edit.glb');
    const editingTab = () => vscode.window.tabGroups.all.flatMap(group => group.tabs).find(tab => tab.input instanceof vscode.TabInputCustom && tab.input.uri.toString() === editUri.toString());
    await frame.locator('[data-tab="palette"]').click();
    await frame.waitForFunction(() => document.querySelectorAll('#paletteGrid button').length === 8 && document.querySelector('#paletteGrid img').naturalWidth > 0, null, { timeout: 30000 });
    await frame.locator('#paletteGrid button').last().scrollIntoViewIfNeeded();
    await frame.waitForFunction(() => [...document.querySelectorAll('#paletteGrid img')].at(-1).naturalWidth > 0);
    assert.match(await frame.locator('#paletteCount').textContent(), /\d+ of \d+ materials/);
    const viewport = await frame.locator('#canvas').boundingBox();
    await frame.locator('#canvas').click({ position: { x: viewport.width * .5, y: viewport.height * .55 } });
    assert.notEqual(await frame.locator('#surfaceTarget').inputValue(), '', 'Viewport picking must select the clicked primitive');
    assert(await frame.locator('#tab-palette').evaluate(element => element.classList.contains('active')));
    // Deterministic authored surface selection also covers meshes with several primitives.
    await frame.locator('#surfaceTarget').selectOption('0:0');
    const oldMaterial = await frame.locator('#surfaceInfo').textContent();
    await frame.locator('#paletteSearch').fill('structures/common/rusted-steel');
    await frame.locator('[data-material="structures/common/rusted-steel"]').click();
    await frame.waitForFunction(() => !document.getElementById('assignPalette').disabled);
    await window.screenshot({ path: path.join(root, 'test-output/vscode-material-palette.png') });
    await frame.locator('#assignPalette').click();
    await frame.waitForFunction(() => document.getElementById('surfaceInfo').textContent.includes('structures/common/rusted-steel') && document.getElementById('editNotice').textContent.includes('Unsaved'));
    assert(editingTab().isDirty); assert.deepEqual(await fs.readFile(editFixture), original, 'Assign must not write until Save');
    await frame.locator('#undoEdit').click(); await frame.waitForFunction(text => document.getElementById('surfaceInfo').textContent === text, oldMaterial);
    assert(!editingTab().isDirty);
    await frame.locator('#redoEdit').click(); await frame.waitForFunction(() => document.getElementById('surfaceInfo').textContent.includes('structures/common/rusted-steel'));
    await frame.locator('#saveGlb').click(); await frame.waitForFunction(() => document.getElementById('saveGlb').disabled && !document.getElementById('editNotice').textContent.includes('Unsaved'));
    assert(!editingTab().isDirty);
    const saved = readGlb(await fs.readFile(editFixture)), before = readGlb(original);
    assert.deepEqual(saved.binary, before.binary); assert.deepEqual(saved.json.accessors, before.json.accessors);
    const assigned = saved.json.materials[saved.json.meshes[saved.json.nodes[0].mesh].primitives[0].material]; assert.match(assigned.name, /rusted-steel/);
    await frame.locator('#editPlacement').click();
    assert(await frame.locator('#uvOffsetU').isVisible()); assert(await frame.locator('#uvScaleU').isVisible()); assert(await frame.locator('#uvRotation').isVisible());
    assert.equal(await frame.locator('#applyPlacement, #applyProperties').count(), 0);
    await frame.locator('#surfaceProperties summary').click();
    assert(await frame.locator('#editRoughness').isDisabled());
    await frame.locator('#editTint').fill('#55cc99');
    // No Apply or wait for the preview: Ctrl+S must include the most recent input.
    await frame.locator('#editTint').press('Control+s');
    await frame.waitForFunction(() => document.getElementById('saveGlb').disabled && !document.getElementById('editNotice').textContent.includes('Unsaved'));
    assert(!editingTab().isDirty);
    await vscode.commands.executeCommand('workbench.action.closeActiveEditor');
    await vscode.commands.executeCommand('vscode.openWith', editUri, 'megamek.glb'); await findEditor('material-edit.glb');
    await frame.locator('[data-tab="materials"]').click(); await frame.locator('#surfaceTarget').selectOption('0:0');
    assert.equal(await frame.locator('#editTint').inputValue(), '#55cc99'); assert.match(await frame.locator('#surfaceInfo').textContent(), /rusted-steel/);
    await frame.evaluate(() => { const input = document.getElementById('uvOffsetU'); input.focus(); for (const value of [.1, .2, .3, .4]) { input.value = value; input.dispatchEvent(new Event('input', { bubbles: true })); } });
    await frame.locator('#undoEdit').click(); await frame.waitForFunction(() => document.getElementById('uvOffsetU').value === '0' && document.getElementById('uvReset').disabled);
    assert(!editingTab().isDirty, 'A continuous adjustment must undo in one step');
    await frame.locator('#redoEdit').click(); await frame.waitForFunction(() => document.getElementById('uvOffsetU').value === '0.4');
    await frame.locator('#undoEdit').click(); await frame.waitForFunction(() => document.getElementById('uvOffsetU').value === '0');
    await frame.locator('#uvOffsetU').fill('0.25'); await frame.locator('#uvOffsetV').fill('-0.5'); await frame.locator('#uvLinkScale').check(); await frame.locator('#uvScaleU').fill('2'); assert.equal(await frame.locator('#uvScaleV').inputValue(), '2');
    await frame.locator('#uvLinkScale').uncheck(); await frame.locator('#uvScaleV').fill('3'); await frame.locator('#uvTurnRight').click(); assert.equal(await frame.locator('#uvRotation').inputValue(), '90');
    await frame.locator('#previewChecker').click(); assert.equal(await frame.locator('#shading').inputValue(), 'checker');
    await frame.waitForFunction(() => document.getElementById('editNotice').textContent.includes('Unsaved') && !document.getElementById('saveGlb').disabled);
    await frame.locator('#saveGlb').click(); await frame.waitForFunction(() => document.getElementById('saveGlb').disabled && !document.getElementById('editNotice').textContent.includes('Unsaved'));
    const placed = readGlb(await fs.readFile(editFixture)), surface = placed.json.meshes[placed.json.nodes[0].mesh].primitives[0];
    assert.deepEqual(surface.extras.mmTexturePlacement.offset, [.25, -.5]); assert.deepEqual(surface.extras.mmTexturePlacement.scale, [2, 3]); assert.equal(surface.extras.mmTexturePlacement.rotation, 90);
    assert.deepEqual(placed.binary.subarray(0, before.binary.length), before.binary);
    await window.screenshot({ path: path.join(root, 'test-output/vscode-texture-placement.png') });
    await frame.locator('#placementAdvanced summary').click();
    await frame.locator('#uvReset').click(); await frame.waitForFunction(() => document.getElementById('uvOffsetU').value === '0' && document.getElementById('uvReset').disabled);
    await frame.locator('#undoEdit').click(); await frame.waitForFunction(() => document.getElementById('uvOffsetU').value === '0.25' && !document.getElementById('uvReset').disabled);
    assert(!editingTab().isDirty);
    await frame.locator('#previewMaterial').click(); await frame.locator('#textureSampling summary').click();
    assert.equal(await frame.locator('#applySampling').count(), 0);
    const originalWrap = await frame.locator('#wrapU').inputValue(), samplingDisk = await fs.readFile(editFixture);
    await frame.evaluate(() => { const input = document.getElementById('wrapU'); input.focus(); for (const value of ['33071', '33648']) { input.value = value; input.dispatchEvent(new Event('input', { bubbles: true })); } });
    await frame.locator('#undoEdit').click(); await frame.waitForFunction(value => document.getElementById('wrapU').value === value && !document.getElementById('editNotice').textContent.includes('Unsaved'), originalWrap);
    assert(!editingTab().isDirty, 'Continuous sampler adjustments must undo together');
    await frame.locator('#redoEdit').click(); await frame.waitForFunction(() => document.getElementById('wrapU').value === '33648' && document.getElementById('editNotice').textContent.includes('Unsaved'));
    await frame.locator('#wrapV').selectOption('33071'); await frame.locator('#minFilter').selectOption('9984'); await frame.locator('#magFilter').selectOption('9728');
    assert.deepEqual(await fs.readFile(editFixture), samplingDisk, 'Live sampling must not write before Save');
    await frame.locator('#magFilter').press('Control+s'); await frame.waitForFunction(() => document.getElementById('saveGlb').disabled && !document.getElementById('editNotice').textContent.includes('Unsaved'));
    const sampled = readGlb(await fs.readFile(editFixture)).json, samplerMaterial = sampled.materials[sampled.meshes[sampled.nodes[0].mesh].primitives[0].material], samplerTexture = sampled.textures[samplerMaterial.pbrMetallicRoughness.baseColorTexture.index];
    assert.equal(sampled.samplers[samplerTexture.sampler].wrapS, 33648); assert.equal(sampled.samplers[samplerTexture.sampler].wrapT, 33071);
    assert.equal(sampled.samplers[samplerTexture.sampler].minFilter, 9984); assert.equal(sampled.samplers[samplerTexture.sampler].magFilter, 9728);
    await vscode.commands.executeCommand('workbench.action.closeActiveEditor');
    await vscode.commands.executeCommand('vscode.openWith', editUri, 'megamek.glb'); await findEditor('material-edit.glb');
    await frame.locator('[data-tab="materials"]').click(); await frame.locator('#surfaceTarget').selectOption('0:0');
    if (!await frame.locator('#textureSampling').evaluate(element => element.open)) await frame.locator('#textureSampling summary').click();
    for (const [id, value] of [['wrapU', '33648'], ['wrapV', '33071'], ['minFilter', '9984'], ['magFilter', '9728']]) assert.equal(await frame.locator('#' + id).inputValue(), value);
    await window.screenshot({ path: path.join(root, 'test-output/vscode-live-sampling.png') });
    const tank = path.join(models, 'buildings/fuel_tanks/fuel_tank_light.glb'), fuelOriginal = rebaseGlb(await fs.readFile(tank), tank, paintFixture), fuelBefore = readGlb(fuelOriginal);
    await fs.writeFile(paintFixture, fuelOriginal);
    const paintNode = fuelBefore.json.nodes.findIndex(n => fuelBefore.json.meshes?.[n.mesh]?.primitives.some(p => fuelBefore.json.materials[p.material].name === 'paint'));
    const paintPrimitive = fuelBefore.json.meshes[fuelBefore.json.nodes[paintNode].mesh].primitives.findIndex(p => fuelBefore.json.materials[p.material].name === 'paint');
    await vscode.commands.executeCommand('vscode.openWith', vscode.Uri.file(paintFixture), 'megamek.glb'); await findEditor('paint-edit.glb');
    await frame.locator('[data-tab="materials"]').click(); await frame.locator('#surfaceTarget').selectOption(`${paintNode}:${paintPrimitive}`); await frame.locator('#vertexPaint summary').click();
    const swatches = await frame.locator('#vertexSwatches input').evaluateAll(inputs => inputs.map(input => input.value));
    const red = swatches.findIndex(hex => { const rgb = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16)); return rgb[0] > rgb[1] * 2 && rgb[0] > rgb[2] * 2; }); assert(red >= 0, 'Fuel tank red paint must have an authored swatch');
    await frame.locator('#vertexSwatches button').nth(red).click(); assert(await frame.locator('#paintMatch').isChecked());
    assert.equal(await frame.locator('#applyVertexPaint').count(), 0);
    await frame.evaluate(() => { const input = document.getElementById('paintColor'); input.focus(); for (const value of ['#22dd66', '#000000', '#2266dd']) { input.value = value; input.dispatchEvent(new Event('input', { bubbles: true })); } });
    await frame.waitForFunction(() => document.getElementById('editNotice').textContent.includes('Unsaved') && !document.getElementById('saveGlb').disabled);
    assert.deepEqual(await fs.readFile(paintFixture), fuelOriginal, 'Live paint must not write before Save');
    await frame.locator('#undoEdit').click(); await frame.waitForFunction(() => document.getElementById('restoreVertexPaint').disabled && !document.getElementById('editNotice').textContent.includes('Unsaved'));
    await frame.locator('#redoEdit').click(); await frame.waitForFunction(() => !document.getElementById('restoreVertexPaint').disabled && document.getElementById('editNotice').textContent.includes('Unsaved'));
    await frame.locator('#paintColor').fill('#3377ee'); await frame.locator('#paintColor').press('Control+s');
    await frame.waitForFunction(() => document.getElementById('saveGlb').disabled && !document.getElementById('editNotice').textContent.includes('Unsaved'));
    const fuelAfter = readGlb(await fs.readFile(paintFixture)), paint = fuelAfter.json.meshes[fuelAfter.json.nodes[paintNode].mesh].primitives[paintPrimitive], oldPaint = fuelBefore.json.meshes[fuelBefore.json.nodes[paintNode].mesh].primitives[paintPrimitive];
    assert.notEqual(paint.attributes.COLOR_0, oldPaint.attributes.COLOR_0); assert.equal(paint.attributes.TEXCOORD_0, oldPaint.attributes.TEXCOORD_0); assert.deepEqual(fuelAfter.binary.subarray(0, fuelBefore.binary.length), fuelBefore.binary);
    assert.notDeepEqual(readAttribute(fuelAfter.json, fuelAfter.binary, paint.attributes.COLOR_0).values, readAttribute(fuelBefore.json, fuelBefore.binary, oldPaint.attributes.COLOR_0).values);
    const savedPaint = readAttribute(fuelAfter.json, fuelAfter.binary, paint.attributes.COLOR_0).values;
    const peak = Math.max(...Array.from(savedPaint).filter((_, i) => i % 4 === 2)); assert(peak > .85, 'Immediate Ctrl+S must include the newest blue value');
    await vscode.commands.executeCommand('workbench.action.closeActiveEditor');
    await vscode.commands.executeCommand('vscode.openWith', vscode.Uri.file(paintFixture), 'megamek.glb'); await findEditor('paint-edit.glb');
    await frame.locator('[data-tab="materials"]').click(); await frame.locator('#surfaceTarget').selectOption(`${paintNode}:${paintPrimitive}`);
    if (!await frame.locator('#vertexPaint').evaluate(element => element.open)) await frame.locator('#vertexPaint summary').click();
    assert.deepEqual(await frame.locator('#vertexSwatches input').evaluateAll(inputs => inputs.map(input => input.value)), swatches, 'Reopening keeps the original paint targets');
    await frame.locator('#vertexSwatches button').nth(red).click();
    await frame.locator('#paintColor').fill('#dd6622'); await frame.locator('#paintColor').press('Control+s');
    await frame.waitForFunction(() => document.getElementById('saveGlb').disabled && !document.getElementById('editNotice').textContent.includes('Unsaved'));
    const recolored = readGlb(await fs.readFile(paintFixture)), recoloredPaint = recolored.json.meshes[recolored.json.nodes[paintNode].mesh].primitives[paintPrimitive];
    assert.notDeepEqual(readAttribute(recolored.json, recolored.binary, recoloredPaint.attributes.COLOR_0).values, savedPaint, 'The original red target remains editable after it was saved blue');
    await frame.locator('#editScope').selectOption('material'); await frame.locator('#paintColor').fill('#cc77ee'); await frame.locator('#paintColor').press('Control+s');
    await frame.waitForFunction(() => document.getElementById('saveGlb').disabled && !document.getElementById('editNotice').textContent.includes('Unsaved'));
    const allPaint = readGlb(await fs.readFile(paintFixture)).json;
    const paintParts = fuelBefore.json.nodes.flatMap((node, ni) => (fuelBefore.json.meshes?.[node.mesh]?.primitives || []).flatMap((part, pi) => part.material === oldPaint.material ? [{ before: part, after: allPaint.meshes[allPaint.nodes[ni].mesh].primitives[pi] }] : []));
    assert(paintParts.some(part => part.before.attributes.COLOR_0 === part.after.attributes.COLOR_0));
    assert(paintParts.filter(part => part.before.attributes.COLOR_0 !== part.after.attributes.COLOR_0).length > 1, 'Immediate save includes paint across LODs while skipping unmatched parts');
    await window.screenshot({ path: path.join(root, 'test-output/vscode-fuel-paint.png') });
    await fs.writeFile(fixture, triangle(10));
    await vscode.commands.executeCommand('vscode.openWith', vscode.Uri.file(fixture), 'megamek.glb');
    await findEditor('reload-fixture.glb');
    await fs.writeFile(fixture, 'incomplete save');
    await frame.waitForFunction(() => document.getElementById('status').textContent === 'Load failed', null, { timeout: 15000 });
    await fs.writeFile(fixture, triangle(20));
    await frame.waitForFunction(() => document.getElementById('status').textContent.includes('20.0'), null, { timeout: 15000 });
    assert.match(await frame.locator('#status').textContent(), /^Authored GLB/);
    comparison = await gitFixture(path.join(root, 'test-output'));
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
    const workingUri = vscode.Uri.file(comparison.file), stagedUri = workingUri.with({ scheme: 'git', query: JSON.stringify({ path: comparison.file, ref: '' }) });
    await vscode.commands.executeCommand('vscode.openWith', workingUri, 'megamek.glb'); await findEditor('review.glb', 'Working copy'); const working = frame;
    await vscode.commands.executeCommand('vscode.openWith', stagedUri, 'megamek.glb', { viewColumn: vscode.ViewColumn.Beside }); await findEditor('review.glb', 'Staged'); const staged = frame;
    assert(await staged.locator('#saveGlb').isDisabled()); assert(await staged.locator('#saveGlbAs').isDisabled());
    await staged.locator('[data-tab="materials"]').click(); await staged.locator('#surfaceTarget').selectOption('0:0'); assert(await staged.locator('#assignExisting').isDisabled()); assert(await staged.locator('#paintMode').isDisabled()); assert(await staged.locator('#wrapU').isDisabled());
    assert.match(await working.locator('#status').textContent(), /30\.0/); assert.match(await staged.locator('#status').textContent(), /20\.0/);
    for (const [editor, roughness] of [[working, .8], [staged, .4]]) {
      await editor.locator('[data-tab="materials"]').click(); assert.match(await editor.locator('#materialDetail pre').textContent(), new RegExp('"roughness": ' + roughness));
      await editor.locator('[data-tab="view"]').click();
    }
    await working.locator('#lod').selectOption('1'); await staged.waitForFunction(() => document.getElementById('lod').value === '1');
    assert.match(await working.locator('#status').textContent(), /15\.0/); assert.match(await staged.locator('#status').textContent(), /10\.0/);
    await vscode.commands.executeCommand('workbench.action.focusSecondEditorGroup');
    await staged.locator('#wire').check(); await working.waitForFunction(() => document.getElementById('wire').checked);
    await staged.locator('#variant').selectOption('snow');
    for (const editor of [working, staged]) await editor.waitForFunction(() => document.getElementById('variant').value === 'snow' && document.getElementById('overlay').textContent === '');
    await comparison.git('add', '.');
    await staged.waitForFunction(() => document.getElementById('status').textContent.includes('15.0'), null, { timeout: 30000 });
    await staged.locator('[data-tab="materials"]').click(); assert.match(await staged.locator('#materialDetail pre').textContent(), /"roughness": 0.8/);
    await working.locator('#inspectorToggle').click(); await staged.locator('#inspectorToggle').click();
    await window.screenshot({ path: path.join(root, 'test-output/vscode-staged-comparison.png') });
    console.log('VS Code PASS: live wrapping/filtering, immediate Ctrl+S and reopened sampler settings, sampler Undo/Redo, live vertex paint, UV controls, palette, read-only Git and linked comparisons.');
  } catch (error) {
    if (frame && !frame.isDetached()) {
      console.log('Editor failure state:', await frame.evaluate(() => ({ palette: document.getElementById('paletteCount').textContent, notice: document.getElementById('editNotice').textContent, cards: [...document.querySelectorAll('#paletteGrid button')].map(b => ({ title: b.title, width: b.querySelector('img').naturalWidth })), overlay: document.getElementById('overlay').textContent })));
      await window.screenshot({ path: path.join(root, 'test-output/vscode-material-failure.png') });
    }
    throw error;
  } finally {
    for (const dirtyFixture of vscode.window.tabGroups.all.flatMap(group => group.tabs).filter(tab => tab.isDirty && tab.input instanceof vscode.TabInputCustom && [editFixture, paintFixture].includes(tab.input.uri.fsPath))) { await vscode.commands.executeCommand('vscode.openWith', dirtyFixture.input.uri, 'megamek.glb'); await vscode.commands.executeCommand('workbench.action.files.revert'); }
    await browser.close(); await vscode.commands.executeCommand('workbench.action.closeAllEditors'); await fs.rm(fixture, { force: true }); await fs.rm(editFixture, { force: true }); await fs.rm(paintFixture, { force: true }); await comparison?.dispose();
  }
};
