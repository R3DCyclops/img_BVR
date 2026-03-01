import pygame
from pygame.locals import *
import moderngl
import numpy as np
import os
import sys
import math
import json
import struct
import argparse
import difflib
import tkinter as tk
from tkinter import ttk, filedialog

script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import utils
utils.add_src_path()

from gtalib import dff as dff_lib
from gtalib import txd as txd_lib

def set_window_icons(window, icon_path):
    if os.path.exists(icon_path):
        try:
            window.iconbitmap(icon_path)
        except:
            pass

def set_pygame_icon(icon_path):
    if os.path.exists(icon_path):
        try:
            from PIL import Image
            img = Image.open(icon_path)
            img = img.resize((32, 32), Image.Resampling.LANCZOS)
            data = img.convert("RGBA").tobytes()
            surface = pygame.image.fromstring(data, (32, 32), "RGBA")
            pygame.display.set_icon(surface)
        except:
            pass

PRESETS_DIR = utils.resource_path("assets/presets_view")

def decode_dxt1_block(data, offset):
    c0, c1 = struct.unpack_from('<HH', data, offset)
    r0 = ((c0 >> 11) & 0x1F) << 3
    g0 = ((c0 >> 5) & 0x3F) << 2
    b0 = (c0 & 0x1F) << 3
    r1 = ((c1 >> 11) & 0x1F) << 3
    g1 = ((c1 >> 5) & 0x3F) << 2
    b1 = (c1 & 0x1F) << 3
    colors = [(r0, g0, b0, 255), (r1, g1, b1, 255)]
    if c0 > c1:
        colors.append(((2 * r0 + r1) // 3, (2 * g0 + g1) // 3, (2 * b0 + b1) // 3, 255))
        colors.append(((r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3, (b0 + 2 * b1) // 3, 255))
    else:
        colors.append(((r0 + r1) // 2, (g0 + g1) // 2, (b0 + b1) // 2, 255))
        colors.append((0, 0, 0, 0))
    indices = struct.unpack_from('<I', data, offset + 4)[0]
    pixels = []
    for i in range(16):
        idx = (indices >> (i * 2)) & 3
        pixels.extend(colors[idx])
    return pixels

def decode_dxt5_block(data, offset):
    a0, a1 = data[offset], data[offset + 1]
    alpha_codes = [a0, a1]
    for i in range(6):
        alpha_codes.append((data[offset + 2 + i] >> (i * 2)) & 0x03)
    alpha_vals = [a0, a1]
    if a0 > a1:
        for i in range(6):
            alpha_vals.append((a0 * (6 - i) + a1 * (i + 1)) // 7)
    else:
        for i in range(4):
            alpha_vals.append((a0 * (4 - i) + a1 * (i + 1)) // 5)
    alpha_vals.extend([0, 255])
    c0, c1 = struct.unpack_from('<HH', data, offset + 8)
    r0 = ((c0 >> 11) & 0x1F) << 3
    g0 = ((c0 >> 5) & 0x3F) << 2
    b0 = (c0 & 0x1F) << 3
    r1 = ((c1 >> 11) & 0x1F) << 3
    g1 = ((c1 >> 5) & 0x3F) << 2
    b1 = (c1 & 0x1F) << 3
    colors = [(r0, g0, b0), (r1, g1, b1)]
    colors.append(((2 * r0 + r1) // 3, (2 * g0 + g1) // 3, (2 * b0 + b1) // 3))
    colors.append(((r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3, (b0 + 2 * b1) // 3))
    indices = struct.unpack_from('<I', data, offset + 12)[0]
    pixels = []
    for i in range(16):
        idx = (indices >> (i * 2)) & 3
        a = alpha_vals[alpha_codes[i]]
        pixels.extend([colors[idx][0], colors[idx][1], colors[idx][2], a])
    return pixels

def decode_dxt(raw, w, h, dxt_type):
    result = bytearray(w * h * 4)
    block_w, block_h = (w + 3) // 4, (h + 3) // 4
    block_size = 8 if dxt_type == 'DXT1' else 16
    decode_func = decode_dxt1_block if dxt_type == 'DXT1' else decode_dxt5_block
    for by in range(block_h):
        for bx in range(block_w):
            offset = (by * block_w + bx) * block_size
            if offset + block_size > len(raw):
                continue
            block = decode_func(raw, offset)
            for iy in range(4):
                for ix in range(4):
                    x, y = bx * 4 + ix, by * 4 + iy
                    if x < w and y < h:
                        pos = (y * w + x) * 4
                        src = (iy * 4 + ix) * 4
                        result[pos:pos + 4] = block[src:src + 4]
    return bytes(result)

def is_clothing_model(frames_list):
    if not frames_list:
        return False
    frame_names = []
    for f in frames_list:
        name = getattr(f, 'name', None)
        frame_names.append(name.lower() if name else '')
    all_names = ' '.join(frame_names)
    car_keywords = ['wheel', 'chassis', 'door', 'bonnet', 'boot', 'bump',
                    'windscreen', 'exhaust', 'engine', 'petrol', 'taillight',
                    'headlight', 'dummy', 'vlo', 'dam', '_ok', 'ug_']
    for kw in car_keywords:
        if kw in all_names:
            return False
    clothing_keywords = ['normal', 'body', 'legs', 'arms', 'torso', 'head',
                         'hands', 'feet', 'upper', 'lower', 'clothes', 'skin']
    for kw in clothing_keywords:
        if kw in all_names:
            return True
    if len(frames_list) <= 10:
        return True
    return False

def extract_texture_names_from_dff(dff_path):
    required = set()
    try:
        dp = dff_lib.dff()
        dp.load_file(dff_path)
        for geom in dp.geometry_list:
            mesh = getattr(geom, "mesh", geom)
            materials = getattr(mesh, "materials", []) or getattr(geom, "material_list", [])
            for mat in materials:
                for attr in ['texture', 'tex_name', 'name']:
                    val = getattr(mat, attr, None)
                    if val and isinstance(val, str) and val.strip():
                        required.add(val.lower().strip())
    except Exception as e:
        print(f"Warning: DFF analysis error: {e}")
    return required

def filename_match_score(dff_name, txd_name):
    dff_base = os.path.splitext(dff_name)[0].lower()
    txd_base = os.path.splitext(txd_name)[0].lower()
    if dff_base == txd_base:
        return 100
    if dff_base in txd_base:
        return 95 if len(dff_base) >= 4 else 50
    if txd_base in dff_base:
        return 90 if len(txd_base) >= 4 else 45
    ratio = difflib.SequenceMatcher(None, dff_base, txd_base).ratio()
    return int(ratio * 80) if ratio >= 0.7 else 0

def find_txd_candidates(dff_path, required_textures):
    directory = os.path.dirname(dff_path)
    dff_name = os.path.basename(dff_path)
    all_txd = [f for f in os.listdir(directory) if f.lower().endswith('.txd')]
    if not all_txd:
        print("Warning: No TXD files found")
        return []
    candidates = []
    for txd_name in all_txd:
        txd_path = os.path.join(directory, txd_name)
        try:
            tp = txd_lib.txd()
            tp.load_file(txd_path)
            txd_textures = {getattr(t, 'name', '').lower().strip() for t in tp.native_textures if getattr(t, 'name', None)}
        except Exception as e:
            print(f"Warning: Failed to read {txd_name}: {e}")
            continue
        material_matches = required_textures & txd_textures if required_textures else set()
        filename_score = 0 if (required_textures and material_matches) else filename_match_score(dff_name, txd_name)
        priority = len(material_matches) * 1000 + filename_score
        if material_matches or filename_score >= 80:
            candidates.append({
                'path': txd_path,
                'name': txd_name,
                'textures': txd_textures,
                'material_matches': material_matches,
                'filename_score': filename_score,
                'priority': priority
            })
    candidates.sort(key=lambda x: x['priority'], reverse=True)
    print(f"Found TXD candidates: {len(candidates)}")
    for i, cand in enumerate(candidates[:5], 1):
        info = f"{len(cand['material_matches'])} matches" if cand['material_matches'] else f"name: {cand['filename_score']}%"
        print(f"   {i}. {cand['name']} ({info})")
    return candidates

VS = """#version 330
in vec3 in_position; in vec2 in_texcoord;
uniform mat4 mvp; uniform vec2 uv_offset; uniform vec2 uv_scale; uniform float uv_rotate;
out vec3 world_pos; out vec2 uv;
void main() {
gl_Position = mvp * vec4(in_position, 1.0); world_pos = in_position;
vec2 fixed_uv = vec2(in_texcoord.x, 1.0 - in_texcoord.y);
float c = cos(uv_rotate); float s = sin(uv_rotate);
uv = (vec2(fixed_uv.x * c - fixed_uv.y * s, fixed_uv.x * s + fixed_uv.y * c) * uv_scale) + uv_offset;
}"""
FS = """#version 330
in vec3 world_pos; in vec2 uv;
uniform sampler2D texture0; uniform int use_texture;
out vec4 fragColor;
void main() {
vec3 color = use_texture == 1 ? texture(texture0, uv).rgb : vec3(0.78, 0.78, 0.78);
vec3 dx = dFdx(world_pos); vec3 dy = dFdy(world_pos);
vec3 normal = normalize(cross(dx, dy));
vec3 light_dir = normalize(vec3(0.5, 1.0, 0.3));
float diff = max(dot(normal, light_dir), 0.0);
float lighting = 0.7 + 0.3 * diff;
fragColor = vec4(color * lighting, 1.0);
}"""

class FixedCam:
    def __init__(self, width, height):
        self.dist = 5.0
        self.yaw = 0.785
        self.pitch = 0.524
        self.width = width
        self.height = height

    def view(self):
        x = self.dist * math.cos(self.pitch) * math.sin(self.yaw)
        y = self.dist * math.sin(self.pitch)
        z = self.dist * math.cos(self.pitch) * math.cos(self.yaw)
        eye = np.array([x, y, z])
        target = np.array([0, 0, 0])
        up = np.array([0, 1, 0])
        f = (target - eye)
        f /= np.linalg.norm(f)
        s = np.cross(f, up)
        s /= np.linalg.norm(s)
        u = np.cross(s, f)
        mat = np.eye(4, dtype='f4')
        mat[0, :3], mat[1, :3], mat[2, :3] = s, u, -f
        mat[0, 3], mat[1, 3], mat[2, 3] = -np.dot(s, eye), -np.dot(u, eye), np.dot(f, eye)
        return mat

    def proj(self):
        fov, near, far = 60.0, 0.1, 100.0
        asp = self.width / self.height
        f = 1.0 / math.tan(math.radians(fov) / 2)
        m = np.zeros((4, 4), dtype='f4')
        m[0, 0] = f / asp
        m[1, 1] = f
        m[2, 2] = (far + near) / (near - far)
        m[2, 3] = (2 * far * near) / (near - far)
        m[3, 2] = -1
        return m

    def zoom(self, v):
        self.dist = max(0.5, min(50.0, self.dist * v))

def create_placeholder_texture(ctx):
    size = 64
    data = np.zeros((size, size, 4), dtype=np.uint8)
    for y in range(size):
        for x in range(size):
            if ((x // 8) + (y // 8)) % 2 == 0:
                data[y, x] = [180, 180, 180, 255]
            else:
                data[y, x] = [100, 100, 100, 255]
    tex = ctx.texture((size, size), 4, data.tobytes())
    tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
    tex.repeat = True
    return tex

def get_frame_world_matrix(frame_index, frames_list):
    transform = np.eye(4, dtype=np.float32)
    current_idx = frame_index
    visited = set()
    while current_idx is not None and current_idx >= 0 and current_idx < len(frames_list):
        if current_idx in visited:
            break
        visited.add(current_idx)
        current = frames_list[current_idx]
        local = np.eye(4, dtype=np.float32)
        if hasattr(current, 'rotation_matrix') and current.rotation_matrix:
            try:
                rm = current.rotation_matrix
                if hasattr(rm, 'right') and hasattr(rm, 'up') and hasattr(rm, 'at'):
                    rot = np.array([
                        [float(rm.right.x), float(rm.right.y), float(rm.right.z)],
                        [float(rm.up.x), float(rm.up.y), float(rm.up.z)],
                        [float(rm.at.x), float(rm.at.y), float(rm.at.z)]
                    ], dtype=np.float32)
                else:
                    rot = np.array(rm, dtype=np.float32).reshape(3, 3)
                local[:3, :3] = rot
            except:
                pass
        if hasattr(current, 'position') and current.position:
            try:
                pos = current.position
                if hasattr(pos, 'x') and hasattr(pos, 'y') and hasattr(pos, 'z'):
                    local[:3, 3] = [float(pos.x), float(pos.y), float(pos.z)]
                else:
                    local[:3, 3] = np.array(pos, dtype=np.float32)
            except:
                pass
        transform = local @ transform
        parent_idx = getattr(current, 'parent', -1)
        if isinstance(parent_idx, int) and parent_idx >= 0:
            current_idx = parent_idx
        else:
            break
    return transform

def get_atomic_attr(atomic, *possible_names, default=-1):
    for name in possible_names:
        if hasattr(atomic, name):
            val = getattr(atomic, name)
            if val is not None:
                return val
    return default

def find_texture_by_frame_name(frame_name, tex_dict_keys):
    if not frame_name or not tex_dict_keys:
        return None
    frame_lower = frame_name.lower().strip()
    if frame_lower in tex_dict_keys:
        return frame_lower
    if 'wheel' in frame_lower:
        for key in tex_dict_keys:
            if 'wheel' in key:
                return key
        return None
    if any(x in frame_lower for x in ['windscreen', 'window', 'glass']):
        for key in tex_dict_keys:
            if any(x in key for x in ['interior', 'glass', 'window']):
                return key
        return None
    if any(x in frame_lower for x in ['chassis', 'door', 'bonnet', 'boot', 'bump',
                                      'exhaust', 'light', 'misc', 'extra', 'ug_',
                                      'ped', 'engine', 'petrol', 'taillight', 'headlight']):
        for key in tex_dict_keys:
            if 'body' in key and 'wheel' not in key:
                return key
        return None
    for key in tex_dict_keys:
        if 'wheel' not in key:
            return key
    return tex_dict_keys[0] if tex_dict_keys else None

class GTAModel:
    def __init__(self, ctx, prog):
        self.ctx = ctx
        self.prog = prog
        self.tex = None
        self.tex_dict = {}
        self.geom_vaos = []
        self.geom_info = []
        self.frames_list = []
        self.is_clothing = False
        self.geom_data_list = []
        self.geom_state = {}
        self.texture_state = {}
        self.original_center = None
        self.original_scale = 1.0

    def load(self, dff_file, txd_candidates):
        dp = dff_lib.dff()
        dp.load_file(dff_file)
        self.geom_data_list = []
        self.geom_state = {}
        self.geom_vaos = []
        self.geom_info = []
        frames_list = getattr(dp, 'frame_list', [])
        atomic_list = getattr(dp, 'atomic_list', [])
        self.frames_list = frames_list
        self.is_clothing = is_clothing_model(frames_list)
        if self.is_clothing:
            print("Detected clothing - parts will be placed side by side")
        else:
            print("Detected vehicle - standard hierarchy")
        print(f"Found frames: {len(frames_list)}, atomics: {len(atomic_list)}, geometries: {len(dp.geometry_list)}")
        geom_to_frame = {}
        for i, atomic in enumerate(atomic_list):
            geom_idx = i
            frame_idx = get_atomic_attr(atomic, 'frame_index', 'frame', 'parent_frame', default=-1)
            if hasattr(frame_idx, 'index'):
                frame_idx = frame_idx.index
            if geom_idx >= 0 and geom_idx < len(dp.geometry_list) and frame_idx >= 0:
                geom_to_frame[geom_idx] = frame_idx
        print(f"Found geometry->frame links: {len(geom_to_frame)}")
        for geom_idx, geom in enumerate(dp.geometry_list):
            mesh = getattr(geom, "mesh", geom)
            frame_idx = geom_to_frame.get(geom_idx, -1)
            geom_name = ""
            if frame_idx >= 0 and frame_idx < len(frames_list):
                geom_name = getattr(frames_list[frame_idx], 'name', '')
            verts = []
            try:
                verts_src = getattr(mesh, "vertices", [])
                if isinstance(verts_src, (list, tuple)):
                    for v in verts_src:
                        try:
                            if hasattr(v, 'x'):
                                coords = [float(v.x), float(v.y), float(v.z)]
                            elif isinstance(v, (list, tuple)) and len(v) >= 3:
                                coords = [float(v[0]), float(v[1]), float(v[2])]
                            else:
                                coords = [0, 0, 0]
                            verts.append(coords)
                        except:
                            continue
            except:
                pass
            if not verts:
                continue
            transform = np.eye(4, dtype=np.float32)
            if frame_idx >= 0 and frame_idx < len(frames_list):
                transform = get_frame_world_matrix(frame_idx, frames_list)
            verts_arr = np.array(verts, dtype=np.float32)
            verts_hom = np.hstack([verts_arr, np.ones((len(verts_arr), 1))])
            verts_transformed = (transform @ verts_hom.T).T[:, :3]
            if self.is_clothing:
                if geom_idx == 0:
                    offset = np.array([0.0, 0.0, 0.0], dtype=np.float32)
                elif geom_idx == 1:
                    offset = np.array([0.0, -0.5, 0.0], dtype=np.float32)
                elif geom_idx == 2:
                    offset = np.array([0.0, 0.5, 0.0], dtype=np.float32)
                else:
                    angle = (geom_idx - 3) * 0.6
                    radius = 2.5
                    offset = np.array([
                        math.cos(angle) * radius,
                        0.0,
                        math.sin(angle) * radius
                    ], dtype=np.float32)
                verts_transformed += offset
            indices = []
            try:
                for t in getattr(mesh, "triangles", []):
                    if hasattr(t, 'a'):
                        indices += [t.a, t.c, t.b]
            except:
                pass
            uvs = []
            try:
                if hasattr(mesh, 'uv_layers') and mesh.uv_layers:
                    for tc in mesh.uv_layers[0]:
                        try:
                            if hasattr(tc, 'u'):
                                uv = [float(tc.u), 1.0 - float(tc.v)]
                            elif hasattr(tc, 'x'):
                                uv = [float(tc.x), 1.0 - float(tc.y)]
                            elif isinstance(tc, (list, tuple)) and len(tc) >= 2:
                                uv = [float(tc[0]), 1.0 - float(tc[1])]
                            else:
                                uv = [0, 1]
                            uvs.append(uv)
                        except:
                            continue
            except:
                pass
            while len(uvs) < len(verts_transformed):
                uvs.append([0.0, 1.0])
            flags = getattr(geom, 'flags', getattr(geom, 'pipeline', 0))
            is_hidden_default = geom_name and ('_vlo' in geom_name.lower() or geom_name.lower() == 'chassis_vlo')
            geom_data = {
                'idx': geom_idx,
                'name': geom_name,
                'verts': verts_transformed,
                'indices': np.array(indices, dtype='i4'),
                'uvs': np.array(uvs, dtype='f4').reshape(-1, 2) if len(uvs) == len(verts_transformed) else None,
                'flags': flags,
                'frame_index': frame_idx,
                'enabled': not is_hidden_default,
                'frame_name': geom_name
            }
            self.geom_data_list.append(geom_data)
            self.geom_state[geom_idx] = not is_hidden_default
            self.geom_info.append({
                'idx': geom_idx,
                'name': geom_name,
                'verts': len(verts_transformed),
                'flags': flags,
                'frame_index': frame_idx,
                'enabled': not is_hidden_default,
                'frame_name': geom_name
            })
        if not self.geom_data_list:
            print("No geometries found!")
            return

        all_verts = np.vstack([g['verts'] for g in self.geom_data_list])
        center = all_verts.mean(axis=0)
        size = all_verts.max(axis=0) - all_verts.min(axis=0)
        global_scale = 2.0 / max(size) if max(size) > 1e-6 else 1.0

        if self.original_center is None:
            self.original_center = center
            self.original_scale = global_scale

        center = self.original_center
        global_scale = self.original_scale

        for geom_data in self.geom_data_list:
            verts_scaled = (geom_data['verts'] - center) * global_scale
            try:
                if geom_data['uvs'] is not None and len(geom_data['uvs']) == len(verts_scaled):
                    data = np.zeros(len(verts_scaled), dtype=[('p', '3f4'), ('uv', '2f4')])
                    data['p'] = verts_scaled
                    data['uv'] = geom_data['uvs']
                    vbo = self.ctx.buffer(data.tobytes())
                    ibo = self.ctx.buffer(geom_data['indices'].tobytes())
                    vao = self.ctx.vertex_array(self.prog, [(vbo, '3f 2f', 'in_position', 'in_texcoord')], ibo)
                else:
                    vbo = self.ctx.buffer(verts_scaled.tobytes())
                    ibo = self.ctx.buffer(geom_data['indices'].tobytes())
                    vao = self.ctx.vertex_array(self.prog, [(vbo, '3f', 'in_position')], ibo)
                self.geom_vaos.append({'vao': vao, 'idx': geom_data['idx'], 'enabled': geom_data['enabled']})
            except Exception as e:
                print(f"VAO geom#{geom_data['idx']}: {e}")
        print(f"Geometries: {len(self.geom_data_list)} | Vertices: {len(all_verts)} | Scale: {global_scale:.3f}")
        self.load_textures(txd_candidates)
        self.tex = list(self.tex_dict.values())[0] if self.tex_dict else create_placeholder_texture(self.ctx)

    def load_textures(self, txd_candidates):
        self.tex_dict.clear()
        try:
            from PIL import Image
            PIL_AVAILABLE = True
        except:
            PIL_AVAILABLE = False
            print("Warning: PIL not installed")
        for cand in txd_candidates:
            if not self.texture_state.get(cand['path'], True):
                continue
            try:
                tp = txd_lib.txd()
                tp.load_file(cand['path'])
                for tex_obj in tp.native_textures:
                    tex_name = getattr(tex_obj, 'name', '')
                    if not tex_name:
                        continue
                    tex_key = tex_name.lower().strip()
                    if tex_key in self.tex_dict:
                        continue
                    w = getattr(tex_obj, 'width', None)
                    h = getattr(tex_obj, 'height', None)
                    if not (w and h):
                        continue
                    raw = None
                    try:
                        if hasattr(tex_obj, 'pixels') and isinstance(tex_obj.pixels, (list, tuple)) and len(tex_obj.pixels) > 0:
                            px = tex_obj.pixels[0]
                            if isinstance(px, (bytes, bytearray)):
                                raw = bytes(px)
                        if not raw:
                            for obj in [tex_obj, getattr(tex_obj, 'raster', None), getattr(tex_obj, 'd3d8', None), getattr(tex_obj, 'd3d9', None)]:
                                if not obj:
                                    continue
                                for attr in ['data', 'pixels', 'buffer', 'raw']:
                                    if hasattr(obj, attr):
                                        data = getattr(obj, attr)
                                        if data and isinstance(data, (bytes, bytearray)):
                                            raw = bytes(data)
                                            break
                                if raw:
                                    break
                    except Exception as e:
                        print(f"  {tex_name}: data extraction error - {e}")
                        continue
                    if not raw:
                        print(f"  {tex_name}: no data")
                        continue
                    d3d_fmt = getattr(tex_obj, 'd3d_format', 0)
                    expected_dxt1 = (w // 4) * (h // 4) * 8
                    expected_dxt3_5 = (w // 4) * (h // 4) * 16
                    is_dxt = d3d_fmt in (0x31545844, 0x33545844, 0x35545844) or len(raw) in (expected_dxt1, expected_dxt3_5)
                    dxt_type = 'DXT1' if d3d_fmt == 0x31545844 or len(raw) == expected_dxt1 else 'DXT5'
                    try:
                        loaded = False
                        if is_dxt:
                            rgba = decode_dxt(raw, w, h, dxt_type)
                            img = Image.frombytes("RGBA", (w, h), rgba)
                            gl_tex = self.ctx.texture((w, h), 4, img.tobytes())
                            loaded = True
                            print(f"  {tex_name} ({w}x{h}) {dxt_type}")
                        elif not is_dxt and PIL_AVAILABLE:
                            for fmt in ["BGRA", "RGBA", "BGR", "RGB"]:
                                try:
                                    mode = "RGBA" if fmt in ["RGBA", "BGRA"] else "RGB"
                                    if len(raw) == w * h * 4:
                                        img = Image.frombytes(mode, (w, h), raw, "raw", fmt)
                                    elif len(raw) == w * h * 3:
                                        img = Image.frombytes(mode.replace('A', ''), (w, h), raw, "raw", fmt)
                                    else:
                                        continue
                                    if img.mode != "RGBA":
                                        img = img.convert("RGBA")
                                    gl_tex = self.ctx.texture((w, h), 4, img.tobytes())
                                    loaded = True
                                    print(f"  {tex_name} ({w}x{h}) {fmt}")
                                    break
                                except:
                                    continue
                        if not loaded:
                            print(f"  {tex_name}: not loaded")
                            continue
                        gl_tex.build_mipmaps()
                        gl_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
                        gl_tex.repeat = True
                        self.tex_dict[tex_key] = gl_tex
                    except Exception as e:
                        print(f"  {tex_name}: decoding error - {e}")
                        continue
            except Exception as e:
                print(f"TXD Error {cand['name']}: {e}")
                continue
        if self.tex_dict:
            self.tex = list(self.tex_dict.values())[0]
            print(f"Loaded textures: {len(self.tex_dict)}: {list(self.tex_dict.keys())}")
        else:
            self.tex = create_placeholder_texture(self.ctx)
            print("No textures loaded - using checkerboard")

    def rebuild_vaos(self):
        for item in self.geom_vaos:
            try:
                item['vao'].release()
            except:
                pass
        self.geom_vaos = []
        
        center = self.original_center if self.original_center is not None else np.array([0.0, 0.0, 0.0])
        global_scale = self.original_scale if self.original_scale else 1.0
        
        for geom_data in self.geom_data_list:
            if not self.geom_state.get(geom_data['idx'], True):
                continue
            try:
                verts_scaled = (geom_data['verts'] - center) * global_scale
                if geom_data['uvs'] is not None and len(geom_data['uvs']) == len(verts_scaled):
                    data = np.zeros(len(verts_scaled), dtype=[('p', '3f4'), ('uv', '2f4')])
                    data['p'] = verts_scaled
                    data['uv'] = geom_data['uvs']
                    vbo = self.ctx.buffer(data.tobytes())
                    ibo = self.ctx.buffer(geom_data['indices'].tobytes())
                    vao = self.ctx.vertex_array(self.prog, [(vbo, '3f 2f', 'in_position', 'in_texcoord')], ibo)
                else:
                    vbo = self.ctx.buffer(verts_scaled.tobytes())
                    ibo = self.ctx.buffer(geom_data['indices'].tobytes())
                    vao = self.ctx.vertex_array(self.prog, [(vbo, '3f', 'in_position')], ibo)
                self.geom_vaos.append({'vao': vao, 'idx': geom_data['idx'], 'enabled': True})
            except:
                pass

    def get_model_matrix(self, yaw, pitch, roll=0):
        cy, sy = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)
        cr, sr = math.cos(roll), math.sin(roll)
        Ry = np.array([[cy, 0, -sy, 0], [0, 1, 0, 0], [sy, 0, cy, 0], [0, 0, 0, 1]], dtype='f4')
        Rx = np.array([[1, 0, 0, 0], [0, cp, -sp, 0], [0, sp, cp, 0], [0, 0, 0, 1]], dtype='f4')
        Rz = np.array([[cr, sr, 0, 0], [-sr, cr, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], dtype='f4')
        return Ry @ Rx @ Rz

    def render(self, mvp, use_tex=True, uv_off=(0, 0), uv_sc=(1, 1), uv_rot=0):
        if not self.geom_vaos:
            return
        self.prog["mvp"].write(mvp.T.astype('f4').tobytes())
        self.prog["uv_offset"].value = uv_off
        self.prog["uv_scale"].value = uv_sc
        self.prog["uv_rotate"].value = uv_rot
        tex_dict_keys = list(self.tex_dict.keys())
        for item in self.geom_vaos:
            if not item['enabled']:
                continue
            geom = next((g for g in self.geom_data_list if g['idx'] == item['idx']), None)
            if not geom:
                continue
            frame_name = geom.get('frame_name')
            tex_key = find_texture_by_frame_name(frame_name, tex_dict_keys)
            tex = self.tex_dict.get(tex_key) if tex_key else None
            if use_tex and tex:
                tex.use(0)
                self.prog["use_texture"].value = 1
            else:
                self.prog["use_texture"].value = 0
            item['vao'].render()

class DFFViewer:
    def __init__(self, width=500, height=500, headless=False):
        self.width = width
        self.height = height
        self.headless = headless
        self.ctx = None
        self.prog = None
        self.model = None
        self.cam = None
        self.screen = None
        self.clock = None
        self.hud_window = None
        self.texture_window = None
        self.geom_window = None
        self.hud_labels = {}
        self.texture_state = {}
        self.texture_widgets = {}
        self.geom_state = {}
        self.geom_widgets = {}
        self.geom_filter_var = None
        self.txd_candidates = []
        self.dff_path = ""
        self.texture_frame = None
        
        self.icon_path = utils.resource_path(os.path.join("assets", "ico.ico"))
        
        if not headless:
            pygame.init()
            self.screen = pygame.display.set_mode((width, height), DOUBLEBUF | OPENGL)
            pygame.display.set_caption(".img BVR viewer")
            set_pygame_icon(self.icon_path)
            self.ctx = moderngl.create_context()
            self.clock = pygame.time.Clock()
        else:
            os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
            pygame.init()
            self.screen = pygame.display.set_mode((width, height), OPENGL | HIDDEN)
            self.ctx = moderngl.create_context()
            self.clock = pygame.time.Clock()
        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.disable(moderngl.CULL_FACE)
        self.ctx.line_width = 3.0
        self.prog = self.ctx.program(vertex_shader=VS, fragment_shader=FS)
        self.prog["texture0"].value = 0
        self.cam = FixedCam(width, height)

    def load_model(self, dff_path, txd_candidates):
        self.dff_path = dff_path
        self.txd_candidates = txd_candidates
        self.model = GTAModel(self.ctx, self.prog)
        self.model.texture_state = self.texture_state
        self.model.load(dff_path, txd_candidates)

    def set_camera_preset(self, yaw, pitch, roll, dist):
        self.cam.yaw = yaw

    def render_to_image(self, yaw, pitch, roll, path=None):
        self.ctx.clear(0.2, 0.2, 0.3)
        mvp = self.cam.proj() @ self.cam.view() @ self.model.get_model_matrix(yaw, pitch, roll)
        self.model.render(mvp, use_tex=True, uv_off=(0, 0), uv_sc=(1, 1), uv_rot=0)
        if path:
            data = pygame.image.tostring(self.screen, "RGB", True)
            from PIL import Image
            img = Image.frombytes("RGB", (self.width, self.height), data)
            img.save(path)
        return self.screen

    def create_hud(self):
        if self.headless:
            return
        self.hud_window = tk.Tk()
        self.hud_window.title("HUD")
        set_window_icons(self.hud_window, self.icon_path)
        self.hud_window.geometry("280x180+100+100")
        self.hud_window.attributes('-topmost', True)
        self.hud_window.resizable(False, False)
        self.hud_window.configure(bg='#1a1a2e')
        self.hud_labels = {}
        for field, color in [('yaw', '#0F6'), ('pitch', '#FC0'), ('roll', '#F6F'), ('zoom', '#6FF'), ('fps', '#AAA')]:
            lbl = tk.Label(self.hud_window, text=f"{field}: 0", font=('Consolas', 16, 'bold'), fg=color, bg='#1a1a2e')
            lbl.pack(anchor='w', padx=10, pady=3)
            self.hud_labels[field] = lbl

    def update_hud(self, yaw, pitch, roll, zoom, fps):
        if not self.hud_window:
            return
        try:
            self.hud_labels['yaw'].config(text=f"YAW:   {math.degrees(yaw):+7.2f}°")
            self.hud_labels['pitch'].config(text=f"PITCH: {math.degrees(pitch):+7.2f}°")
            self.hud_labels['roll'].config(text=f"ROLL:  {math.degrees(roll):+7.2f}°")
            self.hud_labels['zoom'].config(text=f"ZOOM:  {zoom:.3f}")
            self.hud_labels['fps'].config(text=f"FPS: {int(fps)}")
            self.hud_window.update()
        except:
            pass

    def create_texture_ui(self, candidates):
        if self.headless or not candidates:
            return
        try:
            if self.texture_window and self.texture_window.winfo_exists():
                self.texture_window.destroy()
        except:
            pass
        self.texture_window = tk.Tk()
        self.texture_window.title("Textures")
        set_window_icons(self.texture_window, self.icon_path)
        self.texture_window.geometry("450x400+450+100")
        self.texture_window.attributes('-topmost', True)
        self.texture_window.configure(bg='#1a1a2e')
        style = ttk.Style()
        style.configure('Dark.TFrame', background='#1a1a2e')
        style.configure('Dark.TButton', background='#2a2a3e', foreground='#FFF')
        tk.Label(self.texture_window, text="TXD files (click to toggle)",
                 font=('Consolas', 14, 'bold'), bg='#1a1a2e', fg='#FFF').pack(fill='x', padx=10, pady=10)
        btn_frame = tk.Frame(self.texture_window, bg='#1a1a2e')
        btn_frame.pack(fill='x', padx=10, pady=(0, 5))
        tk.Button(btn_frame, text="All [X]", command=lambda: self.select_all_textures(True),
                  bg='#2a2a3e', fg='#0F0', activebackground='#3a3a4e', activeforeground='#0F0').pack(side='left', padx=2)
        tk.Button(btn_frame, text="None [ ]", command=lambda: self.select_all_textures(False),
                  bg='#2a2a3e', fg='#F66', activebackground='#3a3a4e', activeforeground='#F66').pack(side='left', padx=2)
        tk.Button(btn_frame, text="Choose More...", command=self.choose_more_textures,
                  bg='#2a2a3e', fg='#FFF', activebackground='#3a3a4e', activeforeground='#FFF').pack(side='right', padx=2)
        self.texture_frame = tk.Frame(self.texture_window, bg='#1a1a2e')
        self.texture_frame.pack(fill='both', expand=True, padx=10)
        self.refresh_textures()
        print("First texture load...")
        self.on_texture_change()

    def choose_more_textures(self):
        paths = filedialog.askopenfilenames(
            title="Select additional TXD files",
            filetypes=[("TXD Files", "*.txd"), ("All Files", "*.*")]
        )
        if not paths:
            return
        for path in paths:
            if path not in [c['path'] for c in self.txd_candidates]:
                self.txd_candidates.append({
                    'path': path,
                    'name': os.path.basename(path),
                    'priority': 100,
                    'material_matches': set()
                })
                self.texture_state[path] = True
        self.refresh_textures()
        self.on_texture_change()

    def refresh_textures(self):
        if not self.texture_frame:
            return
        for widget in self.texture_frame.winfo_children():
            widget.destroy()
        self.texture_widgets = {}
        for cand in self.txd_candidates:
            path = cand['path']
            if path not in self.texture_state:
                self.texture_state[path] = True
        for cand in self.txd_candidates:
            path = cand['path']
            matches = cand.get('material_matches', set())
            preview = ', '.join(list(matches)[:4]) if matches else '(manual)'
            is_active = self.texture_state.get(path, True)
            status = "[X]" if is_active else "[ ]"
            fg = '#0F6' if is_active else '#888'
            def make_click_handler(p):
                return lambda e=None: self.toggle_texture(p)
            lbl = tk.Label(self.texture_frame,
                           text=f"{status} {cand['name']}\n{preview}",
                           font=('Consolas', 10), bg='#1a1a2e', fg=fg,
                           cursor='hand2', anchor='w', justify='left')
            lbl.bind('<Button-1>', make_click_handler(path))
            lbl.pack(fill='x', pady=3)
            self.texture_widgets[path] = lbl

    def toggle_texture(self, path):
        self.texture_state[path] = not self.texture_state.get(path, True)
        lbl = self.texture_widgets.get(path)
        if lbl:
            old_text = lbl.cget('text')
            lines = old_text.split('\n')
            status = "[X]" if self.texture_state[path] else "[ ]"
            fg_color = '#0F6' if self.texture_state[path] else '#888'
            filename_part = lines[0][4:] if lines[0].startswith(('[X] ', '[ ] ')) else lines[0]
            preview_part = lines[1] if len(lines) > 1 else ''
            lbl.config(text=f"{status} {filename_part}\n{preview_part}", fg=fg_color)
        self.on_texture_change()

    def select_all_textures(self, state):
        for path in self.texture_state:
            self.texture_state[path] = state
            lbl = self.texture_widgets.get(path)
            if lbl:
                status = "[X]" if state else "[ ]"
                fg = '#0F6' if state else '#888'
                old_text = lbl.cget('text')
                lines = old_text.split('\n')
                lbl.config(text=f"{status} {lines[0][4:]}\n{lines[1]}", fg=fg)
        print(f"All textures: {'ON' if state else 'OFF'}")
        self.on_texture_change()

    def create_geometry_ui(self):
        if self.headless or not self.model or not self.model.geom_info:
            return
        try:
            if self.geom_window and self.geom_window.winfo_exists():
                self.geom_window.destroy()
        except:
            pass
        self.geom_window = tk.Tk()
        self.geom_window.title("Geometry")
        set_window_icons(self.geom_window, self.icon_path)
        self.geom_window.geometry("550x450+100+450")
        self.geom_window.attributes('-topmost', True)
        self.geom_window.configure(bg='#1a1a2e')
        search_frame = tk.Frame(self.geom_window, bg='#1a1a2e')
        search_frame.pack(fill='x', padx=10, pady=5)
        tk.Label(search_frame, text="Search:", font=('Consolas', 10), bg='#1a1a2e', fg='#AAA').pack(side='left')
        self.geom_filter_var = tk.StringVar()
        search_entry = tk.Entry(search_frame, textvariable=self.geom_filter_var, font=('Consolas', 10), bg='#2a2a3e', fg='#FFF', insertbackground='#FFF')
        search_entry.pack(side='left', fill='x', expand=True, padx=5)
        self.geom_filter_var.trace_add('write', lambda *args: self.filter_geometry_list())
        btns = tk.Frame(self.geom_window, bg='#1a1a2e')
        btns.pack(fill='x', padx=10, pady=5)
        tk.Button(btns, text="All [X]", command=lambda: self.select_all_geometry(True),
                  bg='#2a2a3e', fg='#0F0', font=('Consolas', 9)).pack(side='left', padx=3)
        tk.Button(btns, text="None [ ]", command=lambda: self.select_all_geometry(False),
                  bg='#2a2a3e', fg='#F66', font=('Consolas', 9)).pack(side='left', padx=3)
        tk.Button(btns, text="Save", command=self.save_geom_settings,
                  bg='#2a2a3e', fg='#6CF', font=('Consolas', 9)).pack(side='left', padx=3)
        tk.Button(btns, text="Load", command=self.load_geom_settings,
                  bg='#2a2a3e', fg='#FC6', font=('Consolas', 9)).pack(side='left', padx=3)
        canvas = tk.Canvas(self.geom_window, bg='#1a1a2e', highlightthickness=0)
        scrollbar = tk.Scrollbar(self.geom_window, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg='#1a1a2e')
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=10, pady=(0, 10))
        scrollbar.pack(side="right", fill="y")
        self.geom_widgets = {}
        saved = self.load_geom_settings_dict()
        for info in self.model.geom_info:
            idx = info['idx']
            name = info.get('name', '')
            verts = info['verts']
            flags = info['flags']
            if name and ('_vlo' in name.lower() or name.lower() == 'chassis_vlo'):
                self.geom_state[idx] = False
            else:
                self.geom_state[idx] = saved.get(str(idx), True)
            display_name = name if name else f"Geom #{idx}"
            def make_click_handler(i):
                return lambda e=None: self.toggle_geometry(i)
            lbl = tk.Label(scrollable_frame,
                           text=f"[{'X' if self.geom_state[idx] else ' '}] #{idx:2d} | {display_name:25s} | {verts:4d}v | {flags:#08x}",
                           font=('Consolas', 9), bg='#1a1a2e', fg='#0F6' if self.geom_state[idx] else '#888',
                           cursor='hand2', anchor='w', justify='left')
            lbl.bind('<Button-1>', make_click_handler(idx))
            lbl.pack(fill='x', pady=1)
            self.geom_widgets[idx] = lbl
        self.filter_geometry_list()

    def filter_geometry_list(self):
        query = self.geom_filter_var.get().lower().strip() if self.geom_filter_var else ""
        for lbl in self.geom_widgets.values():
            lbl.pack_forget()
        for info in self.model.geom_info:
            idx = info['idx']
            name = info.get('name', '').lower()
            display_name = name if name else f"geom #{idx}"
            if not query or query in display_name or query in str(idx):
                lbl = self.geom_widgets.get(idx)
                if lbl:
                    lbl.pack(fill='x', pady=1)

    def toggle_geometry(self, idx):
        self.geom_state[idx] = not self.geom_state.get(idx, True)
        lbl = self.geom_widgets.get(idx)
        if lbl:
            old_text = lbl.cget('text')
            parts = old_text.split('|')
            status = "[X]" if self.geom_state[idx] else "[ ]"
            fg_color = '#0F6' if self.geom_state[idx] else '#888'
            lbl.config(text=f"{status} {parts[0][4:]}|{'|'.join(parts[1:])}", fg=fg_color)
            print(f"Geometry #{idx}: {'ON' if self.geom_state[idx] else 'OFF'}")
        self.on_geometry_change()

    def select_all_geometry(self, state):
        for idx in self.geom_state:
            self.geom_state[idx] = state
            lbl = self.geom_widgets.get(idx)
            if lbl:
                old_text = lbl.cget('text')
                parts = old_text.split('|')
                status = "[X]" if state else "[ ]"
                fg_color = '#0F6' if state else '#888'
                lbl.config(text=f"{status} {parts[0][4:]}|{'|'.join(parts[1:])}", fg=fg_color)
        print(f"All geometries: {'ON' if state else 'OFF'}")
        self.on_geometry_change()

    def load_geom_settings_dict(self):
        settings_file = self.dff_path + ".geom.json"
        if os.path.exists(settings_file):
            try:
                with open(settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_geom_settings(self):
        settings_file = self.dff_path + ".geom.json"
        try:
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.geom_state, f, indent=2)
        except:
            pass

    def load_geom_settings(self):
        saved = self.load_geom_settings_dict()
        for idx in self.geom_state:
            info = next((i for i in self.model.geom_info if i['idx'] == idx), None)
            name = info.get('name', '') if info else ''
            if name and ('_vlo' in name.lower() or name.lower() == 'chassis_vlo'):
                self.geom_state[idx] = False
            else:
                self.geom_state[idx] = saved.get(str(idx), True)
            lbl = self.geom_widgets.get(idx)
            if lbl:
                old_text = lbl.cget('text')
                parts = old_text.split('|')
                status = "[X]" if self.geom_state[idx] else "[ ]"
                fg_color = '#0F6' if self.geom_state[idx] else '#888'
                lbl.config(text=f"{status} {parts[0][4:]}|{'|'.join(parts[1:])}", fg=fg_color)
        print("Geometry settings loaded")
        self.on_geometry_change()

    def on_texture_change(self):
        if self.model and self.txd_candidates:
            active_txd = [c for c in self.txd_candidates if self.texture_state.get(c['path'], True)]
            self.model.load_textures(active_txd)
            if self.model.tex_dict:
                self.model.tex = list(self.model.tex_dict.values())[0]

    def on_geometry_change(self):
        if self.model:
            for geom_data in self.model.geom_data_list:
                idx = geom_data['idx']
                self.model.geom_state[idx] = self.geom_state.get(idx, True)
            self.model.rebuild_vaos()
            print(f"Active geometries: {len(self.model.geom_vaos)}")

    def run_interactive(self, dff_path, txd_candidates):
        if self.headless:
            return
        self.load_model(dff_path, txd_candidates)
        if not self.model.geom_vaos:
            print("Model error")
            return
        self.create_hud()
        self.create_texture_ui(txd_candidates)
        self.create_geometry_ui()
        use_tex = True
        myaw = mpitch = mroll = 0.0
        mouse = False
        last = (0, 0)
        auto = False
        hud_cnt = 0
        mouse_button = 1
        print("Controls:")
        print("  LMB - Rotation (Yaw/Pitch) | RMB - Rotation (Roll)")
        print("  Wheel - Zoom | P - Auto | Z - Reset")
        print("  J - Save Preset | C - Copy to Console")
        print("  chassis_vlo hidden by default")
        print("  Clothing: parts displayed side by side")
        running = True
        while running:
            self.clock.tick(60)
            try:
                if self.texture_window and self.texture_window.winfo_exists():
                    self.texture_window.update()
            except:
                pass
            try:
                if self.geom_window and self.geom_window.winfo_exists():
                    self.geom_window.update()
            except:
                pass
            try:
                if self.hud_window and self.hud_window.winfo_exists():
                    self.hud_window.update()
            except:
                pass
            if auto:
                myaw += 0.005
            keys = pygame.key.get_pressed()
            if keys[K_r]:
                mroll += 0.02
            if keys[K_f]:
                mroll -= 0.02
            for e in pygame.event.get():
                if e.type == QUIT:
                    running = False
                elif e.type == MOUSEBUTTONDOWN:
                    if e.button == 1:
                        mouse = True
                        mouse_button = 1
                        last = pygame.mouse.get_pos()
                    elif e.button == 3:
                        mouse = True
                        mouse_button = 3
                        last = pygame.mouse.get_pos()
                    elif e.button == 4:
                        self.cam.zoom(0.9)
                    elif e.button == 5:
                        self.cam.zoom(1.1)
                elif e.type == MOUSEBUTTONUP and e.button in (1, 3):
                    mouse = False
                elif e.type == MOUSEMOTION and mouse:
                    x, y = pygame.mouse.get_pos()
                    dx = (x - last[0]) * 0.003
                    dy = (y - last[1]) * 0.003
                    last = (x, y)
                    if mouse_button == 1:
                        myaw += dx
                        mroll += dy
                    elif mouse_button == 3:
                        mpitch += dx
                elif e.type == KEYDOWN:
                    if e.key == K_SPACE:
                        myaw = mpitch = mroll = 0.0
                    if e.key == K_p:
                        auto = not auto
                    if e.key == K_z:
                        myaw = mpitch = mroll = 0.0
                        self.cam.yaw, self.cam.pitch, self.cam.dist = 0.785, 0.524, 5.0
                    if e.key == K_j:
                        self.save_preset(myaw, mpitch, mroll, self.cam.dist, os.path.basename(dff_path))
                    if e.key == K_c:
                        print(f"\nPRESET:\nmyaw={myaw:.6f}\nmpitch={mpitch:.6f}\nmroll={mroll:.6f}\ncam_dist={self.cam.dist:.4f}\n")
                    if e.key == K_q and pygame.key.get_mods() & KMOD_CTRL:
                        running = False
            self.ctx.clear(0.2, 0.2, 0.3)
            mvp = self.cam.proj() @ self.cam.view() @ self.model.get_model_matrix(myaw, mpitch, mroll)
            self.model.render(mvp, use_tex, (0, 0), (1, 1), 0)
            hud_cnt += 1
            if hud_cnt >= 5:
                hud_cnt = 0
                self.update_hud(myaw, mpitch, mroll, self.cam.dist, self.clock.get_fps())
            pygame.display.flip()

    def save_preset(self, yaw, pitch, roll, dist, model_name):
        os.makedirs(PRESETS_DIR, exist_ok=True)
        existing = [f for f in os.listdir(PRESETS_DIR) if f.startswith("preset") and f.endswith(".txt")]
        nums = [int(f[6:-4]) for f in existing if f[6:-4].isdigit()]
        num = max(nums) + 1 if nums else 1
        fn = os.path.join(PRESETS_DIR, f"preset{num}.txt")
        yaw_deg = math.degrees(yaw)
        pitch_deg = math.degrees(pitch)
        roll_deg = math.degrees(roll)
        with open(fn, "w", encoding="utf-8") as f:
            f.write("# PRESET\n")
            f.write(f"model_yaw = {yaw:.6f}\n")
            f.write(f"model_pitch = {pitch:.6f}\n")
            f.write(f"model_roll = {roll:.6f}\n")
            f.write(f"cam_dist = {dist:.4f}\n")
        print(f"Preset saved: {fn}")

    def cleanup(self):
        pygame.quit()
        for win in [self.hud_window, self.texture_window, self.geom_window]:
            try:
                if win and win.winfo_exists():
                    win.destroy()
            except:
                pass

def parse_args():
    parser = argparse.ArgumentParser(description="DFF Viewer")
    parser.add_argument("--dff", required=True, help="Path to DFF file")
    parser.add_argument("--mode", choices=["auto", "manual", "none"], default="auto", help="Texture loading mode")
    parser.add_argument("--txd", action="append", default=[], help="Manual TXD files (can be repeated)")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode for batch render")
    parser.add_argument("--width", type=int, default=500, help="Window width")
    parser.add_argument("--height", type=int, default=500, help="Window height")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    dff_path = args.dff
    texture_mode = args.mode
    manual_txd_list = args.txd
    headless = args.headless
    width = args.width
    height = args.height
    print(f"Model: {os.path.basename(dff_path)}")
    print(f"Texture mode: {texture_mode}")
    if texture_mode == "none":
        txd_candidates = []
        print("Texture mode: none (gray model)")
    elif texture_mode == "manual":
        txd_candidates = [{'path': p, 'name': os.path.basename(p), 'priority': 100} for p in manual_txd_list]
        print(f"Texture mode: manual ({len(txd_candidates)} files)")
    else:
        required_global = extract_texture_names_from_dff(dff_path)
        txd_candidates = find_txd_candidates(dff_path, required_global)
        print(f"Texture mode: auto ({len(txd_candidates)} candidates)")
    viewer = DFFViewer(width=width, height=height, headless=headless)
    viewer.run_interactive(dff_path, txd_candidates)
    viewer.cleanup()
    print("Done")