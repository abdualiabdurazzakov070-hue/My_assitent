"""
tg.py: the AI agent's "hands" in Telegram.
The agent (Antigravity) runs these commands in the terminal:

  login                          one-time login (the STUDENT runs this in a terminal)
  me                             who am I
  chats [--search NAME]          last chats (name, @username, id)
  send-text  --to X --text "..." [--yes]
  make-voice --text "..." [--voice uz-m]       -> out/voice_*.ogg
  send-voice --to X --file out/voice_*.ogg [--yes]

Without --yes nothing is sent, only a PREVIEW is printed.
Sending is allowed to ONE person at a time (no bulk sending).
"""
import argparse
import asyncio
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

try:  # Windows console: print Uzbek/Russian letters correctly
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = Path(__file__).resolve().parent
OUT = BASE / "out"
load_dotenv(BASE / ".env")

API_ID = int(os.getenv("TG_API_ID", "0") or 0)
API_HASH = os.getenv("TG_API_HASH", "")
SESSION = str(BASE / "my_account")  # creates my_account.session (= key to your account!)

VOICES = {
    "uz-m": "uz-UZ-SardorNeural",
    "uz-f": "uz-UZ-MadinaNeural",
    "ru-m": "ru-RU-DmitryNeural",
    "ru-f": "ru-RU-SvetlanaNeural",
    "en-m": "en-US-GuyNeural",
    "en-f": "en-US-JennyNeural",
}


def need_keys():
    if not API_ID or not API_HASH:
        sys.exit("XATO: .env ichida TG_API_ID va TG_API_HASH yo'q. README 2-qadamni qiling.")


def client():
    need_keys()
    session_str = os.getenv("TG_SESSION_STRING", "")
    if session_str:
        return TelegramClient(StringSession(session_str), API_ID, API_HASH)
    return TelegramClient(SESSION, API_ID, API_HASH)


async def connected():
    c = client()
    await c.connect()
    if not await c.is_user_authorized():
        await c.disconnect()
        sys.exit("XATO: hali login qilinmagan. O'quvchi terminalda o'zi yozsin:  python tg.py login")
    return c


def name_of(e):
    first = getattr(e, "first_name", None) or getattr(e, "title", None) or ""
    last = getattr(e, "last_name", None) or ""
    return (first + " " + last).strip() or "(nomsiz)"


async def resolve(c, to):
    """@username, numeric id, or part of a chat name -> exactly one person."""
    to = to.strip()
    if to.startswith("@") or to.lstrip("-").isdigit():
        return await c.get_entity(int(to) if to.lstrip("-").isdigit() else to)
    found = []
    async for d in c.iter_dialogs(limit=200):
        if d.is_user and to.lower() in (d.name or "").lower():
            found.append(d.entity)
    if not found:
        sys.exit(f"XATO: «{to}» topilmadi. Avval:  python tg.py chats --search \"{to}\"")
    if len(found) > 1:
        print(f"«{to}» bo'yicha bir nechta odam topildi, aniqrog'ini tanlang (--to @username yoki id):")
        for e in found:
            print(f"  {name_of(e):30} @{e.username or '-':20} id={e.id}")
        sys.exit(1)
    return found[0]


def who(e):
    return f"{name_of(e)} (@{e.username or '-'}, id={e.id})"


# ---------------- commands ----------------

async def cmd_login(a):
    c = client()
    await c.start()  # asks phone -> code from Telegram -> 2FA password (if any)
    me = await c.get_me()
    print(f"OK: login bo'ldi -> {who(me)}")
    await c.disconnect()


async def cmd_me(a):
    c = await connected()
    print("Men:", who(await c.get_me()))
    await c.disconnect()


async def cmd_chats(a):
    c = await connected()
    n = 0
    async for d in c.iter_dialogs(limit=200):
        if not d.is_user or getattr(d.entity, "bot", False):
            continue
        if a.search and a.search.lower() not in (d.name or "").lower():
            continue
        print(f"{d.name[:30]:30} @{d.entity.username or '-':20} id={d.entity.id}")
        n += 1
        if n >= a.limit:
            break
    if n == 0:
        print("Hech kim topilmadi.")
    await c.disconnect()


async def cmd_send_text(a):
    c = await connected()
    e = await resolve(c, a.to)
    print("---- PREVIEW ----")
    print("Kimga :", who(e))
    print("Matn  :", a.text)
    if not a.yes:
        print("Yuborilmadi. O'quvchi «ha» desa, shu buyruqni --yes bilan qayta ishga tushiring.")
    else:
        m = await c.send_message(e, a.text)
        print(f"YUBORILDI ✅ message_id={m.id}")
    await c.disconnect()


async def cmd_make_voice(a):
    import edge_tts
    import imageio_ffmpeg

    voice = VOICES.get(a.voice, a.voice)
    OUT.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    mp3 = OUT / f"voice_{stamp}.mp3"
    ogg = OUT / f"voice_{stamp}.ogg"

    await edge_tts.Communicate(a.text, voice).save(str(mp3))

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()  # ffmpeg ships inside pip, no install needed
    r = subprocess.run(
        [ffmpeg, "-loglevel", "error", "-y", "-i", str(mp3),
         "-ac", "1", "-ar", "48000", "-c:a", "libopus", "-b:a", "48k", str(ogg)],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not ogg.exists():
        print("OGOH: .ogg ga o'girib bo'lmadi, .mp3 ishlatiladi:", r.stderr.strip()[:200])
        print(mp3)
    else:
        print(ogg)


async def cmd_send_voice(a):
    f = Path(a.file)
    if not f.exists():
        sys.exit(f"XATO: fayl yo'q: {f}")
    c = await connected()
    e = await resolve(c, a.to)
    print("---- PREVIEW ----")
    print("Kimga :", who(e))
    print("Golos :", f, f"({f.stat().st_size // 1024} KB)")
    if not a.yes:
        print("Yuborilmadi. O'quvchi golosni eshitib «ha» desa, --yes bilan qayta ishga tushiring.")
    else:
        m = await c.send_file(e, str(f), voice_note=True)
        print(f"YUBORILDI ✅ message_id={m.id}")
    await c.disconnect()


def main():
    p = argparse.ArgumentParser(description="AI agent uchun Telegram buyruqlari")
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("login")
    s.add_parser("me")
    x = s.add_parser("chats"); x.add_argument("--search"); x.add_argument("--limit", type=int, default=30)
    x = s.add_parser("send-text"); x.add_argument("--to", required=True); x.add_argument("--text", required=True); x.add_argument("--yes", action="store_true")
    x = s.add_parser("make-voice"); x.add_argument("--text", required=True); x.add_argument("--voice", default="uz-m")
    x = s.add_parser("send-voice"); x.add_argument("--to", required=True); x.add_argument("--file", required=True); x.add_argument("--yes", action="store_true")
    a = p.parse_args()
    fn = {"login": cmd_login, "me": cmd_me, "chats": cmd_chats, "send-text": cmd_send_text,
          "make-voice": cmd_make_voice, "send-voice": cmd_send_voice}[a.cmd]
    asyncio.run(fn(a))


if __name__ == "__main__":
    main()
