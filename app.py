import os
import json
import re
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from groq import Groq

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACES_DIR = os.path.join(BASE_DIR, "NIKI_CORE", "workspaces")

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
groq_client = Groq(api_key=GROQ_KEY) if GROQ_KEY else None

def sanitize_ws_name(name):
    """Преобразува имената на проектите в безопасен формат за папки."""
    if not name:
        return "general"
    return name.strip().lower().replace(" ", "_")

def clean_ai_response(text):
    """Автоматично коригира типични граматични грешки и смесени латински букви."""
    if not text:
        return text
    
    # 1. Замяна на визуално сходни латински букви с български (homoglyphs)
    lat_to_cyr = {
        'a': 'а', 'e': 'е', 'o': 'о', 'p': 'р', 'c': 'с', 'x': 'х',
        'A': 'А', 'E': 'Е', 'O': 'О', 'P': 'Р', 'C': 'С', 'X': 'Х'
    }
    
    words = text.split()
    cleaned_words = []
    for word in words:
        # Ако думата съдържа преобладаващо кирилица, заменяме единичните латински букви вътре
        cyr_count = len(re.findall(r'[\u0400-\u04FF]', word))
        if cyr_count > 0:
            for lat, cyr in lat_to_cyr.items():
                word = word.replace(lat, cyr)
        cleaned_words.append(word)
    
    result = " ".join(cleaned_words)

    # 2. Поправка на развалени фрази от буквален превод
    fixes = {
        r"\bСъм съгласен\b": "Съгласен съм",
        r"\bсъм съгласен\b": "съм съгласен",
        r"\bАз съм съгласен\b": "Съгласен съм",
        r"\bСъм готов\b": "Готов съм",
        r"\bсъм готов\b": "съм готов"
    }
    for pattern, replacement in fixes.items():
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    return result

def safe_read_json(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            print(f"Грешка при четене на {file_path}: {e}")
            return []
    return []

def safe_write_json(file_path, data):
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Грешка при запис в {file_path}: {e}")
        return False

def call_ai_engine(prompt, context_facts=[]):
    if not groq_client:
        return {
            "reply": f"Обработена инструкция: {prompt}",
            "thought": "Липсва GROQ_API_KEY. Системата работи в локален режим.",
            "extracted_fact": None
        }

    try:
        system_instructions = f"""
        Ти си N.I.K.I. - усъвършенстван персонален асистент и ядро на системата.
        Твоята цел е да помагаш при изграждането на сюжетни линии, архитектура на MMORPG игри, световни загадки и иновации.
        
        ЗАКОВАНА ПАМЕТ И ФАКТИ ЗА ТОЗИ ПРОЕКТ:
        {json.dumps(context_facts, ensure_ascii=False)}
        
        ПРАВИЛА:
        1. Отговаряй ВИНАГИ на чист, граматически правилен български език.
        2. НИКОГА не противоречи на фактите, записани по-горе. Спазвай стриктно логиката на 'Ефекта на пеперудата'.
        3. Бъди креативен, точен и давай практични идеи за разработка.
        """

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            max_tokens=1500
        )

        raw_reply = response.choices[0].message.content
        cleaned_reply = clean_ai_response(raw_reply)

        return {
            "reply": cleaned_reply,
            "thought": f"AI Engine: Groq (Llama 3.3 70B)\n- Валидиран контекст: {len(context_facts)} факта\n- Автоматично чистене на езика: Активно.",
            "extracted_fact": None
        }
    except Exception as e:
        return {
            "reply": f"Грешка при комуникация с AI модела: {str(e)}",
            "thought": f"Грешка: {str(e)}",
            "extracted_fact": None
        }

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/workspaces", methods=["GET", "POST"])
def handle_workspaces():
    if not os.path.exists(WORKSPACES_DIR):
        os.makedirs(WORKSPACES_DIR, exist_ok=True)

    if request.method == "POST":
        data = request.get_json() or {}
        raw_name = data.get("name", "")
        ws_name = sanitize_ws_name(raw_name)
        
        if ws_name:
            ws_path = os.path.join(WORKSPACES_DIR, ws_name)
            os.makedirs(os.path.join(ws_path, "facts"), exist_ok=True)
            os.makedirs(os.path.join(ws_path, "tasks"), exist_ok=True)
            os.makedirs(os.path.join(ws_path, "library"), exist_ok=True)
            
            facts_file = os.path.join(ws_path, "facts", "verified_facts.json")
            if not os.path.exists(facts_file):
                safe_write_json(facts_file, [])

        return jsonify({"status": "success", "workspace": ws_name})

    try:
        entries = os.listdir(WORKSPACES_DIR)
        workspaces = [d for d in entries if os.path.isdir(os.path.join(WORKSPACES_DIR, d))]
    except Exception:
        workspaces = ["general"]

    other_workspaces = sorted([w for w in workspaces if w.lower() != "general"])
    ordered_workspaces = ["general"] + other_workspaces

    return jsonify({"workspaces": ordered_workspaces})

@app.route("/workspace_data/<path:ws_name>")
def workspace_data(ws_name):
    clean_ws = sanitize_ws_name(ws_name)
    ws_path = os.path.join(WORKSPACES_DIR, clean_ws)

    facts_path = os.path.join(ws_path, "facts", "verified_facts.json")
    facts = safe_read_json(facts_path)

    tasks_path = os.path.join(ws_path, "tasks", "backlog.json")
    tasks = safe_read_json(tasks_path)

    library_path = os.path.join(ws_path, "library")
    files = []
    if os.path.exists(library_path) and os.path.isdir(library_path):
        try:
            files = os.listdir(library_path)
        except Exception:
            files = []

    return jsonify({
        "facts": facts,
        "tasks": tasks,
        "files": files
    })

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    message = data.get("message", "").strip()
    active_ws = sanitize_ws_name(data.get("workspace", "general"))

    if not message:
        return jsonify({"reply": "Моля, въведете инструкция.", "monologue": None})

    facts_path = os.path.join(WORKSPACES_DIR, active_ws, "facts", "verified_facts.json")
    existing_facts = safe_read_json(facts_path)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if "изтрий всичко" in message.lower():
        safe_write_json(facts_path, [])
        return jsonify({
            "reply": f"🗑️ Всички факти и записи в проект **{active_ws.upper()}** бяха изчистени.",
            "monologue": "Изчистване на локалната база данни по заявка.",
            "target_workspace": active_ws
        })

    is_save_command = any(kw in message.lower() for kw in ["запиши", "добави факт", "дневник:"])

    if is_save_command:
        clean_text = re.sub(r"^(запиши предното съобщение|запиши|добави факт|дневник:)\s*:?", "", message, flags=re.IGNORECASE).strip()
        if not clean_text:
            clean_text = message

        new_fact = {
            "content": clean_text,
            "timestamp": now_str,
            "confidence": 100,
            "category": "ДИРЕКТЕН ЗАПИС"
        }
        existing_facts.append(new_fact)
        safe_write_json(facts_path, existing_facts)

        reply = f"✅ Успешно записах следното в **{active_ws.upper()}**:\n\n> \"{clean_text}\""
        monologue = f"Запис във база данни:\n- Съдържание: '{clean_text}'\n- Проект: {active_ws.upper()}"

        return jsonify({
            "reply": reply,
            "monologue": monologue,
            "target_workspace": active_ws
        })

    ai_result = call_ai_engine(message, existing_facts)

    return jsonify({
        "reply": ai_result["reply"],
        "monologue": ai_result["thought"],
        "target_workspace": active_ws
    })

@app.route("/upload", methods=["POST"])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"message": "Няма прикачен файл."}), 400
    
    file = request.files['file']
    ws_name = sanitize_ws_name(request.form.get("workspace", "general"))

    if file.filename == '':
        return jsonify({"message": "Не е избран файл."}), 400

    library_path = os.path.join(WORKSPACES_DIR, ws_name, "library")
    os.makedirs(library_path, exist_ok=True)

    save_path = os.path.join(library_path, file.filename)
    file.save(save_path)

    return jsonify({"message": f"Файлът '{file.filename}' беше успешно качен в {ws_name.upper()}."})

@app.route("/delete_file", methods=["POST"])
def delete_file():
    data = request.get_json() or {}
    ws_name = sanitize_ws_name(data.get("workspace", "general"))
    filename = data.get("filename", "")

    if not filename:
        return jsonify({"message": "Невалидно име на файл."}), 400

    file_path = os.path.join(WORKSPACES_DIR, ws_name, "library", filename)

    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            return jsonify({"message": f"Файлът '{filename}' беше изтрит успешно."})
        except Exception as e:
            return jsonify({"message": f"Грешка при изтриване: {str(e)}"}), 500
    
    return jsonify({"message": "Файлът не бе намерен."}), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
