// Solid lava crust: a preview for Godot only. MegaMek renders this material with its own shaders
// (terrain-magma.glsl and magma-solid.glsl), which add the board's banks and relief. This shader declares the
// material's parameters (their names, colour spaces and defaults are what the game reads) and shows its maps as a
// static surface, colouring heat and fissure glow as the game does.
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
// Heat as LINEAR intensity in R (a grey map, not a colour): the shader turns it into emitted colour.
uniform sampler2D texture_emission : hint_default_black, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float emission_energy = 1.0;
// Glow of the fissures between plates (linear, 0 to 1), strongest where the crust itself is cold.
uniform sampler2D texture_glow : hint_default_black, filter_linear_mipmap_anisotropic, repeat_enable;

void fragment() {
	vec4 orm = texture(texture_orm, UV);
	float heat = texture(texture_emission, UV).r;
	float glow = texture(texture_glow, UV).r;
	ALBEDO = albedo.rgb * texture(texture_albedo, UV).rgb;
	AO = orm.r;
	ROUGHNESS = roughness * orm.g;
	METALLIC = metallic * orm.b;
	NORMAL_MAP = texture(texture_normal, UV).rgb;
	NORMAL_MAP_DEPTH = normal_scale;
	vec3 hot = mix(vec3(0.55, 0.006, 0.0002), vec3(0.95, 0.24, 0.004), heat * heat * heat);
	EMISSION = (hot * heat + vec3(0.25, 0.022, 0.0015) * glow * (1.0 - heat)) * emission_energy;
}
