"""One-command demo entrypoint."""

from __future__ import annotations

import json
import os

from config import settings
from pipeline.orchestrator import run_pipeline


def main() -> None:
    os.environ.setdefault("INGESTION_FIXTURE_MODE", "true")
    settings.ingestion_fixture_mode = True
    result = run_pipeline()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
