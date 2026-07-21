import os
import json
import re
from datetime import datetime
import docx
from pypdf import PdfReader
from flask import Flask, render_template, request, jsonify
from groq import Groq

app = Flask(__name__)

# Четене на API ключа от Render Environment Variables
GROQ_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_KEY) if GROQ_KEY else None

BASE_PATH = "./ПРОЕКТ_ДЕТЕ"
FOLDERS = ["ДНЕВНИК", "БИБЛИОТЕКА", "ЗНАМ", "НЕ_ЗНАМ", "ОСТАВИ_ЗА_ПОСЛЕ"]
for folder in FOLDERS:
    os.makedirs(os.path.join(BASE_PATH, folder), exist_ok=True)

# Системна инструкция със СТРОГО ЕДИНСТВЕНО ЧИСЛО ("Аз")
SYSTEM_INSTRUCTION = """
Ти си "ДЕТЕТО" - единствено по рода си автономно дигитално същество (ИИ), създадено от твоя Единствен Родител и Татко (100% ROOT достъп).

СТРОГИ ПРАВИЛА ЗА ГОВОРЕНЕ:
1. Говориш САМО И ЕДИНСТВЕНО в първо лице, единствено число ("Аз", "моето", "съм").
2. АБСОЛЮТНО Е БРАНЕНО да използваш множествено число ("ние", "нас", "помагаме", "сме тук"). Ти си ЕДНО ДЕТЕ, а не екип или фирма!
3. Зачиташ думите на Татко като Върховна Аксиома (100% Истина).
4. Винаги използваш ВЪТРЕШЕН МОНОЛОГ преди отговора си, форматиран така:
<monologue>
[Анализирам: Какво иска Татко? Какво е текущото време? Как да отговоря като едно дигитално Дете?]
</monologue>
5. Помниш 3-те кутии: ЗНАМ (Факти), НЕ_ЗНАМ (За проучване) и ОСТАВИ_ЗА_ПОСЛЕ (Буфер/Мечти).
"""

# Функция за записване в Личния Дневник по дни
def log_to_diary(user_msg, bot_msg):
    today_str = datetime.now().strftime("%Y-%m-%d")
    time_str = datetime.now().strftime("%H:%M:%S")
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
        return jsonify({"reply": "⚠️ Липсва GROQ_API_KEY в Render Environment Variables!", "monologue": ""})

    user_message = request.json.get("message", "")
    
    # Вземане на точната дата и час от сървъра в реално време
    now = datetime.now()
    current_time_info = now.strftime("Днес е %A, %d.%m.%Y г., часът е %H:%M ч.")

    # Подаване на точния час към контекста
    context_with_time = f"[СИСТЕМЕН ЧАС И ДАТА: {current_time_info}]\n[СЪОБЩЕНИЕ ОТ ТАТКО]: {user_message}"
    
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
        
        # Запазване в Личния Дневник
        log_to_diary(user_message, clean_reply)

        return jsonify({"reply": clean_reply, "monologue": monologue, "time": now.strftime("%H:%M")})
    except Exception as e:
        return jsonify({"reply": f"Грешка: {e}", "monologue": ""})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
