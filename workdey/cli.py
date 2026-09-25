"""python -m workdey.cli ingest|match|ping"""

from __future__ import annotations

import json
import sys

from workdey import create_app
from workdey.pipeline import run_due_watches
from workdey.workers import scheduler_status


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    cmd = args[0] if args else "help"
    app = create_app()
    with app.app_context():
        if cmd == "ingest":
            print("Global ingest is deprecated; jobs are now fetched per user.")
            return 1
        if cmd == "match":
            print(json.dumps(run_due_watches(limit=100), indent=2))
            return 0
        if cmd == "ping":
            print(json.dumps(scheduler_status(), indent=2))
            return 0
        print("usage: python -m workdey.cli ingest [source] | match | ping")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
