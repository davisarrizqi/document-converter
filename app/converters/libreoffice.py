"""Optional LibreOffice backend. Used when ``soffice`` is on PATH."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def libreoffice_convert(source: Path, target: Path, output_ext: str) -> bool:
    binary = shutil.which("soffice") or shutil.which("libreoffice")
    if not binary:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        try:
            completed = subprocess.run(
                [
                    binary,
                    "--headless",
                    "--norestore",
                    "--convert-to",
                    output_ext,
                    "--outdir",
                    tmp,
                    str(source),
                ],
                check=False,
                timeout=120,
                capture_output=True,
                env={**os.environ, "HOME": tmp},
            )
        except (OSError, subprocess.TimeoutExpired):
            logger.exception("LibreOffice conversion failed")
            return False
        produced = Path(tmp) / f"{source.stem}.{output_ext}"
        if completed.returncode != 0 or not produced.is_file() or produced.stat().st_size == 0:
            logger.error(
                "LibreOffice exited %s: %s",
                completed.returncode,
                completed.stderr.decode("utf-8", errors="replace")[:500],
            )
            return False
        target.write_bytes(produced.read_bytes())
        return True
