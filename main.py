import asyncio
import logging
import re
import sys
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# --- تنظیمات ربات ---
BOT_TOKEN = "8687413770"
ADMIN_GROUP_ID = -1004411883938
PORT = 10000

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# وضعیت‌های کاربر (FSM)
class SupportStates(StatesGroup):
    waiting_for_feedback = State()
    waiting_for_complaint = State()

# کیبورد اصلی
def main_menu():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="💬 ارتباط با پشتیبانی"), types.KeyboardButton(text="✍️ ثبت نظر و پیشنهاد")],
            [types.KeyboardButton(text="⚠️ ثبت شکایت"), types.KeyboardButton(text="ℹ️ درباره ما")],
        ],
        resize_keyboard=True
    )

def cancel_menu():
    return types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="❌ انصراف")]],
        resize_keyboard=True
    )

# وب‌سرور سبک برای باز نگه داشتن پورت در رندر
async def handle_ping(request):
    return web.Response(text="TonabiBot is running successfully!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logging.info(f"Web server started on port {PORT}")

async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
    )
    dp = Dispatcher(storage=MemoryStorage())

    # شروع ربات یا انصراف
    @dp.message(F.text.in_(["/start", "❌ انصراف"]))
    async def start_handler(message: types.Message, state: FSMContext):
        await state.clear()
        await message.answer(
            "سلام! به بخش پشتیبانی فروشگاه عطر **تونابی** خوش آمدید. 🌹\n\n"
            "لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
            reply_markup=main_menu()
        )

    # درباره ما
    @dp.message(F.text == "ℹ️ درباره ما")
    async def about_us(message: types.Message):
        await message.answer(
            "🌸 **فروشگاه عطر و ادکلن تونابی**\n\n"
            "ارائه‌دهنده بهترین و باکیفیت‌ترین عطرهای روز دنیا با مناسب‌ترین قیمت.\n"
            "همیشه در کنار شما هستیم تا بهترین رایحه را انتخاب کنید.",
            reply_markup=main_menu()
        )

    # درخواست ارتباط با پشتیبانی
    @dp.message(F.text == "💬 ارتباط با پشتیبانی")
    async def support_request(message: types.Message, state: FSMContext):
        await state.set_state(SupportStates.waiting_for_feedback)
        await message.answer(
            "لطفاً پیام یا سوال خود را ارسال کنید تا برای تیم پشتیبانی ارسال شود:",
            reply_markup=cancel_menu()
        )

    # ثبت نظر و پیشنهاد
    @dp.message(F.text == "✍️ ثبت نظر و پیشنهاد")
    async def feedback_request(message: types.Message, state: FSMContext):
        await state.set_state(SupportStates.waiting_for_feedback)
        await message.answer(
            "نظر، پیشنهاد یا انتقاد خود را برای ما بنویسید:",
            reply_markup=cancel_menu()
        )

    # ثبت شکایت
    @dp.message(F.text == "⚠️ ثبت شکایت")
    async def complaint_request(message: types.Message, state: FSMContext):
        await state.set_state(SupportStates.waiting_for_complaint)
        await message.answer(
            "لطفاً متن شکایت خود را به همراه اطلاعات لازم ارسال فرمایید:",
            reply_markup=cancel_menu()
        )

    # دریافت پیام‌های مرحله‌ای (پشتیبانی/شکایت) و ارسال به گروه
    @dp.message(SupportStates.waiting_for_feedback)
    @dp.message(SupportStates.waiting_for_complaint)
    async def forward_feedback_to_admin(message: types.Message, state: FSMContext):
        current_state = await state.get_state()
        title = "⚠️ [شکایت جدید]" if current_state == SupportStates.waiting_for_complaint.state else "💬 [پیام پشتیبانی / نظر]"
        
        user = message.from_user
        username = f"@{user.username}" if user.username else "ندارد"
        text_content = message.text or message.caption or "(بدون متن)"

        caption = (
            f"{title}\n\n"
            f"👤 نام: {user.full_name}\n"
            f"🔗 یوزرنیم: {username}\n"
            f"🆔 آیدی عددی: `{user.id}`\n\n"
            f"📝 متن پیام:\n{text_content}"
        )

        await bot.send_message(ADMIN_GROUP_ID, caption)
        await state.clear()
        await message.answer("✅ پیام شما با موفقیت برای پشتیبانی تونابی ارسال شد.", reply_markup=main_menu())

    # دریافت هر پیام متنی عادی دیگر از چت خصوصی و ارسال به گروه
    @dp.message(F.chat.type == "private")
    async def fallback_user_message(message: types.Message):
        user = message.from_user
        username = f"@{user.username}" if user.username else "ندارد"
        text_content = message.text or message.caption or "(بدون متن)"

        caption = (
            f"📩 [پیام کاربر]\n\n"
            f"👤 نام: {user.full_name}\n"
            f"🔗 یوزرنیم: {username}\n"
            f"🆔 آیدی عددی: `{user.id}`\n\n"
            f"📝 متن پیام:\n{text_content}"
        )
        await bot.send_message(ADMIN_GROUP_ID, caption)
        await message.answer("✅ پیام شما دریافت شد و به پشتیبانی منتقل گردید.", reply_markup=main_menu())

    # پاسخ ادمین با Reply در گروه تلگرام
    @dp.message(F.chat.id == ADMIN_GROUP_ID, F.reply_to_message)
    async def admin_reply_handler(message: types.Message):
        replied = message.reply_to_message
        if not replied or not (replied.text or replied.caption):
            return

        source_text = replied.text or replied.caption
        match = re.search(r"🆔 آیدی عددی:\s*`(\d+)`", source_text)
        if match:
            target_id = int(match.group(1))
            try:
                reply_text = message.text or message.caption or "پاسخ ارسال شد."
                await bot.send_message(
                    target_id,
                    f"💬 **پاسخ پشتیبانی تونابی:**\n\n{reply_text}"
                )
                await message.reply("✅ پاسخ برای کاربر ارسال گردید.")
            except Exception as e:
                await message.reply(f"❌ خطا در ارسال پاسخ به کاربر: {e}")

    # استارت همزمان وب‌سرور و دریافت پیام‌ها
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
