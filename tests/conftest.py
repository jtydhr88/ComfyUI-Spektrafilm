import importlib.util
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent
COMFYUI = PACKAGE.parent.parent
sys.path.insert(0, str(COMFYUI))


def _load_package():
    spec = importlib.util.spec_from_file_location("comfyui_spektrafilm", PACKAGE / "__init__.py",
                                                  submodule_search_locations=[str(PACKAGE)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_load_package()


@pytest.fixture
def folders(tmp_path, monkeypatch):
    import folder_paths

    monkeypatch.setattr(folder_paths, "output_directory", str(tmp_path / "output"))
    monkeypatch.setattr(folder_paths, "input_directory", str(tmp_path / "input"))
    monkeypatch.setattr(folder_paths, "temp_directory", str(tmp_path / "temp"))
    for name in ("output", "input", "temp"):
        (tmp_path / name).mkdir()
    return tmp_path
