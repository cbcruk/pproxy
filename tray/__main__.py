import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tray",
        description="macOS menu bar app for managing the pproxy proxy: "
        "start/stop the proxy and open the rules file for editing.",
    )
    parser.add_argument(
        "--script",
        default="intercept.py",
        help="mitmproxy addon script that builds the addon (default: intercept.py)",
    )
    parser.add_argument(
        "--rules",
        default="rules.json",
        help="JSON rules file opened by “Edit rules…” (default: rules.json)",
    )
    parser.add_argument(
        "--command",
        default="mitmdump",
        help="proxy executable to run — mitmdump or mitmweb (default: mitmdump)",
    )
    args = parser.parse_args()

    try:
        from tray.app import PproxyTray
    except ImportError as e:
        sys.exit(
            f"the menu bar app requires rumps (macOS only): {e}\n"
            f"install it with: pip install 'pproxy[tray]'"
        )

    PproxyTray(script=args.script, rules=args.rules, command=args.command).run()


if __name__ == "__main__":
    main()
