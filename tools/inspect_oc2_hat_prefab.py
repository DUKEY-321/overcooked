"""Read-only inspection of the OC2 default chef hat hierarchy and meshes."""

from __future__ import annotations

from collections import deque
from pathlib import Path
import sys

import numpy as np
import UnityPy


ASSET = Path(
    r"D:\SteamLibrary\steamapps\common\Overcooked! 2\Overcooked2_Data\resources.assets"
)


def local_matrix(transform: object) -> np.ndarray:
    q = transform.m_LocalRotation
    x, y, z, w = q.x, q.y, q.z, q.w
    rotation = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=float,
    )
    scale = transform.m_LocalScale
    rotation = rotation @ np.diag([scale.x, scale.y, scale.z])
    position = transform.m_LocalPosition
    matrix = np.eye(4)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = [position.x, position.y, position.z]
    return matrix


def world_matrix(path_id: int, transforms: dict[int, object]) -> np.ndarray:
    chain: list[object] = []
    while path_id:
        transform = transforms[path_id]
        chain.append(transform)
        path_id = transform.m_Father.path_id
    matrix = np.eye(4)
    for transform in reversed(chain):
        matrix = matrix @ local_matrix(transform)
    return matrix


def main() -> None:
    env = UnityPy.load(str(ASSET))
    objects = {obj.path_id: obj for obj in env.objects}
    transforms = {
        path_id: reader.read()
        for path_id, reader in objects.items()
        if reader.type.name in {"Transform", "RectTransform"}
    }

    print("HatBase ancestor chain:")
    ancestor_id = 3410
    while ancestor_id:
        transform = transforms[ancestor_id]
        game_object = transform.m_GameObject.read()
        print(
            f"  transform={ancestor_id} go={game_object.m_Name} "
            f"father={transform.m_Father.path_id} pos={transform.m_LocalPosition} "
            f"rot={transform.m_LocalRotation} scale={transform.m_LocalScale}"
        )
        ancestor_id = transform.m_Father.path_id

    baseball_mesh = objects[1119].read()
    print("Baseball mesh bind poses:")
    for index, matrix in enumerate(baseball_mesh.m_BindPose):
        print(f"  [{index}] {matrix}")
    bindpose = baseball_mesh.m_BindPose[0]
    bindpose_matrix = np.array(
        [
            [bindpose.e00, bindpose.e01, bindpose.e02, bindpose.e03],
            [bindpose.e10, bindpose.e11, bindpose.e12, bindpose.e13],
            [bindpose.e20, bindpose.e21, bindpose.e22, bindpose.e23],
            [bindpose.e30, bindpose.e31, bindpose.e32, bindpose.e33],
        ]
    )
    renderer_world = world_matrix(3670, transforms)
    bone_world = world_matrix(3410, transforms)
    skinning_rest = np.linalg.inv(renderer_world) @ bone_world @ bindpose_matrix
    np.set_printoptions(precision=8, suppress=True)
    print(f"Baseball renderer world matrix:\n{renderer_world}")
    print(f"HatBase bone world matrix:\n{bone_world}")
    print(f"Renderer-local rest skinning matrix:\n{skinning_rest}")

    # resources.assets path ID 3441 is the Mesh transform containing the
    # avatar-15 Hat_Baseballcap object used as OC2DIYChef's custom-hat template.
    queue = deque([(3441, 0)])
    seen: set[int] = set()
    while queue:
        path_id, depth = queue.popleft()
        if path_id in seen:
            continue
        seen.add(path_id)
        transform = transforms[path_id]
        game_object = transform.m_GameObject.read()
        print(
            f"{'  ' * depth}{path_id} {game_object.m_Name} "
            f"pos={transform.m_LocalPosition} rot={transform.m_LocalRotation} "
            f"scale={transform.m_LocalScale}"
        )
        for pair in game_object.m_Component:
            component = pair.component.read()
            if type(component).__name__ != "SkinnedMeshRenderer":
                continue
            mesh = component.m_Mesh.read()
            print(
                f"{'  ' * (depth + 1)}renderer={pair.component.path_id} "
                f"mesh={component.m_Mesh.path_id}:{mesh.m_Name} "
                f"aabb={component.m_AABB} bones={[bone.path_id for bone in component.m_Bones]}"
            )
            if hasattr(mesh, "m_LocalAABB"):
                print(f"{'  ' * (depth + 2)}mesh_local_aabb={mesh.m_LocalAABB}")
        queue.extend((child.path_id, depth + 1) for child in transform.m_Children)

    names = {"Hat_Baseballcap", "Hat_Santa", "Head", "HatBase"}
    print("\nNamed GameObjects outside the selected subtree:")
    for reader in env.objects:
        if reader.type.name != "GameObject" or reader.peek_name() not in names:
            continue
        game_object = reader.read()
        transform_pair = next(
            (
                pair
                for pair in game_object.m_Component
                if objects[pair.component.path_id].type.name in {"Transform", "RectTransform"}
            ),
            None,
        )
        if transform_pair is None:
            continue
        transform = transform_pair.component.read()
        print(
            f"go={reader.path_id}:{game_object.m_Name} transform={transform_pair.component.path_id} "
            f"father={transform.m_Father.path_id} pos={transform.m_LocalPosition} "
            f"rot={transform.m_LocalRotation} scale={transform.m_LocalScale}"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
