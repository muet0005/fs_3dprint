#!/usr/bin/env python3
import os
import zipfile
import tempfile
import shutil
import trimesh
from lxml import etree as ET

ORIG_3MF = "Exproting_trials_02_for_Ryan.3mf"
NEW_STL  = "bh.wholebrain.smoothed.stl"
NEW_STL = "bh.fsaverage.wholebrain.smoothed.stl"

OUTPUT   = "Exproting_trials_02_for_Ryan.fsaverage.gcode/Exproting_trials_02_for_Ryan.fsaverage.3mf"

CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PROD_NS = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"

NS = {"m": CORE_NS, "p": PROD_NS}

def q(ns, tag) -> str:
    return f"{{{ns}}}{tag}"

def indent(e, level=0):
    i = "\n" + level * "  "
    if len(e):
        if not e.text or not e.text.strip():
            e.text = i + "  "
        for sub in e:
            indent(sub, level + 1)
        if not e.tail or not e.tail.strip():
            e.tail = i
    else:
        if level and (not e.tail or not e.tail.strip()):
            e.tail = i

def parse_transform(s: str):
    vals = [float(x) for x in s.split()]
    if len(vals) != 12:
        raise ValueError(f"Expected 12 transform numbers, got {len(vals)}")
    return vals

def format_transform(vals):
    return " ".join(f"{v:.9f}" for v in vals)

# ---- Extract package ----
tmp = tempfile.mkdtemp()
with zipfile.ZipFile(ORIG_3MF, "r") as z:
    z.extractall(tmp)

scene_path = os.path.join(tmp, "3D", "3dmodel.model")
if not os.path.exists(scene_path):
    raise FileNotFoundError(f"Missing scene model: {scene_path}")

# ---- Load new mesh (STL) ----
mesh = trimesh.load(NEW_STL)
verts = mesh.vertices
faces = mesh.faces

print(f"🔹 STL vertices: {len(verts)}, triangles: {len(faces)}")

# ---- Read scene (3D/3dmodel.model) and find referenced object part ----
scene_tree = ET.parse(scene_path)
scene_root = scene_tree.getroot()

# 1) Find the (first) build item and its objectid + transform
item = scene_root.find(".//m:build/m:item", NS)
if item is None:
    raise RuntimeError("No <build><item> found in 3D/3dmodel.model")

objectid = item.get("objectid")
if not objectid:
    raise RuntimeError("Build <item> has no objectid attribute")

item_transform = item.get("transform")
if not item_transform:
    raise RuntimeError("Build <item> has no transform attribute")

# 2) Find the object with that id in resources
obj = scene_root.find(f".//m:resources/m:object[@id='{objectid}']", NS)
if obj is None:
    raise RuntimeError(f"Could not find <object id='{objectid}'> in resources")

# 3) Orca stores the geometry as a component with p:path="/3D/Objects/....model"
component = obj.find(".//m:components/m:component", NS)
if component is None:
    raise RuntimeError("Object has no <components><component>; expected Orca-style external object")

part_path = component.get(q(PROD_NS, "path"))  # p:path
if not part_path:
    raise RuntimeError("Component missing p:path (production extension)")

# part_path is usually like "/3D/Objects/xxx.model" -> make it filesystem-relative
part_rel = part_path.lstrip("/").replace("/", os.sep)
geom_path = os.path.join(tmp, part_rel)

if not os.path.exists(geom_path):
    raise FileNotFoundError(f"Referenced geometry part not found: {geom_path}")

print(f"Scene objectid={objectid} references geometry part: {part_path}")

# ---- Replace geometry in the referenced part (3D/Objects/*.model) ----
geom_tree = ET.parse(geom_path)
geom_root = geom_tree.getroot()

# Choose the first mesh under resources/object (typical for these parts)
geom_obj = geom_root.find(".//m:resources/m:object", NS)
if geom_obj is None:
    raise RuntimeError("Geometry part has no <resources><object>")

mesh_node = geom_obj.find(".//m:mesh", NS)
if mesh_node is None:
    raise RuntimeError("Geometry part has no <mesh> node")

# wipe old geometry
for child in list(mesh_node):
    mesh_node.remove(child)

# write new vertices (namespaced!)
verts_node = ET.SubElement(mesh_node, q(CORE_NS, "vertices"))
for v in verts:
    ET.SubElement(
        verts_node,
        q(CORE_NS, "vertex"),
        {"x": f"{v[0]:.9f}", "y": f"{v[1]:.9f}", "z": f"{v[2]:.9f}"}
    )

# write new triangles (namespaced!)
tris_node = ET.SubElement(mesh_node, q(CORE_NS, "triangles"))
for f in faces:
    ET.SubElement(
        tris_node,
        q(CORE_NS, "triangle"),
        {"v1": str(int(f[0])), "v2": str(int(f[1])), "v3": str(int(f[2]))}
    )

indent(geom_root)
geom_tree.write(geom_path, encoding="UTF-8", xml_declaration=True)

print("Geometry replaced in referenced Objects part!")

# ---- DROP TO PLATE FIX (adjust scene build item transform) ----
min_z = float(verts[:, 2].min())
dz = -min_z
print(f"Auto drop amount: {dz:.3f} mm")

T = parse_transform(item_transform)
# indices 9,10,11 are Tx,Ty,Tz in 3MF 3x4 row-major
T[11] += dz
item.set("transform", format_transform(T))

indent(scene_root)
scene_tree.write(scene_path, encoding="UTF-8", xml_declaration=True)

print("Updated build transform in 3D/3dmodel.model")

# ---- Repack ----
out_base = OUTPUT[:-4]
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)

shutil.make_archive(out_base, "zip", tmp)
shutil.move(out_base + ".zip", OUTPUT)
shutil.rmtree(tmp)

print("Output:", OUTPUT)

