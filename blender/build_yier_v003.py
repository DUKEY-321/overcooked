"""Build Yier's first complete OC2DIYChef parts into a non-overwriting v003 workspace."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct
import sys

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(r"F:\dev\overcooke")
INPUT_BLEND = PROJECT_ROOT / "characters" / "yier" / "source" / "yier_work-v002.blend"
OUTPUT_BLEND = PROJECT_ROOT / "characters" / "yier" / "source" / "yier_work-v003.blend"
STAGING_PACKAGE = PROJECT_ROOT / "exports" / "staging" / "174-yier"

PALETTE = (
    "YIER_0095_LightBlue",
    "YIER_material_3",
    "YIER_material_4",
    "YIER_0131_Silver_1",
    "YIER_0131_Silver",
    "YIER_0133_Gray",
    "YIER_material_0",
    "YIER_material_8",
    "YIER_0106_DarkBlue",
)

SOURCE_OBJECTS = {
    "YIER_0095_LightBlue": "YIER_Material2.001",
    "YIER_material_3": "YIER_Material2.002",
    "YIER_material_4": "YIER_Material2.003",
    "YIER_0131_Silver_1": "YIER_Material2.004",
    "YIER_0131_Silver": "YIER_Material2.005",
    "YIER_0133_Gray": "YIER_Material3",
    "YIER_material_0": "YIER_Material3.002",
    "YIER_material_8": "YIER_Material3.003",
    "YIER_0106_DarkBlue": "YIER_Material3.004",
}

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


@dataclass(frozen=True)
class Component:
    object_name: str
    material_name: str
    vertex_indices: tuple[int, ...]
    faces: tuple[tuple[int, ...], ...]
    digest: str
    signed_volume: float
    center: tuple[float, float, float]
    dimensions: tuple[float, float, float]
    triangles: int


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


def material_name(obj: bpy.types.Object) -> str:
    materials = [slot.material.name for slot in obj.material_slots if slot.material]
    require(len(materials) == 1, f"{obj.name}: expected one material, found {materials}")
    return materials[0]


def component_records(obj: bpy.types.Object) -> list[Component]:
    mesh = obj.data
    require(obj.matrix_world.is_identity, f"{obj.name}: non-identity object transform")
    require(all(len(poly.vertices) == 3 for poly in mesh.polygons), f"{obj.name}: non-triangle polygon found")
    neighbors = [set() for _ in mesh.vertices]
    for edge in mesh.edges:
        left, right = edge.vertices
        neighbors[left].add(right)
        neighbors[right].add(left)
    unseen = set(range(len(mesh.vertices)))
    records: list[Component] = []
    source_material = material_name(obj)

    while unseen:
        start = min(unseen)
        unseen.remove(start)
        stack = [start]
        vertices = {start}
        while stack:
            current = stack.pop()
            for other in neighbors[current]:
                if other in unseen:
                    unseen.remove(other)
                    vertices.add(other)
                    stack.append(other)
        faces = tuple(
            tuple(poly.vertices)
            for poly in mesh.polygons
            if poly.vertices[0] in vertices
        )
        if not faces:
            continue
        require(all(set(face).issubset(vertices) for face in faces), f"{obj.name}: component face crosses vertex set")
        vertex_indices = tuple(sorted(vertices))
        coordinate = {
            index: tuple(round(value, 7) for value in mesh.vertices[index].co)
            for index in vertex_indices
        }
        coordinates = sorted(coordinate.values())
        polygons = sorted(tuple(sorted(coordinate[index] for index in face)) for face in faces)
        digest = hashlib.sha256()
        for item in coordinates:
            digest.update(struct.pack("<3d", *item))
        digest.update(b"|")
        for polygon in polygons:
            digest.update(struct.pack("<I", len(polygon)))
            for item in polygon:
                digest.update(struct.pack("<3d", *item))

        lower = tuple(min(mesh.vertices[index].co[axis] for index in vertices) for axis in range(3))
        upper = tuple(max(mesh.vertices[index].co[axis] for index in vertices) for axis in range(3))
        center = tuple((lower[axis] + upper[axis]) * 0.5 for axis in range(3))
        dimensions = tuple(upper[axis] - lower[axis] for axis in range(3))
        signed_volume = 0.0
        for face in faces:
            a, b, c = (mesh.vertices[index].co for index in face)
            signed_volume += a.dot(b.cross(c)) / 6.0
        records.append(
            Component(
                object_name=obj.name,
                material_name=source_material,
                vertex_indices=vertex_indices,
                faces=faces,
                digest=digest.hexdigest(),
                signed_volume=signed_volume,
                center=center,
                dimensions=dimensions,
                triangles=len(faces),
            )
        )
    return records


def choose_outward_components(records: list[Component]) -> tuple[list[Component], int, int]:
    groups: dict[str, list[Component]] = defaultdict(list)
    for record in records:
        groups[record.digest].append(record)
    chosen: list[Component] = []
    duplicate_groups = 0
    removed_triangles = 0
    for digest, group in groups.items():
        if len(group) == 1:
            chosen.append(group[0])
            continue
        require(len(group) == 2, f"Duplicate component {digest} has {len(group)} copies")
        ordered = sorted(group, key=lambda item: item.signed_volume)
        negative, positive = ordered
        require(
            negative.signed_volume < 0.0 < positive.signed_volume,
            f"Duplicate component {digest} does not have opposite winding",
        )
        chosen.append(positive)
        duplicate_groups += 1
        removed_triangles += negative.triangles
    return chosen, duplicate_groups, removed_triangles


def select_visible_components(records: list[Component]) -> list[Component]:
    """Keep the material-facing components proven correct by backface-culling renders."""
    chosen: list[Component] = []
    for record in records:
        material = record.material_name
        center_x, center_y, center_z = record.center
        dim_x, _dim_y, dim_z = record.dimensions
        keep = material in {
            "YIER_0095_LightBlue",
            "YIER_0131_Silver_1",
            "YIER_0131_Silver",
            "YIER_0133_Gray",
            "YIER_material_0",
            "YIER_material_8",
            "YIER_0106_DarkBlue",
        }
        if material == "YIER_material_3":
            keep = (
                (dim_x > 0.70 and center_z > 0.70)
                or (dim_x > 0.30 and dim_z > 0.25 and abs(center_x) < 0.10 and center_z < 0.60)
                or (abs(center_x) > 0.15 and center_y > -0.10 and 0.40 < center_z < 0.60 and dim_z > 0.12)
                or (record.triangles == 552 and 0.28 < center_z < 0.32 and abs(center_x) < 0.15)
            )
        elif material == "YIER_material_4":
            keep = False
        if keep:
            chosen.append(record)
    return chosen


def classify(record: Component) -> str:
    material = record.material_name
    center_x, center_y, center_z = record.center
    dim_x, _dim_y, dim_z = record.dimensions

    if material == "YIER_0095_LightBlue":
        return "Body_Body"
    if material == "YIER_material_3":
        if dim_x > 0.70 and center_z > 0.70:
            return "Head"
        if dim_x > 0.30 and dim_z > 0.25 and abs(center_x) < 0.10 and center_z < 0.60:
            return "Body_Body"
        if abs(center_x) > 0.15 and center_y > -0.10 and 0.40 < center_z < 0.60 and dim_z > 0.12:
            return "Hand_Open_L" if center_x > 0.0 else "Hand_Open_R"
        if record.triangles == 552 and center_z < 0.35:
            return "Body_Body"
    elif material == "YIER_0131_Silver_1":
        return "Body_Bottom"
    elif material == "YIER_0131_Silver":
        return "Head"
    elif material == "YIER_0133_Gray":
        if center_y < -0.33 and center_z > 0.72 and abs(center_x) > 0.08:
            return "Eyes"
        return "Head"
    elif material == "YIER_material_0":
        return "Body_Tail"
    elif material in {"YIER_material_8", "YIER_0106_DarkBlue"}:
        return "Head"
    raise RuntimeError(
        f"Unclassified component: material={material} object={record.object_name} "
        f"center={tuple(round(value, 6) for value in record.center)} "
        f"dimensions={tuple(round(value, 6) for value in record.dimensions)} "
        f"triangles={record.triangles}"
    )


def palette_uv_triangle(material: str) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    index = PALETTE.index(material)
    column = index % 3
    row = index // 3
    center_u = (column + 0.5) / 3.0
    center_v = (row + 0.5) / 3.0
    delta = 0.04
    return (
        (center_u - delta, center_v - delta),
        (center_u + delta, center_v - delta),
        (center_u, center_v + delta),
    )


def create_part_mesh(name: str, records: list[Component], sources: dict[str, bpy.types.Object]) -> bpy.types.Mesh:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    face_uvs: list[tuple[tuple[float, float], tuple[float, float], tuple[float, float]]] = []
    for record in records:
        source_mesh = sources[record.object_name].data
        mapping: dict[int, int] = {}
        for source_index in record.vertex_indices:
            mapping[source_index] = len(vertices)
            vertices.append(tuple(source_mesh.vertices[source_index].co))
        for face in record.faces:
            faces.append(tuple(mapping[index] for index in face))
            face_uvs.append(palette_uv_triangle(record.material_name))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    require(not mesh.validate(clean_customdata=False), f"{name}: mesh validation changed data")
    mesh.update(calc_edges=True)
    uv_layer = mesh.uv_layers.new(name="YIER_PALETTE_UV")
    require(len(mesh.polygons) == len(face_uvs), f"{name}: polygon/UV count mismatch")
    for polygon, uv_triangle in zip(mesh.polygons, face_uvs, strict=True):
        polygon.use_smooth = True
        require(len(polygon.loop_indices) == 3, f"{name}: non-triangle polygon after construction")
        for loop_index, uv in zip(polygon.loop_indices, uv_triangle, strict=True):
            uv_layer.data[loop_index].uv = uv
    return mesh


def create_atlas(path: Path, material_colors: dict[str, tuple[float, float, float, float]]) -> bpy.types.Image:
    width = height = 512
    image = bpy.data.images.new("YIER_FLAT_COLOR_ATLAS", width=width, height=height, alpha=True)
    pixels = [0.0] * (width * height * 4)
    for y in range(height):
        row = min(y * 3 // height, 2)
        for x in range(width):
            column = min(x * 3 // width, 2)
            color = material_colors[PALETTE[row * 3 + column]]
            offset = (y * width + x) * 4
            pixels[offset : offset + 4] = color
    image.pixels.foreach_set(pixels)
    image.file_format = "PNG"
    image.filepath_raw = str(path / "t_Head.png")
    image.save()
    image.filepath_raw = str(path / "t_Body.png")
    image.save()
    image.pack()
    return image


def create_atlas_material(image: bpy.types.Image) -> bpy.types.Material:
    material = bpy.data.materials.new("YIER_GAME_ATLAS")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    principled = next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
    if principled is None:
        principled = nodes.new("ShaderNodeBsdfPrincipled")
    output = next((node for node in nodes if node.type == "OUTPUT_MATERIAL"), None)
    if output is None:
        output = nodes.new("ShaderNodeOutputMaterial")
    if not principled.outputs["BSDF"].is_linked:
        material.node_tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    principled.inputs["Roughness"].default_value = 0.65
    principled.inputs["Metallic"].default_value = 0.0
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = image
    texture.interpolation = "Closest"
    material.node_tree.links.new(texture.outputs["Color"], principled.inputs["Base Color"])
    return material


def clone_object(source: bpy.types.Object, name: str, collection: bpy.types.Collection) -> bpy.types.Object:
    clone = bpy.data.objects.new(name, source.data.copy())
    collection.objects.link(clone)
    return clone


def mesh_stats(obj: bpy.types.Object) -> tuple[int, int]:
    obj.data.calc_loop_triangles()
    return len(obj.data.vertices), len(obj.data.loop_triangles)


def bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    lower = Vector(tuple(min(point[axis] for point in points) for axis in range(3)))
    upper = Vector(tuple(max(point[axis] for point in points) for axis in range(3)))
    return lower, upper


def align_hand_to_reference(obj: bpy.types.Object, reference: bpy.types.Object) -> float:
    source_lower, source_upper = bounds(obj)
    reference_lower, reference_upper = bounds(reference)
    source_center = (source_lower + source_upper) * 0.5
    reference_center = (reference_lower + reference_upper) * 0.5
    source_height = source_upper.z - source_lower.z
    reference_height = reference_upper.z - reference_lower.z
    require(source_height > 0.0 and reference_height > 0.0, f"{obj.name}: invalid hand height")
    scale = reference_height / source_height
    require(1.05 < scale < 1.20, f"{obj.name}: unexpected hand alignment scale: {scale}")
    for vertex in obj.data.vertices:
        vertex.co = reference_center + (vertex.co - source_center) * scale
    obj.data.update(calc_edges=True)
    obj["reference_alignment_scale"] = scale
    obj["reference_target_center"] = tuple(reference_center)
    return scale


def export_obj(obj: bpy.types.Object, path: Path) -> None:
    bpy.ops.object.select_all(action="DESELECT")
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


def main() -> None:
    mode = parse_mode()
    require(bpy.app.background, "Yier build must run in an isolated background process")
    require(Path(bpy.data.filepath) == INPUT_BLEND, f"Unexpected input workspace: {bpy.data.filepath}")
    work = bpy.data.collections.get("WORK_YIER")
    export_collection = bpy.data.collections.get("EXPORT_PARTS")
    require(work is not None, "Missing WORK_YIER")
    require(export_collection is not None, "Missing EXPORT_PARTS")
    require(len(export_collection.all_objects) == 0, "EXPORT_PARTS is not empty in v002")

    sources = {
        obj.name: obj
        for obj in work.all_objects
        if obj.type == "MESH"
    }
    require(set(sources) == set(SOURCE_OBJECTS.values()), f"Unexpected work objects: {sorted(sources)}")
    require(
        {material_name(obj) for obj in sources.values()} == set(PALETTE),
        "Unexpected Yier material palette",
    )
    all_records = [record for obj in sources.values() for record in component_records(obj)]
    _outward_audit, duplicate_groups, exact_duplicate_triangles = choose_outward_components(all_records)
    require(duplicate_groups == 21, f"Unexpected cross-material duplicate groups: {duplicate_groups}")
    require(exact_duplicate_triangles == 6566, f"Unexpected cross-material triangle audit: {exact_duplicate_triangles}")
    chosen = select_visible_components(all_records)
    chosen_triangles = sum(record.triangles for record in chosen)
    removed_triangles = sum(record.triangles for record in all_records) - chosen_triangles
    require(len(chosen) == 38, f"Unexpected visible component count: {len(chosen)}")
    require(chosen_triangles == 18993, f"Unexpected visible triangle count: {chosen_triangles}")
    require(removed_triangles == 8774, f"Unexpected semantic triangle removal: {removed_triangles}")

    assignments: dict[str, list[Component]] = defaultdict(list)
    for record in chosen:
        assignments[classify(record)].append(record)
    required_base_parts = {"Head", "Eyes", "Hand_Open_L", "Hand_Open_R", "Body_Body", "Body_Bottom", "Body_Tail"}
    require(set(assignments) == required_base_parts, f"Unexpected part assignments: {sorted(assignments)}")
    for part in sorted(assignments):
        triangles = sum(record.triangles for record in assignments[part])
        print(f"[YIER mapping] part={part} components={len(assignments[part])} triangles={triangles}")
    print(
        f"[YIER mapping] source_components={len(all_records)} chosen_components={len(chosen)} "
        f"duplicate_groups={duplicate_groups} exact_duplicate_triangles={exact_duplicate_triangles} "
        f"semantic_removed_triangles={removed_triangles}"
    )
    if mode == "dry-run":
        print("[YIER v003 dry-run] PASS")
        return

    require(not OUTPUT_BLEND.exists(), f"Refusing to overwrite: {OUTPUT_BLEND}")
    require(not STAGING_PACKAGE.exists(), f"Refusing to overwrite: {STAGING_PACKAGE}")
    STAGING_PACKAGE.mkdir(parents=True, exist_ok=False)

    material_colors = {
        name: tuple(bpy.data.materials[name].diffuse_color)
        for name in PALETTE
    }
    image = create_atlas(STAGING_PACKAGE, material_colors)
    atlas_material = create_atlas_material(image)
    created: dict[str, bpy.types.Object] = {}
    for part in sorted(assignments):
        mesh = create_part_mesh(part, assignments[part], sources)
        mesh.materials.append(atlas_material)
        obj = bpy.data.objects.new(part, mesh)
        export_collection.objects.link(obj)
        created[part] = obj

    reference = bpy.data.collections.get("REF_EXISTING")
    require(reference is not None, "Missing REF_EXISTING")
    reference.hide_viewport = False
    bpy.context.view_layer.update()
    left_references = [obj for obj in reference.all_objects if obj.name.startswith("REF_Hand_Open_L_")]
    right_references = [obj for obj in reference.all_objects if obj.name.startswith("REF_Hand_Open_R_")]
    require(len(left_references) == 1 and len(right_references) == 1, "Reference hand lookup is ambiguous")
    left_scale = align_hand_to_reference(created["Hand_Open_L"], left_references[0])
    right_scale = align_hand_to_reference(created["Hand_Open_R"], right_references[0])
    require(abs(left_scale - right_scale) < 1e-5, "Left/right hand alignment scales differ")
    reference.hide_viewport = True
    bpy.context.view_layer.update()

    eyes_blinks = clone_object(created["Eyes"], "Eyes2_Blinks", export_collection)
    for vertex in eyes_blinks.data.vertices:
        center_x = -0.148420 if vertex.co.x < 0.0 else 0.159273
        center_z = 0.763336
        vertex.co.x = center_x + (vertex.co.x - center_x) * 1.12
        vertex.co.z = center_z + (vertex.co.z - center_z) * 0.18
    eyes_blinks.data.update(calc_edges=True)
    created["Eyes2_Blinks"] = eyes_blinks
    created["Hand_Grip_L"] = clone_object(created["Hand_Open_L"], "Hand_Grip_L", export_collection)
    created["Hand_Grip_R"] = clone_object(created["Hand_Open_R"], "Hand_Grip_R", export_collection)

    require(set(created) == set(EXPORT_NAMES), f"Unexpected export parts: {sorted(created)}")
    require(all(obj.matrix_world.is_identity for obj in created.values()), "Export object transforms are not identity")
    require(all(len(obj.data.uv_layers) == 1 for obj in created.values()), "One or more export parts lack UVs")
    require(all(len(obj.data.materials) == 1 for obj in created.values()), "One or more export parts lack atlas material")

    head_lower, head_upper = bounds(created["Head"])
    require(head_lower.z >= 0.52 and head_upper.z > 1.20, f"Unexpected Head bounds: {head_lower}, {head_upper}")
    left_lower, left_upper = bounds(created["Hand_Open_L"])
    right_lower, right_upper = bounds(created["Hand_Open_R"])
    require(left_lower.x > 0.14 and right_upper.x < -0.14, "Hand side assignment is incorrect")
    body_lower, body_upper = bounds(created["Body_Body"])
    require(body_lower.z >= 0.20 and body_upper.z <= 0.62, f"Unexpected Body_Body bounds: {body_lower}, {body_upper}")

    for name in EXPORT_NAMES:
        obj = created[name]
        vertices, triangles = mesh_stats(obj)
        require(vertices > 0 and triangles > 0, f"{name}: empty export mesh")
        require(triangles < 20000, f"{name}: triangle budget exceeded: {triangles}")
        export_obj(obj, STAGING_PACKAGE / f"{name}.obj")
        obj["export_vertices"] = vertices
        obj["export_triangles"] = triangles

    for collection in bpy.data.collections:
        collection.hide_viewport = collection != export_collection
        collection.hide_render = collection != export_collection
    export_collection.hide_viewport = False
    export_collection.hide_render = False
    export_collection["revision"] = "v003-first-complete"
    export_collection["cross_material_duplicate_groups_removed"] = duplicate_groups
    export_collection["cross_material_exact_triangles_audited"] = exact_duplicate_triangles
    export_collection["semantic_triangles_removed"] = removed_triangles
    export_collection["grip_hands_match_open_hands"] = True
    bpy.context.scene["workspace_revision"] = "v003-first-complete"
    bpy.context.scene["active_character"] = "yier"
    readme = bpy.data.texts.get("README_YIER_BUBU_WORK.txt")
    if readme is not None:
        readme.write(
            "\nV003 first complete game build: Head/Eyes/Blinks/four hands/Body_Body/"
            "Body_Bottom/Body_Tail, flat-color atlas, grip hands equal open hands for first playtest.\n"
        )

    result = bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_BLEND), check_existing=False)
    require("FINISHED" in result, f"Saving v003 failed: {sorted(result)}")
    require(OUTPUT_BLEND.is_file() and OUTPUT_BLEND.stat().st_size > 0, "Saved v003 is missing or empty")
    print(f"[YIER v003 build] PASS blend={OUTPUT_BLEND} staging={STAGING_PACKAGE}")


if __name__ == "__main__":
    main()
