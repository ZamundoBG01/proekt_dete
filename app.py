import os
import json
import re
import shutil
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from groq import Groq
import pypdf
import docx
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACES_DIR = os.path.join(BASE_DIR, "NIKI_CORE", "workspaces")

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

groq_client = Groq(api_key=GROQ_KEY) if GROQ_KEY else None

# --- ИНИЦИАЛИЗАЦИЯ НА БАЗАТА ДАННИ ---
def get_db_connection():
    if not DATABASE_URL:
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return conn
    except Exception as e:
        print(f"Грешка при връзка с DB: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                # Таблица за факти
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS verified_facts (
                        id SERIAL PRIMARY KEY,
                        workspace VARCHAR(100) NOT NULL,
                        content TEXT NOT NULL,
                        category VARCHAR(100),
                        confidence INT DEFAULT 100,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                # Таблица за причинно-следствени вериги
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS causal_chains (
                        id SERIAL PRIMARY KEY,
                        workspace VARCHAR(100) NOT NULL,
                        cause TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.commit()
        except Exception as e:
            print(f"Грешка при създаване на таблици: {e}")
        finally:
            conn.close()

# Стартираме базата при пускане
init_db()

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

# --- ФУНКЦИИ ЗА РАБОТА С ФАКТИ (DB + ФАЙЛОВЕН БЕКЪП) ---
def get_workspace_facts(ws_name):
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT content, category, confidence, created_at FROM verified_facts WHERE workspace = %s ORDER BY id ASC;", (ws_name,))
                rows = cur.fetchall()
                facts = []
                for r in rows:
                    facts.append({
                        "content": r["content"],
                        "category": r["category"],
                        "confidence": r["confidence"],
                        "timestamp": r["created_at"].strftime("%Y-%m-%d %H:%M:%S") if r["created_at"] else ""
                    })
                return facts
        except Exception as e:
            print(f"DB Read Error: {e}")
        finally:
            conn.close()

    # Резервен вариант през JSON
    facts_path = os.path.join(WORKSPACES_DIR, ws_name, "facts", "verified_facts.json")
    if os.path.exists(facts_path):
        try:
            with open(facts_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return []
    return []

def add_workspace_fact(ws_name, content, category="ДИРЕКТЕН ЗАПИС"):
    conn = get_db_connection()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO verified_facts (workspace, content, category) VALUES (%s, %s, %s);", (ws_name, content, category))
                cur.execute("INSERT INTO causal_chains (workspace, cause) VALUES (%s, %s);", (ws_name, content))
                conn.commit()
        except Exception as e:
            print(f"DB Write Error: {e}")
        finally:
            conn.close()

    # Записваме и във файловата система като бекъп
    ws_path = os.path.join(WORKSPACES_DIR, ws_name, "facts")
    os.makedirs(ws_path, exist_ok=True)
    facts_file = os.path.join(ws_path, "verified_facts.json")
    
    existing = []
    if os.path.exists(facts_file):
        try:
            with open(facts_file, "r", encoding="utf-8") as f: existing = json.load(f)
        except: existing = []
    
    existing.append({"content": content, "timestamp": now_str, "confidence": 100, "category": category})
    try:
        with open(facts_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except: pass

def clear_workspace_data(ws_name):
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM verified_facts WHERE workspace = %s;", (ws_name,))
                cur.execute("DELETE FROM causal_chains WHERE workspace = %s;", (ws_name,))
                conn.commit()
        except Exception as e: print(f"DB Clear Error: {e}")
        finally: conn.close()

# --- AI ДВИГАТЕЛ ЗА "ЕФЕКТА НА ПЕПЕРУДАТА" ---
def call_ai_engine(prompt, context_facts=[], file_list=[], library_context=""):
    if not groq_client:
        return {
            "reply": f"Обработена инструкция: {prompt}",
            "thought": "Липсва GROQ_API_KEY."
        }

    try:
        files_str = ", ".join(file_list) if file_list else "Няма качени файлове"

        system_instructions = f"""
        Ти си N.I.K.I. - архитект на логиката и симулациите ("Ефекта на пеперудата") за писатели и гейм-разработчици.

        СПИСЪК НА ФАЙЛОВЕ В БИБЛИОТЕКАТА:
        [{files_str}]

        ПРОВЕРЕНИ ФАКТИ И ПРАВИЛА В ТОЗИ ПРОЕКТ/СВЯТ:
        {json.dumps(context_facts, ensure_ascii=False)}

        СЪДЪРЖАНИЕ НА КАЧЕНИТЕ ФАЙЛОВЕ:
        {library_context[:6000] if library_context else 'Няма допълнителен текст.'}

        ПРАВИЛА ЗА РАБОТА С "ЕФЕКТА НА ПЕПЕРУДАТА":
        1. Ако има директен конфликт с фактите, ЗАДЪЛЖИТЕЛНО започни с:
           "⚠️ **ЛОГИЧЕСКА АЛАРМА (Ефект на пеперудата):**" и обясни защо.

        2. Когато провеждаш АНАЛИЗ или СИМУЛАЦИЯ на промяна:
           - **Секция 1: 🔒 ТВЪРДА ДЕТЕРМИНИРАНА ВЕРИГА (Неизбежни преки последици)**
             Проследи стъпка по стъпка физическите, икономическите и пряко дефинирани логически последици от А до Я.
             
           - **Секция 2: 🎲 СИМУЛАЦИЯ НА 10 ВАРИАНТА (Спонтанни вторични променливи)**
             Изброи до 10 развиващи се разклонения. 
             ВАЖНО: За ВСЕКИ вариант НЕ просто описвай прякото действие, а **генерирай СПОНТАННА ВТОРИЧНА ПРОМЕНЛИВА** (нов герой, ненадеен ресурс, революция, нов конфликт, природно събитие), която се поражда от ситуацията.
             Посочи процентна вероятност (напр. *Вариант 3/10 - 70% вероятност*) и обясни как тази нова променлива отваря **ИЗЦЯЛО НОВ СЮЖЕТЕН КЛОН** за писателя/разработчика.

        3. Отговаряй ВИНАГИ на правилен български език.
        """

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=2500
        )

        raw_reply = response.choices[0].message.content
        cleaned_reply = clean_ai_response(raw_reply)

        return {
            "reply": cleaned_reply,
            "thought": f"AI Engine: Groq (Llama 3.3 70B)\n- Използвани базисни факти: {len(context_facts)}\n- Файлове в библиотеката: {len(file_list)}"
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
            os.makedirs(os.path.join(ws_path, "library"), exist_ok=True)

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
    facts = get_workspace_facts(clean_ws)

    library_path = os.path.join(WORKSPACES_DIR, clean_ws, "library")
    files = []
    if os.path.exists(library_path) and os.path.isdir(library_path):
        try: files = os.listdir(library_path)
        except: files = []

    return jsonify({
        "facts": facts,
        "tasks": [],
        "files": files
    })

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    message = data.get("message", "").strip()
    active_ws = sanitize_ws_name(data.get("workspace", "general"))

    if not message:
        return jsonify({"reply": "Моля, въведете инструкция.", "monologue": None})

    existing_facts = get_workspace_facts(active_ws)

    # Четене на файлове
    library_path = os.path.join(WORKSPACES_DIR, active_ws, "library")
    file_list = []
    library_text = ""
    if os.path.exists(library_path):
        file_list = [f for f in os.listdir(library_path) if os.path.isfile(os.path.join(library_path, f))]
        for fname in file_list:
            fpath = os.path.join(library_path, fname)
            extracted = extract_text_from_file(fpath)
            library_text += f"\n--- ФАЙЛ: {fname} ---\n" + (extracted if extracted else "[ПРАЗЕН ФАЙЛ]")

    # ГЪВКАВА КОМАНДА ЗА ИЗТРИВАНЕ
    match_del = re.match(r"^(изтрий|премахни)(\s+проект|\s+директория)?\s+(.+)$", message, re.IGNORECASE)
    if match_del:
        target_ws = sanitize_ws_name(match_del.group(3))
        if target_ws == "general":
            return jsonify({"reply": "⚠️ Основният проект **GENERAL** не може да бъде изтрит.", "monologue": "Отказано изтриване."})
        
        clear_workspace_data(target_ws)
        target_path = os.path.join(WORKSPACES_DIR, target_ws)
        if os.path.exists(target_path):
            shutil.rmtree(target_path)

        return jsonify({"reply": f"🗑️ Проектът/директорията **{target_ws.upper()}** беше изтрит(а) завинаги (и от базата данни).", "monologue": f"Изтриване: {target_ws}", "target_workspace": "general"})

    if "изтрий всичко" in message.lower():
        clear_workspace_data(active_ws)
        return jsonify({
            "reply": f"🗑️ Всички факти в проект **{active_ws.upper()}** бяха изчистени от базата данни.",
            "monologue": "Изчистване на локалната база данни.",
            "target_workspace": active_ws
        })

    is_save_command = any(kw in message.lower() for kw in ["запиши", "добави факт", "дневник:"])

    if is_save_command:
        clean_text = re.sub(r"^(запиши предното съобщение|запиши|добави факт|дневник:)\s*:?", "", message, flags=re.IGNORECASE).strip()
        if not clean_text:
            clean_text = message

        add_workspace_fact(active_ws, clean_text)

        reply = f"✅ Записах следното за постоянно в базата данни на **{active_ws.upper()}**:\n\n> \"{clean_text}\""
        monologue = f"Запис в базата данни:\n- Съдържание: '{clean_text}'\n- Проект: {active_ws.upper()}"

        return jsonify({
            "reply": reply,
            "monologue": monologue,
            "target_workspace": active_ws
        })

    ai_result = call_ai_engine(message, existing_facts, file_list, library_text)

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
