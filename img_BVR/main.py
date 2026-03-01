import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import sys
import subprocess
from pathlib import Path
import pygame
from pygame.locals import *
import shutil
import hashlib

import utils
utils.add_src_path()

if __name__ == "__main__" and "--dff" in sys.argv:
    from view import parse_args, DFFViewer, extract_texture_names_from_dff, find_txd_candidates
    args = parse_args()
    
    dff_path = args.dff
    texture_mode = args.mode
    manual_txd_list = args.txd
    headless = args.headless
    width = args.width
    height = args.height
    
    if texture_mode == "none":
        txd_candidates = []
    elif texture_mode == "manual":
        txd_candidates = [{'path': p, 'name': os.path.basename(p), 'priority': 100} for p in manual_txd_list]
    else:
        required_global = extract_texture_names_from_dff(dff_path)
        txd_candidates = find_txd_candidates(dff_path, required_global)
        
    viewer = DFFViewer(width=width, height=height, headless=headless)
    viewer.run_interactive(dff_path, txd_candidates)
    viewer.cleanup()
    sys.exit(0)

from extractor import get_dff_list, IMGArchive, pack_img, SECTOR_SIZE, NAME_SIZE
from renderer import batch_render
import webbrowser
from PIL import Image, ImageTk, ImageSequence
import pygame.mixer as mixer


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(".img BVR")
        
        icon_path = utils.resource_path(os.path.join("assets", "ico.ico"))
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except:
                pass

        self.window_width = 700
        self.window_height = 550
        self.root.geometry(f"{self.window_width}x{self.window_height}")
        self.root.resizable(False, False)
        
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True)
        
        self.batch_tex_mode = tk.StringVar(value="textures")
        self.viewer_tex_mode = tk.StringVar(value="auto")
        self.batch_source = tk.StringVar(value="img")
        self.manual_txd_paths = []
        
        self.create_batch_tab()
        self.create_unpack_tab()
        self.create_viewer_tab()
        self.create_credits_tab()
        
        
    def load_logo(self, logo_path, height_px):
        try:
            img = Image.open(logo_path)
            aspect = img.width / img.height
            new_width = int(height_px * aspect)
            img_resized = img.resize((new_width, height_px), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img_resized)
            photo._reference = img
            return photo
        except Exception as e:
            print(f"Logo load error: {e}")
            return None

    def create_credits_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Credits")
        
        self.gif_height = 250
        self.gif_delay_ms = 150
        
        ttk.Label(frame, text="created by m0reslav", font=('Consolas', 14, 'bold')).pack(pady=(20, 10))
        
        gif_path = utils.resource_path(os.path.join("assets", "avatar.gif"))
        if os.path.exists(gif_path):
            self.gif_frames = []
            gif_img = Image.open(gif_path)
            for frm in ImageSequence.Iterator(gif_img):
                aspect = frm.width / frm.height
                new_width = int(self.gif_height * aspect)
                resized = frm.copy().resize((new_width, self.gif_height), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(resized)
                photo._reference = frm
                self.gif_frames.append(photo)
            self.gif_label = ttk.Label(frame)
            self.gif_label.pack(pady=10)
            self.gif_index = 0
            self.animate_gif()
        
        self.audio_playing = False
        self.audio_paused = False
        self.audio_available = False
        self.audio_initialized = False
        self.music_path = utils.resource_path(os.path.join("assets", "util.mp3"))
        
        btn = tk.Button(frame, text="▶", font=('Consolas', 12), width=5, command=self.toggle_audio)
        btn.pack(pady=10)
        self.audio_btn = btn
        
        self.audio_status_label = ttk.Label(frame, text="", font=('Consolas', 9))
        self.audio_status_label.pack(pady=(0, 10))
        
        vol_frame = ttk.Frame(frame)
        vol_frame.pack(pady=(0, 10))
        ttk.Label(vol_frame, text="Volume:").pack(side='left', padx=(0, 5))
        self.volume_var = tk.DoubleVar(value=50.0)
        vol_slider = ttk.Scale(vol_frame, variable=self.volume_var, from_=0, to=100, 
                               orient='horizontal', length=150, command=self.on_volume_change)
        vol_slider.pack(side='left')
        self.volume_label = ttk.Label(vol_frame, text="50%", width=4)
        self.volume_label.pack(side='left', padx=(5, 0))
        
        link_frame = ttk.Frame(frame)
        link_frame.pack(pady=20)
        self.create_hyperlink(link_frame, "my Github", "https://github.com/R3DCyclops  ").pack(pady=2)
        self.create_hyperlink(link_frame, "my website", "https://moreslav.ru  ").pack(pady=2)
    
    def animate_gif(self):
        if not hasattr(self, 'gif_frames') or not self.gif_frames:
            return
        photo = self.gif_frames[self.gif_index]
        self.gif_label.config(image=photo)
        self.gif_label.image = photo
        self.gif_index = (self.gif_index + 1) % len(self.gif_frames)
        self.root.after(self.gif_delay_ms, self.animate_gif)
    
    def on_volume_change(self, value):
        if not self.audio_available:
            return
        try:
            vol = float(value) / 100.0
            pygame.mixer.music.set_volume(vol)
            if hasattr(self, 'volume_label'):
                self.volume_label.config(text=f"{int(float(value))}%")
        except:
            pass
    
    def toggle_audio(self):
        if not self.audio_initialized:
            if not os.path.exists(self.music_path):
                return
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=256)
                pygame.mixer.music.load(self.music_path)
                pygame.mixer.music.set_volume(self.volume_var.get() / 100.0)
                self.audio_initialized = True
                self.audio_available = True
            except pygame.error as e:
                print(f"Audio init failed: {e}")
                self.audio_btn.config(state='disabled', text="X", fg="#F66")
                self.audio_status_label.config(text="Speaker not found", foreground="red")
                return
            except Exception as e:
                print(f"Audio setup error: {e}")
                self.audio_btn.config(state='disabled', text="X", fg="#F66")
                self.audio_status_label.config(text="Speaker not found", foreground="red")
                return
        
        if not self.audio_available:
            return
        
        try:
            if not self.audio_playing:
                pygame.mixer.music.play(loops=-1)
                self.audio_playing = True
                self.audio_paused = False
                self.audio_btn.config(text="⏸", bg="#2a2a3e", fg="#0F6")
            elif self.audio_paused:
                pygame.mixer.music.unpause()
                self.audio_paused = False
                self.audio_btn.config(text="⏸", fg="#0F6")
            else:
                pygame.mixer.music.pause()
                self.audio_paused = True
                self.audio_btn.config(text="▶", fg="#FC0")
        except pygame.error as e:
            print(f"Audio playback error: {e}")
            self.audio_available = False
            self.audio_btn.config(state='disabled', text="✗", fg="#F66")
    
    def create_hyperlink(self, parent, text, url):
        lbl = tk.Label(parent, text=text, fg="#6CF", bg='#1a1a2e', cursor="hand2", font=('Consolas', 10))
        lbl.bind("<Button-1>", lambda e: webbrowser.open(url))
        lbl.bind("<Enter>", lambda e: lbl.config(fg="#9EF"))
        lbl.bind("<Leave>", lambda e: lbl.config(fg="#6CF"))
        return lbl

    def create_batch_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=".img Batch")
        top_frame = ttk.Frame(frame, padding=10)
        top_frame.pack(fill='x')
        
        source_frame = ttk.LabelFrame(top_frame, text="Source Type", padding=10)
        source_frame.pack(side='left', fill='x', expand=True, padx=(0, 10))
        
        ttk.Radiobutton(source_frame, text="Batch from IMG",
                        variable=self.batch_source, value="img",
                        command=self.on_source_change).grid(row=0, column=0, sticky='w')
        ttk.Radiobutton(source_frame, text="Batch from Folder",
                        variable=self.batch_source, value="folder",
                        command=self.on_source_change).grid(row=0, column=1, sticky='w', padx=30)
        
        self.source_label = ttk.Label(source_frame, text="IMG file:")
        self.source_label.grid(row=1, column=0, sticky='w', pady=(10, 0))
        self.source_path_var = tk.StringVar()
        ttk.Entry(source_frame, textvariable=self.source_path_var, width=35).grid(row=1, column=1, sticky='ew', padx=5, pady=(10, 0))
        self.browse_btn = ttk.Button(source_frame, text="Browse IMG", command=self.select_source)
        self.browse_btn.grid(row=1, column=2, sticky='w', padx=(0, 5), pady=(10, 0))
        source_frame.grid_columnconfigure(1, weight=1)
        
        size_frame = ttk.LabelFrame(top_frame, text="Output Image Size", padding=10)
        size_frame.pack(side='right', fill='x', padx=(10, 0))
        ttk.Label(size_frame, text="Vertical size (px):").pack(anchor='w')
        self.size_var = tk.StringVar(value="500")
        size_entry = ttk.Entry(size_frame, textvariable=self.size_var, width=10)
        size_entry.pack(anchor='w', pady=5)
        ttk.Label(size_frame, text="+2x width", font=('Consolas', 8), foreground='gray').pack(anchor='w')
        
        tex_frame = ttk.LabelFrame(frame, text="Textures", padding=10)
        tex_frame.pack(fill='x', padx=10, pady=(0, 5))
        ttk.Radiobutton(tex_frame, text="Auto-textures (semi stable)",
                        variable=self.batch_tex_mode, value="textures").grid(row=0, column=0, sticky='w')
        ttk.Radiobutton(tex_frame, text="No textures",
                        variable=self.batch_tex_mode, value="no_textures").grid(row=0, column=1, sticky='w', padx=30)
        
        list_frame = ttk.LabelFrame(frame, text="Select DFF files", padding=10)
        list_frame.pack(fill='both', expand=True, padx=10, pady=5)
        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(fill='x', pady=(0, 5))
        ttk.Button(btn_frame, text="Select All", command=self.select_all_dff).pack(side='left', padx=(0, 5))
        ttk.Button(btn_frame, text="Remove Selection", command=self.deselect_all_dff).pack(side='left')
        
        self.dff_listbox = tk.Listbox(list_frame, selectmode='multiple', exportselection=0)
        self.dff_listbox.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.dff_listbox.yview)
        scrollbar.pack(side='right', fill='y')
        self.dff_listbox.config(yscrollcommand=scrollbar.set)
        
        ttk.Button(list_frame, text="Batch Render", command=self.start_batch).pack(pady=10)
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self.status_var, foreground="gray").pack(pady=5)

    def on_source_change(self):
        if self.batch_source.get() == "img":
            self.source_label.config(text="IMG file:")
            self.browse_btn.config(text="Browse IMG", command=self.select_img_batch)
        else:
            self.source_label.config(text="Folder:")
            self.browse_btn.config(text="Browse Folder", command=self.select_folder_batch)

    def select_source(self):
        if self.batch_source.get() == "img":
            self.select_img_batch()
        else:
            self.select_folder_batch()

    def select_img_batch(self):
        path = filedialog.askopenfilename(filetypes=[("IMG Files", "*.img")])
        if path:
            self.source_path_var.set(path)
            self.status_var.set("Reading file list...")
            dffs = get_dff_list(path)
            self.dff_listbox.delete(0, tk.END)
            for d in dffs:
                self.dff_listbox.insert(tk.END, d)
            self.status_var.set(f"Found {len(dffs)} DFF files")

    def select_folder_batch(self):
        folder = filedialog.askdirectory(title="Select folder with DFF/TXD files")
        if folder:
            self.source_path_var.set(folder)
            self.status_var.set("Reading file list...")
            dffs = [f.name for f in Path(folder).glob("*.dff")]
            self.dff_listbox.delete(0, tk.END)
            for d in sorted(dffs):
                self.dff_listbox.insert(tk.END, d)
            self.status_var.set(f"Found {len(dffs)} DFF files in folder")

    def select_all_dff(self):
        if self.dff_listbox.size() > 0:
            self.dff_listbox.select_set(0, tk.END)

    def deselect_all_dff(self):
        if self.dff_listbox.size() > 0:
            self.dff_listbox.selection_clear(0, tk.END)

    def start_batch(self):
        source_path = self.source_path_var.get()
        if not source_path:
            messagebox.showerror("Error", "Please select an IMG file or folder")
            return
        selected_indices = self.dff_listbox.curselection()
        if not selected_indices:
            messagebox.showerror("Error", "Please select at least one DFF file")
            return
        dff_list = [self.dff_listbox.get(i) for i in selected_indices]
        try:
            v_size = int(self.size_var.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid vertical size value")
            return
        use_tex = self.batch_tex_mode.get() == "textures"
        source_type = self.batch_source.get()

        def worker():
            try:
                batch_render(source_path, dff_list, use_tex, v_size, self.status_var.set, source_type)
                self.root.after(0, lambda: messagebox.showinfo("Success", "Batch render completed!"))
            except Exception as ex:
                self.root.after(0, lambda err=ex: messagebox.showerror("Error", str(err)))
            finally:
                self.root.after(0, lambda: self.status_var.set("Ready"))
        
        self.status_var.set("Rendering...")
        threading.Thread(target=worker, daemon=True).start()

    def create_unpack_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="IMG Unpack")
        ttk.Label(frame, text="IMG file operations", font=('Consolas', 12)).pack(pady=20)
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="Unpack IMG", command=self.start_unpack).pack(side='left', padx=10)
        ttk.Button(btn_frame, text="Pack to IMG", command=self.start_pack).pack(side='left', padx=10)
        ttk.Button(btn_frame, text="Edit IMG", command=self.start_edit).pack(side='left', padx=10)
        self.unpack_status = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self.unpack_status).pack(pady=10)
        
        logo_height = 300
        logo_path = utils.resource_path(os.path.join("assets", "logo.png"))
        if os.path.exists(logo_path):
            self.logo_img = self.load_logo(logo_path, logo_height)
            if self.logo_img:
                lbl = ttk.Label(frame, image=self.logo_img)
                lbl.image = self.logo_img
                lbl.pack(pady=(10, 0))

    def start_pack(self):
        folder = filedialog.askdirectory(title="Select folder with files to pack")
        if not folder:
            return
        output = filedialog.asksaveasfilename(defaultextension=".img", filetypes=[("IMG Files", "*.img")], title="Save IMG as")
        if not output:
            return
        def worker():
            try:
                self.unpack_status.set("Packing...")
                count = pack_img(folder, output, lambda i, t, m: self.unpack_status.set(m))
                self.root.after(0, lambda: messagebox.showinfo("Success", f"Packed {count} files"))
            except Exception as ex:
                err_msg = str(ex)
                self.root.after(0, lambda msg=err_msg: messagebox.showerror("Error", msg))
            finally:
                self.root.after(0, lambda: self.unpack_status.set("Ready"))
        threading.Thread(target=worker, daemon=True).start()

    def start_edit(self):
        img_path = filedialog.askopenfilename(filetypes=[("IMG Files", "*.img")], title="Select IMG to edit")
        if not img_path:
            return
        IMGEditWindow(self.root, img_path)

    def select_img_unpack(self):
        path = filedialog.askopenfilename(filetypes=[("IMG Files", "*.img")])
        if path:
            self.unpack_path_var.set(path)


    def start_unpack(self):
        img_path = filedialog.askopenfilename(filetypes=[("IMG Files", "*.img")], title="Select IMG to unpack")
        if not img_path:
            return
        dest = filedialog.askdirectory(title="Select destination folder")
        if not dest:
            return
        def worker():
            try:
                self.unpack_status.set("Unpacking...")
                output_dir = os.path.join(dest, Path(img_path).stem)
                os.makedirs(output_dir, exist_ok=True)
                with IMGArchive(img_path) as arc:
                    count = arc.extract(output_dir)
                self.root.after(0, lambda: messagebox.showinfo("Success", f"Extracted {count} files to {output_dir}"))
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda msg=err_msg: messagebox.showerror("Error", msg))
            finally:
                self.root.after(0, lambda: self.unpack_status.set("Ready"))
        threading.Thread(target=worker, daemon=True).start()

    def create_viewer_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Viewer")
        tex_frame = ttk.LabelFrame(frame, text="Texture Mode", padding=10)
        tex_frame.pack(fill='x', padx=10, pady=10)
        ttk.Radiobutton(tex_frame, text="Auto-search textures",
                        variable=self.viewer_tex_mode, value="auto").grid(row=0, column=0, sticky='w')
        ttk.Radiobutton(tex_frame, text="Manual texture selection",
                        variable=self.viewer_tex_mode, value="manual").grid(row=0, column=1, sticky='w', padx=30)
        ttk.Radiobutton(tex_frame, text="No textures (gray model)",
                        variable=self.viewer_tex_mode, value="none").grid(row=0, column=2, sticky='w', padx=30)
        
        self.manual_btn = ttk.Button(tex_frame, text="Select TXD files...", command=self.select_manual_txd, state='disabled')
        self.manual_btn.grid(row=1, column=0, columnspan=3, pady=10, sticky='w')
        self.viewer_tex_mode.trace_add('write', self.on_viewer_mode_change)
        
        ttk.Button(frame, text="Choose DFF File", command=self.launch_viewer).pack(pady=30)
        ttk.Label(frame, text="Note: Viewer opens in a separate window for OpenGL stability",
                  foreground="gray", font=('Consolas', 9)).pack(pady=5)

    def on_viewer_mode_change(self, *args):
        mode = self.viewer_tex_mode.get()
        if mode == "manual":
            self.manual_btn.config(state='normal')
        else:
            self.manual_btn.config(state='disabled')
        self.manual_txd_paths = []

    def select_manual_txd(self):
        paths = filedialog.askopenfilenames(
            title="Select TXD files",
            filetypes=[("TXD Files", "*.txd"), ("All Files", "*.*")]
        )
        if paths:
            self.manual_txd_paths = list(paths)
            self.status_var.set(f"Selected {len(self.manual_txd_paths)} TXD files")

    def launch_viewer(self):
        dff_path = filedialog.askopenfilename(
            title="Select DFF file",
            filetypes=[("DFF Files", "*.dff")]
        )
        if not dff_path:
            return
        mode = self.viewer_tex_mode.get()
        
        if getattr(sys, 'frozen', False):
            args = [sys.executable, "--dff", dff_path, "--mode", mode]
        else:
            view_script = utils.resource_path(os.path.join("src", "view.py"))
            args = [sys.executable, view_script, "--dff", dff_path, "--mode", mode]
        
        if mode == "manual" and self.manual_txd_paths:
            for txd in self.manual_txd_paths:
                args.extend(["--txd", txd])
        subprocess.Popen(args)


class IMGEditWindow:
    def __init__(self, parent, img_path):
        self.parent = parent
        self.img_path = Path(img_path)
        self.temp_dir = Path("temp_edit") / self.img_path.stem
        self.original_hashes = {}
        self.modified = set()
        self.window = tk.Toplevel(parent)
        self.window.title(f"IMG Editor: {self.img_path.name}")
        self.window.geometry("700x500")
        icon_path = utils.resource_path(os.path.join("assets", "ico.ico"))
        if os.path.exists(icon_path):
            try:
                self.window.iconbitmap(icon_path)
            except:
                pass
        
        self.window.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.setup_ui()
        self.extract_to_temp()
        
    def setup_ui(self):
        list_frame = ttk.Frame(self.window)
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)
        self.file_list = tk.Listbox(list_frame, selectmode='extended')
        self.file_list.pack(side='left', fill='both', expand=True)
        self.file_list.bind('<Button-3>', self.on_right_click)
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.file_list.yview)
        scrollbar.pack(side='right', fill='y')
        self.file_list.config(yscrollcommand=scrollbar.set)
        btn_frame = ttk.Frame(self.window)
        btn_frame.pack(fill='x', padx=10, pady=(0, 10))
        ttk.Button(btn_frame, text="Replace with...", command=self.replace_selected).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Delete", command=self.delete_selected).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Add...", command=self.add_file).pack(side='left', padx=5)
        self.status_var = tk.StringVar(value="")
        ttk.Label(btn_frame, textvariable=self.status_var).pack(side='right')
        save_frame = ttk.Frame(self.window)
        save_frame.pack(fill='x', padx=10, pady=(0, 10))
        ttk.Button(save_frame, text="Save", command=self.on_save).pack(side='right', padx=5)
        ttk.Button(save_frame, text="Cancel", command=self.on_cancel).pack(side='right', padx=5)
    def extract_to_temp(self):
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        with IMGArchive(self.img_path) as arc:
            for entry in arc.entries:
                pos = entry.offset * SECTOR_SIZE
                size = entry.length * SECTOR_SIZE
                arc.file.seek(pos)
                data = arc.file.read(size)
                output_path = self.temp_dir / entry.name
                with open(output_path, 'wb') as f:
                    f.write(data)
                self.original_hashes[entry.name] = hashlib.md5(data).hexdigest()
        self.refresh_list()
    def refresh_list(self):
        self.file_list.delete(0, tk.END)
        for f in sorted(self.temp_dir.iterdir(), key=lambda x: x.name.lower()):
            marker = "*" if f.name in self.modified else ""
            self.file_list.insert(tk.END, f"{marker}{f.name}")
    def on_right_click(self, event):
        index = self.file_list.nearest(event.y)
        self.file_list.selection_clear(0, tk.END)
        self.file_list.selection_set(index)
        menu = tk.Menu(self.window, tearoff=0)
        menu.add_command(label="Replace with...", command=self.replace_selected)
        menu.add_command(label="Delete", command=self.delete_selected)
        menu.add_command(label="Export...", command=self.export_selected)
        menu.post(event.x_root, event.y_root)
    def replace_selected(self):
        selection = self.file_list.curselection()
        if not selection:
            return
        filename = self.file_list.get(selection[0]).lstrip("*")
        target_path = self.temp_dir / filename
        new_path = filedialog.askopenfilename(title="Select replacement file")
        if not new_path:
            return
        shutil.copy2(new_path, target_path)
        self.modified.add(filename)
        self.refresh_list()
        self.status_var.set(f"Replaced: {filename}")
    def delete_selected(self):
        selection = self.file_list.curselection()
        if not selection:
            return
        filename = self.file_list.get(selection[0]).lstrip("*")
        target_path = self.temp_dir / filename
        target_path.unlink()
        self.modified.add(filename)
        self.refresh_list()
        self.status_var.set(f"Deleted: {filename}")
    def add_file(self):
        paths = filedialog.askopenfilenames(title="Add files to IMG")
        if not paths:
            return
        for p in paths:
            shutil.copy2(p, self.temp_dir / Path(p).name)
            self.modified.add(Path(p).name)
        self.refresh_list()
        self.status_var.set(f"Added {len(paths)} file(s)")
    def export_selected(self):
        selection = self.file_list.curselection()
        if not selection:
            return
        filename = self.file_list.get(selection[0]).lstrip("*")
        src = self.temp_dir / filename
        dst = filedialog.asksaveasfilename(initialfile=filename, title="Export file")
        if dst:
            shutil.copy2(src, dst)
    def on_save(self):
        output_path = filedialog.asksaveasfilename(initialfile=self.img_path.name, defaultextension=".img", filetypes=[("IMG Files", "*.img")], title="Save IMG as")
        if not output_path:
            return
        try:
            self.status_var.set("Packing...")
            count = pack_img(str(self.temp_dir), output_path, lambda i, t, m: self.status_var.set(m))
            messagebox.showinfo("Success", f"Packed {count} files to {output_path}")
            self.cleanup()
            self.window.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to pack: {e}")
            self.status_var.set("Ready")
    def on_cancel(self):
        self.cleanup()
        self.window.destroy()
    def cleanup(self):
        if self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
            except:
                pass
    def __del__(self):
        self.cleanup()


if __name__ == "__main__":
    root = tk.Tk()
    try:
        style = ttk.Style()
        style.theme_use('clam')
    except:
        pass
    app = App(root)
    root.mainloop()