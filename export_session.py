import os
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")
API_ID = int(os.getenv("TG_API_ID", "0") or 0)
API_HASH = os.getenv("TG_API_HASH", "")
SESSION = str(BASE / "my_account")

async def main():
    if not API_ID or not API_HASH:
        print("XATO: .env ichida TG_API_ID yoki TG_API_HASH yo'q.")
        return
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        print("XATO: Hali login qilinmagan!")
        await client.disconnect()
        return
    session_string = StringSession.save(client.session)
    print("\n--- SIZNING TG_SESSION_STRING ---")
    print(session_string)
    print("---------------------------------\n")
    print("Ushbu uzun matnni Render'da TG_SESSION_STRING o'zgaruvchisiga qiymat sifatida yozing.")
    await client.disconnect()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
