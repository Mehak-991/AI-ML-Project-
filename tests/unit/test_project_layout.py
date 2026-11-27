"""The setup guide's layout (app.models, app.repository, `python main.py`) maps onto the real code."""

import importlib
import json
from pathlib import Path

import app.database.models as orm
import app.models as models
import app.repositories.employees as employee_repo
import app.repository as repository

ROOT = Path(__file__).resolve().parents[2]


def test_app_models_reexports_the_same_orm_classes() -> None:
    for name in models.__all__:
        assert getattr(models, name) is getattr(orm, name), name
    assert set(models.__all__) == set(orm.__all__)


def test_app_repository_reexports_the_same_classes() -> None:
    assert repository.EmployeeRepository is employee_repo.EmployeeRepository
    for name in repository.__all__:
        assert getattr(repository, name).__name__ == name


def test_root_main_runs_the_app_with_uvicorn(monkeypatch) -> None:
    calls = {}
    module = importlib.import_module("main")
    monkeypatch.setattr(module.uvicorn, "run", lambda target, **kw: calls.update(target=target, **kw))
    monkeypatch.setenv("PORT", "8123")
    module.main()
    assert calls["target"] == "app.main:app"
    assert calls["port"] == 8123
    assert calls["host"] == "127.0.0.1"  # never all interfaces by default


def test_welcome_endpoint(client) -> None:
    body = client.get("/").json()
    assert body["message"].startswith("Welcome to")
    assert body["docs_url"] == "/docs"


def test_guide_folders_exist() -> None:
    for folder in ("app/api", "app/models", "app/services", "app/repository", "app/database",
                   "app/schemas", "app/utils", "datasets", "notebooks", "uploads",
                   "trained_models", "tests", "logs"):
        assert (ROOT / folder).is_dir(), folder


def test_starter_notebook_is_valid_and_has_no_outputs() -> None:
    nb = json.loads((ROOT / "notebooks" / "01_explore_dataset.ipynb").read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4
    assert all(not c.get("outputs") for c in nb["cells"] if c["cell_type"] == "code")
