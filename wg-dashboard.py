#!/usr/bin/env python3
"""
WireGuard Web GUI Dashboard
Main executable entrypoint.
Loads modular components from src/ (logic, db, templates, and static assets).
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.app import main

if __name__ == "__main__":
    main()
