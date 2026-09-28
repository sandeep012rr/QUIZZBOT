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

# --- AI से सभी क्विज़ निकालने का फ़ंक्शन ---
def generate_quiz_data(text):
    prompt = f"""
    नीचे दिए गए टेक्स्ट को पढ़ें और उसमें से जितने भी बहुविकल्पीय प्रश्न (MCQ) बन सकते हैं या दिए गए हैं, वे सभी निकालें।
    हर प्रश्न को एक दूसरे से अलग करने के लिए बीच में '###' लिखें।
    आउटपुट बिल्कुल इसी फॉर्मेट में होना चाहिए (कोई बोल्ड या एक्स्ट्रा टेक्स्ट न लिखें):

    Question: [प्रश्न लिखें, अधिकतम 250 अक्षरों में]
    A: [पहला विकल्प, अधिकतम 80 अक्षरों में]
    B: [दूसरा विकल्प, अधिकतम 80 अक्षरों में]
    C: [तीसरा विकल्प, अधिकतम 80 अक्षरों में]
    D: [चौथा विकल्प, अधिकतम 80 अक्षरों में]
    Answer: [A, B, C, या D]
    Solution: [सही उत्तर का कारण, अधिकतम 150 अक्षरों में]
    ###
    Question: [अगला प्रश्न]
    ...

    टेक्स्ट: {text[:15000]}
    """
    response = model.generate_content(prompt)
    return response.text

# --- मल्टीपल क्विज़ डेटा को अलग करने का स्मार्ट फ़ंक्शन ---
def parse_quiz_data(raw_data):
    quizzes = []
    blocks = raw_data.strip().split('###')
    
    for block in blocks:
        if not block.strip():
            continue
            
        lines = block.strip().split('\n')
        quiz = {"options": [], "question": "", "correct_option_id": 0, "solution": "सही उत्तर चुनने के लिए धन्यवाद!"}
        
        for line in lines:
            line = line.strip().replace("**", "") 
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
                
        if len(quiz['options']) >= 2 and quiz['question']:
            quizzes.append(quiz)
            
    return quizzes

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
        d.text((50, 50), "आज का महत्वपूर्ण प्रश्न", fill=(255, 255, 0), font=font)
        wrapped_text = textwrap.fill(question_text, width=45)
        d.text((50, 120), wrapped_text, fill=(255, 255, 255), font=font)
    except Exception as e:
        print(f"Font Error: {e}")
        
    banner_path = "banner.png"
    img.save(banner_path)
    return banner_path

# --- टेलीग्राम पर फ़ाइल भेजने का हिस्सा (30 सेकंड गैप के साथ) ---
@bot.message_handler(content_types=['document'])
def handle_docs(message):
    try:
        bot.reply_to(message, "फ़ाइल प्राप्त हुई। सभी प्रश्न और बैनर तैयार किए जा रहे हैं, कृपया प्रतीक्षा करें...")
        
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
            bot.reply_to(message, "इस फ़ाइल में कोई प्रश्न नहीं मिल पाया। कृपया दूसरी फ़ाइल भेजें।")
            return
            
        bot.reply_to(message, f"✅ कुल {len(quizzes)} प्रश्न मिले हैं। अब ये एक-एक करके 30 सेकंड के अंतराल पर चैनल पर पोस्ट होंगे!")
        
        # सभी सवालों को एक-एक करके लूप में पोस्ट करना
        for index, quiz_data in enumerate(quizzes):
            banner_path = create_banner(quiz_data['question'])
            
            with open(banner_path, 'rb') as photo:
                bot.send_photo(CHANNEL_ID, photo, caption=f"👇 **प्रश्न {index + 1}/{len(quizzes)} - आज का क्विज़ अटेम्प्ट करें!** 👇", parse_mode="Markdown")
                
            safe_question = quiz_data['question'][:290] 
            safe_options = [opt[:95] for opt in quiz_data['options']]
            safe_explanation = quiz_data['solution'][:195]
                
            bot.send_poll(
                chat_id=CHANNEL_ID,
                question=safe_question,
                options=safe_options,
                type="quiz",
                correct_option_id=quiz_data['correct_option_id'],
                explanation=safe_explanation, 
                is_anonymous=True
            )
            
            # अगर यह आखिरी प्रश्न नहीं है, तो 30 सेकंड का ब्रेक लें
            if index < len(quizzes) - 1:
                time.sleep(30)
                
        bot.reply_to(message, f"🎉 सभी {len(quizzes)} क्विज़ सफलतापूर्वक पोस्ट कर दिए गए हैं!")
        
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
    
