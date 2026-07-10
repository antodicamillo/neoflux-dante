"""Audit log append-only. Ogni decisione ed esecuzione di tool viene registrata."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

_LOG = Path(__file__).resolve().parent.parent / "logs" / "audit.log"


def audit(event: str, **fields) -> None:
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "event": event,
        **fields,
    }
    with open(_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
