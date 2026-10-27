"""Lazy imports of optional packages with actionable error messages."""

import importlib
import importlib.util
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


def is_available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def install_hint(module: str) -> str:
    root = module.split(".")[0]
    if root in ("torch", "torchvision"):
        return TORCH_HINT
    return f'pip install -e ".[{EXTRA_FOR_MODULE.get(root, "ai")}]"'


def require(module: str, purpose: str) -> ModuleType:
    """Import `module` or raise a 503 error explaining how to install it."""
    try:
        return importlib.import_module(module)
    except ImportError:
        hint = install_hint(module)
        raise OptionalDependencyMissingError(
            f"{purpose} requires the optional package '{module}'. {hint}",
            details={"package": module, "install": hint},
        ) from None
