import shlex
import subprocess
from pathlib import Path


class EditorError(RuntimeError):
    """Raised when the configured editor cannot be launched.

    The message is safe to show to the user (e.g. in an alert).
    """


def open_in_editor(path: str | Path, editor_command: str) -> None:
    """Open ``path`` in the editor named by ``editor_command``.

    The command is split shell-style, so extra flags are supported
    (e.g. ``"code -n"`` or ``"subl -w"``); the file path is appended as
    the final argument. The editor is launched detached — this returns
    immediately without waiting for the editor to close.

    Args:
        path: The file to open.
        editor_command: The editor command, e.g. ``"code"``.

    Raises:
        EditorError: If the command is blank or the editor is not found.
    """
    parts = shlex.split(editor_command)
    if not parts:
        raise EditorError("no editor configured")
    try:
        subprocess.Popen([*parts, str(path)])
    except FileNotFoundError:
        raise EditorError(
            f"editor {parts[0]!r} not found — set a different editor "
            f"(PPROXY_EDITOR or the app's “Set editor…” menu)"
        )
    except OSError as e:
        raise EditorError(f"could not launch editor {parts[0]!r}: {e}")
