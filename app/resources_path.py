# app/resources_path.py
import sys
from pathlib import Path

def resource(*parts) -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parents[1]
    return base.joinpath(*parts)