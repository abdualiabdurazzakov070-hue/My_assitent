"""
answer_calls.py: kiruvchi Telegram qo'ng'iroqlarini avtomatik ko'taruvchi 24/7 AI yordamchi (Web Service compatible).
"""
import argparse
import asyncio
import sys
import time
from pathlib import Path
import http.server
import socketserver
import threading

import edge_tts
from dotenv import load_dotenv
from mutagen.mp3 import MP3
from pytgcalls import PyTgCalls, filters
from pytgcalls.types import CallConfig, ChatUpdate, MediaStream, RecordStream
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import (
    PhoneCall,
    PhoneCallAccepted,
    PhoneCallDiscarded,
    UpdatePhoneCall,
)
import os

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = Path(__file__).resolve().parent
OUT = BASE / "out"
load_dotenv(BASE / ".env")
API_ID = int(os.getenv("TG_API_ID", "0") or 0)
API_HASH = os.getenv("TG_API_HASH", "")
SESSION = str(BASE / "my_account")

VOICES = {
    "uz-m": "uz-UZ-SardorNeural",
    "uz-f": "uz-UZ-MadinaNeural",
    "ru-m": "ru-RU-DmitryNeural",
    "ru-f": "ru-RU-SvetlanaNeural",
    "en-m": "en-US-GuyNeural",
    "en-f": "en-US-JennyNeural",
}


def stream(path: Path) -> MediaStream:
    return MediaStream(str(path), video_flags=MediaStream.Flags.IGNORE)


async def make_tts(text: str, voice_key: str, out_path: Path) -> float:
    voice = VOICES.get(voice_key, voice_key)
    await edge_tts.Communicate(text, voice).save(str(out_path))
    return float(MP3(str(out_path)).info.length)


def run_health_server():
    port = int(os.getenv("PORT", "10000"))
    class HealthHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Bot is running 24/7!")
        def log_message(self, format, *args):
            pass
    try:
        with socketserver.TCPServer(("", port), HealthHandler) as httpd:
            print(f"Health server listening on port {port}", flush=True)
            httpd.serve_forever()
    except Exception as e:
        print(f"Health server error: {e}", flush=True)


async def run_bot(a):
    if not API_ID or not API_HASH:
        print("XATO: .env ichida TG_API_ID / TG_API_HASH yo'q.", flush=True)
        return

    OUT.mkdir(exist_ok=True)
    greeting_mp3 = OUT / "auto_greeting.mp3"
    bye_mp3 = OUT / "auto_bye.mp3"

    print("TTS fayllari tayyorlanmoqda...", flush=True)
    greeting_len = await make_tts(a.text, a.voice, greeting_mp3)
    bye_len = await make_tts(a.bye, a.voice, bye_mp3)

    session_str = os.getenv("TG_SESSION_STRING", "")
    if session_str:
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    else:
        client = TelegramClient(SESSION, API_ID, API_HASH)
    
    await client.connect()
    if not await client.is_user_authorized():
        print("XATO: login qilinmagan. Terminalda: .venv\\Scripts\\python.exe tg.py login", flush=True)
        await client.disconnect()
        return

    me = await client.get_me()
    print(
        f"24/7 Tayyor ✅ Kiruvchi qo'ng'iroqlarni kutyapman: {me.first_name} (@{me.username or '-'}) "
        f"[kutish: {a.delay}s, voice: {a.voice}]",
        flush=True,
    )

    app = PyTgCalls(client)
    active_calls: set[int] = set()
    ended_events: dict[int, asyncio.Event] = {}
    answered_elsewhere_events: dict[int, asyncio.Event] = {}

    @client.on(events.Raw(types=[UpdatePhoneCall]))
    async def _on_raw_phone_call(update):
        pc = getattr(update, "phone_call", None)
        if pc is None:
            return
        uid = getattr(pc, "admin_id", None)
        if uid == me.id:
            uid = getattr(pc, "participant_id", None)
        if uid not in active_calls:
            return
        if isinstance(pc, (PhoneCall, PhoneCallAccepted)):
            ev = answered_elsewhere_events.get(uid)
            if ev:
                ev.set()
        elif isinstance(pc, PhoneCallDiscarded):
            ev = ended_events.get(uid)
            if ev:
                ev.set()

    async def handle_call(chat_id: int):
        if chat_id in active_calls:
            return
        active_calls.add(chat_id)
        ended = asyncio.Event()
        answered_elsewhere = asyncio.Event()
        ended_events[chat_id] = ended
        answered_elsewhere_events[chat_id] = answered_elsewhere
        rec_path = None
        caller_name = f"id={chat_id}"
        try:
            try:
                entity = await client.get_entity(chat_id)
                first = getattr(entity, "first_name", "") or ""
                last = getattr(entity, "last_name", "") or ""
                uname = getattr(entity, "username", None)
                full = (first + " " + last).strip() or f"id={chat_id}"
                caller_name = f"{full} (@{uname})" if uname else full
            except Exception:
                pass

            if a.delay > 0:
                print(
                    f"📞 Kiruvchi qo'ng'iroq: {caller_name}. O'zingiz ko'tarishingiz uchun {a.delay}s kutyapman...",
                    flush=True,
                )
                wait_ended = asyncio.create_task(ended.wait())
                wait_other = asyncio.create_task(answered_elsewhere.wait())
                done, pending = await asyncio.wait(
                    [wait_ended, wait_other],
                    timeout=a.delay,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
                if answered_elsewhere.is_set():
                    print(f"📱 O'zingiz ko'tardingiz ({caller_name}), AI aralashmaydi.", flush=True)
                    return
                if ended.is_set():
                    print(f"📵 Qo'ng'iroq uzildi ({caller_name}).", flush=True)
                    return

            print(f"🤖 Vaqt tugadi -> AI ko'tarmoqda ({caller_name})...", flush=True)
            await app.play(int(chat_id), stream(greeting_mp3))
            print(f"🎙 Gapiryapman ({greeting_len:.0f}s)...", flush=True)

            try:
                await asyncio.wait_for(ended.wait(), greeting_len + 1.0)
            except asyncio.TimeoutError:
                pass

            if not ended.is_set() and a.listen > 0:
                stamp = time.strftime("%Y%m%d-%H%M%S")
                rec_path = OUT / f"incoming_{stamp}.wav"
                print(f"👂 Tinglayapman ({a.listen}s)...", flush=True)
                await app.record(chat_id, RecordStream(audio=str(rec_path)))
                try:
                    await asyncio.wait_for(ended.wait(), a.listen)
                except asyncio.TimeoutError:
                    pass

            if not ended.is_set():
                await app.play(chat_id, stream(bye_mp3))
                try:
                    await asyncio.wait_for(ended.wait(), bye_len + 0.8)
                except asyncio.TimeoutError:
                    pass
                try:
                    await app.leave_call(chat_id)
                except Exception:
                    pass

            print(f"✅ Qo'ng'iroq yakunlandi ({caller_name})", flush=True)
            if rec_path and rec_path.exists() and rec_path.stat().st_size > 1000:
                await client.send_file(
                    "me",
                    str(rec_path),
                    caption=f"📞 **Kiruvchi qo'ng'iroq javobi**\nKimdan: {caller_name}",
                )
        except Exception as ex:
            print(f"XATO ({caller_name}): {type(ex).__name__}: {ex}", flush=True)
            try:
                await app.leave_call(chat_id)
            except Exception:
                pass
        finally:
            ended_events.pop(chat_id, None)
            answered_elsewhere_events.pop(chat_id, None)
            active_calls.discard(chat_id)

    @app.on_update(filters.chat_update(ChatUpdate.Status.INCOMING_CALL))
    async def _on_incoming(_, update):
        asyncio.create_task(handle_call(update.chat_id))

    @app.on_update(filters.chat_update(ChatUpdate.Status.DISCARDED_CALL | ChatUpdate.Status.BUSY_CALL))
    async def _on_ended(_, update):
        ev = ended_events.get(update.chat_id)
        if ev:
            ev.set()

    await app.app_start() if hasattr(app, "app_start") else await app.start()
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def main_loop(a):
    while True:
        try:
            await run_bot(a)
        except Exception as e:
            print(f"OGOH: Asosiy siklda xato yuz berdi: {e}. 5 soniyadan keyin qayta ulanaman...", flush=True)
            await asyncio.sleep(5)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="24/7 Kiruvchi Telegram qo'ng'iroqlarini ko'taruvchi AI yordamchi")
    p.add_argument(
        "--text",
        default="Assalomu alaykum! Men Abdualining ai assistent yordamchisiman. Hozir Abduali qongiroqni kotara olamagani uchun men kotardim , iltimos xabaringizni ovoz bilan qoldiring, men albatta yetkazaman!",
    )
    p.add_argument("--bye", default="Rahmat, xabaringizni saqlab oldim! Xayr!")
    p.add_argument("--voice", default="uz-m")
    p.add_argument("--delay", type=int, default=10, help="O'zingiz ko'tarishingiz uchun kutish (soniya)")
    p.add_argument("--listen", type=int, default=15, help="Javobni yozib olish davomiyligi (soniya)")
    args = p.parse_args()

    # Start HTTP health check server in background thread for Render Web Service
    threading.Thread(target=run_health_server, daemon=True).start()

    try:
        asyncio.run(main_loop(args))
    except KeyboardInterrupt:
        pass
