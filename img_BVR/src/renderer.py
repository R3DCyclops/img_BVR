import os
import shutil
import pygame
from pygame.locals import *
from pathlib import Path
from PIL import Image
import numpy as np

import utils
utils.add_src_path()

from view import DFFViewer, find_txd_candidates, extract_texture_names_from_dff
from extractor import IMGArchive

PRESETS = [
    {'yaw': -8.412000, 'pitch': -0.380000, 'roll': -1.568000, 'dist': 2.5},
    {'yaw': -5.148000, 'pitch': -0.180000, 'roll': -1.297000, 'dist': 2.5}
]

def batch_render(source_path, dff_list, use_textures, v_size, progress_callback, source_type="img"):
    if source_type == "img":
        temp_dir = Path("temp_batch")
        output_base = Path("renders") / Path(source_path).stem
        output_base.mkdir(parents=True, exist_ok=True)
        if progress_callback:
            progress_callback("Unpacking IMG...")
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir()
        with IMGArchive(source_path) as arc:
            for entry in arc.entries:
                if entry.name in dff_list or entry.name.lower().endswith('.txd'):
                    pos = entry.offset * 2048
                    size = entry.length * 2048
                    arc.file.seek(pos)
                    data = arc.file.read(size)
                    with open(temp_dir / entry.name, 'wb') as f:
                        f.write(data)
        work_dir = temp_dir
        cleanup_dir = True
    else:
        work_dir = Path(source_path)
        output_base = Path("renders") / Path(source_path).name
        output_base.mkdir(parents=True, exist_ok=True)
        cleanup_dir = False
    
    square_size = v_size
    viewer = DFFViewer(width=square_size, height=square_size, headless=True)
    rendered_images = []
    for i, dff_name in enumerate(dff_list):
        if progress_callback:
            progress_callback(f"Render {i + 1}/{len(dff_list)}: {dff_name}")
        dff_path = work_dir / dff_name
        if use_textures:
            required = extract_texture_names_from_dff(str(dff_path))
            txd_candidates = find_txd_candidates(str(dff_path), required)
            textures_to_process = [c['path'] for c in txd_candidates] if txd_candidates else [None]
        else:
            textures_to_process = [None]
        for t_idx, txd_path in enumerate(textures_to_process):
            txd_list = [{'path': txd_path, 'name': os.path.basename(txd_path), 'priority': 100}] if txd_path else []
            viewer.load_model(str(dff_path), txd_list)
            combined_img = Image.new('RGB', (square_size * 2, square_size), (30, 30, 30))
            for p_idx, preset in enumerate(PRESETS):
                viewer.cam.dist = preset['dist']
                viewer.render_to_image(preset['yaw'], preset['pitch'], preset['roll'])
                if viewer.screen:
                    try:
                        import OpenGL.GL as gl
                        gl.glReadBuffer(gl.GL_FRONT)
                        data = gl.glReadPixels(0, 0, square_size, square_size, gl.GL_RGB, gl.GL_UNSIGNED_BYTE)
                        img_array = np.frombuffer(data, dtype=np.uint8).reshape(square_size, square_size, 3)[::-1]
                        img_part = Image.fromarray(img_array)
                    except:
                        data = pygame.image.tostring(viewer.screen, "RGB", True)
                        img_part = Image.frombytes("RGB", (square_size, square_size), data)
                combined_img.paste(img_part, (p_idx * square_size, 0))
            suffix = f"_tex{t_idx + 1}" if len(textures_to_process) > 1 else ""
            save_name = f"{Path(dff_name).stem}{suffix}.png"
            save_path = output_base / save_name
            combined_img.save(save_path)
            rendered_images.append(save_path)
            print(f"  Saved: {save_name}")
    batch_dir = output_base / "batch"
    batch_dir.mkdir(exist_ok=True)
    if rendered_images:
        create_multiple_grids(rendered_images, square_size, batch_dir)
    viewer.cleanup()
    if cleanup_dir and Path("temp_batch").exists():
        shutil.rmtree(Path("temp_batch"))
    if progress_callback:
        progress_callback("Done!")

def create_multiple_grids(images, square_size, output_dir):
    cell_w = square_size
    cell_h = square_size
    grid_w = 3 * cell_w
    grid_h = 3 * cell_h
    groups = [images[i:i+9] for i in range(0, len(images), 9)]
    for group_idx, group in enumerate(groups, 1):
        grid = Image.new('RGB', (grid_w, grid_h), (30, 30, 30))
        for i, path in enumerate(group):
            if i >= 9:
                break
            img = Image.open(path)
            left_half = img.crop((0, 0, square_size, square_size))
            if left_half.size != (cell_w, cell_h):
                left_half = left_half.resize((cell_w, cell_h), Image.Resampling.LANCZOS)
            col = i % 3
            row = i // 3
            grid.paste(left_half, (col * cell_w, row * cell_h))
        suffix = f"_grid{group_idx}" if len(groups) > 1 else ""
        grid_path = output_dir / f"grid_3x3{suffix}.png"
        grid.save(grid_path)
        print(f"  Saved grid {group_idx}/{len(groups)}: {grid_path} ({len(group)}/9 images, left-half only)")

def create_grid(images, square_size):
    return create_multiple_grids(images, square_size, Path("."))