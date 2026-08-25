"""Read-only verification for a separated Yier or Bubu workspace."""

from __future__ import annotations

import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(r"F:\dev\overcooke")
EXPECTED = {
    "YIER": {
        "collection": "WORK_YIER",
        "revisions": {
            "v001": {
                "path": PROJECT_ROOT / "characters" / "yier" / "source" / "yier_work-v001.blend",
                "stats": (9, 20700, 37986),
            },
            "v002": {
                "path": PROJECT_ROOT / "characters" / "yier" / "source" / "yier_work-v002.blend",
                "stats": (9, 15354, 27767),
                "deduplicated_reverse_shells": 13,
                "deduplicated_triangles": 10219,
            },
        },
    },
    "BUBU": {
        "collection": "WORK_BUBU",
        "revisions": {
            "v001": {
                "path": PROJECT_ROOT / "characters" / "bubu" / "source" / "bubu_work-v001.blend",
                "stats": (6, 12616, 22644),
            },
            "v002": {
                "path": PROJECT_ROOT / "characters" / "bubu" / "source" / "bubu_work-v002.blend",
                "stats": (6, 8338, 14528),
                "deduplicated_reverse_shells": 13,
                "deduplicated_triangles": 8116,
            },
        },
    },
}


def parse_arguments() -> tuple[str, str]:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if (
        len(arguments) != 4
        or arguments[0] != "--character"
        or arguments[2] != "--revision"
    ):
        raise RuntimeError("Usage: ... -- --character YIER|BUBU --revision v001|v002")
    character = arguments[1].upper()
    if character not in EXPECTED:
        raise RuntimeError(f"Unsupported character: {arguments[1]}")
    revision = arguments[3].lower()
    if revision not in EXPECTED[character]["revisions"]:
        raise RuntimeError(f"Unsupported revision: {arguments[3]}")
    return character, revision


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
    require(bool(points), "No polygon-mesh bounds are available")
    lower = Vector(tuple(min(point[index] for point in points) for index in range(3)))
    upper = Vector(tuple(max(point[index] for point in points) for index in range(3)))
    return lower, upper


def stats(objects: list[bpy.types.Object]) -> tuple[int, int, int]:
    meshes = [obj for obj in objects if obj.type == "MESH"]
    vertices = sum(len(obj.data.vertices) for obj in meshes)
    triangles = 0
    for obj in meshes:
        obj.data.calc_loop_triangles()
        triangles += len(obj.data.loop_triangles)
    return len(meshes), vertices, triangles


def main() -> None:
    character, revision = parse_arguments()
    character_expected = EXPECTED[character]
    expected = character_expected["revisions"][revision]
    actual_path = Path(bpy.data.filepath)
    require(actual_path == expected["path"], f"Unexpected workspace path: {actual_path}")
    require(len(bpy.data.scenes) == 1, "Workspace must contain exactly one scene")
    require(len(bpy.data.libraries) == 0, "Linked external Blender libraries are not allowed")

    expected_collections = {
        "REF_EXISTING",
        "SOURCE_YIER",
        "EXPORT_PARTS",
        "WORKSPACE_GUIDES",
        character_expected["collection"],
    }
    scene_collections = {child.name for child in bpy.context.scene.collection.children}
    require(scene_collections == expected_collections, f"Unexpected scene collections: {sorted(scene_collections)}")

    reference = bpy.data.collections["REF_EXISTING"]
    source = bpy.data.collections["SOURCE_YIER"]
    work = bpy.data.collections[character_expected["collection"]]
    require(reference.hide_select and reference.hide_viewport and reference.hide_render, "Reference must be locked and hidden")
    require(source.hide_viewport and source.hide_render, "Combined source must be hidden")
    require(not work.hide_viewport and not work.hide_render, "Active work collection must be visible")
    require("README_YIER_BUBU_WORK.txt" in bpy.data.texts, "Embedded workspace README is missing")
    require(bpy.context.scene.get("active_character") == character.lower(), "Scene character metadata is incorrect")
    if revision == "v002":
        require(work.get("revision") == "v002", "V002 collection revision metadata is missing")
        require(
            bpy.context.scene.get("workspace_revision") == "v002-deduplicated",
            "V002 scene revision metadata is missing",
        )
        require(
            work.get("deduplicated_reverse_shells") == expected["deduplicated_reverse_shells"],
            "Unexpected reverse-shell group count",
        )
        require(
            work.get("deduplicated_triangles") == expected["deduplicated_triangles"],
            "Unexpected deduplicated triangle count",
        )

    objects = list(work.all_objects)
    actual_stats = stats(objects)
    require(actual_stats == expected["stats"], f"Unexpected mesh stats: {actual_stats}")
    require(all(obj.matrix_world.is_identity for obj in objects), "Work object transforms are not identity")
    require(all(len(obj.modifiers) == 0 for obj in objects), "Unexpected work modifiers found")
    require(all(not obj.data.shape_keys for obj in objects), "Unexpected shape keys found")

    work_materials = {
        slot.material
        for obj in objects
        for slot in obj.material_slots
        if slot.material is not None
    }
    source_materials = {
        slot.material
        for obj in source.all_objects
        if obj.type == "MESH"
        for slot in obj.material_slots
        if slot.material is not None
    }
    require(work_materials.isdisjoint(source_materials), "Work materials still share source datablocks")
    require(all(material.name.startswith(f"{character}_") for material in work_materials), "Work material prefix is incorrect")

    work_lower, work_upper = bounds(objects)
    require(all(math.isfinite(value) for value in (*work_lower, *work_upper)), "Non-finite work bounds")

    reference.hide_viewport = False
    bpy.context.view_layer.update()
    reference_objects = [
        obj
        for obj in reference.all_objects
        if obj.type == "MESH" and "Knife" not in obj.name and len(obj.data.polygons) > 0
    ]
    reference_lower, reference_upper = bounds(reference_objects)
    reference.hide_viewport = True
    bpy.context.view_layer.update()

    tolerance = 1e-5
    require(abs(work_lower.z - reference_lower.z) <= tolerance, "Work bottom is not aligned to reference")
    require(abs(work_upper.z - reference_upper.z) <= tolerance, "Work top is not aligned to reference")
    work_center = (work_lower + work_upper) * 0.5
    reference_center = (reference_lower + reference_upper) * 0.5
    require(abs(work_center.x - reference_center.x) <= tolerance, "Work X center is not aligned")
    require(abs(work_center.y - reference_center.y) <= tolerance, "Work depth center is not aligned")

    custom_normals = sum(1 for obj in objects if obj.data.has_custom_normals)
    require(custom_normals == actual_stats[0], "One or more work meshes lost custom normals")

    print(f"[{character} {revision} workspace verify] PASS")
    print(f"[{character} workspace verify] meshes={actual_stats[0]} vertices={actual_stats[1]} triangles={actual_stats[2]}")
    print(f"[{character} workspace verify] bounds min={tuple(round(value, 6) for value in work_lower)} max={tuple(round(value, 6) for value in work_upper)}")
    print(f"[{character} workspace verify] materials={len(work_materials)} custom_normals={custom_normals}")


if __name__ == "__main__":
    main()
