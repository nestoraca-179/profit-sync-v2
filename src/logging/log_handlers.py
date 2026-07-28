"""Custom logging handlers."""

from __future__ import annotations

import gzip
import shutil
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

class CompressedTimedRotatingFileHandler(TimedRotatingFileHandler):
    """Rotate log files daily and compress old files."""

    def doRollover(self) -> None:
        super().doRollover()
        candidates = sorted(Path(self.baseFilename).parent.glob(Path(self.baseFilename).name + ".*"))
        for candidate in candidates:
            if candidate.suffix == ".gz" or not candidate.is_file():
                continue
            compressed = candidate.with_suffix(candidate.suffix + ".gz")
            with candidate.open("rb") as source, gzip.open(compressed, "wb") as target:
                shutil.copyfileobj(source, target)
            candidate.unlink(missing_ok=True)