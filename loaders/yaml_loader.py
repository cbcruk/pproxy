import logging
from pathlib import Path

import yaml

from loaders.base import BaseLoader
from engine import RuleEngine

logger = logging.getLogger("pproxy")


class YamlLoader(BaseLoader):
    """Loads rules from a YAML file with automatic hot-reload.

    Behaves identically to JsonLoader but parses YAML via
    ``yaml.safe_load``. If parsing fails, the last valid rules are kept.

    Args:
        path: Path to the YAML rules file.
        engine: The RuleEngine to load rules into.
    """

    def __init__(self, path: str | Path, engine: RuleEngine) -> None:
        self._path = Path(path)
        self._engine = engine
        self._mtime = 0.0
        self._last_valid: list[dict] = []

    def reload_if_changed(self) -> bool:
        try:
            mtime = self._path.stat().st_mtime
            if mtime == self._mtime:
                return False

            with open(self._path) as f:
                rules = yaml.safe_load(f)

            self._engine.load(rules)
            self._last_valid = rules
            self._mtime = mtime
            logger.info(f"[pproxy] rules reloaded: {len(rules)} rules")
            return True

        except FileNotFoundError:
            logger.warning(f"[pproxy] {self._path} not found")
        except yaml.YAMLError as e:
            logger.warning(
                f"[pproxy] YAML parse error (keeping last valid rules): {e}"
            )

        return False
