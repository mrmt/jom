from __future__ import annotations

from pathlib import Path

import pytest

from jom.overrides import load_overrides


def test_missing_file_returns_empty(tmp_path: Path):
    assert load_overrides(tmp_path / "nope.txt") == {}


def test_parses_simple_entries(tmp_path: Path):
    p = tmp_path / "dates.txt"
    p.write_text(
        "# コメント\n"
        "\n"
        "a.mov,2025-03-14T10:30:00+09:00\n"
        "  b.mp4  ,  2025-04-01T15:00:00\n"
    )
    d = load_overrides(p)
    assert set(d) == {"a.mov", "b.mp4"}
    assert d["a.mov"].year == 2025 and d["a.mov"].month == 3 and d["a.mov"].day == 14
    assert d["b.mp4"].month == 4


def test_rejects_bad_line(tmp_path: Path):
    p = tmp_path / "dates.txt"
    p.write_text("no_comma_here\n")
    with pytest.raises(ValueError, match="形式でない"):
        load_overrides(p)


def test_rejects_bad_datetime(tmp_path: Path):
    p = tmp_path / "dates.txt"
    p.write_text("a.mov,not-a-date\n")
    with pytest.raises(ValueError, match="パースできない"):
        load_overrides(p)


def test_last_wins_on_duplicate(tmp_path: Path):
    p = tmp_path / "dates.txt"
    p.write_text(
        "a.mov,2020-01-01T00:00:00\n"
        "a.mov,2025-06-15T12:00:00\n"
    )
    d = load_overrides(p)
    assert d["a.mov"].year == 2025
