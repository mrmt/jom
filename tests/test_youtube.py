from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

from jom import youtube
from jom.main import upload_cli
from jom.youtube import (
    UploadError,
    UploadRequest,
    build_body,
    default_title,
    load_credentials,
    parse_tags,
    resolve_description,
    watch_url,
)


def _req(**kw) -> UploadRequest:
    defaults = dict(path=Path("output/jom.mp4"), title="タイトル")
    defaults.update(kw)
    return UploadRequest(**defaults)


def test_parse_tags_splits_and_strips():
    assert parse_tags(" 旅行 , 2025 ,,家族 ") == ["旅行", "2025", "家族"]


def test_parse_tags_empty_gives_empty_list():
    assert parse_tags("") == []
    assert parse_tags(None) == []


def test_default_title_without_dates_is_stem():
    assert default_title(Path("output/jom.mp4")) == "jom"


def test_default_title_with_date_range():
    dates = [datetime(2025, 3, 20, 10, 0), datetime(2025, 3, 14, 9, 0)]
    assert default_title(Path("output/jom.mp4"), dates) == "jom 2025-03-14〜2025-03-20"


def test_default_title_single_day_omits_range():
    dates = [datetime(2025, 3, 14, 9, 0), datetime(2025, 3, 14, 23, 0)]
    assert default_title(Path("output/jom.mp4"), dates) == "jom 2025-03-14"


def test_resolve_description_prefers_file(tmp_path: Path):
    f = tmp_path / "desc.txt"
    f.write_text("ファイルの説明")
    assert resolve_description("インラインの説明", f) == "ファイルの説明"
    assert resolve_description("インラインの説明", None) == "インラインの説明"
    assert resolve_description(None, None) == ""


def test_build_body_maps_fields():
    body = build_body(_req(description="説明", tags=["a", "b"], privacy="unlisted",
                           category_id="19", made_for_kids=True))
    assert body["snippet"] == {
        "title": "タイトル",
        "description": "説明",
        "tags": ["a", "b"],
        "categoryId": "19",
    }
    assert body["status"] == {
        "privacyStatus": "unlisted",
        "selfDeclaredMadeForKids": True,
    }


def test_build_body_defaults_to_private():
    assert build_body(_req())["status"]["privacyStatus"] == "private"


def test_build_body_rejects_unknown_privacy():
    with pytest.raises(ValueError, match="privacy"):
        build_body(_req(privacy="secret"))


def test_build_body_rejects_empty_title():
    with pytest.raises(ValueError, match="タイトル"):
        build_body(_req(title="   "))


def test_watch_url():
    assert watch_url("abc123") == "https://www.youtube.com/watch?v=abc123"


def test_upload_missing_file_raises(tmp_path: Path):
    with pytest.raises(UploadError, match="動画が無い"):
        youtube.upload(_req(path=tmp_path / "nope.mp4"))


def test_load_credentials_without_client_secrets_raises(tmp_path: Path):
    with pytest.raises(UploadError, match="クライアントシークレット"):
        load_credentials(tmp_path / "client_secret.json", tmp_path / "token.json")


def test_upload_cli_passes_request_and_prints_url(tmp_path: Path, monkeypatch):
    video = tmp_path / "movie.mp4"
    video.write_bytes(b"dummy")
    captured: dict = {}

    def fake_upload(req, *, client_secrets, token_file, open_browser, progress):
        captured["req"] = req
        captured["token_file"] = token_file
        captured["open_browser"] = open_browser
        progress(0.5)
        return "VIDEOID123"

    monkeypatch.setattr("jom.main.upload", fake_upload)
    result = CliRunner().invoke(upload_cli, [
        str(video), "--privacy", "unlisted", "--tags", "旅行,家族",
        "--description", "説明", "--no-browser",
        "--token", str(tmp_path / "t.json"),
    ])
    assert result.exit_code == 0, result.output
    req = captured["req"]
    assert req.path == video
    assert req.title == "movie"        # --title 未指定なのでファイル名から
    assert req.privacy == "unlisted"
    assert req.tags == ["旅行", "家族"]
    assert req.description == "説明"
    assert captured["open_browser"] is False
    assert captured["token_file"] == tmp_path / "t.json"
    assert "https://www.youtube.com/watch?v=VIDEOID123" in result.output


def test_upload_cli_reports_upload_error(tmp_path: Path, monkeypatch):
    video = tmp_path / "movie.mp4"
    video.write_bytes(b"dummy")

    def fake_upload(req, **kw):
        raise UploadError("認証ファイルが無い")

    monkeypatch.setattr("jom.main.upload", fake_upload)
    result = CliRunner().invoke(upload_cli, [str(video)])
    assert result.exit_code != 0
    assert "認証ファイルが無い" in result.output


def test_upload_cli_rejects_missing_video(tmp_path: Path):
    result = CliRunner().invoke(upload_cli, [str(tmp_path / "nope.mp4")])
    assert result.exit_code != 0
