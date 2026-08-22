"""Load the dash-named scripts as importable modules."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import pathlib
import sys

import pytest

BIN = pathlib.Path(__file__).resolve().parent.parent / "bin"


def _load(name: str, filename: str):
    path = BIN / filename
    # These scripts have no .py suffix, so the loader has to be named explicitly.
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_file_location(name, path, loader=loader)
    assert spec and spec.loader, path
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def polish_mod():
    return _load("dictate_polish", "dictate-polish.py")


@pytest.fixture(scope="session")
def watch_mod():
    return _load("dictate_watch", "dictate-watch")


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """No stray dictionary or recent.json from the developer's own machine."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("DICTATE_DICTIONARY", str(tmp_path / "dictionary"))
    monkeypatch.setenv("DICTATE_CONTEXT_FILE", str(tmp_path / "recent.json"))
    monkeypatch.delenv("DICTATE_CONTEXT", raising=False)
    monkeypatch.delenv("DICTATE_LLM_ALLOW_REMOTE", raising=False)
    return tmp_path
