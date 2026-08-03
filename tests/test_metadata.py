from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

from jom.metadata import VideoMeta, probe


def test_probe_reads_resolution_and_duration(red: Path):
    m = probe(red)
    assert m.width == 320
    assert m.height == 240
    assert 0.9 <= m.duration <= 1.2
    assert m.vcodec == "h264"


def test_probe_uses_creation_time_metadata(red: Path):
    m = probe(red)
    # 合成時に 2025-01-15T12:00:00Z を焼き込んでいる
    assert m.creation_time.year == 2025
    assert m.creation_time.month == 1
    assert m.creation_time.day in (14, 15, 16)  # ローカルTZ変換で日跨ぎ許容


def test_probe_prefers_date_tag_over_creation_time(tmp_path: Path):
    """dateタグとcreation_timeが両方あればdateを採用"""
    src = tmp_path / "both.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-t", "0.5", "-i", "color=c=gray:s=160x120:r=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
        "-metadata", "creation_time=2020-01-01T00:00:00.000000Z",
        "-metadata", "date=2023-06-15T10:30:00+09:00",
        str(src),
    ], check=True)
    m = probe(src)
    assert m.creation_time.year == 2023
    assert m.creation_time.month == 6
    assert m.creation_time.day == 15


def test_probe_falls_back_to_mtime_when_metadata_missing(tmp_path: Path):
    src = tmp_path / "nometa.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "color=c=gray:s=160x120:d=0.5:r=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
        str(src),
    ], check=True)
    target = datetime(2024, 6, 1, 10, 0, 0).timestamp()
    os.utime(src, (target, target))
    m = probe(src)
    assert m.creation_time.year == 2024
    assert m.creation_time.month == 6


def test_date_label_format(red: Path):
    m = probe(red)
    assert m.date_label == m.creation_time.strftime("%Y-%m-%d %H:%M")


def _meta(**kw) -> VideoMeta:
    defaults = dict(path=Path("x.mp4"), width=1, height=1, duration=0.0, vcodec="h264",
                    creation_time=datetime(2025, 1, 1, 0, 0))
    defaults.update(kw)
    return VideoMeta(**defaults)


def test_date_label_with_epoch_appends_day():
    m = _meta(creation_time=datetime(2025, 3, 20, 10, 30), epoch=datetime(2025, 3, 14, 0, 0))
    # 3/14=day1, 3/15=day2, ..., 3/20=day7
    assert m.date_label == "2025-03-20 10:30 (day 7)"


def test_date_label_epoch_same_day_is_day1():
    m = _meta(creation_time=datetime(2025, 3, 14, 23, 59), epoch=datetime(2025, 3, 14, 0, 0))
    assert m.date_label == "2025-03-14 23:59 (day 1)"


def test_date_label_without_epoch_omits_day():
    m = _meta(creation_time=datetime(2025, 3, 14, 10, 30))
    assert m.date_label == "2025-03-14 10:30"


def test_pixels_computes_area(red: Path):
    m = probe(red)
    assert m.pixels == 320 * 240
