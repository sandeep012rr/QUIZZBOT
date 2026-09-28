import telebot
import PyPDF2
import docx
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont
import os
import textwrap
from flask import Flask
import threading
import time

# API Keys
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.0-pro')

# --- Flask Web Server (Render को फ्री में चलाने के लिए) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Telegram Quiz Bot is Running 24/7!"

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

# --- AI से क्विज़ बनाने का फ़ंक्शन ---
def generate_quiz_data(text):
    prompt = f"""
    नीचे दिए गए टेक्स्ट को पढ़ें और उसमें से 1 बेहतरीन प्रतियोगी परीक्षा स्तर का बहुविकल्पीय प्रश्न (MCQ) बनाएँ।
    आउटपुट बिल्कुल इसी फॉर्मेट में होना चाहिए, इसके अलावा कोई भी अतिरिक्त शब्द न लिखें:

    Question: [यहाँ प्रश्न लिखें]
    (a) [पहला विकल्प]
    (b) [दूसरा विकल्प]
    (c) [तीसरा विकल्प]
    (d) [चौथा विकल्प]
    Answer: [a, b, c, या d]
    Solution: [सही उत्तर का विस्तृत कारण]

    टेक्स्ट: {text[:3000]}
    """
    response = model.generate_content(prompt)
    return response.text

# --- क्विज़ डेटा को अलग करने का फ़ंक्शन ---
def parse_quiz_data(raw_data):
    lines = raw_data.strip().split('\n')
    quiz = {"options": []}
    
    for line in lines:
        line = line.strip()
        if line.startswith("Question:"):
            quiz['question'] = line.replace("Question:", "").strip()
        elif line.startswith("(a)"):
            quiz['options'].append(line.replace("(a)", "").strip())
        elif line.startswith("(b)"):
            quiz['options'].append(line.replace("(b)", "").strip())
        elif line.startswith("(c)"):
            quiz['options'].append(line.replace("(c)", "").strip())
        elif line.startswith("(d)"):
            quiz['options'].append(line.replace("(d)", "").strip())
        elif line.startswith("Answer:"):
            ans_char = line.replace("Answer:", "").strip().lower()
            ans_map = {'a': 0, 'b': 1, 'c': 2, 'd': 3}
            quiz['correct_option_id'] = ans_map.get(ans_char, 0)
        elif line.startswith("Solution:"):
            quiz['solution'] = line.replace("Solution:", "").strip()
            
    return quiz

# --- इमेज बैनर बनाने का फ़ंक्शन ---
def create_banner(question_text):
    img = Image.new('RGB', (800, 400), color=(41, 128, 185)) 
    d = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("Mukta-Regular.ttf", 35)
    except:
        font = ImageFont.load_default()
        
    d.text((50, 50), "📚 आज का महत्वपूर्ण प्रश्न", fill=(255, 255, 0), font=font)
    
    wrapped_text = textwrap.fill(question_text, width=45)
    d.text((50, 120), wrapped_text, fill=(255, 255, 255), font=font)
    
    banner_path = "banner.png"
    img.save(banner_path)
    return banner_path

# --- जब आप टेलीग्राम पर फ़ाइल भेजेंगे तब यह चलेगा ---
@bot.message_handler(content_types=['document'])
def handle_docs(message):
    try:
        bot.reply_to(message, "फ़ाइल प्राप्त हुई। प्रश्न और बैनर तैयार किया जा रहा है...")
        
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        file_ext = ".pdf" if message.document.file_name.endswith('.pdf') else ".docx"
        file_path = f"temp{file_ext}"
        
        with open(file_path, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        text = extract_text(file_path)
        raw_quiz = generate_quiz_data(text)
        quiz_data = parse_quiz_data(raw_quiz)
        
        banner_path = create_banner(quiz_data['question'])
        
        with open(banner_path, 'rb') as photo:
            bot.send_photo(CHANNEL_ID, photo, caption="👇 **आज का क्विज़ अटेम्प्ट करें!** 👇", parse_mode="Markdown")
            
        bot.send_poll(
            chat_id=CHANNEL_ID,
            question=quiz_data['question'],
            options=quiz_data['options'],
            type="quiz",
            correct_option_id=quiz_data['correct_option_id'],
            explanation=quiz_data.get('solution', 'सही उत्तर चुनने के लिए धन्यवाद!'), 
            is_anonymous=True
        )
        
        bot.reply_to(message, "✅ क्विज़ आपके चैनल पर सफलतापूर्वक पोस्ट कर दिया गया है!")
        
    except Exception as e:
        bot.reply_to(message, f"❌ कोई तकनीकी समस्या आई: {e}")

# --- बॉट और वेब सर्वर दोनों को एक साथ चलाना ---
if __name__ == "__main__":
    t = threading.Thread(target=run_server)
    t.start()
    
    print("बॉट चालू हो गया है...")
    while True:
        try:
            bot.remove_webhook()
            bot.polling(none_stop=True, skip_pending=True, timeout=60)
        except Exception as e:
            print(f"Error in polling: {e}")
            time.sleep(5)
