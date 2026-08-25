"""Read-only structural and OBJ round-trip verification for Yier v004."""

from __future__ import annotations

import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(r"F:\dev\overcooke")
EXPECTED_BLEND = PROJECT_ROOT / "characters" / "yier" / "source" / "yier_work-v004.blend"
PACKAGE_HAT_NAME = "SignCap"
WORKSPACE_HAT_NAMES = ("SignCap", "YierCap", "YierBlueCap")
HAT_TEMPLATE_OFFSET = Vector((0.0, 0.10684707760810852, 1.036182165145874))
EXPECTED = {
    "Body_Body": ((1710, 3312), (-0.218287, -0.244838, 0.210471), (0.230154, 0.203603, 0.612743)),
    "Body_Bottom": ((3284, 6519), (-0.204153, -0.244895, 0.491210), (0.215040, 0.189415, 0.559353)),
    "Body_Tail": ((554, 1104), (-0.054387, 0.161064, 0.323086), (0.047440, 0.262732, 0.424754)),
    "Eyes": ((334, 330), (-0.181219, -0.370525, 0.730937), (0.192072, -0.347563, 0.795735)),
    "Eyes2_Blinks": ((334, 330), (-0.185155, -0.370525, 0.757504), (0.196008, -0.347563, 0.769168)),
    "Hand_Grip_L": ((554, 1104), (0.223770, -0.112868, 0.429249), (0.391484, 0.006951, 0.611220)),
    "Hand_Grip_R": ((554, 1104), (-0.391571, -0.112868, 0.429249), (-0.223856, 0.006951, 0.611220)),
    "Hand_Open_L": ((554, 1104), (0.223770, -0.112868, 0.429249), (0.391484, 0.006951, 0.611220)),
    "Hand_Open_R": ((554, 1104), (-0.391571, -0.112868, 0.429249), (-0.223856, 0.006951, 0.611220)),
    "Head": ((2686, 4224), (-0.391887, -0.380051, 0.524227), (0.396321, 0.355252, 1.166443)),
}
HAT_ROOT_BOUNDS = (
    (-0.483925939, -0.434340686, 0.586582541),
    (0.488357961, 0.391069829, 1.209822059),
)
HAT_LOCAL_BOUNDS = (
    (-0.483925939, -0.541187763, -0.449599624),
    (0.488357961, 0.284222752, 0.173639894),
)


def parse_resources_root() -> Path:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(arguments) != 2 or arguments[0] != "--resources-root":
        raise RuntimeError("Usage: ... -- --resources-root <Resources directory>")
    return Path(arguments[1]).resolve()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points = [
        obj.matrix_world @ Vector(corner)
        for obj in objects
        if obj.type == "MESH" and len(obj.data.polygons) > 0
        for corner in obj.bound_box
    ]
    require(bool(points), "No mesh bounds")
    lower = Vector(tuple(min(point[axis] for point in points) for axis in range(3)))
    upper = Vector(tuple(max(point[axis] for point in points) for axis in range(3)))
    return lower, upper


def stats(objects: list[bpy.types.Object]) -> tuple[int, int]:
    vertices = 0
    triangles = 0
    for obj in objects:
        if obj.type != "MESH":
            continue
        obj.data.calc_loop_triangles()
        vertices += len(obj.data.vertices)
        triangles += len(obj.data.loop_triangles)
    return vertices, triangles


def require_close(
    actual: Vector,
    expected: tuple[float, float, float],
    label: str,
    tolerance: float = 2e-5,
) -> None:
    require(
        all(abs(actual[axis] - expected[axis]) <= tolerance for axis in range(3)),
        f"{label}: actual={tuple(actual)} expected={expected}",
    )


def validate_mesh(obj: bpy.types.Object) -> None:
    mesh = obj.data
    require(all(len(poly.vertices) == 3 for poly in mesh.polygons), f"{obj.name}: non-triangle polygon")
    require(len(mesh.uv_layers) == 1, f"{obj.name}: expected one UV layer")
    require(len(mesh.materials) == 1 and mesh.materials[0].name == "YIER_GAME_ATLAS", f"{obj.name}: atlas material mismatch")
    require(all(math.isfinite(value) for vertex in mesh.vertices for value in vertex.co), f"{obj.name}: non-finite vertex")
    uv_data = mesh.uv_layers.active.data
    for polygon in mesh.polygons:
        require(polygon.normal.length > 0.0, f"{obj.name}: zero polygon normal")
        uvs = [Vector(uv_data[index].uv) for index in polygon.loop_indices]
        require(all(0.0 <= value <= 1.0 for uv in uvs for value in uv), f"{obj.name}: UV outside 0..1")
        require(abs((uvs[1] - uvs[0]).cross(uvs[2] - uvs[0])) > 1e-6, f"{obj.name}: degenerate UV triangle")


def topology_and_uv_equal(left: bpy.types.Object, right: bpy.types.Object) -> bool:
    if len(left.data.vertices) != len(right.data.vertices) or len(left.data.polygons) != len(right.data.polygons):
        return False
    if any(tuple(a.vertices) != tuple(b.vertices) for a, b in zip(left.data.polygons, right.data.polygons, strict=True)):
        return False
    left_uv = left.data.uv_layers.active.data
    right_uv = right.data.uv_layers.active.data
    return all(tuple(a.uv) == tuple(b.uv) for a, b in zip(left_uv, right_uv, strict=True))


def verify_hat_offset(root_hat: bpy.types.Object, local_hat: bpy.types.Object) -> None:
    require(topology_and_uv_equal(root_hat, local_hat), "Root/local hat topology or UV differs")
    for root_vertex, local_vertex in zip(root_hat.data.vertices, local_hat.data.vertices, strict=True):
        delta = root_vertex.co - local_vertex.co
        require((delta - HAT_TEMPLATE_OFFSET).length <= 1e-6, f"HatBase offset mismatch: {tuple(delta)}")


def verify_round_trip(path: Path, expected: bpy.types.Object, label: str) -> None:
    require(path.is_file() and path.stat().st_size > 0, f"Missing OBJ: {path}")
    expected_stats = stats([expected])
    expected_lower, expected_upper = bounds([expected])
    before = set(bpy.data.objects)
    result = bpy.ops.wm.obj_import(
        filepath=str(path),
        forward_axis="NEGATIVE_Z",
        up_axis="Y",
        use_split_objects=False,
        use_split_groups=False,
    )
    require("FINISHED" in result, f"OBJ round-trip import failed: {label}")
    created = [obj for obj in set(bpy.data.objects) - before if obj.type == "MESH"]
    require(bool(created), f"OBJ round-trip created no mesh: {label}")
    require(stats(created) == expected_stats, f"OBJ round-trip stats mismatch: {label}")
    actual_lower, actual_upper = bounds(created)
    require_close(actual_lower, tuple(expected_lower), f"{label} round-trip lower")
    require_close(actual_upper, tuple(expected_upper), f"{label} round-trip upper")
    require(all(len(obj.data.uv_layers) == 1 for obj in created), f"{label}: round-trip UV missing")
    for created_obj in created:
        mesh = created_obj.data
        bpy.data.objects.remove(created_obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def main() -> None:
    resources_root = parse_resources_root()
    character_package = resources_root / "Sign"
    hat_package = resources_root / "HATS" / PACKAGE_HAT_NAME
    require(bpy.app.background, "Verification must run in a background process")
    require(Path(bpy.data.filepath) == EXPECTED_BLEND, f"Unexpected v004 path: {bpy.data.filepath}")
    require(character_package.is_dir(), f"Character package is missing: {character_package}")
    require(hat_package.is_dir(), f"Hat package is missing: {hat_package}")
    require(len(bpy.data.scenes) == 1, "Expected one scene")
    require(len(bpy.data.libraries) == 0, "Linked Blender libraries are not allowed")

    export = bpy.data.collections.get("EXPORT_PARTS")
    optional = bpy.data.collections.get("OPTIONAL_HATS")
    root_reference = bpy.data.collections.get("HAT_ROOT_REFERENCE")
    require(export is not None and optional is not None and root_reference is not None, "v004 collections are incomplete")
    objects = {obj.name: obj for obj in export.all_objects if obj.type == "MESH"}
    optional_objects = {obj.name: obj for obj in optional.all_objects if obj.type == "MESH"}
    root_objects = {obj.name: obj for obj in root_reference.all_objects if obj.type == "MESH"}
    require(set(objects) == set(EXPECTED), f"Unexpected export objects: {sorted(objects)}")
    workspace_hat_names = [name for name in WORKSPACE_HAT_NAMES if name in optional_objects]
    require(len(workspace_hat_names) == 1, f"Unexpected optional hats: {sorted(optional_objects)}")
    workspace_hat_name = workspace_hat_names[0]
    require(set(optional_objects) == {workspace_hat_name}, f"Unexpected optional hats: {sorted(optional_objects)}")
    require(set(root_objects) == {f"{workspace_hat_name}_RootReference"}, f"Unexpected root references: {sorted(root_objects)}")
    require(export.get("revision") == "v004-default-hatless-optional-cap", "Revision metadata mismatch")
    require(export.get("default_hat") == "None", "Default hat metadata mismatch")
    require(export.get("default_triangle_total") == 20235, "Default triangle metadata mismatch")
    require(optional.get("hat_name") == workspace_hat_name and optional.get("hat_triangles") == 1296, "Optional hat metadata mismatch")
    require(tuple(optional.get("hat_template_offset_blender")) == tuple(HAT_TEMPLATE_OFFSET), "Hat offset metadata mismatch")
    require(bpy.context.scene.get("workspace_revision") == "v004-default-hatless-optional-cap", "Scene revision mismatch")
    preference_pair = (
        bpy.context.scene.get("prefer_default"),
        bpy.context.scene.get("prefer_optional_hat"),
    )
    allowed_preference_pairs = {
        ("174-yier HAT=None", f"174-yier HAT={workspace_hat_name}"),
        ("Sign HAT=None", "Sign HAT=SignCap"),
    }
    require(preference_pair in allowed_preference_pairs, "Preference metadata mismatch")
    require(not export.hide_viewport and not export.hide_render, "EXPORT_PARTS must be visible")
    require(optional.hide_viewport and optional.hide_render, "OPTIONAL_HATS should be hidden by default")
    require(root_reference.hide_viewport and root_reference.hide_render, "HAT_ROOT_REFERENCE should be hidden by default")

    for name, (expected_stats, expected_lower, expected_upper) in EXPECTED.items():
        obj = objects[name]
        require(obj.matrix_world.is_identity, f"{name}: non-identity transform")
        require(len(obj.modifiers) == 0 and not obj.data.shape_keys, f"{name}: unexpected modifier or shape key")
        require(stats([obj]) == expected_stats, f"{name}: unexpected stats {stats([obj])}")
        actual_lower, actual_upper = bounds([obj])
        require_close(actual_lower, expected_lower, f"{name} lower")
        require_close(actual_upper, expected_upper, f"{name} upper")
        validate_mesh(obj)

    local_hat = optional_objects[workspace_hat_name]
    root_hat = root_objects[f"{workspace_hat_name}_RootReference"]
    for obj, expected_bounds, label in [
        (local_hat, HAT_LOCAL_BOUNDS, "local hat"),
        (root_hat, HAT_ROOT_BOUNDS, "root hat"),
    ]:
        require(obj.matrix_world.is_identity, f"{label}: non-identity transform")
        require(stats([obj]) == (698, 1296), f"{label}: unexpected stats {stats([obj])}")
        actual_lower, actual_upper = bounds([obj])
        require_close(actual_lower, expected_bounds[0], f"{label} lower")
        require_close(actual_upper, expected_bounds[1], f"{label} upper")
        validate_mesh(obj)
    verify_hat_offset(root_hat, local_hat)

    character_triangles = sum(stats([obj])[1] for obj in objects.values())
    require(character_triangles == 20235, f"Unexpected default triangle total: {character_triangles}")
    require(character_triangles + stats([local_hat])[1] == 21531, "Optional-hat triangle total no longer matches v003")

    for name, obj in sorted(objects.items()):
        verify_round_trip(character_package / f"{name}.obj", obj, name)
    verify_round_trip(hat_package / f"{PACKAGE_HAT_NAME}.obj", local_hat, PACKAGE_HAT_NAME)

    character_files = {path.name for path in character_package.iterdir() if path.is_file()}
    required_character_files = {
        "INFO", "ATTRIBUTION.txt", "t_Head.png", "t_Body.png", "m_Head.txt", "m_Body.txt",
        *(f"{name}.obj" for name in EXPECTED),
    }
    require(required_character_files <= character_files, f"Character files missing: {sorted(required_character_files - character_files)}")
    hat_files = {path.name for path in hat_package.iterdir() if path.is_file()}
    required_hat_files = {
        f"{PACKAGE_HAT_NAME}.obj",
        f"t_{PACKAGE_HAT_NAME}.png",
        f"m_{PACKAGE_HAT_NAME}.txt",
        "ATTRIBUTION.txt",
    }
    require(required_hat_files <= hat_files, f"Hat files missing: {sorted(required_hat_files - hat_files)}")

    image = bpy.data.images.get("YIER_FLAT_COLOR_ATLAS")
    require(image is not None and tuple(image.size) == (512, 512), "Packed atlas is missing or wrong size")
    require(image.packed_file is not None, "Atlas is not packed into v004")
    print("[YIER v004 verify] PASS")
    print(
        f"[YIER v004 verify] default_objects={len(objects)} default_triangles={character_triangles} "
        f"optional_hat_triangles={stats([local_hat])[1]} resources={resources_root}"
    )


if __name__ == "__main__":
    main()
