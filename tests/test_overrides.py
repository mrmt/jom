from __future__ import annotations

from pathlib import Path

import pytest

from jom.overrides import load_overrides


def test_missing_file_returns_empty(tmp_path: Path):
    o = load_overrides(tmp_path / "nope.txt")
    assert o.dates == {}
    assert o.epoch is None


def test_parses_simple_entries(tmp_path: Path):
    p = tmp_path / "dates.txt"
    p.write_text(
        "# コメント\n"
        "\n"
        "a.mov,2025-03-14T10:30:00+09:00\n"
        "  b.mp4  ,  2025-04-01T15:00:00\n"
    )
    o = load_overrides(p)
    assert set(o.dates) == {"a.mov", "b.mp4"}
    assert o.dates["a.mov"].year == 2025 and o.dates["a.mov"].month == 3 and o.dates["a.mov"].day == 14
    assert o.dates["b.mp4"].month == 4
    assert o.epoch is None


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
    o = load_overrides(p)
    assert o.dates["a.mov"].year == 2025


def test_parses_epoch(tmp_path: Path):
    p = tmp_path / "dates.txt"
    p.write_text(
        "epoch,2025-03-14T00:00:00\n"
        "a.mov,2025-03-15T10:00:00\n"
    )
    o = load_overrides(p)
    assert o.epoch is not None
    assert o.epoch.year == 2025 and o.epoch.month == 3 and o.epoch.day == 14
    assert set(o.dates) == {"a.mov"}


def test_epoch_last_wins(tmp_path: Path):
    p = tmp_path / "dates.txt"
    p.write_text(
        "epoch,2020-01-01T00:00:00\n"
        "epoch,2025-06-15T00:00:00\n"
    )
    o = load_overrides(p)
    assert o.epoch is not None and o.epoch.year == 2025
