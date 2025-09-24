import os
import re
import tempfile
import asyncio
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, MessageHandler, filters, ContextTypes

from urllib.parse import urlparse

import aiohttp
from yt_dlp import YoutubeDL

from logging import basicConfig, getLogger, INFO

logger = getLogger(__name__)

# --- Config from ENV ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
WHITELIST = set(
    int(cid.strip()) for cid in os.environ.get("WHITELIST", "").split(",") if cid.strip()
)
MAX_SIZE_MB = int(os.environ.get("MAX_SIZE_MB", "50"))   # Telegram supports large files; keep some headroom
YTDLP_FORMAT = os.environ.get("YTDLP_FORMAT", "bv*+ba/b")  # best video+audio or best
YTDLP_RESTRICT_FNAME = os.environ.get("YTDLP_RESTRICT_FNAME", "true").lower() == "true"
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "45"))

URL_REGEX = re.compile(
    r"(https?://[^\s]+)", re.IGNORECASE
)

VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv", ".m4v"}
VIDEO_DOMAINS = [
    # YouTube
    "youtube.com", "m.youtube.com", "youtu.be", "youtube-nocookie.com",
    # TikTok
    "tiktok.com", "vm.tiktok.com",
    # Instagram
    "instagram.com", "cdninstagram.com",
    # X / Twitter
    "x.com", "twitter.com", "fxtwitter.com", "vxtwitter.com", "video.twimg.com",
    # Facebook
    "facebook.com", "m.facebook.com", "fb.watch",
    # Vimeo
    "vimeo.com", "player.vimeo.com",
    # Twitch
    "twitch.tv", "clips.twitch.tv",
    # Reddit
    "reddit.com", "v.redd.it",
    # Streamable
    "streamable.com",
    # Dailymotion
    "dailymotion.com", "dai.ly",
    "drive.google.com",
]


def bytes_to_mb(b: int) -> float:
    return b / (1024 * 1024)

def _is_video_content_type(ct: str | None) -> bool:
    return bool(ct and ct.lower().startswith("video/"))

def ytdlp_download(url: str, out_dir: Path) -> Path | None:
    ydl_opts = {
        "outtmpl": str(out_dir / "%(title).200B.%(ext)s"),
        "format": YTDLP_FORMAT,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": YTDLP_RESTRICT_FNAME,
        "merge_output_format": "mp4",
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # yt-dlp returns actual filename used
        filepath = ydl.prepare_filename(info)
        if filepath and Path(filepath).exists():
            return Path(filepath)
    return None

async def http_head(session: aiohttp.ClientSession, url: str):
    try:
        async with session.head(url, timeout=HTTP_TIMEOUT, allow_redirects=True) as r:
            return r
    except Exception:
        return None

async def http_get_to_file(session: aiohttp.ClientSession, url: str, out_path: Path) -> tuple[bool, int]:
    size = 0
    try:
        async with session.get(url, timeout=None) as r:
            r.raise_for_status()
            with out_path.open("wb") as f:
                async for chunk in r.content.iter_chunked(1 << 14):
                    if not chunk:
                        continue
                    size += len(chunk)
                    if bytes_to_mb(size) > MAX_SIZE_MB:
                        return False, size
                    f.write(chunk)
        return True, size
    except Exception:
        return False, size

def pick_first_url(text: str) -> str | None:
    if not text:
        return None
    m = URL_REGEX.search(text)
    return m.group(1) if m else None

def host_matches(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    allowed = any(host == d or host.endswith("." + d) for d in (d.lower() for d in VIDEO_DOMAINS))
    if not allowed:
        return False
    return True

async def reject_if_not_whitelisted(update: Update) -> bool:
    cid = update.effective_chat.id if update.effective_chat else None
    if cid not in WHITELIST:
        try:
            await update.effective_message.reply_text("⚠️ This chat is not allowed to use this bot.")
            logger.warning(f"Rejected message from non-whitelisted chat {cid}")
        except Exception:
            pass
        return True
    return False

async def send_typing(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int):
    try:
        await ctx.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_VIDEO)
    except Exception:
        pass

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # whitelist check
    if await reject_if_not_whitelisted(update):
        return

    msg = update.effective_message
    text = msg.text or msg.caption or ""
    url = pick_first_url(text)
    if not url:
        return  # ignore non-url messages

    for domain in VIDEO_DOMAINS:
        if domain in url.lower():
            break
    else:
        return

    await send_typing(context, update.effective_chat.id)

    # workspace
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)

        # try quick path: direct video URL (by head/content-type or file extension)
        async with aiohttp.ClientSession() as session:
            head = await http_head(session, url)
            content_type = head.headers.get("Content-Type") if head else None
            ext = Path(url.split("?")[0].split("#")[0]).suffix.lower()

            file_path = tmpdir / "video_download"
            downloaded = False
            size = 0

            if not downloaded:
                try:
                    fp = await asyncio.to_thread(ytdlp_download, url, tmpdir)
                    if fp:
                        file_path = fp
                        downloaded = True
                        size = file_path.stat().st_size
                except Exception:
                    downloaded = False

        if not downloaded:
            await msg.reply_text("❌ Couldn't download this link. It may be unsupported or blocked.")
            return

        if bytes_to_mb(size) > MAX_SIZE_MB:
            await msg.reply_text(
                f"⚠️ File is too large ({bytes_to_mb(size):.1f} MB). Limit is {MAX_SIZE_MB} MB."
            )
            return

        # Try sending as video first (Telegram/clients like previews)
        try:
            await msg.reply_video(
                video=file_path.open("rb"),
                read_timeout=1800,
                write_timeout=3600,
            )
            return
        except Exception as e:
            logger.warning(f"Failed to send as video: {e}")
            pass

        # Fallback to document if Telegram rejects as "video"
        try:
            await msg.reply_document(document=file_path.open("rb"))
        except Exception as e:
            await msg.reply_text(f"❌ Upload failed: {e}")

def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is required")

    app = Application.builder().token(BOT_TOKEN).concurrent_updates(True).build()
    app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, handle_message))
    # Also catch bare links (Telegram marks as entities even without text context)
    app.add_handler(MessageHandler(filters.Entity("url"), handle_message))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
