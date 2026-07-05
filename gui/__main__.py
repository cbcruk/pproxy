import argparse

from gui.server import serve


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m gui",
        description="Web GUI for managing pproxy rules. Edits the JSON rules "
        "file that the proxy engine hot-reloads.",
    )
    parser.add_argument(
        "rules",
        nargs="?",
        default="rules.json",
        help="Path to the JSON rules file (default: rules.json)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Interface to bind (default: 127.0.0.1, local only)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="TCP port (default: 8765)",
    )
    args = parser.parse_args()
    serve(args.rules, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
