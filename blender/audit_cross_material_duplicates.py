"""Read-only audit for exact connected components duplicated across mesh objects."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import struct
import sys

import bmesh
import bpy


def parse_character() -> str:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(arguments) != 2 or arguments[0] != "--character":
        raise RuntimeError("Usage: ... -- --character YIER|BUBU")
    character = arguments[1].upper()
    if character not in {"YIER", "BUBU"}:
        raise RuntimeError(f"Unsupported character: {arguments[1]}")
    return character


def records(obj: bpy.types.Object) -> list[dict[str, object]]:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    unseen = set(bm.verts)
    result: list[dict[str, object]] = []
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
        coordinate = {vertex: tuple(round(value, 7) for value in vertex.co) for vertex in vertices}
        coordinates = sorted(coordinate.values())
        polygons = sorted(tuple(sorted(coordinate[vertex] for vertex in face.verts)) for face in faces)
        digest = hashlib.sha256()
        for item in coordinates:
            digest.update(struct.pack("<3d", *item))
        digest.update(b"|")
        for polygon in polygons:
            digest.update(struct.pack("<I", len(polygon)))
            for item in polygon:
                digest.update(struct.pack("<3d", *item))
        center = tuple(
            round(
                (min(vertex.co[index] for vertex in vertices) + max(vertex.co[index] for vertex in vertices)) * 0.5,
                6,
            )
            for index in range(3)
        )
        signed_volume = sum(
            face.verts[0].co.dot(face.verts[1].co.cross(face.verts[2].co)) / 6.0
            for face in faces
            if len(face.verts) == 3
        )
        result.append(
            {
                "hash": digest.hexdigest(),
                "object": obj.name,
                "material": obj.material_slots[0].material.name if obj.material_slots and obj.material_slots[0].material else None,
                "center": center,
                "triangles": sum(max(len(face.verts) - 2, 0) for face in faces),
                "signed_volume": round(signed_volume, 12),
            }
        )
    bm.free()
    return result


def main() -> None:
    character = parse_character()
    work = bpy.data.collections.get(f"WORK_{character}")
    if work is None:
        raise RuntimeError(f"Missing WORK_{character}")
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for obj in work.all_objects:
        if obj.type == "MESH":
            for record in records(obj):
                groups[str(record["hash"])].append(record)
    duplicates = 0
    triangles = 0
    for digest, group in sorted(groups.items()):
        object_names = {str(item["object"]) for item in group}
        if len(group) <= 1 or len(object_names) <= 1:
            continue
        duplicates += 1
        triangles += (len(group) - 1) * int(group[0]["triangles"])
        print(f"hash={digest} copies={len(group)} records={group}")
    print(f"[{character} cross-material audit] groups={duplicates} potential_triangle_savings={triangles}")


if __name__ == "__main__":
    main()
