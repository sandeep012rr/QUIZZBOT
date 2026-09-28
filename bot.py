import telebot
import PyPDF2
import docx
import google.generativeai as genai
import os
from flask import Flask
import threading
import time
import json
import random

# --- 6 API KEYS SETUP ---
# Apni 6 alag-alag keys yahan in double quotes (" ") ke andar daalein
API_KEYS = [
    "API_KEY_1_YAHAN_DAALEIN",
    "API_KEY_2_YAHAN_DAALEIN",
    "API_KEY_3_YAHAN_DAALEIN",
    "API_KEY_4_YAHAN_DAALEIN",
    "API_KEY_5_YAHAN_DAALEIN",
    "API_KEY_6_YAHAN_DAALEIN"
]

# Telegram Tokens (Ye Render Environment se hi aayenge)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")

bot = telebot.TeleBot(BOT_TOKEN)

# --- Flask Web Server ---
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Telegram 6-API Quiz Bot is Running 24/7!"

def run_server():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# --- PDF/DOCX se text nikalne ka function ---
def extract_text(file_path):
    text = ""
    if file_path.endswith('.pdf'):
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text += page.extract_text() + "\n"
    elif file_path.endswith('.docx'):
        doc = docx.Document(file_path)
        for para in doc.paragraphs:
            text += para.text + "\n"
    return text

# --- AI se JSON format me Quiz nikalne ka function (Random API Key ke sath) ---
def generate_quiz_data(text):
    # Har baar PDF aane par randomly ek key select hogi!
    current_key = random.choice(API_KEYS)
    genai.configure(api_key=current_key)
    model = genai.GenerativeModel('gemini-3.8-flash')
    
    prompt = f"""
    You are an Expert Quiz Master and Competitive Exam Content Creator. 
    Your task is to generate high-quality, hard-level Multiple Choice Questions (MCQs) strictly based on the text/document provided by the user.

    RULES:
    1. Base Content: Create questions ONLY from the provided text/document.
    2. Difficulty Level: Hard (Include Conceptual, Match the following, and Analytical questions).
    3. Length Limit (CRITICAL): Telegram has strict length limits. The "question" text MUST be concise and UNDER 250 characters. Keep options under 80 characters, and solutions under 150 characters.
    4. Language: Hindi.
    5. Question Count: Generate exactly 20 questions.
    6. Options: Provide exactly 4 options (A, B, C, D) for each question.
    7. Correct Answer: Only one option must be correct.
    8. Solution: Provide a brief, logical explanation for the correct answer.
    9. STRICT OUTPUT FORMAT: Return ONLY a valid JSON array.

    JSON FORMAT TEMPLATE:
    [
      {{
        "question": "प्रश्न यहाँ लिखें?",
        "A": "पहला विकल्प",
        "B": "दूसरा विकल्प",
        "C": "तीसरा विकल्प",
        "D": "चौथा विकल्प",
        "answer": "A",
        "solution": "यहाँ विस्तृत समाधान लिखें।",
        "positive_marks": "2",
        "negative_marks": "0.66"
      }}
    ]

    टेक्स्ट: {text[:40000]}
    """
    response = model.generate_content(prompt)
    return response.text

# --- JSON Data Decode function ---
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
                "solution": item.get("solution", "सही उत्तर चुनने के लिए धन्यवाद!")
            }
            ans = str(item.get("answer", "A")).strip().upper()
            ans_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
            quiz['correct_option_id'] = ans_map.get(ans, 0)
            if len(quiz['options']) >= 2 and quiz['question']:
                quizzes.append(quiz)
    except Exception as e:
        print(f"JSON Parsing Error: {e}")
    return quizzes

# --- Background Quiz Sender ---
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
            print(f"Poll bhejne me error: {e}")
            
    bot.reply_to(message, f"🎉 Sabhi {len(quizzes)} questions channel par successfully post ho gaye!")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "✅ Main 6 API Keys ke sath fully active hu! PDF bhej dijiye.")

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    try:
        bot.reply_to(message, "⏳ File mil gayi h. Questions ban rahe hain, kripya wait karein...")
        
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
            bot.reply_to(message, "❌ Is file se questions nahi ban paye.")
            return
            
        bot.reply_to(message, f"✅ Kul {len(quizzes)} questions ban gaye hain. Ab ye background me aate rahenge!")
        
        threading.Thread(target=send_quizzes_background, args=(message, quizzes)).start()
        
    except Exception as e:
        # Error handling ko thoda user friendly banaya hai
        if "429" in str(e):
            bot.reply_to(message, "❌ Quota Exceeded! Lagta hai 6 ki 6 keys thak gayi hain. Kripya 2-3 minute baad dobara PDF bhejein.")
        else:
            bot.reply_to(message, f"❌ Technical Error: {e}")

if __name__ == "__main__":
    t = threading.Thread(target=run_server)
    t.start()
    
    print("Bot chalu ho gaya h (with 6 APIs)...")
    
    try:
        bot.remove_webhook()
        time.sleep(2)
    except:
        pass

    while True:
        try:
            bot.polling(none_stop=True, skip_pending=True, timeout=20)
        except Exception as e:
            print(f"Error in polling: {e}")
            time.sleep(5)
    
