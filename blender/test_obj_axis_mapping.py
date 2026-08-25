"""Read-only experiment: report Blender world bounds for OBJ axis settings."""

from __future__ import annotations

from pathlib import Path

import bpy
from mathutils import Vector


OBJ = Path(
    r"D:\SteamLibrary\steamapps\common\Overcooked! 2\BepInEx\plugins"
    r"\OC2DIYChef\Resources\171-pinkpig\Head.obj"
)
COMBINATIONS = (
    ("NEGATIVE_Z", "Y"),
    ("NEGATIVE_Y", "Z"),
    ("Y", "Z"),
    ("Z", "Y"),
)


def bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points = [
        obj.matrix_world @ Vector(corner)
        for obj in objects
        if obj.type == "MESH"
        for corner in obj.bound_box
    ]
    lower = Vector(tuple(min(point[index] for point in points) for index in range(3)))
    upper = Vector(tuple(max(point[index] for point in points) for index in range(3)))
    return lower, upper


for forward, up in COMBINATIONS:
    before = set(bpy.data.objects)
    result = bpy.ops.wm.obj_import(
        filepath=str(OBJ),
        forward_axis=forward,
        up_axis=up,
        use_split_objects=True,
        use_split_groups=True,
    )
    created = list(set(bpy.data.objects) - before)
    lower, upper = bounds(created)
    print(
        f"[OBJ axes] forward={forward} up={up} result={sorted(result)} "
        f"min={tuple(round(value, 6) for value in lower)} "
        f"max={tuple(round(value, 6) for value in upper)} "
        f"dimensions={tuple(round(value, 6) for value in (upper - lower))}"
    )
    for obj in created:
        bpy.data.objects.remove(obj, do_unlink=True)
