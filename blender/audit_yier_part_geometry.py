"""Read-only geometric audit for mapping the Yier workspace to OC2 parts."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import struct

import bmesh
import bpy
from mathutils import Vector


BODY_THRESHOLDS = (0.22, 0.30, 0.38, 0.46, 0.54)


def component_records(obj: bpy.types.Object) -> list[dict[str, object]]:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    if any(len(face.verts) != 3 for face in bm.faces):
        bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bm.normal_update()
    bm.verts.ensure_lookup_table()
    unseen = set(bm.verts)
    records: list[dict[str, object]] = []

    while unseen:
        start = unseen.pop()
        stack = [start]
        vertices = {start}
        while stack:
            vertex = stack.pop()
            for edge in vertex.link_edges:
                other = edge.other_vert(vertex)
                if other in unseen:
                    unseen.remove(other)
                    vertices.add(other)
                    stack.append(other)
        faces = {face for vertex in vertices for face in vertex.link_faces}
        if not faces:
            continue

        world = {
            vertex: obj.matrix_world @ vertex.co
            for vertex in vertices
        }
        coordinates = {
            vertex: tuple(round(value, 7) for value in world[vertex])
            for vertex in vertices
        }
        polygons = sorted(
            tuple(sorted(coordinates[vertex] for vertex in face.verts))
            for face in faces
        )
        digest = hashlib.sha256()
        for coordinate in sorted(coordinates.values()):
            digest.update(struct.pack("<3d", *coordinate))
        digest.update(b"|")
        for polygon in polygons:
            digest.update(struct.pack("<I", len(polygon)))
            for coordinate in polygon:
                digest.update(struct.pack("<3d", *coordinate))

        lower = Vector(tuple(min(co[index] for co in world.values()) for index in range(3)))
        upper = Vector(tuple(max(co[index] for co in world.values()) for index in range(3)))
        center = (lower + upper) * 0.5
        signed_volume = 0.0
        normal_sum = Vector((0.0, 0.0, 0.0))
        surface_area = 0.0
        normal_matrix = obj.matrix_world.to_3x3().inverted().transposed()
        for face in faces:
            a, b, c = (world[vertex] for vertex in face.verts)
            signed_volume += a.dot(b.cross(c)) / 6.0
            area = face.calc_area()
            surface_area += area
            normal_sum += (normal_matrix @ face.normal).normalized() * area

        material_indices = sorted({face.material_index for face in faces})
        records.append(
            {
                "hash": digest.hexdigest(),
                "vertices": len(vertices),
                "triangles": len(faces),
                "center": [round(value, 6) for value in center],
                "min": [round(value, 6) for value in lower],
                "max": [round(value, 6) for value in upper],
                "dimensions": [round(value, 6) for value in upper - lower],
                "surface_area": round(surface_area, 9),
                "signed_volume": round(signed_volume, 12),
                "normal_sum": [round(value, 9) for value in normal_sum],
                "material_indices": material_indices,
            }
        )

    bm.free()
    records.sort(key=lambda item: (-int(item["triangles"]), item["center"]))
    return records


def material_record(material: bpy.types.Material | None) -> dict[str, object] | None:
    if material is None:
        return None
    return {
        "name": material.name,
        "diffuse_rgba": [round(value, 6) for value in material.diffuse_color],
    }


def body_band_audit() -> dict[str, object]:
    selections = {
        "YIER_Material2.001": {1, 2},
        "YIER_Material2.002": {4, 7, 8},
    }
    values: list[float] = []
    spans: list[tuple[float, float]] = []
    triangles = 0

    for object_name, component_ids in selections.items():
        obj = bpy.data.objects[object_name]
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        if any(len(face.verts) != 3 for face in bm.faces):
            bmesh.ops.triangulate(bm, faces=list(bm.faces))
        bm.verts.ensure_lookup_table()
        unseen = set(bm.verts)
        groups: list[dict[str, object]] = []
        while unseen:
            start = unseen.pop()
            stack = [start]
            vertices = {start}
            while stack:
                vertex = stack.pop()
                for edge in vertex.link_edges:
                    other = edge.other_vert(vertex)
                    if other in unseen:
                        unseen.remove(other)
                        vertices.add(other)
                        stack.append(other)
            faces = {face for vertex in vertices for face in vertex.link_faces}
            if not faces:
                continue
            lower = Vector(tuple(min(vertex.co[i] for vertex in vertices) for i in range(3)))
            upper = Vector(tuple(max(vertex.co[i] for vertex in vertices) for i in range(3)))
            groups.append(
                {
                    "vertices": vertices,
                    "faces": faces,
                    "triangles": len(faces),
                    "center": list((lower + upper) * 0.5),
                }
            )
        groups.sort(key=lambda item: (-int(item["triangles"]), item["center"]))

        for component_id in component_ids:
            group = groups[component_id - 1]
            values.extend(vertex.co.z for vertex in group["vertices"])
            for face in group["faces"]:
                zs = [vertex.co.z for vertex in face.verts]
                spans.append((min(zs), max(zs)))
                triangles += 1
        bm.free()

    bands = [0] * 6
    for value in values:
        if value <= 0.22:
            bands[0] += 1
        elif value <= 0.30:
            bands[1] += 1
        elif value <= 0.38:
            bands[2] += 1
        elif value <= 0.46:
            bands[3] += 1
        elif value <= 0.54:
            bands[4] += 1
        else:
            bands[5] += 1

    crossing = {
        f"{threshold:.2f}": sum(low < threshold < high for low, high in spans)
        for threshold in BODY_THRESHOLDS
    }
    return {
        "axis_note": "Blender Z becomes OBJ/game Y with Forward -Z, Up Y",
        "triangles": triangles,
        "sampled_vertices": len(values),
        "vertex_bands_leq_022_030_038_046_054_gt": bands,
        "triangles_crossing_each_threshold": crossing,
        "max_triangle_vertical_span": round(max(high - low for low, high in spans), 9),
    }


def object_world_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    coordinates = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    lower = Vector(tuple(min(co[index] for co in coordinates) for index in range(3)))
    upper = Vector(tuple(max(co[index] for co in coordinates) for index in range(3)))
    return lower, upper


def hand_alignment_audit(all_records: list[dict[str, object]]) -> dict[str, object]:
    records = {str(record["id"]): record for record in all_records}
    mapping = {
        "L": ("YIER_Material2.002:C06", "REF_Hand_Open_L_左手-球.017"),
        "R": ("YIER_Material2.002:C01", "REF_Hand_Open_R_左手-球.016"),
    }
    reference_collection = bpy.data.collections["REF_EXISTING"]
    previous_hidden = reference_collection.hide_viewport
    reference_collection.hide_viewport = False
    bpy.context.view_layer.update()
    try:
        result: dict[str, object] = {}
        for side, (source_id, reference_name) in mapping.items():
            source = records[source_id]
            source_min = Vector(source["min"])
            source_max = Vector(source["max"])
            source_center = (source_min + source_max) * 0.5
            reference_min, reference_max = object_world_bounds(bpy.data.objects[reference_name])
            reference_center = (reference_min + reference_max) * 0.5
            result[side] = {
                "source_component": source_id,
                "source_center": [round(value, 6) for value in source_center],
                "reference_center": [round(value, 6) for value in reference_center],
                "translate_to_reference_center": [
                    round(value, 6) for value in reference_center - source_center
                ],
                "source_dimensions": [round(value, 6) for value in source_max - source_min],
                "reference_dimensions": [
                    round(value, 6) for value in reference_max - reference_min
                ],
            }
        return result
    finally:
        reference_collection.hide_viewport = previous_hidden


def main() -> None:
    collection = bpy.data.collections.get("WORK_YIER")
    if collection is None:
        raise RuntimeError("WORK_YIER collection is missing")

    all_records: list[dict[str, object]] = []
    for obj in sorted(collection.all_objects, key=lambda item: item.name):
        if obj.type != "MESH":
            continue
        materials = [material_record(slot.material) for slot in obj.material_slots]
        for index, component in enumerate(component_records(obj), start=1):
            record = {
                "id": f"{obj.name}:C{index:02d}",
                "object": obj.name,
                "materials": materials,
                **component,
            }
            all_records.append(record)
            print("COMPONENT=" + json.dumps(record, ensure_ascii=False, sort_keys=True))

    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in all_records:
        groups[str(record["hash"])].append(record)
    for digest, records in sorted(groups.items()):
        if len(records) < 2:
            continue
        summary = {
            "hash": digest,
            "members": [record["id"] for record in records],
            "materials": [record["materials"] for record in records],
            "triangles_each": records[0]["triangles"],
            "signed_volumes": [record["signed_volume"] for record in records],
            "normal_sums": [record["normal_sum"] for record in records],
        }
        print("CROSS_OBJECT_DUPLICATE=" + json.dumps(summary, ensure_ascii=False, sort_keys=True))
    print("BODY_BAND_AUDIT=" + json.dumps(body_band_audit(), ensure_ascii=False, sort_keys=True))
    print(
        "HAND_ALIGNMENT="
        + json.dumps(hand_alignment_audit(all_records), ensure_ascii=False, sort_keys=True)
    )


if __name__ == "__main__":
    main()
