"""Report connected polygon components in a prepared character workspace."""

from __future__ import annotations

import json
import sys

import bmesh
import bpy
from mathutils import Vector


def parse_character() -> str:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(arguments) != 2 or arguments[0] != "--character":
        raise RuntimeError("Usage: ... -- --character YIER|BUBU")
    character = arguments[1].upper()
    if character not in {"YIER", "BUBU"}:
        raise RuntimeError(f"Unsupported character: {arguments[1]}")
    return character


def connected_components(mesh: bpy.types.Mesh) -> list[dict[str, object]]:
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    unseen = set(bm.verts)
    components: list[dict[str, object]] = []

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
        lower = Vector(
            tuple(min(vertex.co[index] for vertex in vertices) for index in range(3))
        )
        upper = Vector(
            tuple(max(vertex.co[index] for vertex in vertices) for index in range(3))
        )
        center = (lower + upper) * 0.5
        triangles = sum(max(len(face.verts) - 2, 0) for face in faces)
        components.append(
            {
                "vertices": len(vertices),
                "faces": len(faces),
                "triangles": triangles,
                "center": [round(value, 6) for value in center],
                "min": [round(value, 6) for value in lower],
                "max": [round(value, 6) for value in upper],
                "dimensions": [round(value, 6) for value in (upper - lower)],
            }
        )

    bm.free()
    components.sort(key=lambda item: (-int(item["triangles"]), item["center"]))
    return components


def main() -> None:
    character = parse_character()
    collection = bpy.data.collections.get(f"WORK_{character}")
    if collection is None:
        raise RuntimeError(f"WORK_{character} collection is missing")

    print(f"[{character} component audit] BEGIN")
    for obj in sorted(collection.all_objects, key=lambda item: item.name):
        if obj.type != "MESH":
            continue
        components = connected_components(obj.data)
        print(
            json.dumps(
                {
                    "object": obj.name,
                    "materials": [
                        slot.material.name if slot.material else None
                        for slot in obj.material_slots
                    ],
                    "component_count": len(components),
                    "components": components,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    print(f"[{character} component audit] END")


if __name__ == "__main__":
    main()
