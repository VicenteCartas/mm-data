import * as THREE from 'three';

const sampledMaps = ['map', 'normalMap', 'roughnessMap', 'metalnessMap', 'aoMap', 'emissiveMap', 'mmSharedEmissionMap', 'bumpMap'];
const wrapping = { 10497: THREE.RepeatWrapping, 33071: THREE.ClampToEdgeWrapping, 33648: THREE.MirroredRepeatWrapping };
const filtering = { 9728: THREE.NearestFilter, 9729: THREE.LinearFilter, 9984: THREE.NearestMipmapNearestFilter, 9985: THREE.LinearMipmapNearestFilter, 9986: THREE.NearestMipmapLinearFilter, 9987: THREE.LinearMipmapLinearFilter };

export function materialSampling(material, sampler, owned) {
  if (!material.mmSamplingCloned) {
    // A material clone still shares its textures. Copy them once, keeping the loaded images.
    const copies = new Map();
    for (const role of sampledMaps) {
      const source = material[role]; if (!source) continue;
      if (!copies.has(source)) { const texture = source.clone(); copies.set(source, texture); owned.add(texture); }
      material[role] = copies.get(source);
    }
    material.mmSamplingCloned = true;
  }
  for (const role of sampledMaps) {
    const texture = material[role]; if (!texture) continue;
    texture.wrapS = wrapping[sampler.wrapS]; texture.wrapT = wrapping[sampler.wrapT];
    texture.minFilter = filtering[sampler.minFilter]; texture.magFilter = filtering[sampler.magFilter];
    texture.needsUpdate = true;
  }
}

export function materialLighting(material, surface, night = false) {
  const gltf = surface?.gltf || {}, spec = surface?.managed;
  const ownGlow = gltf.emissiveFactor?.some(v => v !== 0);
  const mode = gltf.extras?.mmEmission || (spec?.nightEmission ? 'night' : 'always');
  const muted = mode === 'off' || (!night && mode === 'night');
  // Each live material clone owns its uniform. Updating it also covers cached shader programs.
  material.mmGlow ||= { value: new THREE.Color(0, 0, 0) };
  material.mmGlow.value.setRGB(0, 0, 0);
  if (!muted && !ownGlow && spec && (spec.emissionOperator === 0 || !spec.maps.emission)) {
    material.mmGlow.value.fromArray(spec.emissionColor).convertSRGBToLinear().multiplyScalar(spec.emissionEnergy);
  }
  material.emissiveIntensity = muted ? 0 : gltf.extensions?.KHR_materials_emissive_strength?.emissiveStrength ?? 1;
}

export function materialFactors(material, surface) {
  const gltf = surface?.gltf || {}, spec = surface?.managed, pbr = gltf.pbrMetallicRoughness || {};
  const ownGlow = gltf.emissiveFactor?.some(v => v !== 0);
  material.color.fromArray(pbr.baseColorFactor || [1, 1, 1]);
  if (spec) material.color.multiply(new THREE.Color().fromArray(spec.tint).convertSRGBToLinear());
  material.opacity = pbr.baseColorFactor?.[3] ?? 1;
  material.roughness = spec?.roughness ?? pbr.roughnessFactor ?? 1;
  material.metalness = spec?.metallic ?? pbr.metallicFactor ?? 1;
  material.side = gltf.doubleSided ? THREE.DoubleSide : THREE.FrontSide;
  const paint = !!(spec ? spec.paintMask : gltf.extras?.mmPaintMask);
  material.transparent = !paint && gltf.alphaMode === 'BLEND'; material.depthWrite = !material.transparent;
  material.alphaTest = !paint && gltf.alphaMode === 'MASK' ? gltf.alphaCutoff ?? .5 : 0;
  if (material.emissive) {
    material.emissive.fromArray(gltf.emissiveFactor || [0, 0, 0]);
    material.emissiveIntensity = gltf.extensions?.KHR_materials_emissive_strength?.emissiveStrength ?? 1;
    if (spec?.maps.emission && !gltf.emissiveTexture) {
      material.emissiveMap = ownGlow ? null : material.mmSharedEmissionMap;
      if (!ownGlow) {
        material.emissive.copy(spec.emissionOperator === 0 ? new THREE.Color().setRGB(spec.emissionEnergy, spec.emissionEnergy, spec.emissionEnergy) : new THREE.Color().fromArray(spec.emissionColor).convertSRGBToLinear().multiplyScalar(spec.emissionEnergy));
      }
    }
  }
  materialLighting(material, surface);
  material.needsUpdate = true;
}

// Preview mapping of docs/gpu-board-materials.md. The original GLB and .tres are never modified.
export async function prepareMaterials(gltf, asset, owned, report) {
  const textureLoader = new THREE.TextureLoader();
  const cache = new Map();
  async function texture(map, template, color = false, channel = null) {
    const key = [map.url, color, channel, template?.wrapS, template?.wrapT, template?.minFilter, template?.magFilter].join('|');
    if (!cache.has(key)) cache.set(key, (async () => {
      let result = await textureLoader.loadAsync(map.url);
      owned.add(result);
      if (channel !== null) {
        const canvas = document.createElement('canvas'); canvas.width = result.image.width; canvas.height = result.image.height;
        const ctx = canvas.getContext('2d', { willReadFrequently: true }); ctx.drawImage(result.image, 0, 0);
        const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height);
        for (let at = 0; at < pixels.data.length; at += 4) {
          const v = channel === 4 ? .2126 * pixels.data[at] + .7152 * pixels.data[at + 1] + .0722 * pixels.data[at + 2] : pixels.data[at + channel];
          pixels.data[at] = pixels.data[at + 1] = pixels.data[at + 2] = v; pixels.data[at + 3] = 255;
        }
        ctx.putImageData(pixels, 0, 0); result = new THREE.CanvasTexture(canvas); owned.add(result);
      }
      result.flipY = false; result.colorSpace = color ? THREE.SRGBColorSpace : THREE.NoColorSpace;
      if (template) for (const key of ['wrapS', 'wrapT', 'minFilter', 'magFilter', 'anisotropy']) result[key] = template[key];
      else result.wrapS = result.wrapT = THREE.RepeatWrapping;
      return result;
    })());
    return cache.get(key);
  }
  const loaded = await gltf.parser.getDependencies('material');
  loaded.forEach(material => owned.add(material));
  for (const surface of asset.surfaces) {
    const material = loaded[surface.index]; if (!material) continue;
    const spec = surface.managed;
    if (spec) {
      try {
        material.roughnessMap = spec.maps.roughness ? await texture(spec.maps.roughness, material.map, false, spec.channels.roughness) : null;
        material.metalnessMap = spec.maps.metallic ? await texture(spec.maps.metallic, material.map, false, spec.channels.metallic) : null;
        if (!surface.gltf.normalTexture && spec.maps.normal) { material.normalMap = await texture(spec.maps.normal, material.map); material.normalScale.set(spec.normalScale, spec.normalScale); }
        if (!surface.gltf.occlusionTexture && spec.maps.ao) material.aoMap = await texture(spec.maps.ao, material.map, false, spec.channels.ao);
        if (spec.maps.emission && !surface.gltf.emissiveTexture) {
          material.mmSharedEmissionMap = await texture(spec.maps.emission, material.map, true);
        }
        if (spec.maps.height && !material.normalMap) { material.bumpMap = await texture(spec.maps.height, material.map); material.bumpScale = spec.heightScale / 100 * (spec.heightFlip ? -1 : 1); }
      } catch (error) { report(`${surface.name}: map preview failed: ${error.message}`); }
    }
    materialFactors(material, surface);
    const paint = !!(spec ? spec.paintMask : surface.gltf.extras?.mmPaintMask);
    const hasGlow = spec && (spec.emissionOperator === 0 || !spec.maps.emission) && spec.emissionColor.slice(0, 3).some(v => v !== 0);
    if (paint || hasGlow) {
      material.onBeforeCompile = function(shader) {
        shader.uniforms.mmGlow = this.mmGlow;
        shader.fragmentShader = 'uniform vec3 mmGlow;\n' + shader.fragmentShader;
        shader.fragmentShader = shader.fragmentShader.replace('#include <emissivemap_fragment>', '#include <emissivemap_fragment>\ntotalEmissiveRadiance += mmGlow;');
        if (paint) shader.fragmentShader = shader.fragmentShader.replace('#include <color_fragment>', `
          #if defined(USE_COLOR) || defined(USE_COLOR_ALPHA)
            #ifdef USE_MAP
              diffuseColor.rgb *= mix(vec3(1.0), vColor.rgb, texture2D(map, vMapUv).a);
            #else
              diffuseColor.rgb *= vColor.rgb;
            #endif
          #endif
        `);
      };
      material.customProgramCacheKey = () => `mm-paint-${paint}-glow`;
    }
    material.needsUpdate = true;
  }
  // GLTFLoader creates vertex-color and flat-shading derivatives during parsing. Keep those flags,
  // but apply the same managed surface and shader hooks to every rendered derivative.
  gltf.scene.traverse(object => {
    if (!object.isMesh) return;
    const association = gltf.parser.associations.get(object.material);
    const index = association?.materials;
    const source = loaded[index];
    if (source && source !== object.material) {
      const vertexColors = object.material.vertexColors, flatShading = object.material.flatShading;
      object.material.copy(source); object.material.vertexColors = vertexColors; object.material.flatShading = flatShading;
      object.material.mmGlow = { value: source.mmGlow.value.clone() };
      object.material.mmSharedEmissionMap = source.mmSharedEmissionMap;
      object.material.onBeforeCompile = source.onBeforeCompile; object.material.customProgramCacheKey = source.customProgramCacheKey;
    }
    object.userData.mmMaterial = index;
  });
}

export async function modifyGeometry(gltf, asset, owned) {
  const originals = new Map();
  for (const mesh of asset.metadata.meshes || []) for (const primitive of mesh.primitives) {
    const source = primitive.extras?.mmVertexPaint?.source;
    if (Number.isInteger(source)) originals.set(source, null);
  }
  await Promise.all([...originals.keys()].map(async source => originals.set(source, await gltf.parser.getDependency('accessor', source))));
  gltf.scene.traverse(object => {
    if (!object.isMesh) return;
    owned.add(object.geometry); object.geometry = object.geometry.clone();
    const geometry = object.geometry, count = geometry.attributes.position.count;
    let colors = geometry.attributes.color;
    if (!colors) { colors = new THREE.Float32BufferAttribute(new Float32Array(count * 3).fill(1), 3); geometry.setAttribute('color', colors); }
    const association = gltf.parser.associations.get(object), primitive = asset.metadata.meshes?.[association?.meshes]?.primitives[association?.primitives ?? 0];
    const source = primitive?.extras?.mmVertexPaint?.source;
    geometry.userData.authoredPaint = source === null ? new THREE.Float32BufferAttribute(new Float32Array(count * 3).fill(1), 3) : originals.get(source) || colors;
    // Convert normalized/interleaved colors to an editable float copy; glTF colors are already linear.
    const values = new Float32Array(count * colors.itemSize);
    for (let i = 0; i < count; i++) for (let c = 0; c < colors.itemSize; c++) values[i * colors.itemSize + c] = colors.getComponent(i, c);
    colors = new THREE.Float32BufferAttribute(values, colors.itemSize); geometry.setAttribute('color', colors);
    const change = asset.surfaces[object.userData.mmMaterial]?.changes;
    if (change?.colours && change.colours.length !== count) throw Error('Variant colour count differs from its primitive');
    for (let i = 0; i < count; i++) for (let c = 0; c < colors.itemSize; c++) {
      if (change?.colours) colors.array[i * colors.itemSize + c] = change.colours[i][c];
      else if (change?.colourScale) colors.array[i * colors.itemSize + c] *= change.colourScale[c] ?? 1;
    }
    geometry.userData.originalColors = colors.array.slice();
    if (geometry.attributes.uv) geometry.userData.originalUv = geometry.attributes.uv.clone();
    object.mmOriginalMaterial = object.material;
  });
}

export function applyColors(scene, slots, replacements) {
  scene.traverse(object => {
    if (!object.isMesh) return;
    const geometry = object.geometry, ids = geometry.attributes._colour_slot, color = geometry.attributes.color;
    if (!ids || !color) return;
    const original = geometry.userData.originalColors;
    for (let i = 0; i < ids.count; i++) {
      const slot = Math.round(ids.getX(i)) - 1;
      if (!slots[slot] || !replacements[slot]) continue;
      const from = new THREE.Color(slots[slot].colour), to = new THREE.Color(replacements[slot]);
      for (const [c, key] of ['r', 'g', 'b'].entries()) color.array[i * color.itemSize + c] = (from[key] > 1e-6 ? original[i * color.itemSize + c] / from[key] : 1) * to[key];
    }
    color.needsUpdate = true;
  });
}

// Same atlas contract documented in RigidGlb.label; UVs start from the authored blank-cell layout on every edit.
export function applyLabel(scene, text) {
  const alphabet = ' ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-';
  const meshes = []; let places = 0;
  scene.traverse(object => {
    if (!object.isMesh || !object.mmOriginalMaterial?.userData.mmLabel || !object.geometry.attributes.uv) return;
    meshes.push(object);
    const uv = object.geometry.userData.originalUv;
    for (let i = 0; i < uv.count; i++) places = Math.max(places, Math.floor(uv.getX(i)) + 1);
  });
  const shown = text.toUpperCase().slice(0, places), start = Math.floor((places - shown.length) / 2);
  for (const object of meshes) {
    const uv = object.geometry.attributes.uv, original = object.geometry.userData.originalUv;
    for (let i = 0; i < uv.count; i++) {
      const u = original.getX(i), v = original.getY(i), place = Math.floor(u), index = place - start;
      const character = index >= 0 && index < shown.length ? Math.max(0, alphabet.indexOf(shown[index])) : 0;
      uv.setXY(i, place + (character % 8 + (u - place) * 8) / 8, (Math.floor(character / 8) + v * 8) / 8);
    }
    uv.needsUpdate = true;
  }
}
