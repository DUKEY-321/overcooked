"""Create a safe Blender workspace for the OC2 Yier chef prototype.

Run this file from a fresh, unsaved Blender startup scene.  It reads the
existing pink-pig OC2DIYChef package as a locked visual reference, but never
writes to that package.  The resulting .blend is saved only when every
required collection and at least one reference OBJ were created successfully.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(r"F:\dev\overcooke")
OUTPUT_BLEND = PROJECT_ROOT / "characters" / "yier" / "source" / "yier_prototype.blend"
REFERENCE_DIR = Path(
    r"D:\SteamLibrary\steamapps\common\Overcooked! 2\BepInEx\plugins"
    r"\OC2DIYChef\Resources\171-pinkpig"
)
YIER_SOURCE_DIR = PROJECT_ROOT / "assets" / "source_yier"

REF_COLLECTION = "REF_EXISTING"
SOURCE_COLLECTION = "SOURCE_YIER"
EXPORT_COLLECTION = "EXPORT_PARTS"
GUIDE_COLLECTION = "WORKSPACE_GUIDES"

REQUIRED_EXPORT_NAMES = (
    "Head",
    "Eyes",
    "Eyes2_Blinks",
    "Hand_Open_L",
    "Hand_Open_R",
    "Hand_Grip_L",
    "Hand_Grip_R",
    "Body_Body",
    "Body_Bottom",
)


def require_safe_start() -> None:
    """Refuse to overwrite files or modify a user's active Blender project."""
    if not bpy.app.background:
        raise RuntimeError(
            "For safety this initializer only runs in an isolated background process. "
            "Use blender.exe --background --factory-startup --python <script>. "
            "Open the generated .blend interactively only after verification."
        )

    if OUTPUT_BLEND.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing file: {OUTPUT_BLEND}\n"
            "Rename or move that file before deliberately creating a new prototype."
        )

    if not REFERENCE_DIR.is_dir():
        raise FileNotFoundError(f"Reference directory is missing: {REFERENCE_DIR}")

    reference_objs = sorted(REFERENCE_DIR.glob("*.obj"))
    if not reference_objs:
        raise FileNotFoundError(f"No OBJ reference parts found in: {REFERENCE_DIR}")

    # Opening this script in Blender's Text Editor marks a new file as dirty,
    # so is_dirty cannot distinguish the script text from real modelling work.
    # A saved filepath is always unsafe; for an unsaved file, validate the
    # complete factory-startup object/collection shape below.
    if bpy.data.filepath:
        raise RuntimeError(
            "This initializer only runs in a fresh, unsaved Blender startup scene. "
            "Use File > New > General, then run the script again."
        )

    if len(bpy.data.scenes) != 1:
        raise RuntimeError("Multiple scenes exist; refusing to modify this Blender session")

    scene = bpy.context.scene
    startup_names = {"Cube", "Camera", "Light"}
    actual_names = {obj.name for obj in scene.objects}
    if actual_names not in (set(), startup_names):
        raise RuntimeError(
            "Scene is not an empty or factory General startup scene; refusing to clear: "
            + ", ".join(sorted(actual_names))
        )

    if len(bpy.data.objects) != len(scene.objects):
        raise RuntimeError("Unlinked/orphan objects exist; refusing to modify this Blender session")

    child_names = {child.name for child in scene.collection.children}
    allowed_children = (set(), {"Collection"})
    if child_names not in allowed_children:
        raise RuntimeError(
            "Unexpected scene collections exist; refusing to clear: "
            + ", ".join(sorted(child_names))
        )

    if actual_names == startup_names:
        cube = scene.objects["Cube"]
        expected_types = {"Cube": "MESH", "Camera": "CAMERA", "Light": "LIGHT"}
        wrong_types = [
            name for name, expected in expected_types.items() if scene.objects[name].type != expected
        ]
        cube_is_default = (
            len(cube.data.vertices) == 8
            and len(cube.data.polygons) == 6
            and cube.location.length < 1e-8
            and cube.rotation_euler.to_matrix().is_identity
            and all(abs(value - 1.0) < 1e-8 for value in cube.scale)
        )
        if wrong_types or not cube_is_default:
            raise RuntimeError("Factory startup objects were modified; refusing to clear the scene")


def clear_startup_scene(scene: bpy.types.Scene) -> None:
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    # A normal General startup file has no custom child collections, but remove
    # empty startup children if present so the generated hierarchy is exact.
    for child in list(scene.collection.children):
        scene.collection.children.unlink(child)
        if child.users == 0:
            bpy.data.collections.remove(child)


def create_collection(scene: bpy.types.Scene, name: str, color_tag: str) -> bpy.types.Collection:
    if bpy.data.collections.get(name) is not None:
        raise RuntimeError(f"Collection already exists in fresh scene: {name}")
    collection = bpy.data.collections.new(name)
    collection.color_tag = color_tag
    scene.collection.children.link(collection)
    return collection


def find_layer_collection(
    layer_collection: bpy.types.LayerCollection, target: bpy.types.Collection
) -> bpy.types.LayerCollection | None:
    if layer_collection.collection == target:
        return layer_collection
    for child in layer_collection.children:
        match = find_layer_collection(child, target)
        if match is not None:
            return match
    return None


def activate_collection(scene: bpy.types.Scene, collection: bpy.types.Collection) -> None:
    layer_collection = find_layer_collection(
        scene.view_layers[0].layer_collection, collection
    )
    if layer_collection is None:
        raise RuntimeError(f"Collection is not present in active view layer: {collection.name}")
    scene.view_layers[0].active_layer_collection = layer_collection


def move_to_collection(obj: bpy.types.Object, collection: bpy.types.Collection) -> None:
    for current in list(obj.users_collection):
        current.objects.unlink(obj)
    collection.objects.link(obj)


def import_obj(path: Path) -> None:
    """Use Blender 4.x's importer, with the Blender 3.x add-on as fallback."""
    if hasattr(bpy.ops.wm, "obj_import"):
        bpy.ops.wm.obj_import(
            filepath=str(path),
            forward_axis="NEGATIVE_Z",
            up_axis="Y",
            use_split_objects=True,
            use_split_groups=True,
        )
        return

    if hasattr(bpy.ops.import_scene, "obj"):
        bpy.ops.import_scene.obj(
            filepath=str(path),
            axis_forward="-Z",
            axis_up="Y",
            use_split_objects=True,
            use_split_groups=True,
        )
        return

    raise RuntimeError("No OBJ importer is available in this Blender installation")


def imported_objects(before: set[bpy.types.Object]) -> set[bpy.types.Object]:
    return set(bpy.data.objects) - before


def import_reference_parts(
    scene: bpy.types.Scene, collection: bpy.types.Collection
) -> list[bpy.types.Object]:
    activate_collection(scene, collection)
    result: list[bpy.types.Object] = []

    for obj_path in sorted(REFERENCE_DIR.glob("*.obj")):
        before = set(bpy.data.objects)
        import_obj(obj_path)
        created = imported_objects(before)
        if not created:
            raise RuntimeError(f"Importer created no objects for: {obj_path}")
        for obj in created:
            move_to_collection(obj, collection)
            obj.name = f"REF_{obj_path.stem}_{obj.name}"
            obj.hide_select = True
            obj["oc2_reference"] = True
            obj["oc2_reference_file"] = str(obj_path)
            result.append(obj)

    collection["purpose"] = "Locked visual reference imported from OC2DIYChef"
    collection["source_directory"] = str(REFERENCE_DIR)
    collection["do_not_edit"] = True
    collection.hide_select = True
    collection.hide_render = True
    return result


def source_candidates() -> list[Path]:
    """Choose one source format to avoid importing duplicate Sketchfab exports."""
    priorities = ((".glb",), (".gltf",), (".fbx",), (".obj",), (".dae",))
    all_files = [path for path in YIER_SOURCE_DIR.rglob("*") if path.is_file()]
    for suffixes in priorities:
        matches = sorted(path for path in all_files if path.suffix.lower() in suffixes)
        if matches:
            if len(matches) > 1:
                display = "\n- ".join(str(path) for path in matches)
                raise RuntimeError(
                    "Multiple source files with the same preferred format were found; "
                    "refusing to stack duplicate models:\n- " + display
                )
            return matches
    return []


def import_source_file(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix in {".glb", ".gltf"}:
        result = bpy.ops.import_scene.gltf(filepath=str(path), import_pack_images=True)
    elif suffix == ".fbx":
        result = bpy.ops.import_scene.fbx(filepath=str(path), axis_forward="-Z", axis_up="Y")
    elif suffix == ".obj":
        import_obj(path)
        return
    elif suffix == ".dae":
        try:
            result = bpy.ops.wm.collada_import(filepath=str(path))
        except (AttributeError, RuntimeError) as exc:
            raise RuntimeError(
                "A DAE source was found, but this Blender build has no Collada importer. "
                "Install/enable the official Collada extension or download Sketchfab GLB."
            ) from exc
    else:
        raise RuntimeError(f"Unsupported source format: {path}")

    if "FINISHED" not in result:
        raise RuntimeError(f"Importer did not finish for {path}: {sorted(result)}")


def import_optional_yier_source(
    scene: bpy.types.Scene, collection: bpy.types.Collection
) -> list[bpy.types.Object]:
    activate_collection(scene, collection)
    result: list[bpy.types.Object] = []
    for source_path in source_candidates():
        before = set(bpy.data.objects)
        import_source_file(source_path)
        created = imported_objects(before)
        if not created:
            raise RuntimeError(f"Importer created no objects for: {source_path}")
        for obj in created:
            move_to_collection(obj, collection)
            obj["yier_source_file"] = str(source_path)
            result.append(obj)

    collection["purpose"] = "Editable source model for Yier retopology and part separation"
    collection["source_directory"] = str(YIER_SOURCE_DIR)
    return result


def bounds(objects: Iterable[bpy.types.Object]) -> tuple[Vector, Vector]:
    points: list[Vector] = []
    for obj in objects:
        if obj.type not in {"MESH", "CURVE", "SURFACE", "META", "FONT"}:
            continue
        points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    if not points:
        return Vector((-0.5, -0.5, 0.0)), Vector((0.5, 0.5, 2.0))
    return (
        Vector(tuple(min(point[index] for point in points) for index in range(3))),
        Vector(tuple(max(point[index] for point in points) for index in range(3))),
    )


def point_camera(camera: bpy.types.Object, target: Vector) -> None:
    direction = target - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_camera(
    name: str,
    location: Vector,
    target: Vector,
    ortho_scale: float,
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    data = bpy.data.cameras.new(name)
    data.type = "ORTHO"
    data.ortho_scale = max(ortho_scale, 0.1)
    data.lens = 50
    data.clip_start = 0.001
    data.clip_end = max(1000.0, (location - target).length * 20.0)
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.location = location
    point_camera(obj, target)
    return obj


def add_empty(
    name: str, location: Vector, size: float, collection: bpy.types.Collection
) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = size
    obj.location = location
    collection.objects.link(obj)
    return obj


def build_guides(
    scene: bpy.types.Scene,
    collection: bpy.types.Collection,
    reference_objects: list[bpy.types.Object],
) -> None:
    lower, upper = bounds(reference_objects)
    center = (lower + upper) * 0.5
    dimensions = upper - lower
    largest = max(max(dimensions), 0.25)
    distance = largest * 3.0
    margin = 1.35

    add_empty("YIER_ORIGIN", Vector((0.0, 0.0, 0.0)), largest * 0.06, collection)
    add_empty("REFERENCE_CENTER", center, largest * 0.04, collection)

    front = add_camera(
        "CAM_FRONT",
        Vector((center.x, center.y - distance, center.z)),
        center,
        max(dimensions.x, dimensions.z) * margin,
        collection,
    )
    add_camera(
        "CAM_SIDE",
        Vector((center.x + distance, center.y, center.z)),
        center,
        max(dimensions.y, dimensions.z) * margin,
        collection,
    )
    scene.camera = front
    collection["purpose"] = "Origin and orthographic front/side inspection cameras"


def configure_scene(scene: bpy.types.Scene) -> None:
    scene.name = "Yier_Prototype"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"
    scene.render.resolution_x = 1080
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = True
    scene["project"] = "Overcooked 2 DIY Chef - Yier prototype"
    scene["reference_package"] = str(REFERENCE_DIR)
    scene["export_axes"] = "OBJ forward -Z, up Y"


def add_embedded_readme(source_count: int, reference_count: int) -> None:
    text = bpy.data.texts.new("README_YIER.txt")
    text.write(
        "YIER / OC2DIYChef PROTOTYPE\n"
        "================================\n\n"
        f"Reference objects imported: {reference_count}\n"
        f"Yier source objects imported: {source_count}\n\n"
        "Collections:\n"
        "- REF_EXISTING: packed, hidden, selection-locked visual reference.\n"
        "- SOURCE_YIER: editable source/retopology work.\n"
        "- EXPORT_PARTS: final game-ready mesh parts only.\n"
        "- WORKSPACE_GUIDES: front/side orthographic cameras and origin.\n\n"
        "Expected final part names:\n- "
        + "\n- ".join(REQUIRED_EXPORT_NAMES)
        + "\n\nDo not edit REF_EXISTING. Toggle its monitor icon only for comparison.\n"
    )


def validate_before_save(
    reference_objects: list[bpy.types.Object],
    collections: dict[str, bpy.types.Collection],
) -> None:
    required = {REF_COLLECTION, SOURCE_COLLECTION, EXPORT_COLLECTION, GUIDE_COLLECTION}
    missing = sorted(required - collections.keys())
    if missing:
        raise RuntimeError("Required collections are missing: " + ", ".join(missing))
    scene_children = {child.name for child in bpy.context.scene.collection.children}
    if scene_children != required:
        raise RuntimeError(
            "Unexpected scene collection structure: " + ", ".join(sorted(scene_children))
        )
    if len(bpy.data.scenes) != 1:
        raise RuntimeError("Prototype must contain exactly one scene")
    if not reference_objects:
        raise RuntimeError("No existing OC2 reference objects were imported")
    if OUTPUT_BLEND.exists():
        raise FileExistsError(f"Output appeared during initialization; refusing overwrite: {OUTPUT_BLEND}")


def main() -> None:
    require_safe_start()
    OUTPUT_BLEND.parent.mkdir(parents=True, exist_ok=True)
    YIER_SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    scene = bpy.context.scene
    clear_startup_scene(scene)
    configure_scene(scene)

    ref = create_collection(scene, REF_COLLECTION, "COLOR_05")
    source = create_collection(scene, SOURCE_COLLECTION, "COLOR_04")
    export = create_collection(scene, EXPORT_COLLECTION, "COLOR_01")
    guides = create_collection(scene, GUIDE_COLLECTION, "COLOR_08")
    export["purpose"] = "Final OC2DIYChef OBJ meshes; use exact expected part names"
    export["expected_part_names"] = ",".join(REQUIRED_EXPORT_NAMES)

    reference_objects = import_reference_parts(scene, ref)
    source_objects = import_optional_yier_source(scene, source)
    # Imported objects can carry axis-conversion transforms. Evaluate them while
    # the reference collection is visible; hiding first can leave stale world
    # matrices and produce incorrect guide/camera bounds.
    bpy.context.view_layer.update()
    build_guides(scene, guides, reference_objects)
    # Start hidden. Toggle the monitor icon in the Outliner to compare scale.
    ref.hide_viewport = True
    add_embedded_readme(len(source_objects), len(reference_objects))

    collections = {
        REF_COLLECTION: ref,
        SOURCE_COLLECTION: source,
        EXPORT_COLLECTION: export,
        GUIDE_COLLECTION: guides,
    }
    validate_before_save(reference_objects, collections)

    # Make the .blend standalone. Imported OBJ geometry and any readable texture
    # images are packed into the output; nothing is written back to D:.
    pack_result = bpy.ops.file.pack_all()
    if "FINISHED" not in pack_result:
        raise RuntimeError(f"Packing external files did not finish: {sorted(pack_result)}")

    activate_collection(scene, source)
    save_result = bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_BLEND), check_existing=False)
    if "FINISHED" not in save_result:
        raise RuntimeError(f"Saving the prototype did not finish: {sorted(save_result)}")
    if Path(bpy.data.filepath).resolve() != OUTPUT_BLEND.resolve():
        raise RuntimeError(f"Blender reports an unexpected saved path: {bpy.data.filepath}")
    if not OUTPUT_BLEND.is_file() or OUTPUT_BLEND.stat().st_size == 0:
        raise RuntimeError(f"Saved prototype is missing or empty: {OUTPUT_BLEND}")
    print(f"[Yier initializer] Created: {OUTPUT_BLEND}")
    print(f"[Yier initializer] Imported {len(reference_objects)} reference objects")
    print(f"[Yier initializer] Imported {len(source_objects)} optional Yier source objects")


if __name__ == "__main__":
    main()
