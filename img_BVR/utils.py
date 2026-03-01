import sys
import os

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def add_src_path():
    src_path = resource_path("src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)