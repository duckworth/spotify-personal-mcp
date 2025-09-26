# spotify-personal-mcp

Minimal Spotify API demo (Spotipy) plus an MCP server skeleton, using [Astral uv](https://docs.astral.sh/uv) with `pyproject.toml`.  
Start with the Python demo to verify your Spotify app credentials, then plug into MCP for agent / AI workflows (Claude, Codex CLI, Windsurf, etc).

---

## 📂 Project Contents
- **Demo entrypoint**: `main.py`
- **MCP server**: `mcp_server/spotify_server.py`
- **Env template**: `.env.example`
- **Project config**: `pyproject.toml` (deps managed by uv)
- **Runtime version**: `.tool-versions` (Python pinned with [asdf](https://asdf-vm.com))

---

## 🔧 Prerequisites
- Python **3.13.7** (see `.tool-versions`)
- [Astral `uv`](https://docs.astral.sh/uv/getting-started/installation) installed
- A [Spotify Developer app](https://developer.spotify.com/dashboard/applications) with Client ID & Secret  
  (add `http://127.0.0.1:8888/callback` as a Redirect URI)

---

## 🚀 Setup (Demo mode)

1. **Install deps into a managed venv**
   ```bash
   uv sync
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   ```
   Fill `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`.  
   👉 You can get these values from your [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/applications) after creating an app there.  
   (Optional: `SPOTIFY_REDIRECT_URI`, `SPOTIFY_SCOPE`, `SPOTIFY_TOKEN_CACHE`).

3. **Run the demo**
   ```bash
   uv run python main.py
   ```
   - Opens browser for login  
   - Token cached in `~/.cache/spotify-mcp` by default

4. **Result**  
   Prints your top 10 tracks, then creates a private playlist with them.

---

## 🖥 MCP Server (stdio)

1. **Run the server**
   ```bash
   uv run spotify-mcp
   ```
   or explicitly:
   ```bash
   uv run python mcp_server/spotify_server.py
   ```

2. **Add it to Claude / Codex CLI / Windsurf**
   ```bash
   claude mcp add spotify -- uv run spotify-mcp
   ```

3. **Environment variables**  
   MCP server loads `.env` automatically from project root.

---

## 💡 Example MCP Usage

### Slash commands (direct tool calls)
```text
Call spotify:search_tracks with query="Radiohead", limit=7.
Call spotify:get_top_tracks with limit=20, time_range="long_term", offset=20.
Call spotify:create_playlist with name="Test Mix", description="Songs I’ve been into lately", public=false.
```

### Natural prompts
```text
Claude, get my top 10 tracks and make a playlist called "Test Favorites".
Search for 5 lo-fi beats and add them to my playlist "Focus Mix".
Grab my top 10 tracks from the last 6 months and create "2025 Vibes".
```

---

## ⚠️ Notes
- Redirect URI **must** match one registered in your Spotify app  
  (default: `http://127.0.0.1:8888/callback`).
- Demo asks for top tracks and creates a private playlist.  
  Adjust scopes in `.env` as needed (e.g., `playlist-modify-public`, `user-library-read`).
- Spotify API enforces per-user rate limits → you may see 429s (retry later).