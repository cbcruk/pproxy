import json
from pathlib import Path

from models import Rule


class RuleValidationError(ValueError):
    """Raised when a rule dict is missing required keys or malformed.

    The message is safe to surface directly to the GUI client.
    """


class RuleStore:
    """CRUD access to the JSON rules file that the engine hot-reloads.

    This is the bridge between the GUI and the engine: the GUI edits
    rules through this store, the store writes them to disk, and the
    running proxy's ``JsonLoader`` reloads them automatically on the
    next request. The store therefore never imports the engine.

    Rules are addressed by their position (index) in the file, which is
    also the order the engine evaluates them in (first match wins).

    Args:
        path: Path to the JSON rules file. Created on first write if absent.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    # ── Reading ────────────────────────────────────────────

    def load(self) -> list[dict]:
        """Read all rules from the file.

        Returns:
            The list of rule dicts, or an empty list if the file does
            not exist yet.

        Raises:
            RuleValidationError: If the file exists but is not valid JSON
                or does not contain a JSON array.
        """
        if not self._path.exists():
            return []
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise RuleValidationError(f"rules file is not valid JSON: {e}")
        if not isinstance(data, list):
            raise RuleValidationError("rules file must contain a JSON array")
        return data

    # ── Writing ────────────────────────────────────────────

    def save(self, rules: list[dict]) -> list[dict]:
        """Validate and write the full list of rules to the file.

        Every rule is validated before anything is written, so a single
        bad rule leaves the file untouched.

        Args:
            rules: The complete list of rule dicts to persist.

        Returns:
            The saved rules.

        Raises:
            RuleValidationError: If any rule is invalid.
        """
        for i, rule in enumerate(rules):
            self._validate(rule, i)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
            f.write("\n")
        return rules

    def add(self, rule: dict) -> dict:
        """Append a single rule to the end of the file.

        Args:
            rule: The rule dict to add.

        Returns:
            The added rule.

        Raises:
            RuleValidationError: If the rule is invalid.
        """
        rules = self.load()
        rules.append(rule)
        self.save(rules)
        return rule

    def update(self, index: int, rule: dict) -> dict:
        """Replace the rule at ``index`` with a new rule dict.

        Args:
            index: Zero-based position of the rule to replace.
            rule: The new rule dict.

        Returns:
            The updated rule.

        Raises:
            IndexError: If ``index`` is out of range.
            RuleValidationError: If the rule is invalid.
        """
        rules = self.load()
        self._check_index(rules, index)
        rules[index] = rule
        self.save(rules)
        return rule

    def delete(self, index: int) -> dict:
        """Remove the rule at ``index``.

        Args:
            index: Zero-based position of the rule to remove.

        Returns:
            The removed rule.

        Raises:
            IndexError: If ``index`` is out of range.
        """
        rules = self.load()
        self._check_index(rules, index)
        removed = rules.pop(index)
        self.save(rules)
        return removed

    def move(self, index: int, to: int) -> list[dict]:
        """Move the rule at ``index`` to a new position ``to``.

        Rule order is significant (first match wins), so reordering is a
        real edit. ``to`` is clamped to the valid range.

        Args:
            index: Current position of the rule.
            to: Target position.

        Returns:
            The reordered list of rules.

        Raises:
            IndexError: If ``index`` is out of range.
        """
        rules = self.load()
        self._check_index(rules, index)
        rule = rules.pop(index)
        to = max(0, min(to, len(rules)))
        rules.insert(to, rule)
        self.save(rules)
        return rules

    # ── Helpers ────────────────────────────────────────────

    @staticmethod
    def _check_index(rules: list, index: int) -> None:
        if not 0 <= index < len(rules):
            raise IndexError(f"rule index {index} out of range (0..{len(rules) - 1})")

    @staticmethod
    def _validate(rule: dict, index: int) -> None:
        if not isinstance(rule, dict):
            raise RuleValidationError(f"rule #{index} must be an object")
        try:
            Rule.from_dict(rule)
        except KeyError as e:
            raise RuleValidationError(f"rule #{index} is missing required key {e}")
        except (TypeError, ValueError) as e:
            raise RuleValidationError(f"rule #{index} is invalid: {e}")
