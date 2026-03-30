from abc import ABC, abstractmethod


class BaseLoader(ABC):
    """Abstract base class for all rule loaders.

    Loaders watch an external source (file, API, etc.) and reload
    rules into the engine when the source changes.
    """

    @abstractmethod
    def reload_if_changed(self) -> bool:
        """Check if the source has changed and reload rules if so.

        Returns:
            True if rules were reloaded, False if unchanged or on error.
        """
        ...
