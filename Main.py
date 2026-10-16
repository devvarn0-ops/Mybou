import os
import sqlite3
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime

# --- CONFIGURATION ---
BOT_TOKEN = "8714803932:AAEX0uvRlOndjyh2UBQX8946YOOuxxoBW8U" # Example: "712345678:ABC-DEF..."
CHANNEL_ID = -1004306909977 # Apne Channel ka ID yahan daalein (negative sign ke saath)
ADMIN_IDS = [7850454736] # Apna Telegram ID yahan daalein (integer mein)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE SETUP ---
conn = sqlite3.connect("bot_data.db", check_same_thread=False)
cursor = conn.cursor()

def init_db():
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            referrer_id INTEGER,
            referral_count INTEGER DEFAULT 0,
            is_joined_channel INTEGER DEFAULT 0,
            last_check_time TIMESTAMP
        )
    ''')
    conn.commit()

init_db()

# --- BOT INIT ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    now = datetime.now().isoformat()
    
    # Extract Referrer if present in start args
    referrer_id = None
    if message.text and len(message.text.split()) > 1:
        try:
            # Format expected: /start ref_12345 or just /start 12345
            raw_ref = message.text.split()[1].replace("ref_", "")
            referrer_id = int(raw_ref)
        except ValueError:
            pass

    # Insert or Update user
    cursor.execute('''
        INSERT INTO users (id, username, last_check_time, referrer_id) VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET 
            username = excluded.username, 
            last_check_time = excluded.last_check_time,
            referrer_id = COALESCE(excluded.referrer_id, referrer_id)
    ''', (user_id, message.from_user.username, now, referrer_id))
    
    conn.commit()

    # Check if already joined channel (optimization)
    cursor.execute("SELECT is_joined_channel FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row and row[0] == 1:
        await show_main_menu(message)
    else:
        await ask_join_channel(message)

async def ask_join_channel(message: Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="🔗 Join Channel", url=f"https://t.me/{await get_channel_username()}")
    kb.button(text="✅ I have Joined", callback_data="check_join")
    kb.adjust(1, repeat=True)
    
    await message.answer(
        f"👋 Hello {message.from_user.first_name}!\n\n"
        "Pehle hamare Channel ko join karo. Phir neeche 'I have Joined' dabana.",
        reply_markup=kb.as_markup()
    )

async def show_main_menu(message: Message):
    user_id = message.from_user.id
    
    # Get Referral Count
    cursor.execute("SELECT referral_count FROM users WHERE id = ?", (user_id,))
    res = cursor.fetchone()
    count = res[0] if res else 0
    
    # Generate Referral Link
    bot_username = (await bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    status_text = ""
    if count >= 6:
        status_text = "\n🎉 **Congratulations!** You unlocked the reward!"
    else:
        status_text = f"\n📊 Progress: {count}/6 Referals needed."

    kb = InlineKeyboardBuilder()
    # Using switch_inline_query_current_chat so they can paste it easily
    kb.button(text="🔗 Copy Referral Link", switch_inline_query_current_chat=ref_link.split("?")[1])
    kb.button(text="🏆 Claim Reward", callback_data="claim_reward")
    kb.button(text="👥 My Stats", callback_data="my_stats")
    kb.adjust(1, repeat=True)

    await message.answer(
        f"✅ Welcome back! You are verified.\n\n"
        f"Apne doston ko invite karo. Jab wo join karenge, tumhara count badhega.\n"
        f"{status_text}",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )

@dp.callback_query(lambda c: c.data == "check_join")
async def cb_check_join(callback: CallbackQuery):
    # Re-check logic
    user_id = callback.from_user.id
    is_joined = await check_if_joined(user_id)
    
    if is_joined:
        cursor.execute("UPDATE users SET is_joined_channel = 1 WHERE id = ?", (user_id,))
        
        # If this user was referred by someone, increment that person's count
        cursor.execute("SELECT referrer_id FROM users WHERE id = ?", (user_id,))
        ref_row = cursor.fetchone()
        if ref_row and ref_row[0]:
            referrer_id = ref_row[0]
            cursor.execute("UPDATE users SET referral_count = referral_count + 1 WHERE id = ?", (referrer_id,))
            
        conn.commit()
        
        await callback.message.edit_text("✅ Verified! Now you can access the bot.", 
                                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                             [InlineKeyboardButton(text="Go to Main Menu", callback_data="go_main")]
                                         ]))
    else:
        await callback.answer("Still not joined! Please join first.", show_alert=True)

@dp.callback_query(F.data == "go_main")
async def cb_go_main(callback: CallbackQuery):
    await show_main_menu(callback.message)

@dp.callback_query(F.data == "claim_reward")
async def cb_claim(callback: CallbackQuery):
    user_id = callback.from_user.id
    cursor.execute("SELECT referral_count FROM users WHERE id = ?", (user_id,))
    res = cursor.fetchone()
    count = res[0] if res else 0
    
    if count >= 6:
        # Give the reward link
        reward_link = "https://t.me/+tZuVyQkvY-wwZmE9" # Change this to your actual reward channel
        kb = InlineKeyboardBuilder()
        kb.button(text="🎁 Your Reward Link", url=reward_link)
        await callback.message.edit_text(f"Great! Here is your reward:\n\n{reward_link}", 
                                        reply_markup=kb.as_markup())
    else:
        await callback.answer(f"You need 6 refs. Currently: {count}", show_alert=True)

@dp.callback_query(F.data == "my_stats")
async def cb_my_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    cursor.execute("SELECT referral_count FROM users WHERE id = ?", (user_id,))
    res = cursor.fetchone()
    count = res[0] if res else 0
    
    await callback.answer(f"Your Referrals: {count}/6", show_alert=True)

# --- ADMIN PANEL ---
@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await show_admin_panel(message)

async def show_admin_panel(message: Message):
    cursor.execute("""
        SELECT u.id, u.username, u.referral_count 
        FROM users u 
        WHERE u.referral_count > 0 
        ORDER BY u.referral_count DESC
    """)
    rows = cursor.fetchall()
    
    if not rows:
        text = "No referrals found yet."
    else:
        text = "**Top Referrers:**\n\n"
        for row in rows:
            uid, uname, cnt = row
            text += f"ID: {uid} | User: @{uname} | Refs: {cnt}\n"
            
    kb = InlineKeyboardBuilder()
    kb.button(text="Refresh", callback_data="refresh_admin")
    kb.adjust(1)
    
    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "refresh_admin")
async def cb_refresh_admin(callback: CallbackQuery):
    await callback.message.delete()
    await show_admin_panel(callback.message)

# --- CHANNEL MEMBER EVENTS (The Core Logic) ---

@dp.channel_member()
async def handle_channel_change(event: types.ChatMemberUpdated):
    """
    Triggers when anyone joins or leaves the monitored channel.
    """
    chat_id = event.chat.id
    if chat_id != CHANNEL_ID:
        return
        
    user_id = event.from_user.id
    new_status = event.new_chat_member.status
    old_status = event.old_chat_member.status
    
    # Check if user exists in DB
    cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not cursor.fetchone():
        # New user, create entry
        cursor.execute("INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)", 
                        (user_id, event.from_user.username))
        conn.commit()
        return

    if new_status == 'member' and old_status not in ('member', 'administrator'):
        # User Joined
        cursor.execute("UPDATE users SET is_joined_channel = 1 WHERE id = ?", (user_id,))
        
        # Check if they were referred
        cursor.execute("SELECT referrer_id FROM users WHERE id = ?", (user_id,))
        ref_row = cursor.fetchone()
        
        if ref_row and ref_row[0]:
            referrer_id = ref_row[0]
            # Increment referrer count
            cursor.execute("UPDATE users SET referral_count = referral_count + 1 WHERE id = ?", (referrer_id,))
            logger.info(f"User {user_id} joined. Referrer {referrer_id} count incremented.")
            
    elif new_status not in ('member', 'administrator') and old_status in ('member', 'administrator'):
        # User Left
        cursor.execute("UPDATE users SET is_joined_channel = 0 WHERE id = ?", (user_id,))
        
        # Decrement referrer count if applicable
        cursor.execute("SELECT referrer_id FROM users WHERE id = ?", (user_id,))
        ref_row = cursor.fetchone()
        
        if ref_row and ref_row[0]:
            referrer_id = ref_row[0]
            cursor.execute("UPDATE users SET referral_count = MAX(0, referral_count - 1) WHERE id = ?", (referrer_id,))
            logger.info(f"User {user_id} left. Referrer {referrer_id} count decremented.")

    conn.commit()

async def check_if_joined(user_id):
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

async def get_channel_username():
    try:
        channel = await bot.get_chat(CHANNEL_ID)
        return channel.username
    except Exception:
        return "YOUR_CHANNEL_USERNAME" # Fallback

if __name__ == "__main__":
    dp.run_polling(bot)
