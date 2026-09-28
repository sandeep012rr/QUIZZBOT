import telebot
import PyPDF2
import docx
import google.generativeai as genai
import os
from flask import Flask
import threading
import time
import json

# API Keys
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3.8-flash')

# --- Flask Web Server ---
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Telegram JSON Quiz Bot is Running 24/7!"

def run_server():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# --- PDF/DOCX से टेक्स्ट निकालने का फ़ंक्शन ---
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

# --- AI से JSON फॉर्मेट में 20 क्विज़ निकालने का फ़ंक्शन ---
def generate_quiz_data(text):
    prompt = f"""
    You are an Expert Quiz Master and Competitive Exam Content Creator. 
    Your task is to generate high-quality, hard-level Multiple Choice Questions (MCQs) strictly based on the text/document provided by the user.

    RULES:
    1. Base Content: Create questions ONLY from the provided text/document.
    2. Difficulty Level: Hard (Include Conceptual, Match the following, and Analytical questions).
    3. Length Limit (CRITICAL): Telegram has strict length limits. The "question" text MUST be concise and UNDER 250 characters. DO NOT write very long paragraphs in the question. Keep options under 80 characters, and solutions under 150 characters.
    4. Language: Hindi.
    5. Question Count: Generate exactly 20 questions (or as many as possible if the content is short).
    6. Options: Provide exactly 4 options (A, B, C, D) for each question.
    7. Correct Answer: Only one option must be correct. Randomize the correct option.
    8. Solution: Provide a brief, logical explanation for the correct answer.
    9. STRICT OUTPUT FORMAT: You MUST return the output ONLY as a valid JSON array. Do not wrap the output in markdown code blocks (like ```json). Just output the raw JSON array.

    JSON FORMAT TEMPLATE:
    [
      {{
        "question": "प्रश्न यहाँ लिखें? (ध्यान रहे, बहुत लंबा न हो)",
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

# --- JSON डेटा को डिकोड करने का स्मार्ट फ़ंक्शन ---
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

# --- बॉट का कनेक्शन चेक करने के लिए /start कमांड ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "✅ मैं बिल्कुल सही तरीके से चालू हूँ! कृपया मुझे अपनी PDF या DOCX फ़ाइल भेजें (20 सवालों के लिए)।")

# --- टेलीग्राम पर फ़ाइल भेजने का हिस्सा ---
@bot.message_handler(content_types=['document'])
def handle_docs(message):
    try:
        bot.reply_to(message, "फ़ाइल प्राप्त हुई। 20 हार्ड-लेवल (Hard-Level) प्रश्न तैयार किए जा रहे हैं, इसमें थोड़ा समय लग सकता है, कृपया प्रतीक्षा करें...")
        
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
            bot.reply_to(message, "इस फ़ाइल से प्रश्न नहीं बन पाए। कृपया दूसरी फ़ाइल भेजें।")
            return
            
        bot.reply_to(message, f"✅ कुल {len(quizzes)} हार्ड-लेवल प्रश्न बने हैं। अब ये एक-एक करके 30 सेकंड के अंतराल पर चैनल पर पोस्ट होंगे!")
        
        for index, quiz_data in enumerate(quizzes):
            # सेफ्टी लेयर बरकरार रखी है, लेकिन अब AI खुद ही छोटे प्रश्न भेजेगा
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
                
        bot.reply_to(message, f"🎉 सभी {len(quizzes)} कठिन क्विज़ सफलतापूर्वक पोस्ट कर दिए गए हैं!")
        
    except Exception as e:
        bot.reply_to(message, f"❌ कोई तकनीकी समस्या आई: {e}")

# --- बॉट और वेब सर्वर ---
if __name__ == "__main__":
    t = threading.Thread(target=run_server)
    t.start()
    
    print("बॉट चालू हो गया है...")
    
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
    
