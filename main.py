from __future__ import annotations

import argparse
import json

from config import settings
from runtime.startup_runner import run_startup

def main() -> None:
    parser = argparse.ArgumentParser(description="LaunchMind multi-agent startup launch demo")
    parser.add_argument(
        "--idea",
        type=str,
        default=settings.demo_startup_idea,
        help="Startup idea to process through the multi-agent workflow",
    )
    args = parser.parse_args()
    summary = run_startup(args.idea)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
