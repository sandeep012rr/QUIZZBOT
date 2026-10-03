import os
import re
import time
import threading
import telebot
from pypdf import PdfReader
from docx import Document
from flask import Flask

# ================= RENDER PORT DUMMY SERVER =================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Quiz Bot is live and running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()
# ============================================================

# अपना नया/सुरक्षित Bot Token और Channel ID यहाँ डालें
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7589769291:AAFSErrT1V5Wt1eGZ235vV4M2-QZuPALhTM")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@FIRST_GARDE_SPL")

bot = telebot.TeleBot(BOT_TOKEN)

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
    """
    यूजर के दिए गए सटीक फॉर्मेट से बिना AI के हूबहू सवाल पार्स करता है।
    Format:
    Question: ...
    (a) ...
    (b) ...
    (c) ...
    (d) ...
    Answer: a/b/c/d
    Solution: ...
    """
    quizzes = []
    
    # "Question:" शब्द के आधार पर स्प्लिट करें
    raw_blocks = re.split(r'\n(?=Question:)', "\n" + text.strip())
    
    opt_map = {'a': 0, 'b': 1, 'c': 2, 'd': 3}

    for block in raw_blocks:
        if not block.strip() or "Question:" not in block:
            continue
        
        try:
            # 1. Question निकालें
            q_match = re.search(r'Question:\s*(.*?)(?=\([a-dA-D]\)|Answer:|$)', block, re.DOTALL)
            if not q_match:
                continue
            question = q_match.group(1).strip()
            
            # 2. Options निकालें: (a), (b), (c), (d)
            options = []
            opt_pattern = re.findall(r'\(([a-dA-D])\)\s*(.*?)(?=\([a-dA-D]\)|Answer:|Solution:|Key Points:|Positive Marks:|$)', block, re.DOTALL)
            
            for tag, opt_text in opt_pattern:
                clean_opt = opt_text.strip()
                if clean_opt:
                    options.append(clean_opt)

            # 3. Answer निकालें
            ans_match = re.search(r'Answer:\s*([a-dA-D])', block, re.IGNORECASE)
            if ans_match:
                ans_char = ans_match.group(1).lower()
                correct_id = opt_map.get(ans_char, 0)
            else:
                correct_id = 0

            # 4. Solution / Explanation निकालें
            sol_match = re.search(r'Solution:\s*(.*?)(?=Key Points:|Positive Marks:|Negative Marks:|\n\n|$)', block, re.DOTALL)
            explanation = sol_match.group(1).strip() if sol_match else ""

            # Telegram Quiz की कानूनी सीमाएँ (Length Limits)
            # Question <= 300 chars, Option <= 100 chars, Explanation <= 200 chars
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
    bot.reply_to(message, "नमस्ते! मुझे 'Question / (a)(b)(c)(d) / Answer / Solution' फॉर्मेट वाली PDF या DOCX फ़ाइल भेजें, मैं हूबहू वही प्रश्न सीधे चैनल पर क्विज़ पोल बनाकर पोस्ट कर दूँगा।")

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    local_path = None
    try:
        file_name = message.document.file_name.lower()
        if not (file_name.endswith('.pdf') or file_name.endswith('.docx')):
            bot.reply_to(message, "कृपया केवल PDF या DOCX फ़ाइल भेजें।")
            return

        status_msg = bot.reply_to(message, "⏳ फ़ाइल डाउनलोड की जा रही है...")

        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        local_path = f"temp_{int(time.time())}_{message.document.file_name}"
        with open(local_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        bot.edit_message_text("📖 फ़ाइल से हूबहू प्रश्न पढ़े जा रहे हैं...", chat_id=message.chat.id, message_id=status_msg.message_id)

        if local_path.lower().endswith('.pdf'):
            text = extract_text_from_pdf(local_path)
        else:
            text = extract_text_from_docx(local_path)

        # फाइल डिलीट करें
        if os.path.exists(local_path):
            os.remove(local_path)
            local_path = None

        # प्रश्नों को पार्स करें
        quizzes = parse_exact_mcqs(text)

        if not quizzes:
            bot.edit_message_text("❌ फ़ाइल में निर्धारित फॉर्मेट (Question, (a), (b), Answer) वाले प्रश्न नहीं मिले।", chat_id=message.chat.id, message_id=status_msg.message_id)
            return

        bot.edit_message_text(f"⚡ कुल {len(quizzes)} प्रश्न मिले हैं। चैनल पर पोस्टिंग शुरू हो रही है...", chat_id=message.chat.id, message_id=status_msg.message_id)

        total_posted = 0
        for idx, q in enumerate(quizzes, start=1):
            try:
                # Telegram Quiz Poll पोस्ट करें
                bot.send_poll(
                    chat_id=CHANNEL_ID,
                    question=f"{idx}. {q['question']}"[:300],
                    options=q['options'],
                    type='quiz',
                    correct_option_id=q['correct_id'],
                    explanation=q['explanation'] if q['explanation'] else None,
                    is_anonymous=True
                )
                total_posted += 1
                
                # चैनल में स्पैम ब्लॉक न हो इसलिए हर पोल के बीच 3 से 5 सेकंड का अंतराल
                time.sleep(3)

            except telebot.apihelper.ApiTelegramException as api_err:
                print(f"Telegram API Error on Q{idx}: {api_err}")
                # अगर चैनल में बॉट एडमिन नहीं है तो एरर आएगा
                if "chat not found" in str(api_err).lower() or "not a member" in str(api_err).lower() or "administrator" in str(api_err).lower():
                    bot.send_message(message.chat.id, f"⚠️ एरर: बॉट चैनल ({CHANNEL_ID}) में एडमिन नहीं है या चैनल यूजरनेम गलत है। कृपया बॉट को चैनल में Admin बनाएं।")
                    return
                time.sleep(3)
            except Exception as e:
                print(f"Post Error on Q{idx}: {e}")
                time.sleep(2)

        bot.send_message(message.chat.id, f"🎉 सफलतापूर्वक कुल {total_posted}/{len(quizzes)} प्रश्न चैनल पर अपलोड हो गए हैं!")

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
                
