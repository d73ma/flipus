"""Cek route sync terdaftar di FastAPI."""
import os
import sys
sys.path.insert(0, os.getcwd())
from app.api.v1 import sync
print("SYNC ROUTES:")
for r in sync.router.routes:
    print(" {} {}".format(getattr(r, "methods", "?"), r.path))