"""Phase 33 · ``python -m app.release`` entry point.

Two subcommands, both stdlib-only and both read-only apart from the single ZIP
the packager is asked to write:

    python -m app.release audit   --manifest/--dir/--zip PATH
    python -m app.release package --source dist --output release/…zip

``release/build-release.sh`` calls this dispatcher rather than the submodules
directly, because running a submodule that the package ``__init__`` has already
imported makes :mod:`runpy` emit a warning about double import.
"""

from __future__ import annotations

import sys

from . import audit as audit_module
from . import package as package_module

USAGE = (
    "usage: python -m app.release {audit|package} [options]\n"
    "  audit   --manifest PATH | --dir PATH | --zip PATH\n"
    "  package --source DIR --output ZIP\n"
)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        print(USAGE)
        return 0 if args else 2
    command, rest = args[0], args[1:]
    if command == "audit":
        return audit_module.main(rest)
    if command == "package":
        return package_module.main(rest)
    print(f"unknown subcommand: {command}\n\n{USAGE}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
