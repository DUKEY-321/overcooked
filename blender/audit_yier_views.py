"""Render disposable workbench audit views without saving the loaded blend."""

from pathlib import Path
import tempfile

import bmesh
import bpy


OUTPUT_DIR = Path(tempfile.gettempdir()) / "oc2_yier_audit"


def remove_wrong_facing_source_surfaces() -> None:
    """Apply the audited selection in memory; the file is never saved."""
    bpy.data.objects["YIER_Material2.003"].hide_render = True

    obj = bpy.data.objects["YIER_Material2.002"]
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    unseen = set(bm.verts)
    delete_vertices = set()
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
        triangles = sum(max(len(face.verts) - 2, 0) for face in faces)
        center = [
            (min(vertex.co[index] for vertex in vertices)
             + max(vertex.co[index] for vertex in vertices))
            * 0.5
            for index in range(3)
        ]
        reverse_full_foot = (
            triangles == 1104
            and abs(center[0]) > 0.05
            and abs(center[2] - 0.272664) < 1e-5
        )
        reverse_face_detail = triangles <= 111 and center[1] < -0.2 and center[2] > 0.59
        if reverse_full_foot or reverse_face_detail:
            delete_vertices.update(vertices)

    bmesh.ops.delete(bm, geom=list(delete_vertices), context="VERTS")
    bm.to_mesh(obj.data)
    obj.data.update(calc_edges=True)
    bm.free()


def main() -> None:
    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    work = bpy.data.collections["WORK_YIER"]
    work_objects = set(work.all_objects)
    for obj in bpy.context.scene.objects:
        obj.hide_render = obj not in work_objects and obj.type != "CAMERA"
    remove_wrong_facing_source_surfaces()
    selected_triangles = 0
    for obj in work_objects:
        if obj.type == "MESH" and not obj.hide_render:
            obj.data.calc_loop_triangles()
            selected_triangles += len(obj.data.loop_triangles)
    if selected_triangles != 18_993:
        raise RuntimeError(f"Unexpected selected triangle count: {selected_triangles}")
    print(f"AUDIT_SELECTED_TRIANGLES={selected_triangles}")

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.studio_light = "paint.sl"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "BOTH"
    scene.display.shading.show_specular_highlight = True
    scene.display.shading.show_backface_culling = False
    scene.render.resolution_x = 900
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False

    for camera_name, suffix in (("CAM_FRONT", "front_selected"), ("CAM_SIDE", "side_selected")):
        scene.camera = bpy.data.objects[camera_name]
        scene.render.filepath = str(output_dir / f"yier_{suffix}.png")
        bpy.ops.render.render(write_still=True)
        print(f"AUDIT_RENDER={scene.render.filepath}")


if __name__ == "__main__":
    main()
