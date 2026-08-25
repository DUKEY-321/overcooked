"""Remove exact reverse-wound duplicate shells into a new v002 workspace."""

from __future__ import annotations

from collections import defaultdict
import hashlib
from pathlib import Path
import struct
import sys

import bmesh
import bpy


PROJECT_ROOT = Path(r"F:\dev\overcooke")
CONFIG = {
    "YIER": {
        "input": PROJECT_ROOT / "characters" / "yier" / "source" / "yier_work-v001.blend",
        "output": PROJECT_ROOT / "characters" / "yier" / "source" / "yier_work-v002.blend",
        "collection": "WORK_YIER",
        "before": (9, 20700, 37986),
        "after": (9, 15354, 27767),
        "saving": 10219,
    },
    "BUBU": {
        "input": PROJECT_ROOT / "characters" / "bubu" / "source" / "bubu_work-v001.blend",
        "output": PROJECT_ROOT / "characters" / "bubu" / "source" / "bubu_work-v002.blend",
        "collection": "WORK_BUBU",
        "before": (6, 12616, 22644),
        "after": (6, 8338, 14528),
        "saving": 8116,
    },
}


def parse_character() -> str:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(arguments) != 2 or arguments[0] != "--character":
        raise RuntimeError("Usage: ... -- --character YIER|BUBU")
    character = arguments[1].upper()
    if character not in CONFIG:
        raise RuntimeError(f"Unsupported character: {arguments[1]}")
    return character


def mesh_stats(objects: list[bpy.types.Object]) -> tuple[int, int, int]:
    meshes = [obj for obj in objects if obj.type == "MESH"]
    vertices = sum(len(obj.data.vertices) for obj in meshes)
    triangles = 0
    for obj in meshes:
        obj.data.calc_loop_triangles()
        triangles += len(obj.data.loop_triangles)
    return len(meshes), vertices, triangles


def component_signature(
    vertices: set[bmesh.types.BMVert],
    faces: set[bmesh.types.BMFace],
) -> str:
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
    return digest.hexdigest()


def components(bm: bmesh.types.BMesh) -> list[dict[str, object]]:
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
        signed_volume = sum(
            face.verts[0].co.dot(face.verts[1].co.cross(face.verts[2].co)) / 6.0
            for face in faces
            if len(face.verts) == 3
        )
        result.append(
            {
                "vertices": vertices,
                "faces": faces,
                "hash": component_signature(vertices, faces),
                "signed_volume": signed_volume,
                "triangles": sum(max(len(face.verts) - 2, 0) for face in faces),
            }
        )
    return result


def deduplicate_mesh(obj: bpy.types.Object) -> tuple[int, int]:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in components(bm):
        groups[str(record["hash"])].append(record)

    delete_vertices: set[bmesh.types.BMVert] = set()
    groups_removed = 0
    triangles_removed = 0
    for digest, records in groups.items():
        if len(records) == 1:
            continue
        if len(records) != 2:
            bm.free()
            raise RuntimeError(f"{obj.name}: duplicate group {digest} has {len(records)} copies")
        ordered = sorted(records, key=lambda item: float(item["signed_volume"]))
        negative, positive = ordered
        low = float(negative["signed_volume"])
        high = float(positive["signed_volume"])
        if not low < 0.0 < high:
            bm.free()
            raise RuntimeError(f"{obj.name}: duplicate orientations are not opposite: {low}, {high}")
        relative_error = abs(abs(low) - abs(high)) / max(abs(low), abs(high), 1e-12)
        if relative_error > 1e-4:
            bm.free()
            raise RuntimeError(
                f"{obj.name}: duplicate signed-volume mismatch: {low}, {high}"
            )
        delete_vertices.update(negative["vertices"])
        groups_removed += 1
        triangles_removed += int(negative["triangles"])

    if delete_vertices:
        bmesh.ops.delete(bm, geom=list(delete_vertices), context="VERTS")
        bm.to_mesh(obj.data)
        obj.data.validate(clean_customdata=False)
        obj.data.update(calc_edges=True)
    bm.free()
    return groups_removed, triangles_removed


def main() -> None:
    character = parse_character()
    config = CONFIG[character]
    input_path = config["input"]
    output_path = config["output"]
    if not bpy.app.background:
        raise RuntimeError("Deduplication only runs in Blender background mode")
    if Path(bpy.data.filepath) != input_path:
        raise RuntimeError(f"Unexpected input workspace: {bpy.data.filepath}")
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing workspace: {output_path}")

    collection = bpy.data.collections.get(str(config["collection"]))
    if collection is None:
        raise RuntimeError(f"Missing work collection: {config['collection']}")
    objects = [obj for obj in collection.all_objects if obj.type == "MESH"]
    before = mesh_stats(objects)
    if before != config["before"]:
        raise RuntimeError(f"Unexpected pre-dedup stats: {before}")

    total_groups = 0
    total_removed = 0
    for obj in objects:
        groups_removed, triangles_removed = deduplicate_mesh(obj)
        total_groups += groups_removed
        total_removed += triangles_removed

    after = mesh_stats(objects)
    if after != config["after"]:
        raise RuntimeError(f"Unexpected post-dedup stats: actual={after} expected={config['after']}")
    if total_removed != config["saving"]:
        raise RuntimeError(
            f"Unexpected triangle saving: actual={total_removed} expected={config['saving']}"
        )
    if not all(obj.data.has_custom_normals for obj in objects):
        raise RuntimeError("One or more meshes lost custom normals")

    collection["deduplicated_reverse_shells"] = total_groups
    collection["deduplicated_triangles"] = total_removed
    collection["revision"] = "v002"
    bpy.context.scene["workspace_revision"] = "v002-deduplicated"
    readme = bpy.data.texts.get("README_YIER_BUBU_WORK.txt")
    if readme is not None:
        readme.write(
            f"\nV002 exact reverse-shell deduplication: groups={total_groups}, "
            f"triangles_removed={total_removed}, result={after}.\n"
        )

    result = bpy.ops.wm.save_as_mainfile(filepath=str(output_path), check_existing=False)
    if "FINISHED" not in result:
        raise RuntimeError(f"Saving v002 did not finish: {sorted(result)}")
    if Path(bpy.data.filepath).resolve() != output_path.resolve():
        raise RuntimeError(f"Blender reports an unexpected saved path: {bpy.data.filepath}")
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError(f"Saved v002 is missing or empty: {output_path}")

    print(
        f"[{character} deduplicate] PASS groups={total_groups} triangles_removed={total_removed} "
        f"before={before} after={after}"
    )
    print(f"[{character} deduplicate] Saved: {output_path}")


if __name__ == "__main__":
    main()
