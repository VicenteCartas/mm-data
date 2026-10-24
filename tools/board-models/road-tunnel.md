# Road tunnel portal

Two GLBs share the same portal geometry:

- `data/models/board/road-tunnel.glb`: wing walls, 289 triangles.
- `data/models/board/road-tunnel-bridge.glb`: no wing walls, 273 triangles.

Both use one LOD0. The bridge portal has no `tunnel-wings` part; the arch, deep
shell and lining are identical.

The portal, wing walls and lining carry embedded cast-concrete albedo and normal
maps, with continuous fine aggregate and pores, without panels or tie-hole patterns. The floor's
asphalt image is embedded too: neither GLB needs external image files.
The plain albedo is embedded from the shared `scenery/tunnel-concrete` material's
`data/models/board/textures/scenery/tunnel-concrete_albedo.png` (Material Maker project
`tools/materials/scenery/tunnel-concrete/`); that material also serves retaining walls.
No duplicate gallery PNGs are kept in the authoring tree.
`tools/materials/scenery/gallery-concrete/bake_normal.py` accepts an albedo and a
scratch output path for the normal bake. `tools/texture_tunnel_portals.py` accepts
explicit albedo and normal paths and embeds them in both models while preserving
their geometry and vertex-colour fades.
At runtime the floor receives its approach's
road material (asphalt, gravel or dirt), including the existing normal/surface
maps and world-space texture alignment. Concrete repeats every 24 units across
and up the portal, and the lining unwraps continuously around the arch.
The outer side walls and roof extend the full 36-unit tunnel depth, allowing
the portal to be embedded in a sloping face. The lining and piers do not have
overlapping inner faces. The floor's and lining's vertex colours follow
`BoardTunnel.light`: full light at the hex edge (Y=3), falling off to a dark end
cap at Y=36; a road's verges and markings carried into the tunnel darken alike.

The 30-unit carriageway, an ordinary road's, continues through the entrance to
Y=36. Runtime placement stretches only the lateral dimension for a wider route:
the shared road/rail corridor's full clearance width for a rail portal, which
also follows the enlarged conventional ballast. The arch cut and roadside
clearance use the same inverse transform. Concrete verges fill the remaining
opening width. The floor begins at Y=2.75,
slightly before the shared hex edge at Y=3, with a 0.02-unit recessed lip. This
small underlap seals the lattice's oblique edges without coplanar fighting.

Coordinates: Z up, +Y into the cliff, opening at Y=0, base at Z=0. Opening is
35 units wide, with vertical piers to Z=6.9 and a 16-segment half ellipse rising
10.925 more. The shell is 44.5 units wide and its roof reaches Z=22.1. The wing
walls flare from 21.4 to 27.4 units either side over the 6 units in front of the
opening, falling from 9.2 to 4 units high. `BoardTunnel` uses these dimensions when clipping
the existing terrain for the opening. Update that contract if these change.

Generated reference: `road-tunnel-reference.png`, made with the built-in imagegen
tool. Prompt requested a realistic low-poly concrete portal in a natural cliff,
a thick arched rim, flared wing walls, a deep dark lining, and a two-lane road
width, viewed from the front and three-quarter angle.

This is a visual entrance only; it does not add a traversable tunnel or change
board elevations, exits or movement rules.

`BoardTunnel` places bridge portals at the actual deck elevation, independent
of the terrain family beneath or beside the bridge. The opening must fit in
the facing dry cliff. Ground roads keep the existing grading decisions.
The Lava Tubes 1 fixture has 13 cliff-facing bridge exits and four exits that
connect the bridge decks to one another; only the former receive portals.

Whole decorative rocks are excluded from the shell, wing walls and immediate
road approach. Formations above the portal and beside its cleared footprint
remain. `BoardTunnel.obstructs` defines this small visual clearance.

The shared plain concrete albedo was generated with the built-in imagegen tool.
Its original prompt is saved in `road-tunnel-texture-prompt.json`.
