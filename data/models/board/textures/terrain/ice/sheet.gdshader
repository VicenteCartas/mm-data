// Ice sheet: a preview for Godot only. MegaMek renders ice with its own shader (terrain-ice.glsl), an optical coat
// over the surface beneath with the board's floes, snow, joints and edges. This shader declares the material's
// parameters (their names, colour spaces and defaults are what the game reads) and shows its maps as a static
// surface of bare ice.
shader_type spatial;

uniform vec4 albedo : source_color = vec4(1.0);
// A chromatic tint of the ice, not a final albedo: only its hue matters, normalised as the game does.
uniform sampler2D texture_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
// ORM, as Godot's ORMMaterial3D packs it: R ambient occlusion, G roughness, B metallic.
uniform sampler2D texture_orm : hint_roughness_g, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float roughness : hint_range(0.0, 1.0) = 1.0;
uniform float metallic : hint_range(0.0, 1.0) = 0.0;
uniform sampler2D texture_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float normal_scale : hint_range(-16.0, 16.0) = 1.0;
// Grain height, white highest. heightmap_scale is the relief depth in UV, times 100, as in StandardMaterial3D.
uniform sampler2D texture_heightmap : hint_default_black, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float heightmap_scale = 5.0;
// Cloudiness (linear, 0 to 1): milky ice scatters light beneath its surface.
uniform sampler2D texture_subsurface_scattering : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float subsurface_scattering_strength : hint_range(0.0, 1.0) = 0.0;
// Cracks and trapped bubbles (linear, 0 to 1), which scatter light white.
uniform sampler2D texture_cracks : hint_default_black, filter_linear_mipmap_anisotropic, repeat_enable;

void fragment() {
	vec3 tint = albedo.rgb * texture(texture_albedo, UV).rgb;
	tint /= max(dot(tint, vec3(0.333)), 0.05);
	float cloudy = texture(texture_subsurface_scattering, UV).r * subsurface_scattering_strength;
	float cracks = texture(texture_cracks, UV).r;
	vec3 bare = vec3(0.40, 0.50, 0.56) * mix(vec3(1.0), tint, 0.35) * (1.0 + cloudy * 0.35) + vec3(0.55) * cracks;
	ALBEDO = min(bare, vec3(1.0));
	vec4 orm = texture(texture_orm, UV);
	ROUGHNESS = roughness * orm.g;
	METALLIC = metallic * orm.b;
	NORMAL_MAP = texture(texture_normal, UV).rgb;
	NORMAL_MAP_DEPTH = normal_scale;
	SSS_STRENGTH = cloudy;
}
