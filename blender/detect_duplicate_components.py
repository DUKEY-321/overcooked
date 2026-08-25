"""Detect exactly overlapping connected mesh components without modifying them."""

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


def component_records(mesh: bpy.types.Mesh) -> list[dict[str, object]]:
    bm = bmesh.new()
    bm.from_mesh(mesh)
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
        bm.normal_update()

        coordinate = {
            vertex: tuple(round(value, 7) for value in vertex.co)
            for vertex in vertices
        }
        coords = sorted(coordinate.values())
        polygons = sorted(
            tuple(sorted(coordinate[vertex] for vertex in face.verts)) for face in faces
        )
        digest = hashlib.sha256()
        for item in coords:
            digest.update(struct.pack("<3d", *item))
        digest.update(b"|")
        for polygon in polygons:
            digest.update(struct.pack("<I", len(polygon)))
            for item in polygon:
                digest.update(struct.pack("<3d", *item))

        records.append(
            {
                "hash": digest.hexdigest(),
                "vertices": len(vertices),
                "faces": len(faces),
                "triangles": sum(max(len(face.verts) - 2, 0) for face in faces),
                "signed_volume": round(
                    sum(
                        face.verts[0].co.dot(
                            face.verts[1].co.cross(face.verts[2].co)
                        )
                        / 6.0
                        for face in faces
                        if len(face.verts) == 3
                    ),
                    12,
                ),
                "normal_sum": tuple(
                    round(
                        sum(face.normal[index] * face.calc_area() for face in faces),
                        9,
                    )
                    for index in range(3)
                ),
                "center": tuple(
                    round(
                        (min(vertex.co[index] for vertex in vertices)
                         + max(vertex.co[index] for vertex in vertices))
                        * 0.5,
                        6,
                    )
                    for index in range(3)
                ),
            }
        )

    bm.free()
    return records


def main() -> None:
    character = parse_character()
    collection = bpy.data.collections.get(f"WORK_{character}")
    if collection is None:
        raise RuntimeError(f"WORK_{character} collection is missing")

    total_savings = 0
    duplicate_groups = 0
    print(f"[{character} duplicate audit] BEGIN")
    for obj in sorted(collection.all_objects, key=lambda item: item.name):
        if obj.type != "MESH":
            continue
        groups: dict[str, list[dict[str, object]]] = defaultdict(list)
        for record in component_records(obj.data):
            groups[str(record["hash"])].append(record)
        for digest, records in sorted(groups.items()):
            if len(records) <= 1:
                continue
            duplicate_groups += 1
            savings = (len(records) - 1) * int(records[0]["triangles"])
            total_savings += savings
            print(
                f"object={obj.name} copies={len(records)} triangles_each={records[0]['triangles']} "
                f"saving={savings} center={records[0]['center']} "
                f"orientations={[(record['signed_volume'], record['normal_sum']) for record in records]} "
                f"hash={digest}"
            )
    print(f"[{character} duplicate audit] groups={duplicate_groups} triangle_savings={total_savings}")
    print(f"[{character} duplicate audit] END")


if __name__ == "__main__":
    main()
