"""YouTube Data API v3 への動画アップロード

OAuth 2.0 のインストール済みアプリ (デスクトップアプリ) フローでユーザー認証し、
resumable upload で動画を送る。

必要な認証ファイル:

- クライアントシークレット: Google Cloud Console で作成した OAuth クライアント
  (種類: デスクトップアプリ) の JSON。既定は ``~/.config/jom/client_secret.json``
- トークン: 初回認証後に ``~/.config/jom/youtube_token.json`` へ保存し以降は再利用
  (期限切れは refresh_token で自動更新)

google 系ライブラリは import が重く、アップロードしない時は不要なので関数内で遅延
import する。
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

# youtube.upload は「アップロード専用」の最小スコープ (既存動画の読み書きは不可)
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

CONFIG_DIR = Path(os.environ.get("JOM_CONFIG_DIR", Path.home() / ".config" / "jom"))
DEFAULT_CLIENT_SECRETS = CONFIG_DIR / "client_secret.json"
DEFAULT_TOKEN_FILE = CONFIG_DIR / "youtube_token.json"

PRIVACY_CHOICES = ("private", "unlisted", "public")
DEFAULT_PRIVACY = "private"
# 22 = People & Blogs (ホームビデオ向けの無難な既定値)
DEFAULT_CATEGORY_ID = "22"

# resumable upload の1チャンク (256KBの倍数であること)
CHUNK_SIZE = 8 * 1024 * 1024
# 一時的な失敗のリトライ回数と対象ステータス
MAX_RETRIES = 5
RETRIABLE_STATUS = {500, 502, 503, 504}

WATCH_URL = "https://www.youtube.com/watch?v={video_id}"


class UploadError(RuntimeError):
    """アップロード関連のエラー (依存不足/認証ファイル不足など)"""


@dataclass
class UploadRequest:
    path: Path
    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    privacy: str = DEFAULT_PRIVACY
    category_id: str = DEFAULT_CATEGORY_ID
    made_for_kids: bool = False


def parse_tags(raw: str | None) -> list[str]:
    """カンマ区切りのタグ文字列をリストに (空要素は捨てる)"""
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


def default_title(path: Path, dates: Sequence[datetime] | None = None) -> str:
    """タイトル未指定時の既定値

    撮影日時が分かる場合はファイル名 (拡張子なし) に日付レンジを付ける。
    """
    stem = path.stem
    if not dates:
        return stem
    oldest, newest = min(dates), max(dates)
    if oldest.date() == newest.date():
        return f"{stem} {oldest:%Y-%m-%d}"
    return f"{stem} {oldest:%Y-%m-%d}〜{newest:%Y-%m-%d}"


def resolve_description(text: str | None, file: Path | None) -> str:
    """--description と --description-file を解決 (ファイル優先、両方無ければ空)"""
    if file is not None:
        return file.read_text()
    return text or ""


def build_body(req: UploadRequest) -> dict:
    """videos.insert に渡す body を組み立てる"""
    if req.privacy not in PRIVACY_CHOICES:
        raise ValueError(
            f"privacy は {'/'.join(PRIVACY_CHOICES)} のいずれか: {req.privacy!r}"
        )
    if not req.title.strip():
        raise ValueError("タイトルが空")
    return {
        "snippet": {
            "title": req.title,
            "description": req.description,
            "tags": req.tags,
            "categoryId": req.category_id,
        },
        "status": {
            "privacyStatus": req.privacy,
            "selfDeclaredMadeForKids": req.made_for_kids,
        },
    }


def watch_url(video_id: str) -> str:
    return WATCH_URL.format(video_id=video_id)


def load_credentials(
    client_secrets: Path = DEFAULT_CLIENT_SECRETS,
    token_file: Path = DEFAULT_TOKEN_FILE,
    *,
    open_browser: bool = True,
):
    """保存済みトークンを読む。無効なら refresh、それも不可なら対話認証"""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ModuleNotFoundError as e:  # pragma: no cover - 依存導入済みなら通らない
        raise UploadError(
            "YouTube アップロードには google-api-python-client / "
            "google-auth-oauthlib が必要。`make setup` (uv sync) を実行"
        ) from e

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        if creds.valid:
            return creds
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_token(creds, token_file)
            return creds

    if not client_secrets.exists():
        raise UploadError(
            f"OAuth クライアントシークレットが無い: {client_secrets}\n"
            "Google Cloud Console で YouTube Data API v3 を有効化し、"
            "「デスクトップアプリ」の OAuth クライアントを作って JSON を"
            "このパスに置く (--client-secrets / JOM_YOUTUBE_CLIENT_SECRETS で変更可)"
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=open_browser)
    _save_token(creds, token_file)
    return creds


def _save_token(creds, token_file: Path) -> None:
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json())
    token_file.chmod(0o600)  # リフレッシュトークンを含むので本人のみ読める権限に


def upload(
    req: UploadRequest,
    *,
    client_secrets: Path = DEFAULT_CLIENT_SECRETS,
    token_file: Path = DEFAULT_TOKEN_FILE,
    open_browser: bool = True,
    progress: Callable[[float], None] | None = None,
) -> str:
    """動画をアップロードして video ID を返す

    progress には 0.0〜1.0 の進捗が渡る。
    """
    if not req.path.exists():
        raise UploadError(f"動画が無い: {req.path}")
    body = build_body(req)

    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
    except ModuleNotFoundError as e:  # pragma: no cover - 依存導入済みなら通らない
        raise UploadError(
            "YouTube アップロードには google-api-python-client / "
            "google-auth-oauthlib が必要。`make setup` (uv sync) を実行"
        ) from e

    creds = load_credentials(client_secrets, token_file, open_browser=open_browser)
    # cache_discovery=False: oauth2client 無しの環境で出る警告を避ける
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    media = MediaFileUpload(
        str(req.path), chunksize=CHUNK_SIZE, resumable=True, mimetype="video/*"
    )
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    attempts = 0
    while response is None:
        try:
            status, response = request.next_chunk()
        except HttpError as e:
            if e.resp.status in RETRIABLE_STATUS and attempts < MAX_RETRIES:
                attempts += 1
                time.sleep(2 ** attempts)  # 指数バックオフ
                continue
            raise
        except OSError:
            # 通信断は resumable なので同じ request で再開できる
            if attempts >= MAX_RETRIES:
                raise
            attempts += 1
            time.sleep(2 ** attempts)
            continue
        if status is not None and progress is not None:
            progress(status.progress())

    if progress is not None:
        progress(1.0)
    video_id = response.get("id")
    if not video_id:
        raise UploadError(f"video ID が返らなかった: {response}")
    return video_id
