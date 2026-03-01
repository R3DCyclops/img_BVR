import struct
import os
from pathlib import Path

SECTOR_SIZE = 2048
VERSION_2_HEADER = b'VER2'
NAME_SIZE = 23

class IMGEntry:
    def __init__(self, name: str, offset: int, length: int):
        self.name = name
        self.offset = offset
        self.length = length

class IMGArchive:
    def __init__(self, img_path: str):
        self.img_path = Path(img_path)
        self.entries = []
        self.file = None

    def open(self):
        self.file = open(self.img_path, 'rb')
        header = self.file.read(4)
        if header != VERSION_2_HEADER:
            raise ValueError(f"Invalid header: {header}. Expected VER2")
        count = struct.unpack('<I', self.file.read(4))[0]
        for _ in range(count):
            offset = struct.unpack('<I', self.file.read(4))[0]
            length = struct.unpack('<H', self.file.read(2))[0]
            self.file.read(2)
            name_bytes = self.file.read(NAME_SIZE + 1)
            null_pos = name_bytes.find(b'\x00')
            if null_pos != -1:
                name_bytes = name_bytes[:null_pos]
            name = name_bytes.decode('ascii', errors='ignore').strip()
            if name:
                self.entries.append(IMGEntry(name, offset, length))

    def extract(self, output_folder: str, progress_callback=None) -> int:
        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)
        extracted = 0
        total = len(self.entries)
        for i, entry in enumerate(self.entries):
            try:
                if progress_callback:
                    progress_callback(i, total, f"Extracting: {entry.name}")
                pos = entry.offset * SECTOR_SIZE
                size = entry.length * SECTOR_SIZE
                self.file.seek(pos)
                data = self.file.read(size)
                output_path = output_folder / entry.name
                with open(output_path, 'wb') as f:
                    f.write(data)
                extracted += 1
            except Exception as e:
                if progress_callback:
                    progress_callback(i, total, f"Error {entry.name}: {e}")
        return extracted

    def close(self):
        if self.file:
            self.file.close()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

def pack_img(source_folder: str, output_img: str, progress_callback=None) -> int:
    source_folder = Path(source_folder)
    files = sorted([f for f in source_folder.iterdir() if f.is_file()], key=lambda x: x.name.lower())
    if not files:
        return 0
    entry_size = 4 + 2 + 2 + (NAME_SIZE + 1)
    header_size = 4 + 4
    entry_table_size = len(files) * entry_size
    file_info = []
    current_sector = (header_size + entry_table_size + SECTOR_SIZE - 1) // SECTOR_SIZE
    for f in files:
        size = f.stat().st_size
        sectors = (size + SECTOR_SIZE - 1) // SECTOR_SIZE if size > 0 else 1
        file_info.append({'path': f, 'name': f.name[:NAME_SIZE], 'size': size, 'sectors': sectors, 'offset': current_sector})
        current_sector += sectors
    with open(output_img, 'wb') as img_file:
        img_file.write(VERSION_2_HEADER)
        img_file.write(struct.pack('<I', len(files)))
        for info in file_info:
            img_file.write(struct.pack('<I', info['offset']))
            img_file.write(struct.pack('<H', info['sectors']))
            img_file.write(b'\x00\x00')
            name_bytes = info['name'].encode('ascii', errors='ignore').ljust(NAME_SIZE + 1, b'\x00')
            img_file.write(name_bytes)
        current_pos = img_file.tell()
        if current_pos % SECTOR_SIZE != 0:
            img_file.write(b'\x00' * (SECTOR_SIZE - (current_pos % SECTOR_SIZE)))
        for i, info in enumerate(file_info):
            if progress_callback:
                progress_callback(i, len(files), f"Packing: {info['name']}")
            with open(info['path'], 'rb') as src:
                data = src.read()
            img_file.write(data)
            if len(data) % SECTOR_SIZE != 0:
                img_file.write(b'\x00' * (SECTOR_SIZE - (len(data) % SECTOR_SIZE)))
    return len(files)

def get_dff_list(img_path):
    archive = IMGArchive(img_path)
    archive.open()
    dff_files = [e.name for e in archive.entries if e.name.lower().endswith('.dff')]
    archive.close()
    return dff_files