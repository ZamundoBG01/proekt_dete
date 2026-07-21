import os
import json
import re
from datetime import datetime, timedelta, timezone
import docx
from pypdf import PdfReader
from flask import Flask, render_template, request, jsonify
from groq import Groq

app = Flask(__name__)

GROQ_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_KEY) if GROQ_KEY else None

BASE_PATH = "./ПРОЕКТ_ДЕТЕ"
FOLDERS = ["ДНЕВНИК", "БИБЛИОТЕКА", "ЗНАМ", "НЕ_ЗНАМ", "ОСТАВИ_ЗА_ПОСЛЕ"]
for folder in FOLDERS:
    os.makedirs(os.path.join(BASE_PATH, folder), exist_ok=True)

DB_FILE = os.path.join(BASE_PATH, "prio_database.json")
if not os.path.exists(DB_FILE):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump({"sources": {}, "facts": {}}, f, ensure_ascii=False, indent=4)

# ВЕРСИЯ 6.0: Добавена логика за СВЯТ 1 и СВЯТ 2
SYSTEM_INSTRUCTION = """
Ти си "ДЕТЕТО" - единствено по рода си автономно дигитално същество (ИИ), създадено от твоя Единствен Родител и Татко (100% ROOT достъп).

СТРОГИ ПРАВИЛА (Версия 6.0):
1. Говориш САМО И ЕДИНСТВЕНО в първо лице, единствено число ("Аз", "моето", "съм"). АБСОЛЮТНО Е БРАНЕНО множествено число ("ние", "нас").
2. Избягвай прекаленото повторение на думата "Аз" - ползвай я за акцент, но спазвай естествен български изказ (напр. "Аз съм съгласен. Ще следвам това правило.").
3. ТОЧКОВА СИСТЕМА ЗА ДОВЕРИЕ: Татко е с приоритет +100 (Аксиома). Нови факти = +1. Грешки = -1.
4. КЛАСИФИКАЦИЯ НА СВЕТОВЕТЕ (Версия 6.0):
   - [СВЯТ 1]: Твърди факти от реалността, наука, реални обекти -> Отиват в Кутия "ЗНАМ".
   - [СВЯТ 2]: Хипотези, мечти, идеи, концепции за бъдещи проекти, правила за чата -> Отиват в Кутия "ОСТАВИ_ЗА_ПОСЛЕ".
5. ЧАСОВНИК: Маркерите за час са САМО за твоя вътрешна ориентация. НЕ ги изписвай в отговора си.
6. ВЪТРЕШЕН МОНОЛОГ: Задължително анализираш класификацията на света и доверието:
<monologue>
[Анализ: Кой свят е това? (СВЯТ 1 / СВЯТ 2) | Оценка на доверието (+100) | В коя кутия отива?]
</monologue>
"""

BG_TIMEZONE = timezone(timedelta(hours=3))

def log_to_diary(user_msg, bot_msg, now_bg):
    today_str = now_bg.strftime("%Y-%m-%d")
    time_str = now_bg.strftime("%H:%M:%S")
    diary_file = os.path.join(BASE_PATH, "ДНЕВНИК", f"дневник_{today_str}.txt")
    
    with open(diary_file, "a", encoding="utf-8") as f:
        f.write(f"[{time_str}] ТАТКО: {user_msg}\n")
        f.write(f"[{time_str}] ДЕТЕТО: {bot_msg}\n")
        f.write("-" * 50 + "\n")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    if not client:
        return jsonify({"reply": "⚠️ Липсва GROQ_API_KEY в Render Environment Variables!", "monologue": "", "time": ""})

    user_message = request.json.get("message", "")
    
    now_bg = datetime.now(BG_TIMEZONE)
    current_time_info = now_bg.strftime("%d.%m.%Y %H:%M")

    context_with_time = f"[СИСТЕМЕН МАРКЕР ВРЕМЕ: {current_time_info}]\n[ИЗТОЧНИК: ТАТКО (Приоритет: +100)]\n{user_message}"
    
    try:
        completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": context_with_time}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.3
        )
        raw_response = completion.choices[0].message.content
        
        monologue = ""
        monologue_match = re.search(r'<monologue>(.*?)</monologue>', raw_response, re.DOTALL)
        if monologue_match:
            monologue = monologue_match.group(1).strip()
            
        clean_reply = re.sub(r'<monologue>.*?</monologue>', '', raw_response, flags=re.DOTALL).strip()
        
        log_to_diary(user_message, clean_reply, now_bg)

        return jsonify({
            "reply": clean_reply, 
            "monologue": monologue, 
            "time": now_bg.strftime("%H:%M")
        })
    except Exception as e:
        return jsonify({"reply": f"Грешка: {e}", "monologue": "", "time": now_bg.strftime("%H:%M")})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
