import os
import re
import time
import threading
import telebot
from pypdf import PdfReader
from docx import Document
from flask import Flask

# ================= RENDER PORT SERVER =================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Quiz Bot is live and running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()
# ======================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
# डिफ़ॉल्ट चैनल (अगर यूजर कोई चैनल न बताए)
DEFAULT_CHANNEL = "@FIRST_GARDE_SPL"

bot = telebot.TeleBot(BOT_TOKEN)

# यूजर द्वारा सेट किए गए चैनल को याद रखने के लिए
user_channels = {}

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
            # 1. Question
            q_match = re.search(r'Question:\s*(.*?)(?=\([a-dA-D]\)|Answer:|$)', block, re.DOTALL)
            if not q_match:
                continue
            question = q_match.group(1).strip()

            # 2. Options
            options = []
            opt_pattern = re.findall(r'\(([a-dA-D])\)\s*(.*?)(?=\([a-dA-D]\)|Answer:|Solution:|Key Points:|Positive Marks:|$)', block, re.DOTALL)
            for tag, opt_text in opt_pattern:
                clean_opt = opt_text.strip()
                if clean_opt:
                    options.append(clean_opt)

            # 3. Answer
            ans_match = re.search(r'Answer:\s*([a-dA-D])', block, re.IGNORECASE)
            correct_id = opt_map.get(ans_match.group(1).lower(), 0) if ans_match else 0

            # 4. Solution
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
    current = user_channels.get(message.chat.id, DEFAULT_CHANNEL)
    text = (
        "नमस्ते! 👋\n\n"
        f"🎯 **वर्तमान चैनल:** `{current}`\n\n"
        "📌 **चैनल बदलने के 2 तरीके हैं:**\n"
        "1. फ़ाइल भेजते समय उसके **Caption** में चैनल लिखें (उदा. `@my_new_channel`)\n"
        "2. या कमांड भेजें: `/setchannel @my_new_channel`\n\n"
        "अब आप मुझे अपनी PDF/DOCX फ़ाइल भेज सकते हैं!"
    )
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['setchannel'])
def set_channel_cmd(message):
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.reply_to(
            message,
            "❌ कृपया चैनल का यूज़रनेम भी लिखें!\n\nउदाहरण:\n`/setchannel @my_quiz_channel`",
            parse_mode="Markdown"
        )
        return

    new_channel = parts[1].strip()
    if not new_channel.startswith("@") and not new_channel.startswith("-100"):
        new_channel = "@" + new_channel

    user_channels[message.chat.id] = new_channel
    bot.reply_to(
        message,
        f"✅ चैनल सफलतापूर्वक बदल दिया गया है!\n🎯 **नया चैनल:** `{new_channel}`\n\nअब जो भी फ़ाइल भेजेंगे, प्रश्न इसी चैनल पर जाएंगे। (ध्यान रहे कि बॉट उस चैनल में **Admin** होना चाहिए)",
        parse_mode="Markdown"
    )

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    local_path = None
    try:
        # 1. तय करें कि किस चैनल पर भेजना है
        target_channel = None

        # चेक करें क्या कैप्शन में चैनल दिया गया है?
        if message.caption:
            caption_text = message.caption.strip()
            # कैप्शन में से @username या channel id खोजें
            match = re.search(r'(@[a-zA-Z0-9_]+|-100\d+)', caption_text)
            if match:
                target_channel = match.group(1)

        # अगर कैप्शन में नहीं मिला, तो यूजर द्वारा सेट किया गया चैनल लें
        if not target_channel:
            target_channel = user_channels.get(message.chat.id, DEFAULT_CHANNEL)

        file_name = message.document.file_name.lower()
        if not (file_name.endswith('.pdf') or file_name.endswith('.docx')):
            bot.reply_to(message, "कृपया केवल PDF या DOCX फ़ाइल भेजें।")
            return

        status_msg = bot.reply_to(
            message,
            f"⏳ फ़ाइल डाउनलोड हो रही है...\n🎯 लक्ष्य चैनल: `{target_channel}`",
            parse_mode="Markdown"
        )

        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        local_path = f"temp_{int(time.time())}_{message.document.file_name}"
        with open(local_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        bot.edit_message_text(
            f"📖 फ़ाइल पढ़ी जा रही है...\n🎯 लक्ष्य चैनल: `{target_channel}`",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            parse_mode="Markdown"
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
                "❌ फ़ाइल में निर्धारित फॉर्मेट वाले प्रश्न नहीं मिले।",
                chat_id=message.chat.id,
                message_id=status_msg.message_id
            )
            return

        bot.edit_message_text(
            f"⚡ कुल {len(quizzes)} प्रश्न मिले हैं। `{target_channel}` पर पोस्टिंग शुरू हो रही है...",
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
                time.sleep(3)  # Telegram spam protection ke liye

            except telebot.apihelper.ApiTelegramException as api_err:
                err_str = str(api_err).lower()
                print(f"Telegram API Error on Q{idx}: {api_err}")
                if "chat not found" in err_str or "not a member" in err_str or "administrator" in err_str:
                    bot.send_message(
                        message.chat.id,
                        f"⚠️ **त्रुटि:** बॉट `{target_channel}` में एडमिन नहीं है या चैनल का नाम गलत है।\nकृपया बॉट को चैनल में Admin बनाएं।",
                        parse_mode="Markdown"
                    )
                    return
                time.sleep(3)
            except Exception as e:
                print(f"Post Error on Q{idx}: {e}")
                time.sleep(2)

        bot.send_message(
            message.chat.id,
            f"🎉 सफलतापूर्वक {total_posted}/{len(quizzes)} प्रश्न `{target_channel}` पर अपलोड हो गए हैं!",
            parse_mode="Markdown"
        )

    except Exception as e:
        print(f"General Error: {e}")
        bot.reply_to(message, f"❌ एरर: {e}")
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
            
