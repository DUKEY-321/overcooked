"""Build Bubu's first complete OC2DIYChef resource from the immutable v002 baseline."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
from pathlib import Path
import shutil
import struct
import sys

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_BLEND = PROJECT_ROOT / "characters" / "bubu" / "source" / "bubu_work-v002.blend"
OUTPUT_BLEND = PROJECT_ROOT / "characters" / "bubu" / "source" / "bubu_work-v003.blend"
STAGING_PACKAGE = PROJECT_ROOT / "exports" / "staging" / "175-bubu"
YIER_RESOURCE = PROJECT_ROOT / "exports" / "Resources" / "174-yier"

PALETTE = (
    "BUBU_material",
    "BUBU_0095_LightBlue",
    "BUBU_0131_Silver",
    "BUBU_0133_Gray",
    "BUBU_0106_DarkBlue",
    "BUBU_0024_OrangeRed",
)

SOURCE_OBJECTS = {
    "BUBU_material": "BUBU_Material2",
    "BUBU_0095_LightBlue": "BUBU_Material2.001",
    "BUBU_0131_Silver": "BUBU_Material2.005",
    "BUBU_0133_Gray": "BUBU_Material3",
    "BUBU_0106_DarkBlue": "BUBU_Material3.004",
    "BUBU_0024_OrangeRed": "BUBU_Material3.005",
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

EXPECTED_PARTS = {
    "Head": (3910, 6808),
    "Eyes": (334, 330),
    "Hand_Open_L": (554, 1104),
    "Hand_Open_R": (554, 1104),
    "Body_Body": (554, 1104),
    "Body_Bottom": (1108, 2208),
    "Body_Tail": (554, 1104),
}

ATTRIBUTION = """Model: 表情包的一二布布Yier (Bubu character from the shared scene)
Uploader: 小王子 (hong2695429209)
Source: https://sketchfab.com/3d-models/yier-b15f13be61224129ba3123c0041206c2
License: Creative Commons Attribution 4.0 International (CC BY 4.0)
License URL: https://creativecommons.org/licenses/by/4.0/
Mod author: DUKEY
Modified for a non-commercial Overcooked! 2 test mod: reverse-shell cleanup, component separation, flat-color UV atlas, blink state, scale, hand alignment, and OC2DIYChef part conversion.
"""


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

        faces = tuple(tuple(poly.vertices) for poly in mesh.polygons if poly.vertices[0] in vertices)
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


def choose_visible_winding(records: list[Component]) -> tuple[list[Component], int, int]:
    """Resolve the remaining SketchUp front/back material pairs by outward winding."""
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
        negative, positive = sorted(group, key=lambda item: item.signed_volume)
        require(
            negative.signed_volume < 0.0 < positive.signed_volume,
            f"Duplicate component {digest} does not have opposite winding",
        )
        chosen.append(positive)
        duplicate_groups += 1
        removed_triangles += negative.triangles
        print(
            "[BUBU winding] "
            f"triangles={positive.triangles} keep={positive.material_name} "
            f"drop={negative.material_name} center={tuple(round(value, 6) for value in positive.center)}"
        )
    return chosen, duplicate_groups, removed_triangles


def classify(record: Component) -> str:
    material = record.material_name
    center_x, center_y, center_z = record.center
    dim_x, _dim_y, dim_z = record.dimensions

    if material == "BUBU_material":
        if center_z > 0.70:
            return "Head"
        if abs(center_x) > 0.15 and 0.40 < center_z < 0.62 and dim_z > 0.12:
            return "Hand_Open_L" if center_x > 0.0 else "Hand_Open_R"
        if center_z < 0.35:
            return "Body_Bottom"
        if abs(center_x) < 0.10 and dim_x > 0.40 and dim_z > 0.30:
            return "Body_Body"
    elif material == "BUBU_0095_LightBlue":
        return "Body_Tail" if center_y > 0.15 and center_z < 0.50 else "Head"
    elif material == "BUBU_0133_Gray":
        if abs(center_x) > 0.10 and center_y < -0.35 and center_z > 0.74:
            return "Eyes"
        return "Head"
    elif material in {"BUBU_0131_Silver", "BUBU_0106_DarkBlue", "BUBU_0024_OrangeRed"}:
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
    center_v = (row + 0.5) / 2.0
    delta_u = 0.04
    delta_v = 0.06
    return (
        (center_u - delta_u, center_v - delta_v),
        (center_u + delta_u, center_v - delta_v),
        (center_u, center_v + delta_v),
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
    uv_layer = mesh.uv_layers.new(name="BUBU_PALETTE_UV")
    for polygon, uv_triangle in zip(mesh.polygons, face_uvs, strict=True):
        polygon.use_smooth = True
        require(len(polygon.loop_indices) == 3, f"{name}: non-triangle polygon after construction")
        for loop_index, uv in zip(polygon.loop_indices, uv_triangle, strict=True):
            uv_layer.data[loop_index].uv = uv
    return mesh


def create_atlas(path: Path, colors: dict[str, tuple[float, float, float, float]]) -> bpy.types.Image:
    width = height = 512
    image = bpy.data.images.new("BUBU_FLAT_COLOR_ATLAS", width=width, height=height, alpha=True)
    pixels = [0.0] * (width * height * 4)
    for y in range(height):
        row = min(y * 2 // height, 1)
        for x in range(width):
            column = min(x * 3 // width, 2)
            color = colors[PALETTE[row * 3 + column]]
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
    material = bpy.data.materials.new("BUBU_GAME_ATLAS")
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
    require(1.06 < scale < 1.07, f"{obj.name}: unexpected hand alignment scale: {scale}")
    for vertex in obj.data.vertices:
        vertex.co = reference_center + (vertex.co - source_center) * scale
    obj.data.update(calc_edges=True)
    obj["reference_alignment_scale"] = scale
    obj["reference_target_center"] = tuple(reference_center)
    return scale


def eye_pivots(eyes: bpy.types.Object) -> tuple[tuple[float, float], tuple[float, float]]:
    sides = ([vertex.co for vertex in eyes.data.vertices if vertex.co.x < 0.0],
             [vertex.co for vertex in eyes.data.vertices if vertex.co.x >= 0.0])
    require(all(sides), "Eyes are not separated across X=0")
    pivots = []
    for vertices in sides:
        lower_x = min(vertex.x for vertex in vertices)
        upper_x = max(vertex.x for vertex in vertices)
        lower_z = min(vertex.z for vertex in vertices)
        upper_z = max(vertex.z for vertex in vertices)
        pivots.append(((lower_x + upper_x) * 0.5, (lower_z + upper_z) * 0.5))
    return pivots[0], pivots[1]


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


def write_package_metadata() -> None:
    (STAGING_PACKAGE / "INFO").write_text("ID=175\n", encoding="utf-8")
    (STAGING_PACKAGE / "ATTRIBUTION.txt").write_text(ATTRIBUTION, encoding="utf-8")
    for name in ("m_Head.txt", "m_Body.txt"):
        source = YIER_RESOURCE / name
        require(source.is_file(), f"Missing shared material template: {source}")
        shutil.copyfile(source, STAGING_PACKAGE / name)


def main() -> None:
    mode = parse_mode()
    require(bpy.app.background, "Bubu build must run in an isolated background process")
    require(Path(bpy.data.filepath) == INPUT_BLEND, f"Unexpected input workspace: {bpy.data.filepath}")
    work = bpy.data.collections.get("WORK_BUBU")
    export_collection = bpy.data.collections.get("EXPORT_PARTS")
    require(work is not None, "Missing WORK_BUBU")
    require(export_collection is not None, "Missing EXPORT_PARTS")
    require(len(export_collection.all_objects) == 0, "EXPORT_PARTS is not empty in v002")

    sources = {obj.name: obj for obj in work.all_objects if obj.type == "MESH"}
    require(set(sources) == set(SOURCE_OBJECTS.values()), f"Unexpected work objects: {sorted(sources)}")
    require({material_name(obj) for obj in sources.values()} == set(PALETTE), "Unexpected Bubu material palette")
    require(
        (sum(len(obj.data.vertices) for obj in sources.values()),
         sum(len(obj.data.loop_triangles) for obj in sources.values())) == (8338, 14528),
        "Unexpected Bubu v002 aggregate mesh stats",
    )

    all_records = [record for obj in sources.values() for record in component_records(obj)]
    chosen, duplicate_groups, removed_triangles = choose_visible_winding(all_records)
    require(len(all_records) == 39, f"Unexpected source component count: {len(all_records)}")
    require(duplicate_groups == 10, f"Unexpected cross-material duplicate groups: {duplicate_groups}")
    require(removed_triangles == 766, f"Unexpected cross-material triangle removal: {removed_triangles}")
    require(len(chosen) == 29, f"Unexpected visible component count: {len(chosen)}")
    require(sum(record.triangles for record in chosen) == 13762, "Unexpected visible triangle total")

    assignments: dict[str, list[Component]] = defaultdict(list)
    for record in chosen:
        assignments[classify(record)].append(record)
    require(set(assignments) == set(EXPECTED_PARTS), f"Unexpected part assignments: {sorted(assignments)}")
    for name, records in sorted(assignments.items()):
        vertices = sum(len(record.vertex_indices) for record in records)
        triangles = sum(record.triangles for record in records)
        require((vertices, triangles) == EXPECTED_PARTS[name], f"{name}: unexpected mapping stats {(vertices, triangles)}")
        print(f"[BUBU mapping] part={name} components={len(records)} vertices={vertices} triangles={triangles}")
    if mode == "dry-run":
        print("[BUBU v003 dry-run] PASS")
        return

    require(not OUTPUT_BLEND.exists(), f"Refusing to overwrite: {OUTPUT_BLEND}")
    require(not STAGING_PACKAGE.exists(), f"Refusing to overwrite: {STAGING_PACKAGE}")
    STAGING_PACKAGE.mkdir(parents=True, exist_ok=False)

    colors = {name: tuple(bpy.data.materials[name].diffuse_color) for name in PALETTE}
    image = create_atlas(STAGING_PACKAGE, colors)
    atlas_material = create_atlas_material(image)
    created: dict[str, bpy.types.Object] = {}
    for name in sorted(assignments):
        mesh = create_part_mesh(name, assignments[name], sources)
        mesh.materials.append(atlas_material)
        obj = bpy.data.objects.new(name, mesh)
        export_collection.objects.link(obj)
        created[name] = obj

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

    left_pivot, right_pivot = eye_pivots(created["Eyes"])
    require(abs(left_pivot[0] - (-0.15525651)) < 2e-6, f"Unexpected left eye pivot: {left_pivot}")
    require(abs(right_pivot[0] - 0.16639936) < 2e-6, f"Unexpected right eye pivot: {right_pivot}")
    require(abs(left_pivot[1] - 0.78842366) < 2e-6, f"Unexpected left eye Z pivot: {left_pivot}")
    require(abs(right_pivot[1] - 0.78842366) < 2e-6, f"Unexpected right eye Z pivot: {right_pivot}")
    eyes_blinks = clone_object(created["Eyes"], "Eyes2_Blinks", export_collection)
    for vertex in eyes_blinks.data.vertices:
        center_x, center_z = left_pivot if vertex.co.x < 0.0 else right_pivot
        vertex.co.x = center_x + (vertex.co.x - center_x) * 1.12
        vertex.co.z = center_z + (vertex.co.z - center_z) * 0.18
    eyes_blinks.data.update(calc_edges=True)
    eyes_blinks["left_blink_pivot"] = left_pivot
    eyes_blinks["right_blink_pivot"] = right_pivot
    created["Eyes2_Blinks"] = eyes_blinks
    created["Hand_Grip_L"] = clone_object(created["Hand_Open_L"], "Hand_Grip_L", export_collection)
    created["Hand_Grip_R"] = clone_object(created["Hand_Open_R"], "Hand_Grip_R", export_collection)

    require(set(created) == set(EXPORT_NAMES), f"Unexpected export parts: {sorted(created)}")
    require(all(obj.matrix_world.is_identity for obj in created.values()), "Export object transforms are not identity")
    require(all(len(obj.data.uv_layers) == 1 for obj in created.values()), "One or more export parts lack UVs")
    require(all(len(obj.data.materials) == 1 for obj in created.values()), "One or more export parts lack atlas material")

    for name in EXPORT_NAMES:
        obj = created[name]
        vertices, triangles = mesh_stats(obj)
        require(vertices > 0 and triangles > 0, f"{name}: empty export mesh")
        require(triangles < 20000, f"{name}: triangle budget exceeded: {triangles}")
        export_obj(obj, STAGING_PACKAGE / f"{name}.obj")
        obj["export_vertices"] = vertices
        obj["export_triangles"] = triangles
    write_package_metadata()

    for collection in bpy.data.collections:
        collection.hide_viewport = collection != export_collection
        collection.hide_render = collection != export_collection
    export_collection.hide_viewport = False
    export_collection.hide_render = False
    export_collection["revision"] = "v003-first-complete"
    export_collection["source_components"] = len(all_records)
    export_collection["visible_components"] = len(chosen)
    export_collection["cross_material_duplicate_groups_removed"] = duplicate_groups
    export_collection["cross_material_triangles_removed"] = removed_triangles
    export_collection["runtime_triangle_total"] = 13762
    export_collection["grip_hands_match_open_hands"] = True
    bpy.context.scene["workspace_revision"] = "v003-first-complete"
    bpy.context.scene["active_character"] = "bubu"
    readme = bpy.data.texts.get("README_YIER_BUBU_WORK.txt")
    if readme is not None:
        readme.write(
            "\nBubu v003 first complete game build: Head/Eyes/Blinks/four hands/Body_Body/"
            "Body_Bottom/Body_Tail, flat-color atlas, rigid feet, and reference-aligned hands.\n"
        )

    result = bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_BLEND), check_existing=False)
    require("FINISHED" in result, f"Saving v003 failed: {sorted(result)}")
    require(OUTPUT_BLEND.is_file() and OUTPUT_BLEND.stat().st_size > 0, "Saved v003 is missing or empty")
    print(f"[BUBU v003 build] PASS blend={OUTPUT_BLEND} staging={STAGING_PACKAGE}")


if __name__ == "__main__":
    main()
