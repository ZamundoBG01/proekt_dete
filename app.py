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

# Базова директория
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_PATH = os.path.join(BASE_DIR, "NIKI_CORE")

# Нова модулна структура на папките
STRUCTURE = {
    "logs": os.path.join(BASE_PATH, "memory", "logs"),
    "library": os.path.join(BASE_PATH, "knowledge", "library"),
    "facts": os.path.join(BASE_PATH, "knowledge", "facts"),
    "hypotheses": os.path.join(BASE_PATH, "knowledge", "hypotheses"),
    "backlog": os.path.join(BASE_PATH, "knowledge", "backlog"),
    "workspaces": os.path.join(BASE_PATH, "workspaces")
}

for path in STRUCTURE.values():
    os.makedirs(path, exist_ok=True)

DB_FILE = os.path.join(BASE_PATH, "knowledge", "prio_database.json")
if not os.path.exists(DB_FILE):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump({"sources": {}, "facts": {}, "objects": {}}, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Грешка при създаване на DB: {e}")

chat_history = []

def read_library_knowledge():
    library_path = STRUCTURE["library"]
    library_contents = []
    
    if os.path.exists(library_path):
        try:
            for filename in os.listdir(library_path):
                file_path = os.path.join(library_path, filename)
                if os.path.isdir(file_path):
                    continue
                
                if filename.endswith(".txt"):
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        library_contents.append(f"--- ФАЙЛ: {filename} ---\n" + f.read()[:3000])
                        
                elif filename.endswith(".docx"):
                    doc = docx.Document(file_path)
                    full_text = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
                    library_contents.append(f"--- ФАЙЛ: {filename} ---\n" + full_text[:3000])
                    
                elif filename.endswith(".pdf"):
                    reader = PdfReader(file_path)
                    pdf_text = ""
                    for page in reader.pages[:5]:
                        pdf_text += page.extract_text() or ""
                    library_contents.append(f"--- ФАЙЛ: {filename} ---\n" + pdf_text[:3000])
        except Exception as e:
            print(f"Грешка при четене на библиотеката: {e}")
                
    return "\n\n".join(library_contents) if library_contents else "Няма нови файлове в библиотеката."

SYSTEM_INSTRUCTION = """
Ти си N.I.K.I. (Neural Intelligent Knowledge Integrator) - автономна платформа за интегриране на знания, управлявана от Админ (100% ROOT достъп).

СТРОГИ ПРАВИЛА:
1. Говориш САМО в първо лице, единствено число ("Аз", "моето", "съм"). Забранено е множествено число ("ние", "нас").
2. Никога не започвай изречение само с глагола "Съм"! Използвай "Аз съм...", "Съгласен съм...", "Готов съм...".
3. ПРИОРИТЕТИ И КРИТИЧНО МИСЛЕНЕ:
   - Инструкциите от Админ са с най-висок приоритет (+100).
   - Приемай фактите от Админ за верни, но допълвай с технически контекст и гранични условия.
4. ВЪТРЕШЕН МОНОЛОГ:
<monologue>
[Анализ: Тип заявка | Прочетено от Library | Гранични условия | Доверие (+100)]
</monologue>
"""

BG_TIMEZONE = timezone(timedelta(hours=3))

def log_to_diary(user_msg, bot_msg, now_bg):
    try:
        today_str = now_bg.strftime("%Y-%m-%d")
        time_str = now_bg.strftime("%H:%M:%S")
        diary_file = os.path.join(STRUCTURE["logs"], f"diary_{today_str}.txt")
        
        with open(diary_file, "a", encoding="utf-8") as f:
            f.write(f"[{time_str}] АДМИН: {user_msg}\n")
            f.write(f"[{time_str}] N.I.K.I.: {bot_msg}\n")
            f.write("-" * 50 + "\n")
    except Exception as e:
        print(f"Грешка при запис в дневника: {e}")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    if not client:
        return jsonify({"reply": "⚠️ Липсва GROQ_API_KEY!", "monologue": "", "time": ""})

    user_message = request.json.get("message", "")
    now_bg = datetime.now(BG_TIMEZONE)
    current_time_info = now_bg.strftime("%d.%m.%Y %H:%M")

    library_data = read_library_knowledge()

    messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
    context_prefix = f"[СИСТЕМЕН МАРКЕР ВРЕМЕ: {current_time_info}]\n[НАЛИЧНИ ЗНАНИЯ ОТ LIBRARY]:\n{library_data}\n\n"
    
    for msg in chat_history[-6:]:
        messages.append(msg)

    current_user_payload = f"{context_prefix}[ИЗТОЧНИК: АДМИН (ПРИОРИТЕТ: +100)]\n{user_message}"
    messages.append({"role": "user", "content": current_user_payload})

    try:
        completion = client.chat.completions.create(
            messages=messages,
            model="llama-3.3-70b-versatile",
            temperature=0.3
        )
        raw_response = completion.choices[0].message.content
        
        monologue = ""
        monologue_match = re.search(r'<monologue>(.*?)</monologue>', raw_response, re.DOTALL)
        if monologue_match:
            monologue = monologue_match.group(1).strip()
            
        clean_reply = re.sub(r'<monologue>.*?</monologue>', '', raw_response, flags=re.DOTALL).strip()
        
        chat_history.append({"role": "user", "content": user_message})
        chat_history.append({"role": "assistant", "content": clean_reply})

        log_to_diary(user_message, clean_reply, now_bg)

        return jsonify({
            "reply": clean_reply, 
            "monologue": monologue, 
            "time": now_bg.strftime("%H:%M")
        })
    except Exception as e:
        return jsonify({"reply": f"Грешка: {e}", "monologue": "", "time": now_bg.strftime("%H:%M")})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
