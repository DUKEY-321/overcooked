"""Render read-only front/side/back and per-material-object QA views."""

from __future__ import annotations

import math
from pathlib import Path
import re
import sys

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(r"F:\dev\overcooke")


def parse_arguments() -> tuple[str, Path, str, str, str | None]:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(arguments) % 2 != 0:
        raise RuntimeError("Arguments must be --key value pairs")
    options = dict(zip(arguments[0::2], arguments[1::2], strict=True))
    if "--character" not in options or "--output" not in options:
        raise RuntimeError(
            "Usage: ... -- --character YIER|BUBU --output <directory> "
            "[--collection <name>] [--extra-collection <name>] "
            "[--state all|open|blink|grip]"
        )
    character = options["--character"].upper()
    if character not in {"YIER", "BUBU"}:
        raise RuntimeError(f"Unsupported character: {options['--character']}")
    collection_name = options.get("--collection", f"WORK_{character}")
    state = options.get("--state", "all").lower()
    if state not in {"all", "open", "blink", "grip"}:
        raise RuntimeError(f"Unsupported render state: {state}")
    return (
        character,
        Path(options["--output"]).resolve(),
        collection_name,
        state,
        options.get("--extra-collection"),
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def mesh_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points = [
        obj.matrix_world @ Vector(corner)
        for obj in objects
        if obj.type == "MESH" and len(obj.data.polygons) > 0
        for corner in obj.bound_box
    ]
    require(bool(points), "No renderable mesh bounds")
    lower = Vector(tuple(min(point[index] for point in points) for index in range(3)))
    upper = Vector(tuple(max(point[index] for point in points) for index in range(3)))
    return lower, upper


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_area_light(collection: bpy.types.Collection, name: str, location: tuple[float, float, float], energy: float, size: float) -> None:
    data = bpy.data.lights.new(name=name, type="AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(name=name, object_data=data)
    collection.objects.link(obj)
    obj.location = location
    look_at(obj, Vector((0.0, 0.0, 0.72)))


def render(scene: bpy.types.Scene, camera: bpy.types.Object, target: Vector, location: Vector, ortho_scale: float, path: Path) -> None:
    camera.location = location
    look_at(camera, target)
    camera.data.ortho_scale = ortho_scale
    scene.render.filepath = str(path)
    result = bpy.ops.render.render(write_still=True)
    require("FINISHED" in result, f"Render failed: {path}")
    require(path.is_file() and path.stat().st_size > 0, f"Missing render: {path}")


def main() -> None:
    character, output, collection_name, state, extra_collection_name = parse_arguments()
    require(bpy.app.background, "QA rendering must use an isolated background process")
    output.mkdir(parents=True, exist_ok=True)

    work = bpy.data.collections.get(collection_name)
    require(work is not None, f"Missing collection: {collection_name}")
    render_collections = [work]
    if extra_collection_name is not None:
        extra_collection = bpy.data.collections.get(extra_collection_name)
        require(extra_collection is not None, f"Missing extra collection: {extra_collection_name}")
        render_collections.append(extra_collection)
    meshes = sorted(
        {
            obj
            for collection in render_collections
            for obj in collection.all_objects
            if obj.type == "MESH" and len(obj.data.polygons) > 0
        },
        key=lambda obj: obj.name,
    )
    require(bool(meshes), "No work meshes")
    for collection in bpy.data.collections:
        collection.hide_render = collection not in render_collections
    for collection in render_collections:
        collection.hide_render = False
    excluded: set[str] = set()
    if state == "open":
        excluded = {"Eyes2_Blinks", "Hand_Grip_L", "Hand_Grip_R"}
    elif state == "blink":
        excluded = {"Eyes", "Hand_Grip_L", "Hand_Grip_R"}
    elif state == "grip":
        excluded = {"Eyes2_Blinks", "Hand_Open_L", "Hand_Open_R"}
    for obj in meshes:
        obj.hide_render = obj.name in excluded

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 640
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.image_settings.color_mode = "RGBA"
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.035, 0.04, 0.05, 1.0)
    background.inputs["Strength"].default_value = 0.65

    qa_collection = bpy.data.collections.new("QA_RENDER_TEMP")
    scene.collection.children.link(qa_collection)
    camera_data = bpy.data.cameras.new("QA_CAMERA")
    camera_data.type = "ORTHO"
    camera = bpy.data.objects.new("QA_CAMERA", camera_data)
    qa_collection.objects.link(camera)
    scene.camera = camera

    add_area_light(qa_collection, "QA_KEY", (-3.0, -4.0, 4.5), 500.0, 4.0)
    add_area_light(qa_collection, "QA_FILL", (3.0, -2.0, 2.5), 300.0, 3.0)
    add_area_light(qa_collection, "QA_RIM", (0.0, 3.0, 3.5), 400.0, 3.0)

    visible_meshes = [obj for obj in meshes if not obj.hide_render]
    lower, upper = mesh_bounds(visible_meshes)
    target = (lower + upper) * 0.5
    dimensions = upper - lower
    distance = max(dimensions) * 4.0
    front_scale = max(dimensions.x, dimensions.z) * 1.18
    side_scale = max(dimensions.y, dimensions.z) * 1.18
    prefix = character.lower() if state == "all" else f"{character.lower()}_{state}"
    render(scene, camera, target, target + Vector((0.0, -distance, 0.0)), front_scale, output / f"{prefix}_front.png")
    render(scene, camera, target, target + Vector((distance, 0.0, 0.0)), side_scale, output / f"{prefix}_side.png")
    render(scene, camera, target, target + Vector((0.0, distance, 0.0)), front_scale, output / f"{prefix}_back.png")

    for index, selected in enumerate(meshes, start=1):
        for obj in meshes:
            obj.hide_render = obj != selected
        object_lower, object_upper = mesh_bounds([selected])
        object_target = (object_lower + object_upper) * 0.5
        object_dimensions = object_upper - object_lower
        object_scale = max(object_dimensions.x, object_dimensions.z, 0.05) * 1.22
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", selected.name)
        render(
            scene,
            camera,
            object_target,
            object_target + Vector((0.0, -distance, 0.0)),
            object_scale,
            output / f"{index:02d}_{safe_name}.png",
        )

    print(f"[{character} QA render] PASS images={3 + len(meshes)} output={output}")


if __name__ == "__main__":
    main()
