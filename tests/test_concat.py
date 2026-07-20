from __future__ import annotations

from pathlib import Path

from jom.concat import concat
from jom.metadata import probe
from jom.normalize import normalize


def test_concat_sums_durations(tmp_path: Path, red: Path, green: Path):
    """concat demuxerは正規化済み(同一params)を前提。durationが合算される"""
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    normalize(probe(red), a)
    normalize(probe(green), b)
    out = tmp_path / "joined.mp4"
    concat([a, b], out)
    m = probe(out)
    expected = probe(a).duration + probe(b).duration
    assert abs(m.duration - expected) < 0.5


def test_concat_removes_listfile(tmp_path: Path, red: Path):
    a = tmp_path / "a.mp4"
    normalize(probe(red), a)
    out = tmp_path / "joined.mp4"
    concat([a], out)
    assert not out.with_suffix(".concat.txt").exists()
