"""Read-only structural, animation-state, and OBJ round-trip verification for Bubu v003."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BLEND = PROJECT_ROOT / "characters" / "bubu" / "source" / "bubu_work-v003.blend"
YIER_RESOURCE = PROJECT_ROOT / "exports" / "Resources" / "174-yier"
EXPECTED = {
    "Body_Body": ((554, 1104), (-0.228293896, -0.264621526, 0.270769268), (0.240496397, 0.204168767, 0.630996943)),
    "Body_Bottom": ((1108, 2208), (-0.181902885, -0.110901773, 0.210470989), (0.194105148, 0.051354528, 0.340500653)),
    "Body_Tail": ((554, 1104), (-0.056956291, 0.159698755, 0.328196585), (0.049491167, 0.265980214, 0.434477925)),
    "Eyes": ((334, 330), (-0.189543963, -0.396011293, 0.754554689), (0.200686693, -0.372008294, 0.822292686)),
    "Eyes2_Blinks": ((334, 330), (-0.193658456, -0.396011293, 0.782327235), (0.204801172, -0.372008294, 0.794520080)),
    "Hand_Grip_L": ((554, 1104), (0.223769814, -0.112868197, 0.429248929), (0.391484171, 0.006951280, 0.611219943)),
    "Hand_Grip_R": ((554, 1104), (-0.391570807, -0.112868197, 0.429248929), (-0.223856196, 0.006951280, 0.611219943)),
    "Hand_Open_L": ((554, 1104), (0.223769814, -0.112868197, 0.429248929), (0.391484171, 0.006951280, 0.611219943)),
    "Hand_Open_R": ((554, 1104), (-0.391570807, -0.112868197, 0.429248929), (-0.223856196, 0.006951280, 0.611219943)),
    "Head": ((3910, 6808), (-0.409771085, -0.405969590, 0.538464546), (0.414203405, 0.362698704, 1.209822059)),
}
EXPECTED_FILES = {
    "INFO",
    "ATTRIBUTION.txt",
    "t_Head.png",
    "t_Body.png",
    "m_Head.txt",
    "m_Body.txt",
    *(f"{name}.obj" for name in EXPECTED),
}
LEFT_BLINK_PIVOT = (-0.155256510, 0.788423657)
RIGHT_BLINK_PIVOT = (0.166399360, 0.788423657)


def parse_package() -> Path:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(arguments) != 2 or arguments[0] != "--package":
        raise RuntimeError("Usage: ... -- --package <175-bubu directory>")
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
    require(len(mesh.materials) == 1 and mesh.materials[0].name == "BUBU_GAME_ATLAS", f"{obj.name}: atlas material mismatch")
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
        center_x, center_z = LEFT_BLINK_PIVOT if opened.co.x < 0.0 else RIGHT_BLINK_PIVOT
        expected_x = center_x + (opened.co.x - center_x) * 1.12
        expected_z = center_z + (opened.co.z - center_z) * 0.18
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
    require(maximum_span <= 0.0261, f"Body triangle crosses too much height: {maximum_span}")
    require(crossings == [0, 48, 48, 48, 48], f"Unexpected body weight-plane crossings: {crossings}")
    return maximum_span, crossings


def verify_package_files(package: Path) -> None:
    actual = {entry.name for entry in package.iterdir() if entry.is_file()}
    require(actual == EXPECTED_FILES, f"Unexpected package files: missing={sorted(EXPECTED_FILES - actual)} extra={sorted(actual - EXPECTED_FILES)}")
    info = (package / "INFO").read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    require(info == "ID=175\n", "INFO must be exactly ID=175")
    attribution = (package / "ATTRIBUTION.txt").read_text(encoding="utf-8")
    for required in ("DUKEY", "hong2695429209", "CC BY 4.0", "sketchfab.com/3d-models/yier-b15f13be61224129ba3123c0041206c2"):
        require(required in attribution, f"Attribution is missing: {required}")
    for name in ("m_Head.txt", "m_Body.txt"):
        require((package / name).read_bytes() == (YIER_RESOURCE / name).read_bytes(), f"Shared material settings differ: {name}")
    head_hash = hashlib.sha256((package / "t_Head.png").read_bytes()).hexdigest()
    body_hash = hashlib.sha256((package / "t_Body.png").read_bytes()).hexdigest()
    require(head_hash == body_hash, "Head and body atlases must be byte-identical")


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
    require(export.get("source_components") == 39, "Source component metadata mismatch")
    require(export.get("visible_components") == 29, "Visible component metadata mismatch")
    require(export.get("cross_material_duplicate_groups_removed") == 10, "Duplicate group metadata mismatch")
    require(export.get("cross_material_triangles_removed") == 766, "Duplicate triangle metadata mismatch")
    require(export.get("runtime_triangle_total") == 13762, "Runtime triangle metadata mismatch")
    require(export.get("grip_hands_match_open_hands") is True, "Grip/open metadata mismatch")
    require(bpy.context.scene.get("workspace_revision") == "v003-first-complete", "Scene revision mismatch")
    require(bpy.context.scene.get("active_character") == "bubu", "Active character metadata mismatch")
    require(not export.hide_viewport and not export.hide_render, "EXPORT_PARTS must be visible")
    for collection_name in ("WORK_BUBU", "REF_EXISTING", "SOURCE_YIER"):
        require(bpy.data.collections[collection_name].hide_viewport, f"{collection_name} should be hidden in v003")

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

    image = bpy.data.images.get("BUBU_FLAT_COLOR_ATLAS")
    require(image is not None and tuple(image.size) == (512, 512), "Packed atlas is missing or wrong size")
    require(image.channels == 4, "Packed atlas must be RGBA")
    require(image.packed_file is not None, "Atlas is not packed into v003")
    verify_package_files(package)
    verify_round_trip(package, objects)

    total_vertices = sum(stats([obj])[0] for obj in objects.values())
    total_triangles = sum(stats([obj])[1] for obj in objects.values())
    require((total_vertices, total_triangles) == (9010, 16300), f"Unexpected exported totals: {(total_vertices, total_triangles)}")
    print("[BUBU v003 verify] PASS")
    print(f"[BUBU v003 verify] objects={len(objects)} vertices={total_vertices} triangles={total_triangles}")
    print(f"[BUBU v003 verify] runtime_triangles=13762 body_max_span={maximum_span:.8f}")
    print(f"[BUBU v003 verify] body_weight_crossings={crossings} package={package}")


if __name__ == "__main__":
    main()
