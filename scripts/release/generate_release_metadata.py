from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate release metadata manifest.")
    parser.add_argument("--sha", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--backend-image", required=True)
    parser.add_argument("--engine-image", required=True)
    parser.add_argument("--frontend-image", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git": {
            "sha": args.sha,
            "branch": args.branch,
        },
        "images": {
            "backend": args.backend_image,
            "engine": args.engine_image,
            "frontend": args.frontend_image,
        },
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

