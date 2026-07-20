"""dates.txt による撮影日時の手動オーバーライド

書式:
    # コメント行 (先頭が # の行は無視)
    filename.mov,2025-03-14T10:30:00+09:00
    IMG_2566.MOV,2025-04-01T15:00:00
    # 空行も無視

- 区切り文字はカンマ。ファイル名にカンマが含まれる場合は非対応
- 日時は ISO 8601。タイムゾーン付き推奨。無ければローカル時刻扱い
- ファイル名は assets/ 内のベース名 (パス無し)
- 大文字小文字は区別する
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .metadata import _parse_datetime_tag


def load_overrides(path: Path) -> dict[str, datetime]:
    """dates.txtを読んで {basename: datetime} を返す。ファイル無しなら空dict"""
    if not path.exists():
        return {}
    result: dict[str, datetime] = {}
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # ISO日時にカンマは含まれないのでrsplitで安全に分離
        if "," not in line:
            raise ValueError(f"{path}:{lineno} '<filename>,<iso-datetime>' 形式でない: {raw!r}")
        name, iso = (s.strip() for s in line.rsplit(",", 1))
        dt = _parse_datetime_tag(iso)
        if dt is None:
            raise ValueError(f"{path}:{lineno} 日時をパースできない: {iso!r}")
        result[name] = dt
    return result
