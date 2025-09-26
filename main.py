import os
import sys
from pathlib import Path

import spotipy
from spotipy import SpotifyException
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import CacheFileHandler

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

if load_dotenv:
    PROJECT_ROOT = Path(__file__).resolve().parent
    DOTENV_PATH = PROJECT_ROOT / ".env"
    if DOTENV_PATH.exists():
        load_dotenv(dotenv_path=DOTENV_PATH, override=False)

CACHE_PATH = os.getenv("SPOTIFY_TOKEN_CACHE", os.path.expanduser("~/.cache/spotify-mcp"))


def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return val


def _canonical_scope(scope: str) -> str:
    """Ensure stable, deduped, sorted scopes so we don't 'change' scopes between runs."""
    parts = [s for s in (scope or "").split() if s.strip()]
    return " ".join(sorted(set(parts)))


def get_spotify_client(scope: str) -> spotipy.Spotify:
    client_id = _require_env("SPOTIFY_CLIENT_ID")
    client_secret = _require_env("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

    canon_scope = _canonical_scope(scope)
    cache_handler = CacheFileHandler(cache_path=CACHE_PATH)
    cached = bool(cache_handler.get_cached_token())

    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=canon_scope,
        cache_handler=cache_handler,  # explicit cache handler
        open_browser=not cached,      # only open browser if no cache
        show_dialog=False,
    )
    return spotipy.Spotify(auth_manager=auth)


def main() -> None:
    scope = os.getenv(
        "SPOTIFY_SCOPE",
        "user-top-read user-read-recently-played playlist-modify-private playlist-read-private",
    )

    sp = get_spotify_client(scope)

    try:
        top = sp.current_user_top_tracks(limit=10, time_range="short_term")
    except SpotifyException as ex:
        status = getattr(ex, "http_status", None)
        if status in (401, 403):
            print("Auth/permission error. Check scopes and re-auth.", file=sys.stderr)
        elif status == 429:
            print("Rate limited by Spotify (429). Try again shortly.", file=sys.stderr)
        else:
            print(f"Spotify error ({status}): {getattr(ex, 'msg', ex)}", file=sys.stderr)
        sys.exit(2)

    print("Your top tracks:")
    items = top.get("items", []) or []
    for idx, item in enumerate(items, start=1):
        name = item.get("name", "Unknown")
        artist = (item.get("artists") or [{}])[0].get("name", "Unknown")
        print(f"{idx}. {name} – {artist}")

    me = sp.me()
    uris: list[str] = [t["uri"] for t in items if t.get("uri")]

    playlist = sp.user_playlist_create(me["id"], "AI Test Playlist", public=False)
    if uris:
        # For demos <= 100 tracks; chunk if you go larger
        sp.playlist_add_items(playlist["id"], uris)

    print(f"Created playlist {playlist['name']} with {len(uris)} tracks (id={playlist['id']}).")


if __name__ == "__main__":
    main()
