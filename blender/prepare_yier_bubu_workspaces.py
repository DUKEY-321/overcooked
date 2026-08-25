"""Split, normalize, and save non-destructive Yier/Bubu Blender workspaces.

The downloaded GLB contains both characters, and several meshes combine
disconnected geometry from both sides by material.  This script copies the
source geometry, applies its world transform, splits at the empty X-axis gap,
then scales each character to the existing OC2 chef reference.  The original
prototype and downloaded source files are never overwritten.
"""

from __future__ import annotations

from pathlib import Path
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector


PROJECT_ROOT = Path(r"F:\dev\overcooke")
INPUT_BLEND = PROJECT_ROOT / "characters" / "yier" / "source" / "yier_prototype.blend"
YIER_OUTPUT = PROJECT_ROOT / "characters" / "yier" / "source" / "yier_work-v001.blend"
BUBU_OUTPUT = PROJECT_ROOT / "characters" / "bubu" / "source" / "bubu_work-v001.blend"

SOURCE_COLLECTION = "SOURCE_YIER"
REFERENCE_COLLECTION = "REF_EXISTING"
YIER_COLLECTION = "WORK_YIER"
BUBU_COLLECTION = "WORK_BUBU"
SPLIT_X = 45.0
SPLIT_EPSILON = 1e-6
EXPECTED_STATS = {
    "YIER": (9, 20700, 37986),
    "BUBU": (6, 12616, 22644),
}


def parse_character() -> str:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(arguments) != 2 or arguments[0] != "--character":
        raise RuntimeError("Usage: ... -- --character YIER|BUBU")
    character = arguments[1].upper()
    if character not in EXPECTED_STATS:
        raise RuntimeError(f"Unsupported character: {arguments[1]}")
    return character


def require_safe_start(character: str) -> Path:
    if not bpy.app.background:
        raise RuntimeError("Workspace preparation only runs in Blender background mode")
    if Path(bpy.data.filepath) != INPUT_BLEND:
        raise RuntimeError(f"Unexpected input .blend: {bpy.data.filepath}")
    output = YIER_OUTPUT if character == "YIER" else BUBU_OUTPUT
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing workspace: {output}")
    for name in (YIER_COLLECTION, BUBU_COLLECTION):
        if bpy.data.collections.get(name) is not None:
            raise RuntimeError(f"Working collection already exists in source file: {name}")
    return output


def world_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points = [
        obj.matrix_world @ Vector(corner)
        for obj in objects
        if obj.type == "MESH" and len(obj.data.polygons) > 0
        for corner in obj.bound_box
    ]
    if not points:
        raise RuntimeError("Cannot calculate bounds: no mesh faces")
    lower = Vector(tuple(min(point[index] for point in points) for index in range(3)))
    upper = Vector(tuple(max(point[index] for point in points) for index in range(3)))
    return lower, upper


def create_collection(name: str, color_tag: str) -> bpy.types.Collection:
    collection = bpy.data.collections.new(name)
    collection.color_tag = color_tag
    bpy.context.scene.collection.children.link(collection)
    return collection


def crossing_face_count(mesh: bpy.types.Mesh) -> int:
    count = 0
    for polygon in mesh.polygons:
        xs = [mesh.vertices[index].co.x for index in polygon.vertices]
        if min(xs) < SPLIT_X < max(xs):
            count += 1
    return count


def validate_source_gap(source: bpy.types.Collection) -> tuple[float, float]:
    xs: list[float] = []
    for obj in source.all_objects:
        if obj.type != "MESH" or len(obj.data.polygons) == 0:
            continue
        transformed = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
        xs.extend(vertex.x for vertex in transformed)
    if not xs:
        raise RuntimeError("Source collection has no polygon-mesh vertices")
    if any(abs(value - SPLIT_X) <= SPLIT_EPSILON for value in xs):
        raise RuntimeError(f"A source vertex lies on split X={SPLIT_X}")
    left = [value for value in xs if value < SPLIT_X]
    right = [value for value in xs if value > SPLIT_X]
    if not left or not right:
        raise RuntimeError("Source vertices do not occupy both sides of the split")
    left_max = max(left)
    right_min = min(right)
    if right_min - left_max < 1.0:
        raise RuntimeError(
            f"Source character gap is too small: left_max={left_max} right_min={right_min}"
        )
    return left_max, right_min


def copy_character_meshes(
    source: bpy.types.Collection,
    target: bpy.types.Collection,
    character: str,
) -> tuple[list[bpy.types.Object], int]:
    keep_left = character == "YIER"
    result: list[bpy.types.Object] = []
    discarded_edge_only = 0
    material_copies: dict[bpy.types.Material, bpy.types.Material] = {}

    for source_obj in sorted(source.all_objects, key=lambda item: item.name):
        if source_obj.type != "MESH":
            continue
        if len(source_obj.data.polygons) == 0:
            discarded_edge_only += 1
            continue

        mesh = source_obj.data.copy()
        mesh.name = f"{character}_{source_obj.data.name}"[:63]
        for index, material in enumerate(mesh.materials):
            if material is None:
                continue
            copied = material_copies.get(material)
            if copied is None:
                copied = material.copy()
                copied.name = f"{character}_{material.name}"[:63]
                material_copies[material] = copied
            mesh.materials[index] = copied
        mesh.transform(source_obj.matrix_world)
        mesh.update()

        crossing = crossing_face_count(mesh)
        if crossing:
            bpy.data.meshes.remove(mesh)
            raise RuntimeError(
                f"{source_obj.name}: {crossing} faces cross split X={SPLIT_X}; "
                "automatic character separation is unsafe"
            )

        bm = bmesh.new()
        bm.from_mesh(mesh)
        remove = [
            vertex
            for vertex in bm.verts
            if (vertex.co.x >= SPLIT_X if keep_left else vertex.co.x <= SPLIT_X)
        ]
        if remove:
            bmesh.ops.delete(bm, geom=remove, context="VERTS")
        bm.to_mesh(mesh)
        bm.free()
        mesh.validate(clean_customdata=False)
        mesh.update(calc_edges=True)

        if len(mesh.polygons) == 0:
            bpy.data.meshes.remove(mesh)
            continue

        obj = bpy.data.objects.new(f"{character}_{source_obj.name}"[:63], mesh)
        target.objects.link(obj)
        obj["character"] = character.lower()
        obj["source_object"] = source_obj.name
        obj["split_axis"] = "world_x"
        obj["split_threshold"] = SPLIT_X
        result.append(obj)

    if not result:
        raise RuntimeError(f"No polygon meshes remained for {character}")
    return result, discarded_edge_only


def transform_meshes(
    objects: list[bpy.types.Object],
    reference_lower: Vector,
    reference_upper: Vector,
) -> tuple[float, Vector, Vector]:
    source_lower, source_upper = world_bounds(objects)
    source_height = source_upper.z - source_lower.z
    target_height = reference_upper.z - reference_lower.z
    if source_height <= 0.0 or target_height <= 0.0:
        raise RuntimeError("Source or reference has a non-positive height")

    scale = target_height / source_height
    source_center = (source_lower + source_upper) * 0.5
    reference_center = (reference_lower + reference_upper) * 0.5
    translation = Vector(
        (
            reference_center.x - source_center.x * scale,
            reference_center.y - source_center.y * scale,
            reference_lower.z - source_lower.z * scale,
        )
    )
    transform = Matrix.Translation(translation) @ Matrix.Scale(scale, 4)
    for obj in objects:
        obj.data.transform(transform)
        obj.data.update(calc_edges=True)
    bpy.context.view_layer.update()
    return scale, source_lower, source_upper


def point_camera(camera: bpy.types.Object, target: Vector) -> None:
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def rebuild_guides(reference_lower: Vector, reference_upper: Vector) -> None:
    guides = bpy.data.collections.get("WORKSPACE_GUIDES")
    if guides is None:
        raise RuntimeError("WORKSPACE_GUIDES collection is missing")

    center = (reference_lower + reference_upper) * 0.5
    dimensions = reference_upper - reference_lower
    largest = max(max(dimensions), 0.25)
    distance = largest * 3.0

    reference_center = bpy.data.objects.get("REFERENCE_CENTER")
    if reference_center is not None:
        reference_center.location = center

    front = bpy.data.objects.get("CAM_FRONT")
    side = bpy.data.objects.get("CAM_SIDE")
    if front is None or side is None or front.type != "CAMERA" or side.type != "CAMERA":
        raise RuntimeError("Front/side guide cameras are missing")

    front.location = Vector((center.x, center.y - distance, center.z))
    front.data.ortho_scale = max(dimensions.x, dimensions.z) * 1.35
    point_camera(front, center)

    side.location = Vector((center.x + distance, center.y, center.z))
    side.data.ortho_scale = max(dimensions.y, dimensions.z) * 1.35
    point_camera(side, center)
    bpy.context.scene.camera = front


def collection_stats(objects: list[bpy.types.Object]) -> tuple[int, int, int]:
    vertices = sum(len(obj.data.vertices) for obj in objects)
    triangles = 0
    for obj in objects:
        obj.data.calc_loop_triangles()
        triangles += len(obj.data.loop_triangles)
    return len(objects), vertices, triangles


def save_workspace(
    output: Path,
    character: str,
    visible: bpy.types.Collection,
) -> None:
    visible.hide_viewport = False
    visible.hide_render = False
    bpy.context.scene.name = f"{character.title()}_Work_v001"
    bpy.context.scene["active_character"] = character.lower()
    result = bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False)
    if "FINISHED" not in result:
        raise RuntimeError(f"Saving {character} workspace did not finish: {sorted(result)}")
    if Path(bpy.data.filepath).resolve() != output.resolve():
        raise RuntimeError(f"Blender reports an unexpected saved path: {bpy.data.filepath}")
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"Saved workspace is missing or empty: {output}")
    print(f"[Workspace prepare] Saved {character}: {output}")


def main() -> None:
    character = parse_character()
    output = require_safe_start(character)
    source = bpy.data.collections.get(SOURCE_COLLECTION)
    reference = bpy.data.collections.get(REFERENCE_COLLECTION)
    if source is None or reference is None:
        raise RuntimeError("Source or reference collection is missing")

    # Hidden collections can retain stale world matrices. Evaluate the reference
    # while visible, then restore its locked/hidden presentation before saving.
    reference.hide_viewport = False
    bpy.context.view_layer.update()
    reference_objects = [
        obj
        for obj in reference.all_objects
        if obj.type == "MESH"
        and "Knife" not in obj.name
        and len(obj.data.polygons) > 0
    ]
    reference_lower, reference_upper = world_bounds(reference_objects)
    rebuild_guides(reference_lower, reference_upper)

    left_max, right_min = validate_source_gap(source)
    collection_name = YIER_COLLECTION if character == "YIER" else BUBU_COLLECTION
    color_tag = "COLOR_04" if character == "YIER" else "COLOR_06"
    working = create_collection(collection_name, color_tag)
    objects, discarded = copy_character_meshes(source, working, character)
    scale, source_lower, source_upper = transform_meshes(
        objects, reference_lower, reference_upper
    )

    source.hide_viewport = True
    source.hide_render = True
    reference.hide_select = True
    reference.hide_viewport = True
    reference.hide_render = True

    working["purpose"] = f"Separated and normalized {character.title()} working geometry"
    working["uniform_scale"] = scale
    working["source_bounds"] = str((tuple(source_lower), tuple(source_upper)))
    working["source_gap"] = f"{left_max:.6f}..{right_min:.6f}"

    stats = collection_stats(objects)
    expected = EXPECTED_STATS[character]
    if stats != expected:
        raise RuntimeError(
            f"Unexpected {character} split stats: actual={stats} expected={expected}"
        )

    text = bpy.data.texts.get("README_YIER_BUBU_WORK.txt")
    if text is None:
        text = bpy.data.texts.new("README_YIER_BUBU_WORK.txt")
    text.clear()
    text.write(
        "LOCAL SINGLE-PLAYER / NON-COMMERCIAL PROTOTYPE\n"
        "================================================\n\n"
        f"Active character: {character}\n"
        f"Meshes/vertices/triangles: {stats}\n"
        f"Uniform scale: {scale:.9f}\n"
        f"Source split gap: {left_max:.6f}..{right_min:.6f}\n"
        f"Discarded SketchUp edge-only source meshes: {discarded}\n\n"
        "SOURCE_YIER is the hidden, untouched combined Sketchfab import.\n"
        f"{collection_name} is a separated normalized copy with independent materials.\n"
        "REF_EXISTING remains hidden and selection-locked.\n"
        "No game export parts have been created yet.\n"
    )

    print(
        f"[Workspace prepare] {character} meshes={stats[0]} vertices={stats[1]} "
        f"triangles={stats[2]} scale={scale:.9f}"
    )
    print(
        "[Workspace prepare] Reference bounds "
        f"min={tuple(round(value, 6) for value in reference_lower)} "
        f"max={tuple(round(value, 6) for value in reference_upper)}"
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    save_workspace(output, character, working)


if __name__ == "__main__":
    main()
