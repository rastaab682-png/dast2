# rasta_market_bot.py
# -*- coding: utf-8 -*-
"""
Rasta Market Bot (MVP)
- Collects: 4 photos + 1 video + city + price + condition (A/B/C/D)
- Sends preview to ADMIN with ✅/❌
- On approve -> posts to GROUP with a clean card + video
"""

import os
import re
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, ParseMode
from aiogram.utils import executor
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from dotenv import load_dotenv

# ---------- Config ----------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GROUP_ID = int(os.getenv("GROUP_ID", "0").strip() or "0")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0").strip() or "0")

if not BOT_TOKEN or GROUP_ID == 0 or ADMIN_ID == 0:
    raise SystemExit("Please set BOT_TOKEN, GROUP_ID, ADMIN_ID in .env")

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(bot, storage=MemoryStorage())
dp.middleware.setup(LoggingMiddleware())

# ---------- Helpers ----------
def normalize_price(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0

def approval_keyboard(ad_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ تأیید", callback_data=f"approve:{ad_id}"),
        InlineKeyboardButton("❌ رد", callback_data=f"reject:{ad_id}")
    )
    return kb

def cond_valid(c: str) -> bool:
    return c.upper() in {"A", "B", "C", "D"}

# ---------- FSM States ----------
class SellStates(StatesGroup):
    waiting_photos = State()
    waiting_video = State()
    waiting_city = State()
    waiting_price = State()
    waiting_condition = State()

# In-memory store for simplicity
SESS = {}
ADSEQ = 1000
def get_next_ad_id():
    global ADSEQ
    ADSEQ += 1
    return str(ADSEQ)

WELCOME_TEXT = (
    "سلام 👋 به <b>رستا مارکت</b> خوش اومدی!\n"
    "برای ثبت آگهی، فقط بنویس: <b>فروشنده‌ام</b>\n\n"
    "الزامی‌ها:\n"
    "• ۴ عکس واضح\n• ۱ ویدئو تست 20–40 ثانیه\n• شهر\n• قیمت\n• وضعیت کالا: A/B/C/D"
)

RULES_TEXT = (
    "🔒 <b>قوانین معامله امن</b>\n"
    "1) پرداخت فقط طبق راهنمای ادمین/بات؛ خارج از مسیر رسمی واریز نکنید.\n"
    "2) حضوری = رسید کتبی | ارسال = بیمه + کدرهگیری.\n"
    "3) ۴۸ ساعت مهلت تست؛ مغایرت = برگشت.\n"
    "4) گزارش تخلف = رسیدگی فوری."
)

# ---------- Handlers ----------
@dp.message_handler(commands=['start', 'help'])
async def cmd_start(msg: types.Message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🧰 فروشنده‌ام", callback_data="role:seller"),
        InlineKeyboardButton("🛒 خریدارم", callback_data="role:buyer"),
        InlineKeyboardButton("📜 قوانین معامله امن", callback_data="rules")
    )
    await msg.reply(WELCOME_TEXT, reply_markup=kb)

@dp.callback_query_handler(Text(startswith="rules"))
async def on_rules(call: types.CallbackQuery):
    await call.message.answer(RULES_TEXT)
    await call.answer()

@dp.callback_query_handler(Text(startswith="role:buyer"))
async def role_buyer(call: types.CallbackQuery):
    await call.message.answer("به‌زودی فیلتر خرید هم اضافه می‌شه. فعلاً برای ثبت آگهی فروش «🧰 فروشنده‌ام» رو بزن.")
    await call.answer()

@dp.callback_query_handler(Text(startswith="role:seller"))
async def role_seller(call: types.CallbackQuery):
    await start_seller_flow(call.message)
    await call.answer()

@dp.message_handler(lambda m: m.text and "فروشنده" in m.text)
async def start_seller_text(msg: types.Message):
    await start_seller_flow(msg)

async def start_seller_flow(msg: types.Message):
    uid = msg.from_user.id
    SESS[uid] = {"photos": [], "video": None, "city": None, "price": None, "cond": None, "ad_id": get_next_ad_id()}
    await SellStates.waiting_photos.set()
    await msg.reply("✅ شروع شد! لطفاً ۴ عکس واضح رو یکی‌یکی بفرست.")

@dp.message_handler(state=SellStates.waiting_photos, content_types=['photo'])
async def handle_photos(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    sess = SESS[uid]
    if len(sess["photos"]) < 4:
        sess["photos"].append(msg.photo[-1].file_id)
        await msg.reply(f"📷 عکس {len(sess['photos'])}/4 ذخیره شد.")
    if len(sess["photos"]) == 4:
        await SellStates.waiting_video.set()
        await msg.reply("عالی! حالا ویدئو تست رو بفرست.")

@dp.message_handler(state=SellStates.waiting_video, content_types=['video'])
async def handle_video(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    SESS[uid]["video"] = msg.video.file_id
    await SellStates.waiting_city.set()
    await msg.reply("📍 شهر رو بنویس.")

@dp.message_handler(state=SellStates.waiting_city, content_types=['text'])
async def handle_city(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    SESS[uid]["city"] = msg.text.strip()
    await SellStates.waiting_price.set()
    await msg.reply("💳 قیمت رو بنویس (فقط عدد).")

@dp.message_handler(state=SellStates.waiting_price, content_types=['text'])
async def handle_price(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    price = normalize_price(msg.text)
    if price <= 0:
        await msg.reply("قیمت نامعتبره.")
        return
    SESS[uid]["price"] = price
    await SellStates.waiting_condition.set()
    await msg.reply("🔎 وضعیت کالا: A / B / C / D")

@dp.message_handler(state=SellStates.waiting_condition, content_types=['text'])
async def handle_condition(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    cond = msg.text.strip().upper()
    if not cond_valid(cond):
        await msg.reply("فقط A یا B یا C یا D.")
        return
    SESS[uid]["cond"] = cond
    s = SESS[uid]

    # Preview for ADMIN
    caption = (
        f"🔎 <b>پیش‌نمایش آگهی جدید</b>\n"
        f"آیدی آگهی: <b>#{s['ad_id']}</b>\n"
        f"📍 شهر: {s['city']}\n"
        f"💳 قیمت: {s['price']:,} تومان\n"
        f"🔎 وضعیت: {s['cond']}\n"
        f"ارسال‌کننده: @{msg.from_user.username or msg.from_user.id}"
    )
    media = []
    for i, pid in enumerate(s["photos"]):
        if i == 0:
            media.append(InputMediaPhoto(pid, caption=caption, parse_mode=ParseMode.HTML))
        else:
            media.append(InputMediaPhoto(pid))
    await bot.send_media_group(ADMIN_ID, media)
    await bot.send_message(ADMIN_ID, f"آگهی #{s['ad_id']} را تأیید می‌کنید؟", reply_markup=approval_keyboard(s["ad_id"]))
    await msg.reply("آگهی‌ات برای تأیید ارسال شد.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data.startswith(("approve:", "reject:")))
async def on_approval(call: types.CallbackQuery):
    action, ad_id = call.data.split(":", 1)
    uid = None
    for k, v in list(SESS.items()):
        if v.get("ad_id") == ad_id:
            uid = k
            break
    if not uid:
        await call.answer("این آگهی پیدا نشد.", show_alert=True)
        return
    s = SESS[uid]
    if action == "approve":
        caption = (
            f"🧰 آگهی <b>#{s['ad_id']}</b>\n"
            f"🔎 وضعیت: <b>{s['cond']}</b> | 📍 {s['city']}\n"
            f"💳 قیمت: <b>{s['price']:,}</b> تومان\n"
            f"— — —\n"
            f"🤝 «درخواست خرید #{s['ad_id']}» را در دایرکت ارسال کنید."
        )
        await bot.send_photo(GROUP_ID, s["photos"][0], caption=caption)
        await bot.send_video(GROUP_ID, s["video"], caption="🎥 ویدئو تست")
        await bot.send_message(uid, "✅ آگهی‌ات تایید و در گروه منتشر شد.")
        await call.message.edit_text(f"✅ آگهی #{s['ad_id']} منتشر شد.")
    else:
        await bot.send_message(uid, "❌ آگهی‌ات رد شد.")
        await call.message.edit_text(f"❌ آگهی #{s['ad_id']} رد شد.")
    SESS.pop(uid, None)
    await call.answer()

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
