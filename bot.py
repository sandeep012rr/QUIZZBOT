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

# --- 6 API KEYS SETUP (Render Environment Variables se) ---
API_KEYS = [
    os.environ.get("API_KEY_1"),
    os.environ.get("API_KEY_2"),
    os.environ.get("API_KEY_3"),
    os.environ.get("API_KEY_4"),
    os.environ.get("API_KEY_5"),
    os.environ.get("API_KEY_6")
]

# Khali keys ko hata dein
API_KEYS = [key for key in API_KEYS if key is not None and key.strip() != ""]

# Telegram Tokens
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")

bot = telebot.TeleBot(BOT_TOKEN)

# --- Flask Web Server ---
app = Flask(__name__)

@app.route('/')
def home():
    return f"✅ Telegram 6-API Quiz Bot is Running 24/7! (Active Keys: {len(API_KEYS)})"

def run_server():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

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

def generate_quiz_data(text):
    if not API_KEYS:
        raise Exception("API keys not found in Render Environment!")
        
    keys_to_try = API_KEYS.copy()
    random.shuffle(keys_to_try)
    
    last_error = None
    
    for current_key in keys_to_try:
        try:
            genai.configure(api_key=current_key)
            model = genai.GenerativeModel('gemini-3.8-flash')
            
            prompt = f"""
            You are an Expert Quiz Master and Competitive Exam Content Creator. 
            Your task is to generate high-quality, hard-level Multiple Choice Questions (MCQs) strictly based on the text/document provided by the user.

            CRITICAL INSTRUCTIONS FOR ACCURACY:
            1. Base Content: Create questions ONLY from the provided text. Do not invent information.
            2. Difficulty: Hard (Include Conceptual, Statement-Based, and Analytical questions).
            3. Question Length: Question text MUST be concise and UNDER 250 characters. Options under 80 characters.
            4. Language: Hindi.
            5. Question Count: Generate exactly 20 questions (or as many as possible).
            6. Options: Provide exactly 4 options (A, B, C, D) for each question.
            7. Correct Answer Randomization (CRUCIAL): You MUST distribute the correct answers randomly among A, B, C, and D. DO NOT make 'A' the correct answer for every question. The "answer" field MUST strictly match the key (A, B, C, or D) of the correct option.
            8. Solution Accuracy: The "solution" MUST clearly explain WHY the chosen option is correct based on the provided text. Do not provide generic explanations.
            9. Output Format: Return ONLY a valid JSON array.

            JSON FORMAT TEMPLATE:
            [
              {{
                "question": "प्रश्न यहाँ लिखें?",
                "A": "पहला विकल्प",
                "B": "दूसरा विकल्प (सही)",
                "C": "तीसरा विकल्प",
                "D": "चौथा विकल्प",
                "answer": "B",
                "solution": "यहाँ विस्तृत समाधान लिखें जो यह बताए कि B क्यों सही है।",
                "positive_marks": "2",
                "negative_marks": "0.66"
              }}
            ]

            टेक्स्ट: {text[:40000]}
            """
            
            response = model.generate_content(prompt)
            return response.text 
            
        except Exception as e:
            last_error = e
            if "429" in str(e) or "quota" in str(e).lower():
                print(f"Key failed with Quota Exceeded. Trying next key...")
                continue
            else:
                raise e
                
    raise Exception("Saari 6 API Keys ka Quota khatam ho chuka hai! Kripya 24 ghante wait karein ya nayi Keys dalein.")

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
    bot.reply_to(message, f"✅ Main {len(API_KEYS)} API Keys ke smart-switch system ke sath active hu! PDF bhej dijiye.")

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
        bot.reply_to(message, f"❌ Technical Error: {e}")

if __name__ == "__main__":
    t = threading.Thread(target=run_server)
    t.start()
    
    print("Bot chalu ho gaya h (with Smart Auto-Switch APIs & Fixed Prompt)...")
    
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
