import telebot
import PyPDF2
import docx
import os
from flask import Flask
import threading
import time
import json
import random
import requests

# --- आपकी 6 असली API KEYS (100% CONFIGURED) ---
API_KEYS = [
    "AQ.Ab8RN6KKI3tKaKz6G_RgKKaS7uZdK4HdbyIkvRwA4qS2C8qDAQ",
    "AQ.Ab8RN6KWPbEqUjomMQUyR-tXUIHtPJg4pm_51lncMflOxtZpEA",
    "AQ.Ab8RN6IJdv3mP5IC75nbcXvAjp1VPm3wWJVulrszE2-zaa-ynQ",
    "AQ.Ab8RN6JP1xU6_471YqfIldY4oZDb439bVrwFUCprvl1obtOJ1g",
    "AQ.Ab8RN6IsxSCwjhcuK0ncXbeCInko-fn-YXZIQN6PRYjV9Xpz8A",
    "AQ.Ab8RN6I2cta-zcHIuJa54vuXv6Vkld4YY2-s5lQDS_8cK8ovxw"
]

# Telegram Tokens (Render Environment से)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")

bot = telebot.TeleBot(BOT_TOKEN)

# --- Flask Web Server ---
app = Flask(__name__)

@app.route('/')
def home():
    return f"✅ Telegram 6-API Quiz Bot is Running 24/7! (Keys Loaded: {len(API_KEYS)})"

def run_server():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# --- PDF/DOCX से टेक्स्ट निकालने का फ़ंक्शन ---
def extract_text(file_path):
    text = ""
    if file_path.endswith('.pdf'):
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
    elif file_path.endswith('.docx'):
        doc = docx.Document(file_path)
        for para in doc.paragraphs:
            if para.text:
                text += para.text + "\n"
    return text

# --- Gemini REST API से क्विज़ जनरेट करना (नई AQ. Keys के लिए फुलप्रूफ) ---
def call_gemini_api(prompt, key):
    # gemini-2.5-flash REST endpoint जो AQ. format को सीधे सपोर्ट करता है
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ]
    }
    
    response = requests.post(url, headers=headers, json=payload, timeout=90)
    
    if response.status_code == 200:
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    elif response.status_code == 429:
        raise Exception("429 Quota Exceeded")
    else:
        raise Exception(f"API Error {response.status_code}: {response.text}")

def generate_quiz_data(text):
    keys_to_try = API_KEYS.copy()
    random.shuffle(keys_to_try) # हर बार अलग Key पहले ट्राई होगी
    
    prompt = f"""
    You are an Expert Quiz Master and Competitive Exam Content Creator. 
    Your task is to generate high-quality, hard-level Multiple Choice Questions (MCQs) strictly based on the text/document provided.

    CRITICAL INSTRUCTIONS FOR ACCURACY:
    1. Base Content: Create questions ONLY from the provided text. Do not invent facts.
    2. Difficulty: Hard (Include Conceptual, Statement-Based, and Analytical questions).
    3. Question Length: Question text MUST be concise and UNDER 250 characters. Options under 80 characters.
    4. Language: Hindi.
    5. Question Count: Generate exactly 20 questions (or as many as the text allows).
    6. Correct Answer Randomization (CRUCIAL): Distribute the correct answers evenly and randomly among A, B, C, and D. DO NOT make 'A' the correct answer for every question.
    7. Solution Accuracy: The "solution" MUST clearly explain WHY the chosen option is correct based on the text.
    8. Output Format: Return ONLY a valid raw JSON array without any markdown formatting or explanations.

    JSON FORMAT TEMPLATE:
    [
      {{
        "question": "प्रश्न यहाँ लिखें?",
        "A": "पहला विकल्प",
        "B": "दूसरा विकल्प",
        "C": "तीसरा विकल्प",
        "D": "चौथा विकल्प",
        "answer": "B",
        "solution": "यहाँ विस्तृत समाधान लिखें।",
        "positive_marks": "2",
        "negative_marks": "0.66"
      }}
    ]

    टेक्स्ट: {text[:40000]}
    """
    
    last_err = None
    for key in keys_to_try:
        try:
            return call_gemini_api(prompt, key)
        except Exception as e:
            last_err = e
            print(f"Key failed, trying next key... Error: {e}")
            continue
            
    raise Exception(f"सभी 6 Keys में समस्या आई: {last_err}")

# --- JSON डेटा को डिकोड करने का फ़ंक्शन ---
def parse_quiz_data(raw_data):
    quizzes = []
    try:
        clean_data = raw_data.strip()
        if clean_data.startswith("```json"): clean_data = clean_data[7:]
        if clean_data.startswith("```"): clean_data = clean_data[3:]
        if clean_data.endswith("```"): clean_data = clean_data[:-3]
        clean_data = clean_data.strip()
        
        json_data = json.loads(clean_data)
        
        for item in json_data:
            quiz = {
                "question": item.get("question", "प्रश्न जनरेट नहीं हो पाया"),
                "options": [
                    str(item.get("A", "विकल्प A")),
                    str(item.get("B", "विकल्प B")),
                    str(item.get("C", "विकल्प C")),
                    str(item.get("D", "विकल्प D"))
                ],
                "solution": item.get("solution", "विस्तृत व्याख्या उपलब्ध नहीं है।")
            }
            
            ans = str(item.get("answer", "A")).strip().upper()
            ans_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
            quiz['correct_option_id'] = ans_map.get(ans, 0)
            
            if len(quiz['options']) >= 2 and quiz['question']:
                quizzes.append(quiz)
    except Exception as e:
        print(f"JSON Parsing Error: {e}")
        
    return quizzes

# --- बैकग्राउंड में क्विज़ भेजने वाला फ़ंक्शन ---
def send_quizzes_background(message, quizzes):
    for index, quiz_data in enumerate(quizzes):
        try:
            safe_question = quiz_data['question'][:290] 
            safe_options = [opt[:95] for opt in quiz_data['options']]
            safe_explanation = quiz_data['solution'][:195]
            
            bot.send_message(CHANNEL_ID, f"📝 **कठिन प्रश्न {index + 1}/{len(quizzes)}**", parse_mode="Markdown")
            
            bot.send_poll(
                chat_id=CHANNEL_ID,
                question=safe_question,
                options=safe_options,
                type="quiz",
                correct_option_id=quiz_data['correct_option_id'],
                explanation=safe_explanation, 
                is_anonymous=True
            )
            
            if index < len(quizzes) - 1:
                time.sleep(30)
        except Exception as e:
            print(f"Poll भेजने में त्रुटि: {e}")
            
    bot.reply_to(message, f"🎉 सभी {len(quizzes)} प्रश्न चैनल पर सफलतापूर्वक पोस्ट हो चुके हैं!")

# --- टेलीग्राम बॉट कमांड्स और हैंडलर्स ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, f"✅ बॉट 6-API Keys के साथ पूरी तरह सक्रिय है! कृपया अपनी PDF या DOCX फ़ाइल भेजें।")

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    try:
        bot.reply_to(message, "⏳ फ़ाइल प्राप्त हुई। हार्ड-लेवल के 20 प्रश्न बनाए जा रहे हैं, कृपया 15-20 सेकंड प्रतीक्षा करें...")
        
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        file_ext = ".pdf" if message.document.file_name.endswith('.pdf') else ".docx"
        file_path = f"temp{file_ext}"
        
        with open(file_path, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        text = extract_text(file_path)
        raw_quiz = generate_quiz_data(text)
        quizzes = parse_quiz_data(raw_quiz)
        
        if not quizzes:
            bot.reply_to(message, "❌ इस फ़ाइल से प्रश्न नहीं बन पाए। कृपया दूसरी फ़ाइल भेजें।")
            return
            
        bot.reply_to(message, f"✅ कुल {len(quizzes)} कठिन प्रश्न तैयार हो गए हैं! अब ये एक-एक करके 30 सेकंड के अंतराल पर चैनल में पोस्ट होना शुरू हो रहे हैं।")
        
        # बॉट को फ्री रखने के लिए बैकग्राउंड थ्रेड
        threading.Thread(target=send_quizzes_background, args=(message, quizzes)).start()
        
    except Exception as e:
        bot.reply_to(message, f"❌ तकनीकी त्रुटि: {e}")

# --- मेन एंट्री पॉइंट ---
if __name__ == "__main__":
    t = threading.Thread(target=run_server)
    t.start()
    
    print("बॉट चालू हो गया है (All 6 AQ. Keys Active)...")
    
    try:
        bot.remove_webhook()
        time.sleep(2)
    except:
        pass

    while True:
        try:
            bot.polling(none_stop=True, skip_pending=True, timeout=20)
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)
