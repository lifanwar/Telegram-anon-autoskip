import os
import asyncio
import random
import time
import sqlite3
import signal
import sys
import logging
import re
from dotenv import load_dotenv
from pyrogram import Client, filters

# Setup logging: output ke console dan file bot.log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
         logging.FileHandler("bot.log"),
         logging.StreamHandler()
    ]
)

# Muat variabel dari file .env
load_dotenv()

# Ambil kredensial dan owner id dari environment
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME")
OWNER_ID = int(os.getenv("OWNER_ID"))

# Dictionary untuk menyimpan timer per chat (chat_id: task)
pending_timers = {}
# Dictionary untuk menandai apakah /search harus dikirim
pending_flags = {}

# Set keyword untuk rule kedua, exact match (huruf kecil)
KEYWORDS = {"co", "cowo", "cowok", "cwo", "cwok"}
# Buat regex pattern untuk exact match, word boundaries, case-insensitive
keyword_pattern = re.compile(r'\b(?:' + '|'.join(KEYWORDS) + r')\b', re.IGNORECASE)

# Menyimpan chat IDs yang di-blacklist (tidak akan diproses rules)
blacklisted_chats = set()

async def send_search_after_timeout(client: Client, chat_id: int):
    """
    Menunggu 10 detik dan mengirim /search jika flag untuk chat tersebut masih True.
    """
    try:
        await asyncio.sleep(10)
        if pending_flags.get(chat_id, False):
            logging.info(f"Timer expired for chat {chat_id}. Sending '/search'.")
            await client.send_message(chat_id, "/search")
        pending_timers.pop(chat_id, None)
        pending_flags.pop(chat_id, None)
    except asyncio.CancelledError:
        logging.info(f"Timer cancelled for chat {chat_id}.")
        pending_timers.pop(chat_id, None)
        pending_flags.pop(chat_id, None)

# Buat instance Client menggunakan kredensial dari .env
app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH)

@app.on_message(filters.text)
async def handle_messages(client: Client, message):
    chat_id = message.chat.id
    sender = message.from_user.first_name if message.from_user else "Unknown"
    text = message.text.strip() if message.text else ""
    text_lower = text.lower()
    
    logging.info(f"Received message from {sender} (chat {chat_id}): {text}")
    
    # Perintah /start hanya dari owner - akan menghapus chat dari blacklist jika ada
    if text_lower == "/start":
        if message.from_user and message.from_user.id == OWNER_ID:
            if chat_id in blacklisted_chats:
                blacklisted_chats.remove(chat_id)
            logging.info(f"Bot activated in chat {chat_id} by owner.")
            await client.send_message(chat_id, "Bot activated.")
        else:
            logging.info(f"/start received from non-owner in chat {chat_id}; ignoring.")
        return

    # Perintah /stop hanya dari owner - akan menambahkan chat ke blacklist
    if text_lower == "/stop":
        if message.from_user and message.from_user.id == OWNER_ID:
            blacklisted_chats.add(chat_id)
            if chat_id in pending_timers:
                pending_timers[chat_id].cancel()
                pending_timers.pop(chat_id, None)
            pending_flags.pop(chat_id, None)
            logging.info(f"Bot deactivated in chat {chat_id} by owner.")
            await client.send_message(chat_id, "Bot deactivated.")
        else:
            logging.info(f"/stop received from non-owner in chat {chat_id}; ignoring.")
        return

    # Jika chat dalam blacklist, abaikan pesan
    if chat_id in blacklisted_chats:
        logging.info(f"Ignoring message from blacklisted chat {chat_id}")
        return
        
    # Variabel untuk menandai apakah kita sudah mengirim respon untuk pesan ini
    already_processed = False
    
    # Rule 1: Jika pesan diawali dengan "Partner found 🐵"
    if text.startswith("Partner found 🐵"):
        # Jika sudah ada pending timer, artinya rule 1 sedang diproses, jadi abaikan pesan ini.
        if chat_id in pending_timers:
            logging.info(f"Duplicate 'Partner found' message in chat {chat_id}; ignoring.")
            return
        
        delay = random.uniform(3, 7)
        logging.info(f"Rule 1 triggered in chat {chat_id}. Waiting for {delay:.2f} seconds before sending keyword.")
        await asyncio.sleep(delay)
        
        variants = [
            "co 22",
            "cowo 22",
            "cowok 22",
            "cwo 22",
            "cwok 22",
            "co22",
            "cowo22",
            "cowok22",
            "cwo22",
            "cwok22"
        ]
        chosen_variant = random.choice(variants)
        logging.info(f"Sending chosen variant '{chosen_variant}' to chat {chat_id}.")
        await client.send_message(chat_id, chosen_variant)
        
        pending_flags[chat_id] = True
        task = asyncio.create_task(send_search_after_timeout(client, chat_id))
        pending_timers[chat_id] = task
        return

    # Rule 2: Jika pesan mengandung keyword exact (menggunakan regex)
    if keyword_pattern.search(text) and not already_processed:
        logging.info(f"Rule 2 triggered in chat {chat_id} by exact match. Sending '/next'.")
        pending_flags[chat_id] = False  # Nonaktifkan timer /search
        if chat_id in pending_timers:
            pending_timers[chat_id].cancel()
            pending_timers.pop(chat_id, None)
        await client.send_message(chat_id, "/next")
        already_processed = True
        return
        
    # Rule 3: Jika pesan menyatakan partner telah berhenti dialog
    if text.startswith("*Your partner has stopped the dialog Type /search to find a new partner*") and not already_processed:
        logging.info(f"Rule 3 triggered in chat {chat_id}. Partner stopped dialog. Sending '/search'.")
        # Batalkan pending timer jika ada
        if chat_id in pending_timers:
            pending_timers[chat_id].cancel()
            pending_timers.pop(chat_id, None)
            pending_flags.pop(chat_id, None)
            
        # Tunggu sebentar sebelum mengirim /search
        delay = random.uniform(1, 3)
        await asyncio.sleep(delay)
        await client.send_message(chat_id, "/search")
        already_processed = True
        return
    
    # Untuk pesan lain yang tidak sesuai dengan kondisi sebelumnya
    # Batalkan timer /search jika ada pesan dari chat yang sedang menunggu
    if not already_processed and chat_id in pending_timers and pending_flags.get(chat_id, False):
        logging.info(f"Received non-matching message in chat {chat_id}. Cancelling scheduled /search.")
        pending_flags[chat_id] = False  # Nonaktifkan flag /search
        pending_timers[chat_id].cancel()
        pending_timers.pop(chat_id, None)
        return

def shutdown_handler(sig, frame):
    """
    Handler untuk menangani sinyal shutdown agar bot berhenti secara graceful.
    """
    logging.info(f"Received signal {sig}. Shutting down gracefully...")
    for task in pending_timers.values():
        task.cancel()
    app.stop()
    sys.exit(0)

if __name__ == "__main__":
    # Daftarkan signal handler untuk SIGINT, SIGTERM, dan SIGTSTP
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGTSTP, shutdown_handler)

    while True:
        try:
            app.run()
            break
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                logging.warning("Database locked. Waiting 2 seconds before retrying...")
                time.sleep(2)
            else:
                raise
