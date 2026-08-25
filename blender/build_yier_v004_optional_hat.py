"""Split Yier's blue cap from Head and build a default-hatless v004 package.

The optional HATS mesh is translated from character-root coordinates into the
local coordinates of the stock Hat_Baseballcap renderer reused by OC2DIYChef.
The exact template offset was read from Overcooked2_Data/resources.assets.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import sys

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(r"F:\dev\overcooke")
INPUT_BLEND = PROJECT_ROOT / "characters" / "yier" / "source" / "yier_work-v003.blend"
OUTPUT_BLEND = PROJECT_ROOT / "characters" / "yier" / "source" / "yier_work-v004.blend"
SOURCE_PACKAGE = PROJECT_ROOT / "exports" / "Resources" / "Sign"
STAGING_ROOT = PROJECT_ROOT / "exports" / "staging" / "sign-v004" / "Resources"
STAGING_CHARACTER = STAGING_ROOT / "Sign"
HAT_NAME = "SignCap"
STAGING_HAT = STAGING_ROOT / "HATS" / HAT_NAME

EXPORT_NAMES = (
    "Head",
    "Eyes",
    "Eyes2_Blinks",
    "Hand_Open_L",
    "Hand_Open_R",
    "Hand_Grip_L",
    "Hand_Grip_R",
    "Body_Body",
    "Body_Bottom",
    "Body_Tail",
)

# Unity template transform: Hat_Baseballcap localPosition =
# (0, 1.036182165145874, -0.10684707760810852).  The Blender workspace uses
# (X, -Unity Z, Unity Y), so this is the offset to subtract before OBJ export.
HAT_TEMPLATE_OFFSET = Vector((0.0, 0.10684707760810852, 1.036182165145874))
HAT_PALETTE_CELL = 7


def parse_mode() -> str:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(arguments) != 2 or arguments[0] != "--mode":
        raise RuntimeError("Usage: ... -- --mode dry-run|build")
    mode = arguments[1].lower()
    if mode not in {"dry-run", "build"}:
        raise RuntimeError(f"Unsupported mode: {arguments[1]}")
    return mode


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def mesh_stats(obj: bpy.types.Object) -> tuple[int, int]:
    obj.data.calc_loop_triangles()
    return len(obj.data.vertices), len(obj.data.loop_triangles)


def bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    lower = Vector(tuple(min(point[axis] for point in points) for axis in range(3)))
    upper = Vector(tuple(max(point[axis] for point in points) for axis in range(3)))
    return lower, upper


def palette_cell(mesh: bpy.types.Mesh, polygon: bpy.types.MeshPolygon) -> int:
    uv_data = mesh.uv_layers.active.data
    count = len(polygon.loop_indices)
    center_u = sum(uv_data[index].uv.x for index in polygon.loop_indices) / count
    center_v = sum(uv_data[index].uv.y for index in polygon.loop_indices) / count
    column = min(2, max(0, int(center_u * 3.0)))
    row = min(2, max(0, int(center_v * 3.0)))
    return row * 3 + column


def create_subset_mesh(
    name: str,
    source: bpy.types.Object,
    polygons: list[bpy.types.MeshPolygon],
    offset: Vector,
) -> bpy.types.Mesh:
    source_mesh = source.data
    source_uv = source_mesh.uv_layers.active.data
    source_indices = sorted({index for polygon in polygons for index in polygon.vertices})
    mapping = {source_index: target_index for target_index, source_index in enumerate(source_indices)}
    vertices = [tuple(source_mesh.vertices[index].co - offset) for index in source_indices]
    faces = [tuple(mapping[index] for index in polygon.vertices) for polygon in polygons]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    require(not mesh.validate(clean_customdata=False), f"{name}: mesh validation changed data")
    mesh.update(calc_edges=True)
    uv_layer = mesh.uv_layers.new(name="YIER_PALETTE_UV")
    for target_polygon, source_polygon in zip(mesh.polygons, polygons, strict=True):
        target_polygon.use_smooth = True
        require(len(target_polygon.loop_indices) == 3, f"{name}: non-triangle polygon")
        for target_loop, source_loop in zip(
            target_polygon.loop_indices,
            source_polygon.loop_indices,
            strict=True,
        ):
            uv_layer.data[target_loop].uv = source_uv[source_loop].uv
    for material in source_mesh.materials:
        mesh.materials.append(material)
    return mesh


def create_object(
    name: str,
    mesh: bpy.types.Mesh,
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def export_obj(obj: bpy.types.Object, path: Path) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    result = bpy.ops.wm.obj_export(
        filepath=str(path),
        check_existing=False,
        export_selected_objects=True,
        forward_axis="NEGATIVE_Z",
        up_axis="Y",
        global_scale=1.0,
        apply_modifiers=True,
        apply_transform=False,
        export_uv=True,
        export_normals=True,
        export_colors=False,
        export_materials=False,
        export_triangulated_mesh=True,
        export_object_groups=False,
        export_material_groups=False,
        export_vertex_groups=False,
        export_smooth_groups=False,
    )
    require("FINISHED" in result, f"OBJ export failed: {path}")
    require(path.is_file() and path.stat().st_size > 0, f"Missing OBJ export: {path}")


def copy_required(source_name: str, target: Path) -> None:
    source = SOURCE_PACKAGE / source_name
    require(source.is_file() and source.stat().st_size > 0, f"Missing source package file: {source}")
    shutil.copy2(source, target)
    require(target.is_file() and target.stat().st_size == source.stat().st_size, f"Copy failed: {target}")


def main() -> None:
    mode = parse_mode()
    require(bpy.app.background, "Yier v004 build must run in an isolated background process")
    require(Path(bpy.data.filepath) == INPUT_BLEND, f"Unexpected input workspace: {bpy.data.filepath}")
    require(SOURCE_PACKAGE.is_dir(), f"Missing v003 package: {SOURCE_PACKAGE}")

    export_collection = bpy.data.collections.get("EXPORT_PARTS")
    require(export_collection is not None, "Missing EXPORT_PARTS")
    source_objects = {obj.name: obj for obj in export_collection.all_objects if obj.type == "MESH"}
    require(set(source_objects) == set(EXPORT_NAMES), f"Unexpected v003 export objects: {sorted(source_objects)}")
    source_head = source_objects["Head"]
    require(source_head.matrix_world.is_identity, "v003 Head transform is not identity")
    require(mesh_stats(source_head) == (3384, 5520), f"Unexpected v003 Head stats: {mesh_stats(source_head)}")
    require(len(source_head.data.uv_layers) == 1, "v003 Head must have one UV layer")
    require(len(source_head.data.materials) == 1, "v003 Head must have one material")
    require(all(len(polygon.vertices) == 3 for polygon in source_head.data.polygons), "v003 Head is not triangulated")

    hat_polygons = [
        polygon
        for polygon in source_head.data.polygons
        if palette_cell(source_head.data, polygon) == HAT_PALETTE_CELL
    ]
    head_polygons = [
        polygon
        for polygon in source_head.data.polygons
        if palette_cell(source_head.data, polygon) != HAT_PALETTE_CELL
    ]
    hat_vertices = {index for polygon in hat_polygons for index in polygon.vertices}
    head_vertices = {index for polygon in head_polygons for index in polygon.vertices}
    require(len(hat_polygons) == 1296 and len(hat_vertices) == 698, "Blue-cap selection changed")
    require(len(head_polygons) == 4224 and len(head_vertices) == 2686, "Hatless Head selection changed")
    require(not (hat_vertices & head_vertices), "Hat and Head share vertices; split would create a cut")
    require(len(hat_polygons) + len(head_polygons) == len(source_head.data.polygons), "Polygon split is incomplete")

    print(
        f"[YIER v004 split] source={mesh_stats(source_head)} "
        f"head=({len(head_vertices)}, {len(head_polygons)}) "
        f"hat=({len(hat_vertices)}, {len(hat_polygons)})"
    )
    if mode == "dry-run":
        print("[YIER v004 dry-run] PASS")
        return

    require(not OUTPUT_BLEND.exists(), f"Refusing to overwrite: {OUTPUT_BLEND}")
    require(not STAGING_ROOT.parent.exists(), f"Refusing to overwrite staging build: {STAGING_ROOT.parent}")
    STAGING_CHARACTER.mkdir(parents=True, exist_ok=False)
    STAGING_HAT.mkdir(parents=True, exist_ok=False)

    hat_root_collection = bpy.data.collections.new("HAT_ROOT_REFERENCE")
    optional_hat_collection = bpy.data.collections.new("OPTIONAL_HATS")
    bpy.context.scene.collection.children.link(hat_root_collection)
    bpy.context.scene.collection.children.link(optional_hat_collection)

    default_head_mesh = create_subset_mesh("Head_v004", source_head, head_polygons, Vector())
    hat_root_mesh = create_subset_mesh(
        f"{HAT_NAME}_RootReference",
        source_head,
        hat_polygons,
        Vector(),
    )
    hat_local_mesh = create_subset_mesh(HAT_NAME, source_head, hat_polygons, HAT_TEMPLATE_OFFSET)
    default_head = create_object("Head_v004", default_head_mesh, export_collection)
    hat_root = create_object(f"{HAT_NAME}_RootReference", hat_root_mesh, hat_root_collection)
    hat_local = create_object(HAT_NAME, hat_local_mesh, optional_hat_collection)

    old_head_mesh = source_head.data
    bpy.data.objects.remove(source_head, do_unlink=True)
    if old_head_mesh.users == 0:
        bpy.data.meshes.remove(old_head_mesh)
    default_head.name = "Head"
    default_head.data.name = "Head"

    export_objects = {obj.name: obj for obj in export_collection.all_objects if obj.type == "MESH"}
    require(set(export_objects) == set(EXPORT_NAMES), f"Unexpected v004 parts: {sorted(export_objects)}")
    require(mesh_stats(default_head) == (2686, 4224), f"Unexpected hatless Head stats: {mesh_stats(default_head)}")
    require(mesh_stats(hat_root) == (698, 1296), f"Unexpected root hat stats: {mesh_stats(hat_root)}")
    require(mesh_stats(hat_local) == (698, 1296), f"Unexpected local hat stats: {mesh_stats(hat_local)}")
    require(all(obj.matrix_world.is_identity for obj in [*export_objects.values(), hat_root, hat_local]), "Non-identity export transform")

    for name in EXPORT_NAMES:
        obj = export_objects[name]
        vertices, triangles = mesh_stats(obj)
        require(vertices > 0 and 0 < triangles < 20000, f"{name}: invalid mesh budget {vertices}/{triangles}")
        export_obj(obj, STAGING_CHARACTER / f"{name}.obj")
        obj["export_vertices"] = vertices
        obj["export_triangles"] = triangles

    export_obj(hat_local, STAGING_HAT / f"{HAT_NAME}.obj")
    copy_required("INFO", STAGING_CHARACTER / "INFO")
    copy_required("ATTRIBUTION.txt", STAGING_CHARACTER / "ATTRIBUTION.txt")
    copy_required("t_Head.png", STAGING_CHARACTER / "t_Head.png")
    copy_required("t_Body.png", STAGING_CHARACTER / "t_Body.png")
    copy_required("m_Head.txt", STAGING_CHARACTER / "m_Head.txt")
    copy_required("m_Body.txt", STAGING_CHARACTER / "m_Body.txt")
    copy_required("t_Head.png", STAGING_HAT / f"t_{HAT_NAME}.png")
    copy_required("m_Head.txt", STAGING_HAT / f"m_{HAT_NAME}.txt")
    copy_required("ATTRIBUTION.txt", STAGING_HAT / "ATTRIBUTION.txt")

    for collection in bpy.data.collections:
        collection.hide_viewport = collection != export_collection
        collection.hide_render = collection != export_collection
    export_collection.hide_viewport = False
    export_collection.hide_render = False
    export_collection["revision"] = "v004-default-hatless-optional-cap"
    export_collection["default_hat"] = "None"
    export_collection["default_triangle_total"] = sum(mesh_stats(obj)[1] for obj in export_objects.values())
    optional_hat_collection["hat_name"] = HAT_NAME
    optional_hat_collection["hat_triangles"] = mesh_stats(hat_local)[1]
    optional_hat_collection["hat_template_game_object_path_id"] = 2159
    optional_hat_collection["hat_template_transform_path_id"] = 3670
    optional_hat_collection["hat_template_offset_blender"] = tuple(HAT_TEMPLATE_OFFSET)
    hat_root_collection["purpose"] = "Blender preview and root-space placement reference only; do not export to HATS"
    bpy.context.scene["workspace_revision"] = "v004-default-hatless-optional-cap"
    bpy.context.scene["active_character"] = "Sign"
    bpy.context.scene["prefer_default"] = "Sign HAT=None"
    bpy.context.scene["prefer_optional_hat"] = f"Sign HAT={HAT_NAME}"
    readme = bpy.data.texts.get("README_YIER_BUBU_WORK.txt")
    if readme is not None:
        readme.write(
            "\nV004: blue cap removed from default Head and packaged as optional HATS/"
            f"{HAT_NAME}; HatBase-local offset derived from the stock Baseballcap prefab.\n"
        )

    result = bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_BLEND), check_existing=False)
    require("FINISHED" in result, f"Saving v004 failed: {sorted(result)}")
    require(OUTPUT_BLEND.is_file() and OUTPUT_BLEND.stat().st_size > 0, "Saved v004 is missing or empty")
    print(
        f"[YIER v004 build] PASS blend={OUTPUT_BLEND} "
        f"character={STAGING_CHARACTER} hat={STAGING_HAT}"
    )


if __name__ == "__main__":
    main()
