# file: mcp_server/spotify_server.py
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Literal

import spotipy
from spotipy import SpotifyException
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import CacheFileHandler

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

# Load .env from project root (two levels up from this file)
if load_dotenv:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    DOTENV_PATH = PROJECT_ROOT / ".env"
    if DOTENV_PATH.exists():
        load_dotenv(dotenv_path=DOTENV_PATH, override=False)

# MCP Python SDK (fastmcp)
import contextlib

from mcp.server.fastmcp import FastMCP

# ----------------------------
# Config / constants
# ----------------------------

APP_NAME = "spotify-mcp"
APP_VERSION = "0.2.0"

DEFAULT_SCOPE = os.getenv(
    "SPOTIFY_SCOPE",
    "user-top-read user-read-recently-played playlist-modify-private playlist-read-private",
)

DEFAULT_REDIRECT = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
CACHE_PATH = os.getenv("SPOTIFY_TOKEN_CACHE", os.path.expanduser("~/.cache/spotify-mcp"))

VALID_TIME_RANGES = {"short_term", "medium_term", "long_term"}


# ----------------------------
# Helpers
# ----------------------------
def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


def _canonical_scope(scope: str) -> str:
    """Ensure stable, deduped, sorted scopes so we don't 'change' scopes between runs."""
    parts = [s for s in (scope or "").split() if s.strip()]
    return " ".join(sorted(set(parts)))


# Global singletons
_SPOTIFY_CLIENT: spotipy.Spotify | None = None
_AUTH_MANAGER: SpotifyOAuth | None = None


def _spotify(scope: str = DEFAULT_SCOPE) -> spotipy.Spotify:
    """
    Get or create a singleton Spotify client.
    - Uses a file cache so tokens persist between calls/runs.
    - Only opens a browser if no cache token exists.
    """
    global _SPOTIFY_CLIENT, _AUTH_MANAGER

    if _SPOTIFY_CLIENT is not None:
        return _SPOTIFY_CLIENT

    client_id = _require_env("SPOTIFY_CLIENT_ID")
    client_secret = _require_env("SPOTIFY_CLIENT_SECRET")

    canon_scope = _canonical_scope(scope)
    cache_handler = CacheFileHandler(cache_path=CACHE_PATH)

    # detect whether we already have a cached token
    cached = bool(cache_handler.get_cached_token())

    _AUTH_MANAGER = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=DEFAULT_REDIRECT,
        scope=canon_scope,
        cache_handler=cache_handler,   # <- explicit cache handler
        open_browser=not cached,       # <- only open browser if no cache yet
        show_dialog=False,             # <- don't force consent if cache exists
    )

    _SPOTIFY_CLIENT = spotipy.Spotify(auth_manager=_AUTH_MANAGER)
    return _SPOTIFY_CLIENT


def _chunked(seq: list[str], size: int = 100):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _safe_limit(limit: int, default: int = 10) -> int:
    try:
        n = int(limit)
    except Exception:
        return default
    return max(1, min(50, n))


def _validate_time_range(time_range: str) -> str:
    return time_range if time_range in VALID_TIME_RANGES else "short_term"


def _handle_spotify_ex(ex: SpotifyException) -> None:
    # Surface a concise, actionable error via MCP
    status = getattr(ex, "http_status", None)
    headers = getattr(ex, "headers", {}) or {}
    retry_after = headers.get("Retry-After")
    msg = getattr(ex, "msg", str(ex))

    if status == 429 and retry_after:
        # Back off briefly before raising, so agent retries succeed without immediate failure
        with contextlib.suppress(Exception):
            time.sleep(int(retry_after))
        raise RuntimeError(f"Rate limited by Spotify (429). Suggested retry after {retry_after}s.")
    elif status in (401, 403):
        raise RuntimeError(
            f"Spotify auth/permission error ({status}). Check scopes and login: {msg}"
        )
    else:
        raise RuntimeError(f"Spotify error ({status}): {msg}")


# ----------------------------
# MCP app & tools
# ----------------------------
app = FastMCP(APP_NAME)


@app.tool()
def get_top_tracks(
    limit: int = 10,
    time_range: Literal["short_term", "medium_term", "long_term"] = "short_term",
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Return the current user's top tracks (paged).
    Args:
      limit: 1-50
      time_range: 'short_term' (4 weeks), 'medium_term' (6 months), 'long_term' (years)
      offset: pagination offset (multiple of limit)
    """
    sp = _spotify()
    limit = _safe_limit(limit)
    time_range = _validate_time_range(time_range)
    try:
        resp = sp.current_user_top_tracks(limit=limit, time_range=time_range, offset=offset)
    except SpotifyException as ex:
        _handle_spotify_ex(ex)

    out: list[dict[str, Any]] = []
    for t in resp.get("items", []) or []:
        out.append(
            {
                "id": t.get("id"),
                "uri": t.get("uri"),
                "name": t.get("name"),
                "artist": (t.get("artists") or [{}])[0].get("name"),
                "album": (t.get("album") or {}).get("name"),
            }
        )
    return out


@app.tool()
def search_tracks(query: str, limit: int = 5, offset: int = 0) -> list[dict[str, Any]]:
    """Search for tracks by text query. Returns simplified track metadata."""
    if not query or not query.strip():
        raise ValueError("query is required")
    sp = _spotify()
    limit = _safe_limit(limit)
    try:
        resp = sp.search(q=query, type="track", limit=limit, offset=offset)
    except SpotifyException as ex:
        _handle_spotify_ex(ex)

    items = (resp.get("tracks") or {}).get("items", []) or []
    results: list[dict[str, Any]] = []
    for t in items:
        results.append(
            {
                "id": t.get("id"),
                "uri": t.get("uri"),
                "name": t.get("name"),
                "artist": (t.get("artists") or [{}])[0].get("name"),
                "album": (t.get("album") or {}).get("name"),
            }
        )
    return results


@app.tool()
def create_playlist(
    name: str,
    description: str = "",
    public: bool = False,
    track_uris: list[str] | None = None,
) -> dict[str, Any]:
    """
    Create a playlist and optionally add tracks by URI (chunked).
    Returns: {id, name, tracks_added}
    """
    if not name or not name.strip():
        raise ValueError("name is required")
    sp = _spotify()
    try:
        me = sp.me()
        playlist = sp.user_playlist_create(me["id"], name, public=public, description=description)
        added = 0
        if track_uris:
            for chunk in _chunked(track_uris, 100):
                sp.playlist_add_items(playlist["id"], chunk)
                added += len(chunk)
    except SpotifyException as ex:
        _handle_spotify_ex(ex)

    return {"id": playlist.get("id"), "name": playlist.get("name"), "tracks_added": added}


@app.tool()
def add_tracks_to_playlist(playlist_id: str, uris: list[str]) -> dict[str, Any]:
    """Add track URIs to an existing playlist (chunked)."""
    if not playlist_id:
        raise ValueError("playlist_id is required")
    if not uris:
        return {"playlist_id": playlist_id, "tracks_added": 0}

    sp = _spotify()
    total = 0
    try:
        for chunk in _chunked(uris, 100):
            sp.playlist_add_items(playlist_id, chunk)
            total += len(chunk)
    except SpotifyException as ex:
        _handle_spotify_ex(ex)

    return {"playlist_id": playlist_id, "tracks_added": total}


def main() -> None:
    app.run()  # stdio transport (FastMCP default)


if __name__ == "__main__":
    main()
