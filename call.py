"""
call.py: the AI agent CALLS a Telegram user, speaks a text (TTS), optionally records the answer.

  python call.py --to @username --text "Salom!" [--voice uz-m] [--listen 20] [--yes]

Without --yes nothing happens (PREVIEW only). One person at a time.
Exit code: 0 = answered and spoke, 2 = not answered / busy, 1 = error.
"""
import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

import edge_tts
from dotenv import load_dotenv
from mutagen.mp3 import MP3
from pytgcalls import PyTgCalls, filters
from pytgcalls.types import CallConfig, ChatUpdate, MediaStream, RecordStream
from telethon import TelegramClient

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = Path(__file__).resolve().parent
OUT = BASE / "out"
load_dotenv(BASE / ".env")
API_ID = int(os.getenv("TG_API_ID", "0") or 0)
API_HASH = os.getenv("TG_API_HASH", "")
SESSION = str(BASE / "my_account")  # same session file that `tg.py login` created

VOICES = {"uz-m": "uz-UZ-SardorNeural", "uz-f": "uz-UZ-MadinaNeural",
          "ru-m": "ru-RU-DmitryNeural", "ru-f": "ru-RU-SvetlanaNeural",
          "en-m": "en-US-GuyNeural", "en-f": "en-US-JennyNeural"}


def stream(path):
    return MediaStream(str(path), video_flags=MediaStream.Flags.IGNORE)


async def main(a):
    if not API_ID or not API_HASH:
        sys.exit("XATO: .env ichida TG_API_ID / TG_API_HASH yo'q.")
    OUT.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    mp3 = OUT / f"call_{stamp}.mp3"
    await edge_tts.Communicate(a.text, VOICES.get(a.voice, a.voice)).save(str(mp3))
    length = MP3(str(mp3)).info.length

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        sys.exit("XATO: login qilinmagan. O'quvchi terminalda:  python tg.py login")
    to = a.to.strip()
    e = await client.get_entity(int(to) if to.lstrip("-").isdigit() else to)
    name = (getattr(e, "first_name", "") or getattr(e, "title", "") or "?")
    print("---- PREVIEW ----")
    print("Kimga qo'ng'iroq:", name, f"(@{getattr(e, 'username', None) or '-'}, id={e.id})")
    print("Aytiladigan matn:", a.text)
    print(f"Ovoz: {a.voice}, davomiyligi ~{length:.0f} s, tinglash: {a.listen} s")
    if not a.yes:
        print("Qo'ng'iroq QILINMADI. O'quvchi «ha» desa, --yes bilan qayta ishga tushiring.")
        await client.disconnect()
        return 0

    app = PyTgCalls(client)
    ended = asyncio.Event()

    @app.on_update(filters.chat_update(ChatUpdate.Status.DISCARDED_CALL | ChatUpdate.Status.BUSY_CALL))
    async def _gone(_, update):
        ended.set()

    await app.start()
    code = 0
    try:
        print("Qo'ng'iroq qilinyapti...", flush=True)
        await app.play(e.id, stream(mp3), config=CallConfig(timeout=40))
        # the file starts while it is still ringing -> restart it after pickup
        await asyncio.sleep(1.5)
        await app.play(e.id, stream(mp3))
        print("Ko'tardi, gapiryapman", flush=True)
        if a.listen:
            rec = OUT / f"answer_{stamp}.wav"
            await app.record(e.id, RecordStream(audio=str(rec)))
        try:
            await asyncio.wait_for(ended.wait(), length + a.listen + 2)
        except asyncio.TimeoutError:
            pass
        try:
            await app.leave_call(e.id)
        except Exception:
            pass
        print("Tugadi ✅")
    except Exception as ex:
        n = type(ex).__name__
        code = 2 if ("Timed" in n or "Busy" in n) else 1
        print("Ko'tarmadi:" if code == 2 else "XATO:", n, ex)
    await asyncio.sleep(1)
    await client.disconnect()
    sys.stdout.flush()
    os._exit(code)  # ntgcalls sometimes crashes while closing; skip its teardown


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--to", required=True)
    p.add_argument("--text", required=True)
    p.add_argument("--voice", default="uz-m")
    p.add_argument("--listen", type=int, default=0, help="seconds to record the answer (0 = don't)")
    p.add_argument("--yes", action="store_true")
    asyncio.run(main(p.parse_args()))
