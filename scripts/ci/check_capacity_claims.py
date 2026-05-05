#!/usr/bin/env python3
"""Compatibility wrapper for the broader launch-claims guard."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def main() -> int:
    script = Path(__file__).with_name("check_launch_claims.py")
    spec = importlib.util.spec_from_file_location("check_launch_claims", script)
    if spec is None or spec.loader is None:
        print("Unable to load check_launch_claims.py", file=sys.stderr)
        return 2
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return int(module.main(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
