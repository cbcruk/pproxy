import json
import logging
from pathlib import Path

from loaders.base import BaseLoader
from engine import RuleEngine

logger = logging.getLogger("pproxy")


class JsonLoader(BaseLoader):
    """Loads rules from a JSON file with automatic hot-reload.

    On each ``reload_if_changed`` call, checks the file's modification
    time. If the file changed, it re-parses and reloads rules into the
    engine. If parsing fails, the last valid rules are kept.

    Args:
        path: Path to the JSON rules file.
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
                rules = json.load(f)

            self._engine.load(rules)
            self._last_valid = rules
            self._mtime = mtime
            logger.info(f"[pproxy] rules reloaded: {len(rules)} rules")
            return True

        except FileNotFoundError:
            logger.warning(f"[pproxy] {self._path} not found")
        except json.JSONDecodeError as e:
            logger.warning(
                f"[pproxy] JSON parse error (keeping last valid rules): {e}"
            )

        return False
