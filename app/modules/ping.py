import time
from kurigram import Client, filters
from kurigram.types import Message

@Client.on_message(filters.command("ping", prefixes=".") & filters.me)
async def ping_handler(client: Client, message: Message):
    start_time = time.time()
    reply_msg = await message.reply_text("🏓 **Pinging...**")
    end_time = time.time()
    latency = round((end_time - start_time) * 1000)
    await reply_msg.edit_text(f"🚀 **Pong!**\nLatency: `{latency}ms`")

@Client.on_message(filters.command("info", prefixes=".") & filters.me)
async def info_handler(client: Client, message: Message):
    me = await client.get_me()
    await message.reply_text(
        f"=== **Userbot Info** ===\n"
        f"**Nama:** {me.first_name}\n"
        f"**Username:** @{me.username if me.username else '-'}\n"
        f"**ID:** `{me.id}`\n"
        f"**Framework:** Kurigram (fork of Pyrogram)"
    )
