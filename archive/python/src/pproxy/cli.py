import argparse
import asyncio
import logging
import sys
from typing import Sequence

from .engine import RuleEngine
from .loaders import BaseLoader, get_loader
from .matching import get_matcher

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080

logger = logging.getLogger("pproxy")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``pproxy`` command."""
    parser = argparse.ArgumentParser(
        prog="pproxy",
        description="URL pattern-based HTTP response interceptor.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    run = subcommands.add_parser("run", help="start the intercepting proxy")
    run.add_argument("rules", help="path to a .json, .yaml, or .yml rules file")
    run.add_argument(
        "-H", "--host", default=DEFAULT_HOST, help=f"listen host (default: {DEFAULT_HOST})"
    )
    run.add_argument(
        "-p",
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"listen port (default: {DEFAULT_PORT})",
    )
    run.add_argument(
        "-v", "--verbose", action="store_true", help="log every intercepted request"
    )

    check = subcommands.add_parser("check", help="validate a rules file and exit")
    check.add_argument("rules", help="path to a .json, .yaml, or .yml rules file")

    return parser


def load_engine(rules_path: str) -> tuple[RuleEngine, BaseLoader]:
    """Build an engine and loader for a rules file, and do the initial load.

    Args:
        rules_path: Path to the rules file.

    Returns:
        The engine and the loader that feeds it.

    Raises:
        ValueError: If the file extension has no registered loader.
    """
    engine = RuleEngine()
    loader = get_loader(rules_path, engine)
    loader.reload_if_changed()
    return engine, loader


def run_command(args: argparse.Namespace) -> int:
    """Start mitmproxy with the addon bound to the given rules file."""
    try:
        from .adapters.mitmproxy import MitmproxyAddon
    except ImportError:
        print(
            'mitmproxy is required to run the proxy. '
            'Install it with: pip install "pproxy[proxy]"',
            file=sys.stderr,
        )
        return 1

    from mitmproxy.options import Options
    from mitmproxy.tools.dump import DumpMaster

    try:
        engine, loader = load_engine(args.rules)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    if args.verbose:
        engine.add_hook(
            lambda url, rule: logger.info(
                f"[pproxy] {url} → {rule.name or rule.pattern}"
            )
        )

    async def serve() -> None:
        options = Options(listen_host=args.host, listen_port=args.port)
        master = DumpMaster(options, with_termlog=True, with_dumper=False)
        master.addons.add(MitmproxyAddon(engine, loader))
        await master.run()

    print(f"[pproxy] listening on {args.host}:{args.port} — rules: {args.rules}")
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass
    return 0


def check_command(args: argparse.Namespace) -> int:
    """Load a rules file, report what it contains, and validate each rule."""
    try:
        engine, _ = load_engine(args.rules)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    except Exception as e:
        print(f"failed to load {args.rules}: {e}", file=sys.stderr)
        return 1

    rules = engine.rules
    if not rules:
        print(f"no rules loaded from {args.rules}", file=sys.stderr)
        return 1

    failed = False
    for rule in rules:
        try:
            get_matcher(rule.matcher)
        except ValueError as e:
            print(f"  {rule.pattern}: {e}", file=sys.stderr)
            failed = True
            continue
        label = f" ({rule.name})" if rule.name else ""
        condition = f" graphql:{rule.graphql.describe()}" if rule.graphql else ""
        print(
            f"  {rule.matcher:<5} {rule.pattern}{condition}"
            f" → {rule.response.status_code}{label}"
        )

    if failed:
        return 1
    print(f"{len(rules)} rules OK")
    return 0


COMMANDS = {"run": run_command, "check": check_command}


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``pproxy`` console script."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
