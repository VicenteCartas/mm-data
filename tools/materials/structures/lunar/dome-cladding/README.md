# Lunar dome material set

`dome-cladding`, `dome-deck`, `dome-trim`, `dome-window`, `dome-light` and `dome-marker` are native Material Maker projects for
the generated dome rings, corridors and rigid gate passages. The renderer derives their geometry and UVs from
the board. Roof equipment remains manually placed in the 3D editor.

The `PanelFinish` shader contains the editable panel layout, normal relief, roughness and occlusion. `PlateStudy`
supplies the cladding albedo. Cladding has four bays and two storeys per 36 model units. The procedural roof uses
flush 4.5-unit metal panels with hairline seams, square X-slotted plates at the four-way joins and a finer, lighter
grid crossing each panel centre. Broad bevels and dark grout are deliberately absent. Trim is procedural charcoal
metal, with its own seams and fasteners instead of roof plates.
Pressure windows and inset lights are procedural.
Runtime maps are capped at 512×512: cladding, deck and trim use 512×512, windows use 256×256,
and the uniform white/amber light maps use 32×32. These sizes are stored on the graphs' Material nodes.
Structural borders, pillars and tunnel hoops use the existing palette material `structures/common/matte-steel`,
with a charcoal vertex tint as in the fortress-wall kits.
`dome-trim` supplies the lighter inset fittings. `dome-light` is a nonmetallic lens with emission energy 2.8,
carried through the same model material emission used by the fortress-wall lamps.
`dome-marker` supplies the larger amber lenses at true external corners (energy 2.2); flat-side and re-entrant
pillars have white head lenses. Every exposed pillar face has one main fixture near its head and one small white fixture near
its foot, irrespective of its number of storeys. Foot markers are always white, including external corners. Corner housings follow both adjoining wall faces; exterior columns
reach ground level. Height-step endpoints are not automatically yellow corners.
Roof fastener relief and albedo are coordinated in `PanelFinish` so the fasteners remain visible at board scale.

Export using `tools/materials/export.py structures/lunar/<name>/<name>.ptex`. This exports to a fresh temporary
prefix before updating the shipped maps and `.tres` together. Material Maker's direct export preserves an existing
`.tres`, so an already-existing target can retain old map bindings when inputs change.

## Image sources

The two `sources/plate-study.png` files were created with the built-in imagegen tool from the user's clear-roof
lunar habitat reference and the corresponding procedural albedo layouts. The reference itself is not a game render.
The cladding study remains a texture input. The earlier deck study is retained for provenance; the current deck
graph is entirely procedural and does not sample it. These studies are not screenshots presented as engine output.

Prompt used for both studies:

> Use case: precise-object-edit. Asset type: seamless PBR albedo texture for the game's lunar habitat. Image 1 is
> the edit target, a square texture atlas. Image 2 is the visual quality and material reference. Preserve the
> target's exact orthographic grid layout, seam positions, count of panels, and access hatch placements; do not
> change the dimensions, crop, perspective or add objects. Upgrade its simplistic outlined shapes into the
> richly detailed metal plating in the reference: crisp narrow recessed gasket seams, physically convincing
> inset metal panel lips, tiny metal fasteners with hexagonal heads and small slots, subtle paint scuffs and
> irregular rubbed edges, tiny mineral dust accumulation, occasional tiny manufacturing marks. Warm ivory-gray
> powder-coated metal, maintained but used. Do not add windows, doors, vents, equipment, logos or large text.
> Uniform albedo illumination without directional shadows or directional highlights; only intrinsic color
> variation and narrow dark crevice lines. Edges must repeat seamlessly. Keep the original base brightness.

Cladding addition: preserve four columns by two rows, eight tall bays, with a small service hatch in every second
bay. Deck addition: preserve two columns by two rows, four square roof plates with four fasteners near each
plate's corners; no hatches; fine seams and subtle edge wear.
