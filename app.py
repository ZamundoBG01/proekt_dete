import os
import json
import re
import shutil
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from groq import Groq
import pypdf
import docx

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACES_DIR = os.path.join(BASE_DIR, "NIKI_CORE", "workspaces")

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
groq_client = Groq(api_key=GROQ_KEY) if GROQ_KEY else None

def sanitize_ws_name(name):
    if not name:
        return "general"
    return name.strip().lower().replace(" ", "_")

def clean_ai_response(text):
    if not text:
        return text
    
    lat_to_cyr = {
        'a': 'а', 'e': 'е', 'o': 'о', 'p': 'р', 'c': 'с', 'x': 'х',
        'A': 'А', 'E': 'Е', 'O': 'О', 'P': 'Р', 'C': 'С', 'X': 'Х'
    }
    
    words = text.split()
    cleaned_words = []
    for word in words:
        cyr_count = len(re.findall(r'[\u0400-\u04FF]', word))
        if cyr_count > 0:
            for lat, cyr in lat_to_cyr.items():
                word = word.replace(lat, cyr)
        cleaned_words.append(word)
    
    result = " ".join(cleaned_words)

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

def extract_text_from_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    extracted_text = ""
    try:
        if ext == ".pdf":
            reader = pypdf.PdfReader(file_path)
            for page in reader.pages:
                extracted_text += (page.extract_text() or "") + "\n"
        elif ext in [".docx", ".doc"]:
            doc = docx.Document(file_path)
            for paragraph in doc.paragraphs:
                extracted_text += paragraph.text + "\n"
        elif ext in [".txt", ".json", ".md"]:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    extracted_text = f.read()
            except UnicodeDecodeError:
                with open(file_path, "r", encoding="cp1251") as f:
                    extracted_text = f.read()
    except Exception as e:
        print(f"Грешка при извличане на текст от {file_path}: {e}")
    return extracted_text.strip()

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

def call_ai_engine(prompt, context_facts=[], file_list=[], library_context="", causal_graph=[]):
    if not groq_client:
        return {
            "reply": f"Обработена инструкция: {prompt}",
            "thought": "Липсва GROQ_API_KEY. Системата работи в локален режим."
        }

    try:
        files_str = ", ".join(file_list) if file_list else "Няма качени файлове"

        system_instructions = f"""
        Ти си N.I.K.I. - архитект на логиката и симулациите ("Ефекта на пеперудата") за писатели и гейм-разработчици.

        СПИСЪК НА ВСИЧКИ ФАЙЛОВЕ В БИБЛИОТЕКАТА ({len(file_list)} бр.):
        [{files_str}]

        ПРОВЕРЕНИ ФАКТИ В ПРОЕКТА:
        {json.dumps(context_facts, ensure_ascii=False)}

        ВЕРИГИ НА ПРИЧИННО-СЛЕДСТВЕНИ ВРЪЗКИ:
        {json.dumps(causal_graph, ensure_ascii=False)}

        СЪДЪРЖАНИЕ НА КАЧЕНИТЕ ФАЙЛОВЕ:
        {library_context[:6000] if library_context else 'Няма допълнителен текст в файловете.'}

        ПРАВИЛА ЗА РАБОТА С "ЕФЕКТА НА ПЕПЕРУДАТА":
        1. Ако има логически конфликт с базовите факти, ЗАДЪЛЖИТЕЛНО започни с:
           "⚠️ **ЛОГИЧЕСКА АЛАРМА (Ефект на пеперудата):**" и обясни грешката.

        2. Когато потребителят поиска АНАЛИЗ, СИМУЛАЦИЯ или ПРЕДСКАЗАНИЕ за промяна на елемент:
           - Раздели отговора си на две ясни секции:
             А) 🔒 **ТВЪРДА ДЕТЕРМИНИРАНА ВЕРИГА (Неизбежни последствия):**
                Проследи стъпка по стъпка физическите и пряко дефинирани логически последици от промяната от А до Я.
             Б) 🎲 **СИМУЛАЦИЯ НА 10 СЦЕНАРИЯ (Варианти с вероятности):**
                Изброи до 10 възможни развиващи се разклонения. За всеки вариант посочи процентова вероятност (напр. Вариант 3/10 - 75% вероятност) и обясни кратко защо това е най-вероятният сценарий.

        3. Отговаряй ВИНАГИ на правилен български език.
        """

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4,
            max_tokens=2000
        )

        raw_reply = response.choices[0].message.content
        cleaned_reply = clean_ai_response(raw_reply)

        return {
            "reply": cleaned_reply,
            "thought": f"AI Engine: Groq (Llama 3.3 70B)\n- Сканирани факти: {len(context_facts)}\n- Логически вериги: {len(causal_graph)}\n- Файлове в библиотека: {len(file_list)}"
        }
    except Exception as e:
        return {
            "reply": f"Грешка при комуникация с AI модела: {str(e)}",
            "thought": f"Грешка: {str(e)}"
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

    ws_path = os.path.join(WORKSPACES_DIR, active_ws)
    facts_path = os.path.join(ws_path, "facts", "verified_facts.json")
    causal_path = os.path.join(ws_path, "facts", "causal_graph.json")
    
    existing_facts = safe_read_json(facts_path)
    causal_graph = safe_read_json(causal_path)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Списък и четене на файлове
    library_path = os.path.join(ws_path, "library")
    file_list = []
    library_text = ""
    if os.path.exists(library_path):
        file_list = [f for f in os.listdir(library_path) if os.path.isfile(os.path.join(library_path, f))]
        for fname in file_list:
            fpath = os.path.join(library_path, fname)
            extracted = extract_text_from_file(fpath)
            library_text += f"\n--- ФАЙЛ: {fname} ---\n" + (extracted if extracted else "[ПРАЗЕН ФАЙЛ]")

    # КОМАНДА: ИЗТРИВАНЕ НА ПРОЕКТ
    match_del = re.match(r"^изтрий проект\s+(.+)$", message, re.IGNORECASE)
    if match_del:
        target_ws = sanitize_ws_name(match_del.group(1))
        if target_ws == "general":
            return jsonify({"reply": "⚠️ Основният проект **GENERAL** не може да бъде изтрит.", "monologue": "Отказано изтриване."})
        
        target_path = os.path.join(WORKSPACES_DIR, target_ws)
        if os.path.exists(target_path):
            shutil.rmtree(target_path)
            return jsonify({"reply": f"🗑️ Проектът **{target_ws.upper()}** беше изтрит завинаги.", "monologue": f"Изтриване: {target_ws}", "target_workspace": "general"})

    # КОМАНДА: ПРЕИМЕНУВАНЕ НА ПРОЕКТ
    match_ren = re.match(r"^преименувай проект\s+(.+)\s+на\s+(.+)$", message, re.IGNORECASE)
    if match_ren:
        old_ws = sanitize_ws_name(match_ren.group(1))
        new_ws = sanitize_ws_name(match_ren.group(2))

        if old_ws == "general":
            return jsonify({"reply": "⚠️ Основният проект **GENERAL** не може да бъде преименуван.", "monologue": "Отказана операция."})

        old_path = os.path.join(WORKSPACES_DIR, old_ws)
        new_path = os.path.join(WORKSPACES_DIR, new_ws)

        if not os.path.exists(old_path):
            return jsonify({"reply": f"❌ Проектът **{old_ws}** не съществува.", "monologue": "Грешка при преименуване."})

        if os.path.exists(new_path):
            return jsonify({"reply": f"⚠️ Вече съществува проект с име **{new_ws}**.", "monologue": "Дублирано име."})

        os.rename(old_path, new_path)
        return jsonify({"reply": f"✏️ Проектът **{old_ws.upper()}** беше преименуван на **{new_ws.upper()}**.", "monologue": "Успешно преименуване.", "target_workspace": new_ws})

    if "изтрий всичко" in message.lower():
        safe_write_json(facts_path, [])
        safe_write_json(causal_path, [])
        return jsonify({
            "reply": f"🗑️ Всички факти и логически вериги в проект **{active_ws.upper()}** бяха изчистени.",
            "monologue": "Изчистване на локалната база данни.",
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

        causal_graph.append({"cause": clean_text, "added_on": now_str})
        safe_write_json(causal_path, causal_graph)

        reply = f"✅ Записах следното във фактите и логическата верига на **{active_ws.upper()}**:\n\n> \"{clean_text}\""
        monologue = f"Запис във фактите:\n- Съдържание: '{clean_text}'\n- Проект: {active_ws.upper()}"

        return jsonify({
            "reply": reply,
            "monologue": monologue,
            "target_workspace": active_ws
        })

    ai_result = call_ai_engine(message, existing_facts, file_list, library_text, causal_graph)

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

    return jsonify({"message": f"Файлът '{file.filename}' беше качен успешно в {ws_name.upper()}."})

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
