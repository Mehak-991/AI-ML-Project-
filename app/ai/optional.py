"""Lazy imports of optional packages with actionable error messages."""

import importlib
import importlib.metadata
import importlib.util
import sys
from types import ModuleType

from app.core.exceptions import OptionalDependencyMissingError

# Top-level module -> pyproject extra that provides it.
EXTRA_FOR_MODULE: dict[str, str] = {
    "torch": "torch",
    "torchvision": "torch",
    "transformers": "nlp",
    "sentence_transformers": "nlp",
    "datasets": "nlp",
    "evaluate": "nlp",
    "openai": "llm",
    "tiktoken": "llm",
    "langgraph": "agents",
    "langchain_core": "agents",
    "langchain_text_splitters": "agents",
    "llama_index": "rag",
}

TORCH_HINT = (
    "Install PyTorch for your hardware first, e.g. CPU-only: "
    "pip install torch --index-url https://download.pytorch.org/whl/cpu"
)


# Top-level module -> pip distribution that provides it.
DISTRIBUTION_FOR_MODULE: dict[str, str] = {
    "torch": "torch",
    "torchvision": "torchvision",
    "transformers": "transformers",
    "sentence_transformers": "sentence-transformers",
    "datasets": "datasets",
    "evaluate": "evaluate",
    "openai": "openai",
    "tiktoken": "tiktoken",
    "langgraph": "langgraph",
    "langchain_core": "langchain-core",
    "langchain_text_splitters": "langchain-text-splitters",
    "llama_index": "llama-index-core",
}


def _distribution_installed(module: str) -> bool | None:
    """True/False for known packages; None if we don't know the distribution name."""
    name = DISTRIBUTION_FOR_MODULE.get(module.split(".")[0])
    if name is None:
        return None
    try:
        importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


def is_available(module: str) -> bool:
    """Whether `module` can be imported from an installed package.

    Known packages are checked via their installed distribution: a plain folder with
    the same name (e.g. this project's `datasets/` data directory) would otherwise be
    found as a namespace package, while some real packages (e.g. langgraph 1.x) *are*
    namespace packages.
    """
    installed = _distribution_installed(module)
    if installed is False:
        return False
    try:
        spec = importlib.util.find_spec(module)
    except (ImportError, ValueError):
        return False
    if spec is None:
        return False
    return installed is True or spec.origin is not None


def install_hint(module: str) -> str:
    root = module.split(".")[0]
    if root in ("torch", "torchvision"):
        return TORCH_HINT
    return f'pip install -e ".[{EXTRA_FOR_MODULE.get(root, "ai")}]"'


def require(module: str, purpose: str) -> ModuleType:
    """Import `module` or raise a 503 error explaining how to install it."""
    try:
        # Already-imported modules (including test stubs) are trusted as-is.
        if module not in sys.modules and _distribution_installed(module) is False:
            raise ImportError(f"distribution for {module} is not installed")
        imported = importlib.import_module(module)
        spec = getattr(imported, "__spec__", None)
        unknown_namespace = (
            spec is not None
            and spec.origin is None
            and spec.submodule_search_locations
            and _distribution_installed(module) is None
        )
        if unknown_namespace:
            raise ImportError(f"{module} resolved to a namespace package, not the library")
        return imported
    except ImportError:
        hint = install_hint(module)
        raise OptionalDependencyMissingError(
            f"{purpose} requires the optional package '{module}'. {hint}",
            details={"package": module, "install": hint},
        ) from None
