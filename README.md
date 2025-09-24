# Telegram Video Bot

A minimal Telegram bot that:
- Detects URLs in messages (and inline queries).
- Downloads videos (direct links or via `yt-dlp` for YouTube/TikTok/etc.).
- Replies with the downloaded file.
- Enforces a chat/user whitelist.
- Ships with Docker instructions and a ready-to-use image reference: **`docker.io/heylouiz/telegram-video-bot:latest`**.

> Supports inline mode for direct `.mp4` URLs. For platforms that need `yt-dlp`, use regular DM/group messages (or “Switch to PM” in inline).

---

## 1) Quick start (use the prebuilt image)

Create a `.env` file next to your compose:

```env
BOT_TOKEN=123456789:abc_def_your_bot_token_here
# Comma-separated: chat IDs for DM/groups; user IDs for inline usage
WHITELIST=123456789,-1001122334455
TZ=America/Sao_Paulo

# Optional: timeouts for large uploads (seconds)
TG_READ_TIMEOUT=600
TG_WRITE_TIMEOUT=600
TG_MEDIA_WRITE_TIMEOUT=3600
TG_CONNECT_TIMEOUT=30
TG_POOL_TIMEOUT=10

# Optional: If you run a Local Bot API server (see below), set its base URL (no trailing slash)
# TELEGRAM_API_BASE=http://tg-bot-api:8081
```

Use this **minimal `docker-compose.yml`** (pulls the image from your Docker Hub namespace **`heylouiz`**):

```yaml
version: "3.9"

services:
  video_bot:
    image: docker.io/heylouiz/telegram-video-bot:latest
    container_name: telegram-video-bot
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - TZ=${TZ:-America/Sao_Paulo}
```

Run it:

```bash
docker compose up -d
docker compose logs -f
```

> If you change `.env`, just `docker compose up -d` again.

### One‑liner (without compose)
```bash
docker run -d --name telegram-video-bot   --restart unless-stopped   --env-file .env   docker.io/heylouiz/telegram-video-bot:latest
```

---

## 2) Inline mode (optional)

Enable inline in **BotFather**:
1. `/setinline` → choose your bot → **Enable**.
2. `/setinlineplaceholder` → e.g. `Paste a video URL…`

**Whitelist behavior**:
- Messages in DM/groups: checked by **chat id**.
- Inline queries: checked by **user id** (must be included in `WHITELIST`).

---

## 3) Timeouts & large files

If uploads time out for large files, increase the timeouts via the `.env` variables (`TG_*`).  
For _very large_ files, consider using the **Local Bot API Server** (allows much larger uploads) and set `TELEGRAM_API_BASE`.

### Optional: Local Bot API server with compose
```yaml
services:
  tg-bot-api:
    image: aiogram/telegram-bot-api:latest
    restart: unless-stopped
    ports:
      - "8081:8081"
    environment:
      TELEGRAM_API_ID: "<your_api_id>"
      TELEGRAM_API_HASH: "<your_api_hash>"
    volumes:
      - tgapi-data:/var/lib/telegram-bot-api

volumes:
  tgapi-data:
```

Then add this to `.env`:
```
TELEGRAM_API_BASE=http://localhost:8081
```
(Or use the service name `http://tg-bot-api:8081` if both are in the same compose stack.)

---

## 4) Environment variables (summary)

- `BOT_TOKEN` (required) — Telegram bot token from BotFather.
- `WHITELIST` (required) — comma-separated chat IDs (DM/groups) **and** user IDs (for inline).
- `TZ` — time zone (default `America/Sao_Paulo`).
- `TG_READ_TIMEOUT`, `TG_WRITE_TIMEOUT`, `TG_MEDIA_WRITE_TIMEOUT`, `TG_CONNECT_TIMEOUT`, `TG_POOL_TIMEOUT` — tune PTB/HTTP timeouts.
- `TELEGRAM_API_BASE` — set to your Local Bot API endpoint to allow much larger uploads.

---

## 5) Notes

- The bot downloads to a temp folder and **deletes files automatically** after sending.
- Inline answers can only send pre-hosted direct videos (`.mp4`) unless you use a cached file id flow. For YouTube/TikTok/etc., use DM.
- Domains heuristic is hostname‑based. Extend `VIDEO_DOMAINS` as needed in code.
- If you want persistent logs or keeping sent files, mount volumes accordingly and change the code path.
