"""The video-studio engine's own Python modules, used in-process where the app needs the same logic as `vs`
(lesson matching and checks), so the two can never disagree."""
import importlib
import sys
from functools import lru_cache

from .config import get_settings


@lru_cache
def tools(name: str):
    path = str(get_settings().vs_bin.parent.parent / "tools")
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module(name)


def vs_lessons():
    return tools("lessons")
