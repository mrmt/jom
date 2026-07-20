"""動画メタデータ抽出 (ffprobe)"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class VideoMeta:
    path: Path
    width: int
    height: int
    duration: float
    vcodec: str
    creation_time: datetime  # ローカル時刻

    @property
    def date_label(self) -> str:
        return self.creation_time.strftime("%Y-%m-%d %H:%M")

    @property
    def pixels(self) -> int:
        return self.width * self.height


def probe(path: Path) -> VideoMeta:
    """ffprobeでメタデータ抽出。date → creation_time → mtime の順にフォールバック

    `date` はタイムゾーン付き (iPhone等が撮影時ローカル時刻で書き込む) のため優先。
    `creation_time` は通常UTC。両方無ければファイルのmtimeを使う。
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration:format_tags=date,creation_time",
        "-show_entries", "stream=codec_type,codec_name,width,height",
        "-of", "json",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)

    v_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
        None,
    )
    if v_stream is None:
        # codec_type が返らないケースもあるので width/height を持つ最初のを video とみなす
        v_stream = next(
            (s for s in data.get("streams", []) if s.get("width")),
            None,
        )
    if v_stream is None:
        raise RuntimeError(f"映像ストリーム不明: {path}")

    fmt = data.get("format", {})
    duration = float(fmt.get("duration", 0.0))
    tags = fmt.get("tags", {})

    creation = _parse_datetime_tag(tags.get("date")) \
        or _parse_datetime_tag(tags.get("creation_time"))
    if creation is None:
        mtime = path.stat().st_mtime
        creation = datetime.fromtimestamp(mtime)

    return VideoMeta(
        path=path,
        width=int(v_stream["width"]),
        height=int(v_stream["height"]),
        duration=duration,
        vcodec=v_stream.get("codec_name", ""),
        creation_time=creation,
    )


def _parse_datetime_tag(s: str | None) -> datetime | None:
    """ISO 8601風の日時文字列をローカルナイーブdatetimeに変換

    受け付ける形式例:
      - 2026-07-16T13:57:05.000000Z         (UTC)
      - 2026-07-16T19:47:38+09:00           (TZ付き)
      - 2026-07-19T16:11:59+0900            (TZ付き、コロンなし)
    """
    if not s:
        return None
    # +0900 → +09:00 (fromisoformatはPy3.11以降なら不要だが安全側)
    normalized = s.replace("Z", "+00:00")
    # 末尾が ±HHMM の場合コロンを挿入
    if len(normalized) >= 5 and normalized[-5] in "+-" and normalized[-3] != ":":
        normalized = normalized[:-2] + ":" + normalized[-2:]
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone().replace(tzinfo=None)
