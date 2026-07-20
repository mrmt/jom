"""正規化済み動画をconcat demuxerで連結"""
from __future__ import annotations

import subprocess
from pathlib import Path


def concat(files: list[Path], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    listfile = out_path.with_suffix(".concat.txt")
    lines = [f"file '{p.resolve()}'\n" for p in files]
    listfile.write_text("".join(lines))
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "concat", "-safe", "0",
        "-i", str(listfile),
        "-c", "copy",
        "-movflags", "+faststart",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    listfile.unlink(missing_ok=True)
    return out_path
