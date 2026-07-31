"""Entry point for `python -m decomp_workbench`.

The console script installed by `[project.scripts]` is the supported way in,
but `python -m` is what people reach for when the script is not on PATH -- a
checkout used with `PYTHONPATH=src`, a virtualenv whose `bin/` is not active, a
CI step that installed with `--target`. Without this module that invocation
fails with "No module named decomp_workbench.__main__", which reads like a
broken install rather than a missing convenience.
"""

from __future__ import annotations

from .cli import main

#: Re-exported so the delegation is a checkable fact and not just an import.
__all__ = ["main"]

if __name__ == "__main__":
    raise SystemExit(main())
