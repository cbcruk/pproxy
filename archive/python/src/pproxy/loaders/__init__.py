from pathlib import Path

from .base import BaseLoader
from .json_loader import JsonLoader
from .yaml_loader import YamlLoader
from ..engine import RuleEngine

LOADERS: dict[str, type[BaseLoader]] = {
    ".json": JsonLoader,
    ".yaml": YamlLoader,
    ".yml": YamlLoader,
}
"""Rules file extension to loader class. Add new formats here."""


def get_loader(path: str | Path, engine: RuleEngine) -> BaseLoader:
    """Pick a loader for a rules file based on its extension.

    Args:
        path: Path to the rules file.
        engine: The RuleEngine the loader will load rules into.

    Returns:
        A loader bound to the path and engine.

    Raises:
        ValueError: If the extension has no registered loader.
    """
    suffix = Path(path).suffix.lower()
    if suffix not in LOADERS:
        raise ValueError(
            f"Unsupported rules file {str(path)!r}. Choose from {list(LOADERS)}"
        )
    return LOADERS[suffix](path, engine)


__all__ = ["BaseLoader", "JsonLoader", "YamlLoader", "LOADERS", "get_loader"]
