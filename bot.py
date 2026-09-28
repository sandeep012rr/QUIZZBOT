import os
import re
import time
import json
import telebot
import requests
from pypdf import PdfReader
from docx import Document

BOT_TOKEN = "7589769291:AAFSErrT1V5Wt1eGZ235vV4M2-QZuPALhTM"
CHANNEL_ID = "@FIRST_GARDE_SPL"
GROQ_API_KEY = "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"

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

def call_groq_single(model_name, prompt, max_tokens=850):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You are an expert exam quiz creator. Always return ONLY a valid JSON object with quizzes array."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": max_tokens
    }
    response = requests.post(url, headers=headers, json=payload, timeout=90)
    if response.status_code == 200:
        raw_content = response.json()["choices"][0]["message"]["content"]
        return extract_quizzes_robust(raw_content)
    else:
        raise Exception(f"{model_name} {response.status_code}: {response.text[:200]}")

def generate_quiz_with_groq(text_content):
    total_len = len(text_content)
    p1 = text_content[:min(2500, total_len)]
    p2 = text_content[min(2000, total_len):min(5000, total_len)] if total_len > 2000 else text_content[:2500]
    p3 = text_content[min(4500, total_len):min(7500, total_len)] if total_len > 4500 else text_content[:2500]

    batches = [
        ("qwen/qwen3.8-27b", p1, 7, 1),
        ("openai/gpt-oss-120b", p2, 7, 2),
        ("openai/gpt-oss-20b", p3, 6, 3)
    ]

    all_quizzes = []
    errors = []

    for model, content, count, part_num in batches:
        prompt = f"""
आप एक शिक्षक भर्ती एवं प्रतियोगी परीक्षा विशेषज्ञ हैं। 
नीचे दी गई सामग्री के आधार पर ठीक {count} बहुत कठिन, विश्लेषणात्मक (Hard Level) बहुविकल्पीय प्रश्न (MCQs) केवल शुद्ध हिंदी में तैयार करें (भाग {part_num})।

नियम:
1. प्रत्येक प्रश्न में ठीक 4 विकल्प होने चाहिए।
2. प्रश्न और व्याख्या संक्षिप्त रखें।
3. केवल शुद्ध JSON फॉर्मेट दें।

JSON संरचना:
{{
  "quizzes": [
    {{
      "question": "कठिन प्रश्न यहाँ लिखें",
      "options": ["विकल्प 1", "विकल्प 2", "विकल्प 3", "विकल्प 4"],
      "correct_option_id": 0,
      "explanation": "संक्षिप्त व्याख्या"
    }}
  ]
}}

सामग्री:
{content}
"""
        try:
            print(f"Calling {model} (max_tokens: 850)...")
            res = call_groq_single(model, prompt, max_tokens=850)
            if res:
                all_quizzes.extend(res)
                print(f"Success: {len(res)} questions from {model}")
        except Exception as e:
            err = str(e)
            print(f"Batch Error ({model}): {err}")
            errors.append(err)

    if not all_quizzes:
        raise Exception(f"सभी प्रयास विफल रहे: {'; '.join(errors)}")

    return all_quizzes

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "नमस्ते! मुझे कोई भी PDF या DOCX फ़ाइल भेजें, मैं कठिन बहुविकल्पीय प्रश्न बनाकर सीधे चैनल पर पोस्ट कर दूँगा।")

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

        bot.edit_message_text("⚡ AI से कठिन प्रश्न तैयार किए जा रहे हैं...", chat_id=message.chat.id, message_id=status_msg.message_id)

        quizzes = generate_quiz_with_groq(text)

        if not quizzes:
            bot.edit_message_text("❌ प्रश्न तैयार नहीं हो सके। कृपया दोबारा प्रयास करें।", chat_id=message.chat.id, message_id=status_msg.message_id)
            return

        bot.edit_message_text(f"✅ {len(quizzes)} प्रश्न तैयार! अब 30-30 सेकंड के अंतराल में चैनल पर पोस्ट किए जा रहे हैं...", chat_id=message.chat.id, message_id=status_msg.message_id)

        for i, q in enumerate(quizzes):
            try:
                question = str(q.get("question", ""))[:255]
                options = [str(opt)[:100] for opt in q.get("options", [])][:4]
                correct_id = int(q.get("correct_option_id", 0))
                explanation = str(q.get("explanation", ""))[:190]

                if len(options) >= 2:
                    bot.send_poll(
                        chat_id=CHANNEL_ID,
                        question=f"Q{i+1}. {question}",
                        options=options,
                        type='quiz',
                        correct_option_id=correct_id,
                        explanation=explanation,
                        is_anonymous=False
                    )
                    time.sleep(30)
            except Exception as pe:
                print(f"Poll Error on Q{i+1}: {pe}")
                time.sleep(5)

        bot.send_message(message.chat.id, f"🎉 सभी {len(quizzes)} प्रश्न चैनल पर सफलतापूर्वक पोस्ट हो चुके हैं!")

    except Exception as e:
        print(f"Error: {e}")
        bot.reply_to(message, f"❌ एरर: {e}")

print("Bot started with 850 Token Batching...")
bot.infinity_polling()
    
