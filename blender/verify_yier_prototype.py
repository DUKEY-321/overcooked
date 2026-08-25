"""Read-only structural checks for the generated Yier Blender prototype."""

from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Vector


EXPECTED_BLEND = Path(r"F:\dev\overcooke\characters\yier\source\yier_prototype.blend")
EXPECTED_COLLECTIONS = {
    "REF_EXISTING",
    "SOURCE_YIER",
    "EXPORT_PARTS",
    "WORKSPACE_GUIDES",
}


def mesh_stats(objects: list[bpy.types.Object]) -> tuple[int, int, int]:
    meshes = [obj for obj in objects if obj.type == "MESH"]
    vertices = sum(len(obj.data.vertices) for obj in meshes)
    triangles = 0
    for obj in meshes:
        obj.data.calc_loop_triangles()
        triangles += len(obj.data.loop_triangles)
    return len(meshes), vertices, triangles


def world_dimensions(objects: list[bpy.types.Object]) -> Vector:
    points = [
        obj.matrix_world @ Vector(corner)
        for obj in objects
        if obj.type == "MESH"
        for corner in obj.bound_box
    ]
    if not points:
        return Vector((0.0, 0.0, 0.0))
    lower = Vector(tuple(min(point[index] for point in points) for index in range(3)))
    upper = Vector(tuple(max(point[index] for point in points) for index in range(3)))
    return upper - lower


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    actual_blend = Path(bpy.data.filepath)
    require(actual_blend == EXPECTED_BLEND, f"Unexpected .blend path: {actual_blend}")
    require(EXPECTED_COLLECTIONS.issubset(bpy.data.collections.keys()), "Required collections missing")

    scene = bpy.context.scene
    require(len(bpy.data.scenes) == 1, "Prototype must contain exactly one scene")
    scene_collections = {child.name for child in scene.collection.children}
    require(scene_collections == EXPECTED_COLLECTIONS, f"Unexpected scene collections: {sorted(scene_collections)}")
    require(scene.name == "Yier_Prototype", f"Unexpected scene name: {scene.name}")
    require(scene.unit_settings.system == "METRIC", "Scene is not metric")
    require(abs(scene.unit_settings.scale_length - 1.0) < 1e-8, "Unexpected unit scale")
    require(scene.camera is not None and scene.camera.name == "CAM_FRONT", "Front camera is not active")
    require("README_YIER.txt" in bpy.data.texts, "Embedded README is missing")
    require(len(bpy.data.libraries) == 0, "Linked external Blender libraries are not allowed")

    reference = bpy.data.collections["REF_EXISTING"]
    source = bpy.data.collections["SOURCE_YIER"]
    export = bpy.data.collections["EXPORT_PARTS"]
    guides = bpy.data.collections["WORKSPACE_GUIDES"]

    reference_objects = list(reference.all_objects)
    source_objects = list(source.all_objects)
    guide_names = {obj.name for obj in guides.all_objects}

    require(reference_objects, "No existing chef reference objects were imported")
    require(source_objects, "No Yier source objects were imported")
    require(reference.hide_select, "Reference collection must be selection-locked")
    require(reference.hide_viewport, "Reference collection should start hidden")
    require(reference.hide_render, "Reference collection should be excluded from rendering")
    require({"CAM_FRONT", "CAM_SIDE", "YIER_ORIGIN", "REFERENCE_CENTER"}.issubset(guide_names), "Workspace guides missing")
    require(len(export.all_objects) == 0, "Fresh EXPORT_PARTS collection should be empty")

    reference_was_hidden = reference.hide_viewport
    reference.hide_viewport = False
    bpy.context.view_layer.update()
    ref_meshes, ref_vertices, ref_triangles = mesh_stats(reference_objects)
    ref_size = world_dimensions(reference_objects)
    reference.hide_viewport = reference_was_hidden
    bpy.context.view_layer.update()
    src_meshes, src_vertices, src_triangles = mesh_stats(source_objects)
    require(ref_meshes > 0 and ref_triangles > 0, "Reference meshes are empty")
    require(src_meshes > 0 and src_triangles > 0, "Yier source meshes are empty")

    src_size = world_dimensions(source_objects)
    require(all(math.isfinite(value) and value > 1e-9 for value in ref_size), f"Invalid reference dimensions: {tuple(ref_size)}")
    require(all(math.isfinite(value) and value > 1e-9 for value in src_size), f"Invalid source dimensions: {tuple(src_size)}")

    external_images = [
        image.name
        for image in bpy.data.images
        if image.source in {"FILE", "TILED", "SEQUENCE", "MOVIE"}
        and image.packed_file is None
    ]
    require(not external_images, "Unpacked external images remain: " + ", ".join(external_images))

    armatures = [obj.name for obj in source_objects if obj.type == "ARMATURE"]
    print("[Yier verify] PASS")
    print(f"[Yier verify] reference meshes={ref_meshes} vertices={ref_vertices} triangles={ref_triangles}")
    print(f"[Yier verify] source meshes={src_meshes} vertices={src_vertices} triangles={src_triangles}")
    print(f"[Yier verify] reference dimensions={tuple(round(value, 6) for value in ref_size)}")
    print(f"[Yier verify] source dimensions={tuple(round(value, 6) for value in src_size)}")
    print(f"[Yier verify] materials={len(bpy.data.materials)} images={len(bpy.data.images)}")
    print(f"[Yier verify] source armatures={len(armatures)} actions={len(bpy.data.actions)}")


if __name__ == "__main__":
    main()
