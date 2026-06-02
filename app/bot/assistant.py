import os
import asyncio
import logging
from kurigram import Client, filters
from kurigram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from kurigram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired, FloodWait
from app.bot.userbot_manager import manager, API_ID, API_HASH
from app.database import AsyncSessionLocal, ClientSession
from sqlalchemy.future import select

logger = logging.getLogger("assistant_bot")

BOT_TOKEN = os.getenv("ASSISTANT_BOT_TOKEN")

# Initialize the assistant bot client
# We don't load plugins for assistant bot to prevent loading userbot plugins in assistant mode
assistant_app = Client(
    name="assistant_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

# Keyboards
main_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("➕ Tambah Client (OTP)"), KeyboardButton("🔑 Tambah via Session String")],
        [KeyboardButton("📊 Status Client"), KeyboardButton("❓ Bantuan")]
    ],
    resize_keyboard=True
)


@assistant_app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    await message.reply_text(
        "Halo! Saya adalah Asisten Userbot Telegram.\n\n"
        "Saya dapat membantu Anda mendeploy client userbot baru "
        "hanya dengan menggunakan nomor HP Telegram Anda.",
        reply_markup=main_keyboard
    )

@assistant_app.on_message(filters.regex("📊 Status Client") & filters.private)
async def status_handler(client: Client, message: Message):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ClientSession))
        sessions = result.scalars().all()
    
    if not sessions:
        await message.reply_text("Tidak ada client yang terdaftar.")
        return
        
    text = "=== **Daftar Client Userbot** ===\n\n"
    for s in sessions:
        status = manager.get_client_status(s.phone_number)
        emoji = "🟢" if status == "online" else "🔴"
        text += f"{emoji} `{s.phone_number}` - Status: **{status.upper()}**\n"
        
    await message.reply_text(text)

@assistant_app.on_message(filters.regex("➕ Tambah Client \(OTP\)") & filters.private)
async def add_client_handler(client: Client, message: Message):
    user_id = message.from_user.id
    manager.auth_states[user_id] = {"step": "waiting_phone"}
    await message.reply_text(
        "Silakan kirimkan nomor HP Telegram Anda dalam format internasional.\n"
        "Contoh: `+628123456789`"
    )

@assistant_app.on_message(filters.regex("🔑 Tambah via Session String") & filters.private)
async def add_session_handler(client: Client, message: Message):
    user_id = message.from_user.id
    manager.auth_states[user_id] = {"step": "waiting_session_phone"}
    await message.reply_text(
        "Silakan kirim nomor HP/Label untuk client ini (misal: `+628123456789`):"
    )


@assistant_app.on_message(filters.regex("❓ Bantuan") & filters.private)
async def help_handler(client: Client, message: Message):
    await message.reply_text(
        "**Panduan Penggunaan Asisten Bot:**\n\n"
        "1. Klik tombol **Tambah Client**.\n"
        "2. Kirim nomor telepon dengan kode negara (misal +62...).\n"
        "3. Tunggu kode OTP masuk ke Telegram Anda, lalu kirimkan kode OTP tersebut ke bot ini.\n"
        "4. Jika akun Anda memiliki Verifikasi 2 Langkah (2FA), masukkan password saat diminta.\n"
        "5. Selesai! Userbot Anda akan langsung aktif."
    )

@assistant_app.on_message(filters.private & filters.text)
async def state_handler(client: Client, message: Message):
    user_id = message.from_user.id
    state = manager.auth_states.get(user_id)
    
    if not state:
        return
        
    text = message.text.strip()
    
    if text.lower() in ["/cancel", "cancel", "batal"]:
        temp_client = state.get("temp_client")
        if temp_client:
            try:
                await temp_client.disconnect()
            except:
                pass
        manager.auth_states.pop(user_id, None)
        await message.reply_text("Proses login dibatalkan.", reply_markup=main_keyboard)
        return
        
    step = state.get("step")

    
    if step == "waiting_session_phone":
        manager.auth_states[user_id] = {
            "step": "waiting_session_string",
            "phone_number": text
        }
        await message.reply_text("Silakan kirim Pyrogram v2 Session String Anda:")
        return

    elif step == "waiting_session_string":
        phone_number = state.get("phone_number")
        session_string = text
        await message.reply_text("Memverifikasi & menyimpan Session String...")
        try:
            temp_client = Client(
                name=f"temp_session_{user_id}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=session_string,
                in_memory=True
            )
            await temp_client.connect()
            me = await temp_client.get_me()
            await temp_client.disconnect()
            
            async with AsyncSessionLocal() as db_session:
                result = await db_session.execute(select(ClientSession).where(ClientSession.phone_number == phone_number))
                existing = result.scalar_one_or_none()
                if existing:
                    existing.session_string = session_string
                    existing.is_active = True
                else:
                    new_session = ClientSession(
                        phone_number=phone_number,
                        session_string=session_string,
                        is_active=True
                    )
                    db_session.add(new_session)
                await db_session.commit()
                
            await manager.start_client(phone_number, session_string)
            await message.reply_text(
                f"🎉 **Sukses!** Userbot untuk `{phone_number}` (User: @{me.username or me.first_name}) "
                "berhasil dideploy menggunakan Session String.",
                reply_markup=main_keyboard
            )
        except Exception as e:
            logger.error(f"Error adding manual session string: {e}")
            await message.reply_text(
                f"❌ **Gagal!** Session string tidak valid atau terjadi error: `{e}`\n\n"
                "Proses dibatalkan. Silakan ulangi lagi.",
                reply_markup=main_keyboard
            )
        finally:
            manager.auth_states.pop(user_id, None)
        return

    elif step == "waiting_phone":
        if not text.startswith("+") or len(text) < 10:
            await message.reply_text("Format nomor salah. Harap gunakan format internasional (+62...)")
            return
            
        await message.reply_text("Sedang menghubungkan ke Telegram... Mohon tunggu.")
        
        # Initialize a temporary client
        temp_client = Client(
            name=f"temp_{user_id}",
            api_id=API_ID,
            api_hash=API_HASH,
            in_memory=True
        )
        
        try:
            await temp_client.connect()
            code_info = await temp_client.send_code(text)
            
            # Save state
            manager.auth_states[user_id] = {
                "step": "waiting_otp",
                "phone_number": text,
                "phone_code_hash": code_info.phone_code_hash,
                "temp_client": temp_client
            }
            await message.reply_text(
                "Kode OTP telah dikirim oleh Telegram.\n"
                "Silakan masukkan kode OTP tersebut di sini.\n\n"
                "Format input OTP: jika kode adalah 12345, silakan kirim `12345`"
            )
        except FloodWait as e:
            await message.reply_text(f"Terlalu banyak mencoba. Silakan tunggu {e.value} detik.")
            await temp_client.disconnect()
            manager.auth_states.pop(user_id, None)
        except Exception as e:
            logger.error(f"Error sending code: {e}")
            await message.reply_text(f"Terjadi kesalahan saat mengirim kode: {e}")
            try:
                await temp_client.disconnect()
            except:
                pass
            manager.auth_states.pop(user_id, None)
            
    elif step == "waiting_otp":
        phone_number = state.get("phone_number")
        phone_code_hash = state.get("phone_code_hash")
        temp_client = state.get("temp_client")
        
        # OTP input
        otp = text.replace(" ", "")
        
        await message.reply_text("Memverifikasi kode OTP...")
        
        try:
            await temp_client.sign_in(phone_number, phone_code_hash, otp)
            await finalize_login(message, temp_client, phone_number, user_id)
        except SessionPasswordNeeded:
            # Requires 2FA
            manager.auth_states[user_id]["step"] = "waiting_2fa"
            await message.reply_text(
                "Akun Anda mengaktifkan Verifikasi 2 Langkah (2FA).\n"
                "Silakan masukkan password 2FA Anda."
            )
        except (PhoneCodeInvalid, PhoneCodeExpired) as e:
            await message.reply_text("Kode OTP salah atau kedaluwarsa. Silakan masukkan kode OTP yang benar.")
        except Exception as e:
            logger.error(f"Error signing in: {e}")
            await message.reply_text(f"Gagal login: {e}. Proses dibatalkan.")
            await temp_client.disconnect()
            manager.auth_states.pop(user_id, None)

    elif step == "waiting_2fa":
        phone_number = state.get("phone_number")
        temp_client = state.get("temp_client")
        password = text
        
        await message.reply_text("Memverifikasi password 2FA...")
        
        try:
            await temp_client.check_password(password)
            await finalize_login(message, temp_client, phone_number, user_id)
        except Exception as e:
            await message.reply_text(f"Password salah atau terjadi kesalahan: {e}. Harap kirim password kembali.")

async def finalize_login(message: Message, temp_client: Client, phone_number: str, user_id: int):
    try:
        session_string = await temp_client.export_session_string()
        await temp_client.disconnect()
        
        # Save to database
        async with AsyncSessionLocal() as session:
            # Check if exists
            result = await session.execute(select(ClientSession).where(ClientSession.phone_number == phone_number))
            existing = result.scalar_one_or_none()
            
            if existing:
                existing.session_string = session_string
                existing.is_active = True
            else:
                new_session = ClientSession(
                    phone_number=phone_number,
                    session_string=session_string,
                    is_active=True
                )
                session.add(new_session)
            
            await session.commit()
            
        # Start in Manager
        await manager.start_client(phone_number, session_string)
        
        await message.reply_text(
            f"🎉 **Sukses!** Userbot untuk `{phone_number}` berhasil dideploy dan saat ini aktif.",
            reply_markup=main_keyboard
        )
    except Exception as e:
        logger.error(f"Error finalizing login: {e}")
        await message.reply_text(f"Gagal menyelesaikan proses setup: {e}")
    finally:
        manager.auth_states.pop(user_id, None)
