import importlib
from pathlib import Path

import pytest

from app import config


@pytest.fixture
def reload_config(monkeypatch, tmp_path):
    def reload(**env):
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "custom" / "nested"))
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return importlib.reload(config)

    yield reload
    monkeypatch.undo()
    importlib.reload(config)


def test_paths_derive_from_data_dir_and_folder_is_created(reload_config, tmp_path):
    cfg = reload_config()
    assert cfg.DB_PATH == tmp_path / "custom" / "nested" / "app.db"
    assert cfg.PDF_DIR == tmp_path / "custom" / "nested" / "pdfs"  # existing libraries live at these paths
    assert cfg.PDF_DIR.is_dir()


def test_default_data_directory_is_data(monkeypatch, tmp_path, reload_config):
    reload_config()  # registers the teardown that restores the module
    monkeypatch.chdir(tmp_path)  # the default is relative, so this keeps it away from any real data/
    monkeypatch.delenv("DATA_DIR")
    assert importlib.reload(config).DATA_DIR == Path("data")
    assert (tmp_path / "data" / "pdfs").is_dir()


def test_primary_model_comes_from_environment(reload_config):
    assert reload_config(GEMINI_MODEL="my-model").GEMINI_MODEL == "my-model"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("a,b", ["a", "b"]),
        (" a , b ", ["a", "b"]),
        ("a,,b,", ["a", "b"]),
        ("", []),
    ],
)
def test_fallback_model_list_parsing(reload_config, raw, expected):
    assert reload_config(GEMINI_FALLBACK_MODELS=raw).GEMINI_FALLBACK_MODELS == expected
