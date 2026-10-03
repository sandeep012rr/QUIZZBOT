import os
import re
import time
import json
import threading
import telebot
import requests
from pypdf import PdfReader
from docx import Document
from flask import Flask

# ================= RENDER PORT SERVER =================
# Render Free Web Service ko port chahiye hota hai taaki crash na ho
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Quiz Bot is running successfully on Render!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# Background thread me Flask server start karein
threading.Thread(target=run_web, daemon=True).start()
# ======================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "7589769291:AAFSErrT1V5Wt1eGZ235vV4M2-QZuPALhTM")
CHANNEL_ID = "@FIRST_GARDE_SPL"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")
MODEL_NAME = "qwen/qwen3.8-27b"

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

def extract_quizzes_robust(raw_text):
    quizzes = []
    if not raw_text:
        return quizzes

    cleaned = raw_text.strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json")[1].split("```")[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```")[1].split("```")[0].strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            for k in ["quizzes", "questions", "quiz", "data"]:
                if k in data and isinstance(data[k], list):
                    return data[k]
        elif isinstance(data, list):
            return data
    except Exception:
        pass

    pattern = re.compile(r'\{\s*"question"\s*:.*?"options"\s*:\s*\[.*?\].*?\}', re.DOTALL)
    matches = pattern.findall(raw_text)
    for m in matches:
        try:
            q_obj = json.loads(m)
            if "question" in q_obj and "options" in q_obj and len(q_obj["options"]) >= 2:
                quizzes.append(q_obj)
        except Exception:
            continue

    return quizzes

def fetch_5_questions(content_chunk, batch_no):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    prompt = f"""
आप एक शिक्षक भर्ती परीक्षा विशेषज्ञ हैं। 
नीचे दी गई पाठ्य सामग्री के आधार पर ठीक 5 बहुत कठिन, विश्लेषणात्मक (Hard Level) बहुविकल्पीय प्रश्न (MCQs) केवल शुद्ध हिंदी में तैयार करें (सेट {batch_no})।

नियम:
1. प्रत्येक प्रश्न में ठीक 4 विकल्प होने चाहिए।
2. प्रश्न और व्याख्या संक्षिप्त रखें।
3. केवल शुद्ध JSON फॉर्मेट दें।

JSON संरचना:
{{
  "quizzes": [
    {{
      "question": "कठिन प्रश्न यहाँ लिखें (संक्षिप्त)",
      "options": ["विकल्प A", "विकल्प B", "विकल्प C", "विकल्प D"],
      "correct_option_id": 0,
      "explanation": "संक्षिप्त व्याख्या"
    }}
  ]
}}

सामग्री:
{content_chunk}
"""

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You are a professional quiz maker. Always output valid JSON object."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 800
    }

    response = requests.post(url, headers=headers, json=payload, timeout=90)
    if response.status_code == 200:
        raw_content = response.json()["choices"][0]["message"]["content"]
        return extract_quizzes_robust(raw_content)
    else:
        raise Exception(f"Groq API {response.status_code}: {response.text[:150]}")

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "नमस्ते! मुझे कोई भी PDF या DOCX फ़ाइल भेजें, मैं 20 कठिन बहुविकल्पीय प्रश्न बनाकर सीधे चैनल पर पोस्ट कर दूँगा।")

@bot.message_handler(content_types=['document'])
def handle_docs(message):
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

        bot.edit_message_text("📖 फ़ाइल पढ़ी जा रही है...", chat_id=message.chat.id, message_id=status_msg.message_id)
        
        if local_path.lower().endswith('.pdf'):
            text = extract_text_from_pdf(local_path)
        else:
            text = extract_text_from_docx(local_path)

        if os.path.exists(local_path):
            os.remove(local_path)

        if len(text.strip()) < 50:
            bot.edit_message_text("❌ फ़ाइल में पर्याप्त टेक्स्ट नहीं मिला।", chat_id=message.chat.id, message_id=status_msg.message_id)
            return

        bot.edit_message_text("⚡ AI से 20 कठिन प्रश्न तैयार किए जा रहे हैं (4 सेट में)...", chat_id=message.chat.id, message_id=status_msg.message_id)

        text_len = len(text)
        chunk_size = max(1500, text_len // 4)
        chunks = [
            text[0 : chunk_size],
            text[chunk_size : chunk_size * 2] if text_len > chunk_size else text[0:chunk_size],
            text[chunk_size * 2 : chunk_size * 3] if text_len > chunk_size * 2 else text[0:chunk_size],
            text[chunk_size * 3 : chunk_size * 4] if text_len > chunk_size * 3 else text[0:chunk_size]
        ]

        total_posted = 0

        for batch_idx in range(4):
            try:
                bot.edit_message_text(f"📝 सेट {batch_idx + 1}/4 तैयार हो रहा है (अब तक {total_posted} पोस्ट हुए)...", chat_id=message.chat.id, message_id=status_msg.message_id)
                quizzes = fetch_5_questions(chunks[batch_idx][:3000], batch_idx + 1)
                
                for q in quizzes:
                    question = str(q.get("question", ""))[:255]
                    options = [str(opt)[:100] for opt in q.get("options", [])][:4]
                    correct_id = int(q.get("correct_option_id", 0))
                    explanation = str(q.get("explanation", ""))[:190]

                    if len(options) >= 2:
                        total_posted += 1
                        bot.send_poll(
                            chat_id=CHANNEL_ID,
                            question=f"Q{total_posted}. {question}",
                            options=options,
                            type='quiz',
                            correct_option_id=correct_id,
                            explanation=explanation,
                            is_anonymous=True
                        )
                        time.sleep(30)
            except Exception as be:
                print(f"Batch {batch_idx + 1} Error: {be}")
                time.sleep(5)

        bot.send_message(message.chat.id, f"🎉 कुल {total_posted} कठिन प्रश्न सफलतापूर्वक चैनल पर पोस्ट हो चुके हैं!")

    except Exception as e:
        print(f"Error: {e}")
        bot.reply_to(message, f"❌ एरर: {e}")

if __name__ == "__main__":
    print("Bot starting...")
    # Puraane kisi bhi pending webhook/conflict ko saaf karein
    try:
        bot.remove_webhook()
    except Exception as ex:
        print(f"Webhook clear error: {ex}")

    # Polling shuru karein
    bot.infinity_polling(skip_pending=True)
