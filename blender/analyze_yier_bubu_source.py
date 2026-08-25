"""Print a read-only object/component audit for the imported Yier/Bubu GLB."""

from __future__ import annotations

import json
from pathlib import Path

import bpy
from mathutils import Vector


EXPECTED_BLEND = Path(r"F:\dev\overcooke\characters\yier\source\yier_prototype.blend")


def world_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    lower = Vector(tuple(min(point[index] for point in points) for index in range(3)))
    upper = Vector(tuple(max(point[index] for point in points) for index in range(3)))
    return lower, upper


def main() -> None:
    if Path(bpy.data.filepath) != EXPECTED_BLEND:
        raise RuntimeError(f"Unexpected .blend path: {bpy.data.filepath}")

    source = bpy.data.collections.get("SOURCE_YIER")
    if source is None:
        raise RuntimeError("SOURCE_YIER collection is missing")

    rows: list[dict[str, object]] = []
    for obj in source.all_objects:
        row: dict[str, object] = {
            "name": obj.name,
            "type": obj.type,
            "parent": obj.parent.name if obj.parent else None,
            "children": len(obj.children),
            "location": [round(value, 6) for value in obj.location],
        }
        if obj.type == "MESH":
            lower, upper = world_bounds(obj)
            obj.data.calc_loop_triangles()
            row.update(
                {
                    "center": [round(value, 6) for value in ((lower + upper) * 0.5)],
                    "min": [round(value, 6) for value in lower],
                    "max": [round(value, 6) for value in upper],
                    "dimensions": [round(value, 6) for value in (upper - lower)],
                    "vertices": len(obj.data.vertices),
                    "triangles": len(obj.data.loop_triangles),
                    "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
                }
            )
        rows.append(row)

    rows.sort(key=lambda row: (row.get("center", [0.0])[0], str(row["name"])))
    print("[Yier/Bubu source audit] BEGIN")
    for row in rows:
        print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    print("[Yier/Bubu source audit] END")

    reference = bpy.data.collections.get("REF_EXISTING")
    if reference is None:
        raise RuntimeError("REF_EXISTING collection is missing")
    reference_was_hidden = reference.hide_viewport
    reference.hide_viewport = False
    bpy.context.view_layer.update()
    print("[OC2 reference bounds] BEGIN")
    for obj in sorted(reference.all_objects, key=lambda item: item.name):
        if obj.type != "MESH":
            continue
        lower, upper = world_bounds(obj)
        print(
            json.dumps(
                {
                    "name": obj.name,
                    "min": [round(value, 6) for value in lower],
                    "max": [round(value, 6) for value in upper],
                    "dimensions": [round(value, 6) for value in (upper - lower)],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    print("[OC2 reference bounds] END")
    reference.hide_viewport = reference_was_hidden


if __name__ == "__main__":
    main()
