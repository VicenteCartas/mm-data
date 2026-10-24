// Molten lava: a preview for Godot only. MegaMek renders this material with its own shaders
// (terrain-magma.glsl and magma-flow.glsl), which add the board's flow, banks and cooling skin. This shader
// declares the material's parameters (their names, colour spaces and defaults are what the game reads) and shows
// its maps as a static surface.
shader_type spatial;

uniform vec4 albedo : source_color = vec4(1.0);
uniform sampler2D texture_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
// ORM, as Godot's ORMMaterial3D packs it: R ambient occlusion, G roughness, B metallic.
uniform sampler2D texture_orm : hint_roughness_g, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float roughness : hint_range(0.0, 1.0) = 1.0;
uniform float metallic : hint_range(0.0, 1.0) = 0.0;
uniform sampler2D texture_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float normal_scale : hint_range(-16.0, 16.0) = 1.0;
// Height, white highest. heightmap_scale is the relief depth in UV, times 100, as in StandardMaterial3D.
uniform sampler2D texture_heightmap : hint_default_black, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float heightmap_scale = 5.0;
// Emitted radiance as LINEAR RGB, times emission_energy. Unlike Godot's own emission (source_color), the map
// stores linear values: the game scales them as they are.
uniform sampler2D texture_emission : hint_default_black, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float emission_energy = 1.0;
// Exposed melt (linear, 0 to 1): where the melt shows through its cooling skin, which alone reflects light.
uniform sampler2D texture_coverage : hint_default_black, filter_linear_mipmap_anisotropic, repeat_enable;

void fragment() {
	vec4 orm = texture(texture_orm, UV);
	float exposed = smoothstep(0.28, 0.56, texture(texture_coverage, UV).r);
	ALBEDO = albedo.rgb * texture(texture_albedo, UV).rgb * (1.0 - exposed);
	AO = orm.r;
	ROUGHNESS = roughness * orm.g;
	METALLIC = metallic * orm.b;
	NORMAL_MAP = texture(texture_normal, UV).rgb;
	NORMAL_MAP_DEPTH = normal_scale;
	EMISSION = texture(texture_emission, UV).rgb * emission_energy;
}
