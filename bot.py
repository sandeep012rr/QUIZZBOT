import telebot
try:
    import pypdf as PyPDF2
except ImportError:
    import PyPDF2
import docx
import os
import threading
import time
import json
import random
import requests

# --- 6 API KEYS (CONFIGURED) ---
API_KEYS = [
    "AQ.Ab8RN6KKI3tKaKz6G_RgKKaS7uZdK4HdbyIkvRwA4qS2C8qDAQ",
    "AQ.Ab8RN6KWPbEqUjomMQUyR-tXUIHtPJg4pm_51lncMflOxtZpEA",
    "AQ.Ab8RN6IJdv3mP5IC75nbcXvAjp1VPm3wWJVulrszE2-zaa-ynQ",
    "AQ.Ab8RN6JP1xU6_471YqfIldY4oZDb439bVrwFUCprvl1obtOJ1g",
    "AQ.Ab8RN6IsxSCwjhcuK0ncXbeCInko-fn-YXZIQN6PRYjV9Xpz8A",
    "AQ.Ab8RN6I2cta-zcHIuJa54vuXv6Vkld4YY2-s5lQDS_8cK8ovxw"
]

# --- TELEGRAM BOT CONFIGURATION ---
BOT_TOKEN = "7589769291:AAFSErrT1V5Wt1eGZ235vV4M2-QZuPALhTM"
CHANNEL_ID = "@FIRST_GARDE_SPL"

bot = telebot.TeleBot(BOT_TOKEN)

# --- PDF / DOCX EXTRACTOR ---
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

# --- GEMINI REST API (AQ KEY COMPATIBLE) ---
def call_gemini_api(prompt, key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    response = requests.post(url, headers=headers, json=payload, timeout=90)
    if response.status_code == 200:
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    elif response.status_code == 429:
        raise Exception("429 Quota Exceeded")
    else:
        raise Exception(f"API Error {response.status_code}: {response.text}")

# --- QUIZ GENERATOR PROMPT ---
def generate_quiz_data(text):
    keys_to_try = API_KEYS.copy()
    random.shuffle(keys_to_try)
    
    prompt = f"""
    You are an Expert Quiz Master and Competitive Exam Content Creator. 
    Your task is to generate high-quality, hard-level Multiple Choice Questions (MCQs) strictly based on the text/document provided.

    CRITICAL INSTRUCTIONS FOR ACCURACY:
    1. Base Content: Create questions ONLY from the provided text. Do not invent facts.
    2. Difficulty: Hard (Include Conceptual, Statement-Based, and Analytical questions).
    3. Question Length: Question text MUST be concise and UNDER 250 characters. Options under 80 characters.
    4. Language: Strictly Hindi (Devanagari script). All questions, options (A, B, C, D), and solutions must be in Hindi.
    5. Question Count: Generate exactly 20 questions (or as many as the text allows).
    6. Correct Answer Randomization (CRUCIAL): Distribute the correct answers evenly and randomly among A, B, C, and D. DO NOT make 'A' the correct answer for every question.
    7. Solution Accuracy: The "solution" MUST clearly explain WHY the chosen option is correct based on the text.
    8. Output Format: Return ONLY a valid raw JSON array without any markdown formatting or backticks.

    JSON FORMAT TEMPLATE:
    [
      {{
        "question": "Question in Hindi here?",
        "A": "Option A in Hindi",
        "B": "Option B in Hindi",
        "C": "Option C in Hindi",
        "D": "Option D in Hindi",
        "answer": "B",
        "solution": "Detailed solution in Hindi here.",
        "positive_marks": "2",
        "negative_marks": "0.66"
      }}
    ]

    Text: {text[:40000]}
    """
    
    last_err = None
    for key in keys_to_try:
        try:
            return call_gemini_api(prompt, key)
        except Exception as e:
            last_err = e
            continue
            
    raise Exception(f"All keys failed: {last_err}")

# --- PARSE JSON RESPONSE ---
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
                "question": item.get("question", ""),
                "options": [
                    str(item.get("A", "")),
                    str(item.get("B", "")),
                    str(item.get("C", "")),
                    str(item.get("D", ""))
                ],
                "solution": item.get("solution", "")
            }
            ans = str(item.get("answer", "A")).strip().upper()
            ans_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
            quiz['correct_option_id'] = ans_map.get(ans, 0)
            if len(quiz['options']) >= 2 and quiz['question']:
                quizzes.append(quiz)
    except Exception as e:
        print(f"JSON Parsing Error: {e}")
    return quizzes

# --- BACKGROUND CHANNEL POSTER ---
def send_quizzes_background(message, quizzes):
    for index, quiz_data in enumerate(quizzes):
        try:
            safe_question = quiz_data['question'][:290] 
            safe_options = [opt[:95] for opt in quiz_data['options']]
            safe_explanation = quiz_data['solution'][:195]
            
            header_text = f"📝 प्रश्न {index + 1}/{len(quizzes)}"
            bot.send_message(CHANNEL_ID, header_text)
            
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
            print(f"Poll Error: {e}")
            
    bot.reply_to(message, "✅ सभी प्रश्न चैनल पर सफलतापूर्वक पोस्ट हो चुके हैं!")

# --- BOT HANDLERS ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "✅ AWS Server पर 6-API बॉट 24×7 लाइव है! कृपया अपनी PDF या DOCX फ़ाइल भेजें।")

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    try:
        bot.reply_to(message, "⏳ फ़ाइल मिल गई है। 20 प्रश्न बनाए जा रहे हैं, कृपया 15-20 सेकंड प्रतीक्षा करें...")
        
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
            bot.reply_to(message, "❌ इस फ़ाइल से प्रश्न नहीं बन पाए।")
            return
            
        bot.reply_to(message, f"✅ कुल {len(quizzes)} प्रश्न तैयार! अब 30-30 सेकंड के अंतराल पर चैनल में पोस्ट हो रहे हैं।")
        
        threading.Thread(target=send_quizzes_background, args=(message, quizzes)).start()
        
    except Exception as e:
        bot.reply_to(message, f"❌ एरर: {e}")

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print("Bot started on AWS...")
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
            
