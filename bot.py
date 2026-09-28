import os
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

def get_valid_groq_models():
    """Groq API se sabhi valid chat models ki list nikalta hai"""
    try:
        url = "https://api.groq.com/openai/v1/models"
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            all_models = [m["id"] for m in res.json().get("data", [])]
            valid = []
            # Audio, Guard, Arabic aur terms wale models ko filter karein
            skip_keywords = ["whisper", "guard", "orpheus", "embed", "tts", "speech", "vision", "audio", "canopylabs", "safeguard"]
            for m in all_models:
                m_lower = m.lower()
                if not any(k in m_lower for k in skip_keywords):
                    valid.append(m)
            if valid:
                return valid
    except Exception as e:
        print(f"Model fetch error: {e}")
    return ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama3-8b-8192", "mixtral-8x7b-32768", "gemma2-9b-it"]

def generate_quiz_with_groq(text_content):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    prompt = f"""
आप एक उच्च स्तरीय शिक्षक भर्ती एवं प्रतियोगी परीक्षा विशेषज्ञ हैं। 
नीचे दिए गए पाठ्य सामग्री (Content) को ध्यानपूर्वक पढ़ें और उसी के आधार पर 20 बहुत कठिन, विश्लेषणात्मक (Hard Level) बहुविकल्पीय प्रश्न (MCQs) हिंदी में तैयार करें।

नियम:
1. प्रश्न और चारों विकल्प पाठ्य सामग्री पर आधारित होने चाहिए।
2. प्रत्येक प्रश्न में 4 विकल्प होने चाहिए।
3. केवल और केवल शुद्ध JSON Format (Object) में आउटपुट दें, कोई अतिरिक्त टेक्स्ट या मार्कडाउन (```json) न लिखें।

JSON संरचना:
{{
  "quizzes": [
    {{
      "question": "प्रश्न यहाँ लिखें (अधिकतम 250 अक्षर)",
      "options": ["विकल्प 1", "विकल्प 2", "विकल्प 3", "विकल्प 4"],
      "correct_option_id": 0,
      "explanation": "संक्षिप्त व्याख्या (अधिकतम 180 अक्षर)"
    }}
  ]
}}

सामग्री:
{text_content[:8000]}
"""

    models_to_try = get_valid_groq_models()
    last_error = ""

    # Agar ek model fail ho toh automatically dusre model se koshish karein
    for model_name in models_to_try:
        try:
            print(f"Trying Groq model: {model_name}")
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": "You are a professional exam quiz generator. Output ONLY a valid JSON object."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.4
            }

            response = requests.post(url, headers=headers, json=payload, timeout=120)
            if response.status_code == 200:
                res_json = response.json()
                content = res_json["choices"][0]["message"]["content"]
                data = json.loads(content)
                quizzes = data.get("quizzes", [])
                if quizzes:
                    return quizzes
            else:
                last_error = f"{model_name} Error {response.status_code}: {response.text}"
                print(last_error)
        except Exception as e:
            last_error = str(e)
            print(f"Failed with {model_name}: {e}")
            continue

    raise Exception(f"सभी उपलब्ध मॉडल्स पर प्रयास किया गया, अंतिम एरर: {last_error}")

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "नमस्ते! मुझे कोई भी PDF या DOCX फ़ाइल भेजें, मैं Groq AI से 20 कठिन प्रश्न बनाकर सीधे चैनल पर पोस्ट कर दूँगा।\n\nउपलब्ध मॉडल्स देखने के लिए /models भेजें।")

@bot.message_handler(commands=['models'])
def list_models(message):
    try:
        models = get_valid_groq_models()
        text = "📋 उपलब्ध Groq मॉडल्स:\n\n" + "\n".join(models)
        bot.reply_to(message, text[:4000])
    except Exception as e:
        bot.reply_to(message, f"❌ एरर: {e}")

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

        bot.edit_message_text("⚡ Groq AI से 20 कठिन प्रश्न बनाए जा रहे हैं...", chat_id=message.chat.id, message_id=status_msg.message_id)

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

        bot.send_message(message.chat.id, "🎉 सभी प्रश्न चैनल पर सफलतापूर्वक पोस्ट हो चुके हैं!")

    except Exception as e:
        print(f"Error: {e}")
        bot.reply_to(message, f"❌ एरर: {e}")

print("Bot started on AWS with Groq AI...")
bot.infinity_polling()
                  
