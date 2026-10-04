import os
import re
import time
import threading
import telebot
from pypdf import PdfReader
from docx import Document
from flask import Flask

# ================= RENDER DUMMY WEB SERVER =================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Quiz Bot is live and running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()
# ============================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
DEFAULT_CHANNEL = "@FIRST_GARDE_SPL"

bot = telebot.TeleBot(BOT_TOKEN)

# User-specific settings store karne ke liye
user_channels = {}
user_delays = {}      # Default gap: 30 seconds
user_inter_msgs = {}  # Har 10 questions ke baad aane wali post

def extract_text_from_pdf(file_path):
    text = ""
    try:
        reader = PdfReader(file_path)
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
    except Exception as e:
        print(f"PDF Error: {e}")
    return text

def extract_text_from_docx(file_path):
    text = ""
    try:
        doc = Document(file_path)
        for p in doc.paragraphs:
            if p.text:
                text += p.text + "\n"
    except Exception as e:
        print(f"DOCX Error: {e}")
    return text

def parse_exact_mcqs(text):
    quizzes = []
    raw_blocks = re.split(r'\n(?=Question:)', "\n" + text.strip())
    opt_map = {'a': 0, 'b': 1, 'c': 2, 'd': 3}

    for block in raw_blocks:
        if not block.strip() or "Question:" not in block:
            continue
        try:
            # 1. Question extract karein
            q_match = re.search(r'Question:\s*(.*?)(?=\([a-dA-D]\)|Answer:|$)', block, re.DOTALL)
            if not q_match:
                continue
            question = q_match.group(1).strip()

            # 2. Options extract karein
            options = []
            opt_pattern = re.findall(r'\(([a-dA-D])\)\s*(.*?)(?=\([a-dA-D]\)|Answer:|Solution:|Key Points:|Positive Marks:|$)', block, re.DOTALL)
            for tag, opt_text in opt_pattern:
                clean_opt = opt_text.strip()
                if clean_opt:
                    options.append(clean_opt)

            # 3. Answer extract karein
            ans_match = re.search(r'Answer:\s*([a-dA-D])', block, re.IGNORECASE)
            correct_id = opt_map.get(ans_match.group(1).lower(), 0) if ans_match else 0

            # 4. Explanation extract karein
            sol_match = re.search(r'Solution:\s*(.*?)(?=Key Points:|Positive Marks:|Negative Marks:|\n\n|$)', block, re.DOTALL)
            explanation = sol_match.group(1).strip() if sol_match else ""

            if question and len(options) >= 2:
                quizzes.append({
                    "question": question[:290],
                    "options": [opt[:98] for opt in options[:4]],
                    "correct_id": min(correct_id, len(options) - 1),
                    "explanation": explanation[:195]
                })
        except Exception as err:
            print(f"Parsing item error: {err}")
            continue

    return quizzes

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    current_chan = user_channels.get(message.chat.id, DEFAULT_CHANNEL)
    current_delay = user_delays.get(message.chat.id, 30)
    current_msg = user_inter_msgs.get(message.chat.id, "Set nahi hai (None)")

    help_text = (
        "🤖 *Quiz Bot Control Panel & Help Menu*\n\n"
        "📊 *Aapka Current Setup:*\n"
        f"• 🎯 Target Channel: `{current_chan}`\n"
        f"• ⏱ Per Question Delay: `{current_delay}` seconds\n"
        f"• 📢 10-Question Interval Post: `{current_msg[:45]}...`\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🛠 *Sabhi Commands ki List:*\n\n"
        "1️⃣ `/setchannel @channel_name`\n"
        "👉 Kisi bhi channel par quiz bhejne ke liye channel set karein.\n"
        "Example: `/setchannel @MyExamChannel`\n\n"
        "2️⃣ `/setdelay <seconds>`\n"
        "👉 Har ek question ke beech ka time gap set karein (min 5s).\n"
        "Example: `/setdelay 45`\n\n"
        "3️⃣ `/setmsg <aapka text>`\n"
        "👉 Har 10 questions ke baad channel par auto-post hone wala custom message set karein.\n"
        "Example:\n`/setmsg Hamare group @MyGroup ko join karein!`\n\n"
        "4️⃣ `/delmsg`\n"
        "👉 10-question interval wale message ko band/delete karne ke liye.\n\n"
        "5️⃣ `/help` ya `/start`\n"
        "👉 Yeh command list aur current settings dekhne ke liye.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📂 *File Kaise Bhejein:*\n"
        "Bas apni `PDF` ya `DOCX` file bot ko send kar dein. Bot questions ko extract karke set kiye gaye channel par automatically poll post kar dega!"
    )
    bot.reply_to(message, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['setchannel'])
def set_channel_cmd(message):
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Channel username likhna zaroori hai!\nExample: `/setchannel @MyQuizChannel`", parse_mode="Markdown")
        return
    new_channel = parts[1].strip()
    if not new_channel.startswith("@") and not new_channel.startswith("-100"):
        new_channel = "@" + new_channel
    user_channels[message.chat.id] = new_channel
    bot.reply_to(message, f"✅ Target Channel set ho gaya: `{new_channel}`\n(Dhyan rahe ki bot channel me *Admin* hona chahiye).", parse_mode="Markdown")

@bot.message_handler(commands=['setdelay'])
def set_delay_cmd(message):
    parts = message.text.strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.reply_to(message, "❌ Seconds me number likhein!\nExample: `/setdelay 45`", parse_mode="Markdown")
        return
    sec = int(parts[1])
    if sec < 5:
        bot.reply_to(message, "⚠️ Telegram spam se bachne ke liye kam se kam 5 seconds rakhein.")
        return
    user_delays[message.chat.id] = sec
    bot.reply_to(message, f"✅ Time duration set ho gaya: Har question ke beech `{sec}` seconds ka gap rahega.", parse_mode="Markdown")

@bot.message_handler(commands=['setmsg'])
def set_interval_message(message):
    msg_content = message.text.replace('/setmsg', '', 1).strip()
    if not msg_content:
        bot.reply_to(message, "❌ Message likhna zaroori hai!\nExample:\n`/setmsg Join our channel @abc for daily PDFs!`", parse_mode="Markdown")
        return
    user_inter_msgs[message.chat.id] = msg_content
    bot.reply_to(message, f"✅ Interval message set ho gaya! Ab har 10 question ke baad yeh post jayegi:\n\n{msg_content}")

@bot.message_handler(commands=['delmsg'])
def delete_interval_message(message):
    user_inter_msgs.pop(message.chat.id, None)
    bot.reply_to(message, "✅ Interval message hata diya gaya hai. Ab sirf questions post honge.")

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    local_path = None
    try:
        target_channel = user_channels.get(message.chat.id, DEFAULT_CHANNEL)
        delay_sec = user_delays.get(message.chat.id, 30)
        custom_interval_post = user_inter_msgs.get(message.chat.id, None)

        # File caption me direct channel check karein
        if message.caption:
            match = re.search(r'(@[a-zA-Z0-9_]+|-100\d+)', message.caption.strip())
            if match:
                target_channel = match.group(1)

        file_name = message.document.file_name.lower()
        if not (file_name.endswith('.pdf') or file_name.endswith('.docx')):
            bot.reply_to(message, "Kripya kewal PDF ya DOCX file bhejein.")
            return

        status_msg = bot.reply_to(
            message,
            f"⏳ File download ho rahi hai...\n🎯 Channel: `{target_channel}`\n⏱ Gap: `{delay_sec}s`",
            parse_mode="Markdown"
        )

        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        local_path = f"temp_{int(time.time())}_{message.document.file_name}"
        with open(local_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        bot.edit_message_text(
            "📖 File se questions extract kiye ja rahe hain...",
            chat_id=message.chat.id,
            message_id=status_msg.message_id
        )

        if local_path.lower().endswith('.pdf'):
            text = extract_text_from_pdf(local_path)
        else:
            text = extract_text_from_docx(local_path)

        if os.path.exists(local_path):
            os.remove(local_path)
            local_path = None

        quizzes = parse_exact_mcqs(text)

        if not quizzes:
            bot.edit_message_text(
                "❌ File me format match nahi hua (Question, (a), (b), Answer format chahiye).",
                chat_id=message.chat.id,
                message_id=status_msg.message_id
            )
            return

        bot.edit_message_text(
            f"⚡ Total {len(quizzes)} questions mile hain.\n`{target_channel}` par posting shuru ho rahi hai...",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            parse_mode="Markdown"
        )

        total_posted = 0
        for idx, q in enumerate(quizzes, start=1):
            try:
                bot.send_poll(
                    chat_id=target_channel,
                    question=f"{idx}. {q['question']}"[:300],
                    options=q['options'],
                    type='quiz',
                    correct_option_id=q['correct_id'],
                    explanation=q['explanation'] if q['explanation'] else None,
                    is_anonymous=True
                )
                total_posted += 1

                # Har 10 questions ke baad custom message bhejna
                if idx % 10 == 0 and custom_interval_post:
                    time.sleep(3)
                    bot.send_message(chat_id=target_channel, text=custom_interval_post)

                # Question delay
                time.sleep(delay_sec)

            except telebot.apihelper.ApiTelegramException as api_err:
                err_str = str(api_err).lower()
                print(f"Telegram API Error on Q{idx}: {api_err}")
                if "chat not found" in err_str or "not a member" in err_str or "administrator" in err_str:
                    bot.send_message(
                        message.chat.id,
                        f"⚠️ Error: Bot `{target_channel}` me admin nahi hai ya username galat hai.",
                        parse_mode="Markdown"
                    )
                    return
                time.sleep(5)
            except Exception as e:
                print(f"Post Error on Q{idx}: {e}")
                time.sleep(3)

        bot.send_message(
            message.chat.id,
            f"🎉 Success! Total {total_posted}/{len(quizzes)} questions post ho chuke hain `{target_channel}` par.",
            parse_mode="Markdown"
        )

    except Exception as e:
        print(f"General Error: {e}")
        bot.reply_to(message, f"❌ Error: {e}")
    finally:
        if local_path and os.path.exists(local_path):
            os.remove(local_path)

if __name__ == "__main__":
    print("Bot is starting...")
    try:
        bot.remove_webhook()
    except Exception as ex:
        print(f"Webhook clear error: {ex}")

    bot.infinity_polling(skip_pending=True)
