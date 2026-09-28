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
import urllib.request

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
    आउटपुट बिल्कुल इसी फॉर्मेट में होना चाहिए (कोई बोल्ड या एक्स्ट्रा टेक्स्ट न लिखें):

    Question: [यहाँ प्रश्न लिखें]
    A: [पहला विकल्प]
    B: [दूसरा विकल्प]
    C: [तीसरा विकल्प]
    D: [चौथा विकल्प]
    Answer: [A, B, C, या D]
    Solution: [सही उत्तर का कारण]

    टेक्स्ट: {text[:3000]}
    """
    response = model.generate_content(prompt)
    return response.text

# --- क्विज़ डेटा को अलग करने का स्मार्ट फ़ंक्शन ---
def parse_quiz_data(raw_data):
    lines = raw_data.strip().split('\n')
    quiz = {"options": [], "question": "प्रश्न जनरेट नहीं हो पाया", "correct_option_id": 0, "solution": "सही उत्तर चुनने के लिए धन्यवाद!"}
    
    for line in lines:
        line = line.strip().replace("**", "") # एक्स्ट्रा बोल्ड मार्क्स हटा दें
        line_lower = line.lower()
        
        if line_lower.startswith("question:"):
            quiz['question'] = line[9:].strip()
        elif line_lower.startswith("a:") or line_lower.startswith("(a)") or line_lower.startswith("a."):
            quiz['options'].append(line[2:].replace(")", "").strip())
        elif line_lower.startswith("b:") or line_lower.startswith("(b)") or line_lower.startswith("b."):
            quiz['options'].append(line[2:].replace(")", "").strip())
        elif line_lower.startswith("c:") or line_lower.startswith("(c)") or line_lower.startswith("c."):
            quiz['options'].append(line[2:].replace(")", "").strip())
        elif line_lower.startswith("d:") or line_lower.startswith("(d)") or line_lower.startswith("d."):
            quiz['options'].append(line[2:].replace(")", "").strip())
        elif line_lower.startswith("answer:"):
            ans = line_lower.replace("answer:", "").strip()
            if 'a' in ans: quiz['correct_option_id'] = 0
            elif 'b' in ans: quiz['correct_option_id'] = 1
            elif 'c' in ans: quiz['correct_option_id'] = 2
            elif 'd' in ans: quiz['correct_option_id'] = 3
        elif line_lower.startswith("solution:"):
            quiz['solution'] = line[9:].strip()
            
    # अगर किसी वजह से AI विकल्प न दे पाए, तो क्रैश होने से बचाने के लिए डिफ़ॉल्ट विकल्प
    if len(quiz['options']) < 2:
        quiz['options'] = ["विकल्प A", "विकल्प B", "विकल्प C", "विकल्प D"]
        
    return quiz

# --- इमेज बैनर बनाने का फ़ंक्शन ---
def create_banner(question_text):
    font_path = "Mukta-Regular.ttf"
    
    if not os.path.exists(font_path):
        try:
            url = "https://raw.githubusercontent.com/google/fonts/main/ofl/mukta/Mukta-Regular.ttf"
            urllib.request.urlretrieve(url, font_path)
        except Exception as e:
            pass

    img = Image.new('RGB', (800, 400), color=(41, 128, 185)) 
    d = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype(font_path, 35)
        # यहाँ से इमोजी हटा दिया गया है ताकि डिब्बा न दिखे
        d.text((50, 50), "आज का महत्वपूर्ण प्रश्न", fill=(255, 255, 0), font=font)
        wrapped_text = textwrap.fill(question_text, width=45)
        d.text((50, 120), wrapped_text, fill=(255, 255, 255), font=font)
    except Exception as e:
        print(f"Font Error: {e}")
        
    banner_path = "banner.png"
    img.save(banner_path)
    return banner_path

# --- टेलीग्राम पर फ़ाइल भेजने का हिस्सा ---
@bot.message_handler(content_types=['document'])
def handle_docs(message):
    try:
        bot.reply_to(message, "फ़ाइल प्राप्त हुई। प्रश्न और क्विज़ तैयार किया जा रहा है...")
        
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
        
        # पहले बैनर भेजेगा
        with open(banner_path, 'rb') as photo:
            bot.send_photo(CHANNEL_ID, photo, caption="👇 **आज का क्विज़ अटेम्प्ट करें!** 👇", parse_mode="Markdown")
            
        # उसके तुरंत बाद क्लिक करने वाला क्विज़ भेजेगा
        bot.send_poll(
            chat_id=CHANNEL_ID,
            question=quiz_data['question'],
            options=quiz_data['options'],
            type="quiz",
            correct_option_id=quiz_data['correct_option_id'],
            explanation=quiz_data['solution'], 
            is_anonymous=True
        )
        
        bot.reply_to(message, "✅ क्विज़ आपके चैनल पर सफलतापूर्वक पोस्ट कर दिया गया है!")
        
    except Exception as e:
        bot.reply_to(message, f"❌ कोई तकनीकी समस्या आई: {e}")

# --- बॉट और वेब सर्वर ---
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
    
