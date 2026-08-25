"""Read-only structural and OBJ round-trip verification for Yier v003."""

from __future__ import annotations

import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(r"F:\dev\overcooke")
EXPECTED_BLEND = PROJECT_ROOT / "characters" / "yier" / "source" / "yier_work-v003.blend"
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
    "Head": ((3384, 5520), (-0.483926, -0.434341, 0.524227), (0.488358, 0.391070, 1.209822)),
}


def parse_package() -> Path:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(arguments) != 2 or arguments[0] != "--package":
        raise RuntimeError("Usage: ... -- --package <174-yier directory>")
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


def require_close(actual: Vector, expected: tuple[float, float, float], label: str, tolerance: float = 2e-5) -> None:
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
        uv_area_twice = abs((uvs[1] - uvs[0]).cross(uvs[2] - uvs[0]))
        require(uv_area_twice > 1e-6, f"{obj.name}: degenerate UV triangle")


def mesh_geometry_equal(left: bpy.types.Object, right: bpy.types.Object) -> bool:
    if len(left.data.vertices) != len(right.data.vertices) or len(left.data.polygons) != len(right.data.polygons):
        return False
    if any(tuple(a.co) != tuple(b.co) for a, b in zip(left.data.vertices, right.data.vertices, strict=True)):
        return False
    if any(tuple(a.vertices) != tuple(b.vertices) for a, b in zip(left.data.polygons, right.data.polygons, strict=True)):
        return False
    left_uv = left.data.uv_layers.active.data
    right_uv = right.data.uv_layers.active.data
    return all(tuple(a.uv) == tuple(b.uv) for a, b in zip(left_uv, right_uv, strict=True))


def verify_blink(open_eyes: bpy.types.Object, blink: bpy.types.Object) -> None:
    require(len(open_eyes.data.vertices) == len(blink.data.vertices), "Blink vertex count mismatch")
    for opened, closed in zip(open_eyes.data.vertices, blink.data.vertices, strict=True):
        center_x = -0.148420 if opened.co.x < 0.0 else 0.159273
        expected_x = center_x + (opened.co.x - center_x) * 1.12
        expected_z = 0.763336 + (opened.co.z - 0.763336) * 0.18
        require(abs(closed.co.x - expected_x) <= 1e-6, "Blink X shaping mismatch")
        require(abs(closed.co.y - opened.co.y) <= 1e-7, "Blink depth changed")
        require(abs(closed.co.z - expected_z) <= 1e-6, "Blink Z shaping mismatch")


def audit_body_weights(body: bpy.types.Object) -> tuple[float, list[int]]:
    thresholds = (0.22, 0.30, 0.38, 0.46, 0.54)
    crossings = [0] * len(thresholds)
    maximum_span = 0.0
    for polygon in body.data.polygons:
        heights = [body.data.vertices[index].co.z for index in polygon.vertices]
        lower = min(heights)
        upper = max(heights)
        maximum_span = max(maximum_span, upper - lower)
        for index, threshold in enumerate(thresholds):
            if lower < threshold < upper:
                crossings[index] += 1
    require(maximum_span <= 0.025, f"Body triangle crosses too much height: {maximum_span}")
    require(crossings == [96, 144, 48, 48, 48], f"Unexpected body weight-plane crossings: {crossings}")
    return maximum_span, crossings


def verify_round_trip(package: Path, objects: dict[str, bpy.types.Object]) -> None:
    for name in sorted(objects):
        obj_path = package / f"{name}.obj"
        require(obj_path.is_file() and obj_path.stat().st_size > 0, f"Missing OBJ: {obj_path}")
        expected_stats = stats([objects[name]])
        expected_lower, expected_upper = bounds([objects[name]])
        before = set(bpy.data.objects)
        result = bpy.ops.wm.obj_import(
            filepath=str(obj_path),
            forward_axis="NEGATIVE_Z",
            up_axis="Y",
            use_split_objects=False,
            use_split_groups=False,
        )
        require("FINISHED" in result, f"OBJ round-trip import failed: {name}")
        created = [obj for obj in set(bpy.data.objects) - before if obj.type == "MESH"]
        require(bool(created), f"OBJ round-trip created no mesh: {name}")
        require(stats(created) == expected_stats, f"OBJ round-trip stats mismatch: {name}")
        actual_lower, actual_upper = bounds(created)
        require_close(actual_lower, tuple(expected_lower), f"{name} round-trip lower")
        require_close(actual_upper, tuple(expected_upper), f"{name} round-trip upper")
        require(all(len(obj.data.uv_layers) == 1 for obj in created), f"{name}: round-trip UV missing")
        for created_obj in created:
            mesh = created_obj.data
            bpy.data.objects.remove(created_obj, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)


def main() -> None:
    package = parse_package()
    require(bpy.app.background, "Verification must run in a background process")
    require(Path(bpy.data.filepath) == EXPECTED_BLEND, f"Unexpected v003 path: {bpy.data.filepath}")
    require(package.is_dir(), f"Package directory is missing: {package}")
    require(len(bpy.data.scenes) == 1, "Expected one scene")
    require(len(bpy.data.libraries) == 0, "Linked Blender libraries are not allowed")

    export = bpy.data.collections.get("EXPORT_PARTS")
    require(export is not None, "Missing EXPORT_PARTS")
    objects = {obj.name: obj for obj in export.all_objects if obj.type == "MESH"}
    require(set(objects) == set(EXPECTED), f"Unexpected export objects: {sorted(objects)}")
    require(export.get("revision") == "v003-first-complete", "Revision metadata mismatch")
    require(export.get("cross_material_duplicate_groups_removed") == 21, "Duplicate group metadata mismatch")
    require(export.get("semantic_triangles_removed") == 8774, "Semantic cleanup metadata mismatch")
    require(export.get("grip_hands_match_open_hands") is True, "Grip/open metadata mismatch")
    require(bpy.context.scene.get("workspace_revision") == "v003-first-complete", "Scene revision mismatch")
    require(not export.hide_viewport and not export.hide_render, "EXPORT_PARTS must be visible")
    require(bpy.data.collections["WORK_YIER"].hide_viewport, "WORK_YIER should be hidden in v003")
    require(bpy.data.collections["REF_EXISTING"].hide_viewport, "Reference should be hidden in v003")
    require(bpy.data.collections["SOURCE_YIER"].hide_viewport, "Combined source should be hidden in v003")

    for name, (expected_stats, expected_lower, expected_upper) in EXPECTED.items():
        obj = objects[name]
        require(obj.matrix_world.is_identity, f"{name}: non-identity transform")
        require(len(obj.modifiers) == 0, f"{name}: unexpected modifier")
        require(not obj.data.shape_keys, f"{name}: unexpected shape keys")
        require(stats([obj]) == expected_stats, f"{name}: unexpected stats {stats([obj])}")
        actual_lower, actual_upper = bounds([obj])
        require_close(actual_lower, expected_lower, f"{name} lower")
        require_close(actual_upper, expected_upper, f"{name} upper")
        validate_mesh(obj)

    require(mesh_geometry_equal(objects["Hand_Open_L"], objects["Hand_Grip_L"]), "Left grip/open geometry differs")
    require(mesh_geometry_equal(objects["Hand_Open_R"], objects["Hand_Grip_R"]), "Right grip/open geometry differs")
    verify_blink(objects["Eyes"], objects["Eyes2_Blinks"])
    maximum_span, crossings = audit_body_weights(objects["Body_Body"])

    image = bpy.data.images.get("YIER_FLAT_COLOR_ATLAS")
    require(image is not None and tuple(image.size) == (512, 512), "Packed atlas is missing or wrong size")
    require(image.packed_file is not None, "Atlas is not packed into v003")
    require((package / "t_Head.png").is_file() and (package / "t_Body.png").is_file(), "Package atlas files are missing")
    verify_round_trip(package, objects)

    total_triangles = sum(stats([obj])[1] for obj in objects.values())
    require(total_triangles == 21531, f"Unexpected exported triangle total: {total_triangles}")
    print("[YIER v003 verify] PASS")
    print(f"[YIER v003 verify] objects={len(objects)} triangles={total_triangles} body_max_span={maximum_span:.6f}")
    print(f"[YIER v003 verify] body_weight_crossings={crossings} package={package}")


if __name__ == "__main__":
    main()
