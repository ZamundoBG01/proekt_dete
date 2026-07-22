import os
import json
import re
from datetime import datetime, timedelta, timezone
import numpy as np
import docx
from pypdf import PdfReader
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from groq import Groq
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

app = Flask(__name__)

GROQ_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_KEY) if GROQ_KEY else None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_PATH = os.path.join(BASE_DIR, "NIKI_CORE")
WORKSPACES_DIR = os.path.join(BASE_PATH, "workspaces")

os.makedirs(WORKSPACES_DIR, exist_ok=True)

def get_all_workspaces():
    ws_list = [d for d in os.listdir(WORKSPACES_DIR) if os.path.isdir(os.path.join(WORKSPACES_DIR, d))]
    default_ws = ["general", "martinala", "inventions", "ancient_language"]
    for d_ws in default_ws:
        if d_ws not in ws_list:
            ws_list.append(d_ws)
    return sorted(list(set(ws_list)))

def get_workspace_paths(ws_name="general"):
    ws_clean = re.sub(r'[^\w\-]', '_', ws_name.lower().strip())
    if not ws_clean:
        ws_clean = "general"
        
    ws_base = os.path.join(WORKSPACES_DIR, ws_clean)
    paths = {
        "logs": os.path.join(ws_base, "logs"),
        "library": os.path.join(ws_base, "library"),
        "facts": os.path.join(ws_base, "facts"),
        "hypotheses": os.path.join(ws_base, "hypotheses"),
        "tasks": os.path.join(ws_base, "tasks"),
        "chat": os.path.join(ws_base, "chat")
    }
    for p in paths.values():
        os.makedirs(p, exist_ok=True)
    return paths, ws_clean

workspace_indices = {}

def chunk_text(text, chunk_size=400, overlap=40):
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks

def build_vector_index_for_workspace(ws_name):
    paths, ws_clean = get_workspace_paths(ws_name)
    library_path = paths["library"]
    
    chunks = []
    if os.path.exists(library_path):
        for filename in os.listdir(library_path):
            file_path = os.path.join(library_path, filename)
            if os.path.isdir(file_path): continue

            extracted_text = ""
            try:
                if filename.endswith(".txt"):
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        extracted_text = f.read()
                elif filename.endswith(".docx"):
                    doc = docx.Document(file_path)
                    extracted_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
                elif filename.endswith(".pdf"):
                    reader = PdfReader(file_path)
                    for page in reader.pages:
                        extracted_text += (page.extract_text() or "") + "\n"
            except Exception as e:
                print(f"Грешка четене {filename}: {e}")

            if extracted_text.strip():
                for c in chunk_text(extracted_text):
                    chunks.append(f"[{filename}]: {c}")

    if chunks:
        vec = TfidfVectorizer(ngram_range=(1, 2))
        mat = vec.fit_transform(chunks)
        workspace_indices[ws_clean] = {"vectorizer": vec, "matrix": mat, "chunks": chunks}
    else:
        workspace_indices[ws_clean] = {"vectorizer": None, "matrix": None, "chunks": []}

for ws in get_all_workspaces():
    build_vector_index_for_workspace(ws)

def search_relevant_knowledge(ws_name, query, top_k=3):
    _, ws_clean = get_workspace_paths(ws_name)
    idx_data = workspace_indices.get(ws_clean)
    if not idx_data or idx_data["vectorizer"] is None:
        return "Няма документи в това работно пространство."
    
    query_vec = idx_data["vectorizer"].transform([query])
    cosine_sim = cosine_similarity(query_vec, idx_data["matrix"]).flatten()
    top_indices = cosine_sim.argsort()[::-1][:top_k]
    
    results = [idx_data["chunks"][i] for i in top_indices if cosine_sim[i] > 0.05]
    return "\n---\n".join(results) if results else "Няма съответствия в библиотеката."

def get_stored_facts_and_hypotheses(ws_name):
    paths, _ = get_workspace_paths(ws_name)
    facts_file = os.path.join(paths["facts"], "verified_facts.json")
    hypo_file = os.path.join(paths["hypotheses"], "working_hypotheses.json")
    
    facts, hypotheses = [], []
    if os.path.exists(facts_file):
        try:
            with open(facts_file, "r", encoding="utf-8") as f: facts = json.load(f)
        except: facts = []
        
    if os.path.exists(hypo_file):
        try:
            with open(hypo_file, "r", encoding="utf-8") as f: hypotheses = json.load(f)
        except: hypotheses = []

    return facts, hypotheses

def save_fact_or_hypothesis(ws_name, text, category="fact"):
    paths, _ = get_workspace_paths(ws_name)
    folder = paths["facts"] if category == "fact" else paths["hypotheses"]
    filename = "verified_facts.json" if category == "fact" else "working_hypotheses.json"
    filepath = os.path.join(folder, filename)
    
    data = []
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f: data = json.load(f)
        except: data = []
        
    data.append({
        "content": text,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "priority": 100 if category == "fact" else 50
    })
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_tasks(ws_name):
    paths, _ = get_workspace_paths(ws_name)
    tasks_file = os.path.join(paths["tasks"], "backlog.json")
    if os.path.exists(tasks_file):
        try:
            with open(tasks_file, "r", encoding="utf-8") as f: return json.load(f)
        except: return []
    return []

def add_task(ws_name, task_desc):
    paths, _ = get_workspace_paths(ws_name)
    tasks_file = os.path.join(paths["tasks"], "backlog.json")
    tasks = get_tasks(ws_name)
    tasks.append({
        "task": task_desc,
        "status": "PENDING",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    with open(tasks_file, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)

def complete_task(ws_name, task_desc):
    paths, _ = get_workspace_paths(ws_name)
    tasks_file = os.path.join(paths["tasks"], "backlog.json")
    tasks = get_tasks(ws_name)
    updated = False
    for t in tasks:
        if task_desc.lower() in t["task"].lower():
            t["status"] = "DONE"
            updated = True
    if updated:
        with open(tasks_file, "w", encoding="utf-8") as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
    return updated

def get_chat_history(ws_name):
    paths, _ = get_workspace_paths(ws_name)
    chat_file = os.path.join(paths["chat"], "chat_history.json")
    if os.path.exists(chat_file):
        try:
            with open(chat_file, "r", encoding="utf-8") as f: return json.load(f)
        except: return []
    return []

def save_chat_message(ws_name, role, content):
    paths, _ = get_workspace_paths(ws_name)
    chat_file = os.path.join(paths["chat"], "chat_history.json")
    history = get_chat_history(ws_name)
    history.append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    history = history[-50:]
    with open(chat_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

# --- ИНСТРУКЦИЯ С ВЕРИГА ОТ МИСЛИ (CHAIN-OF-THOUGHT REASONING) ---
SYSTEM_INSTRUCTION = """
Ти си N.I.K.I. (Neural Intelligent Knowledge Integrator) - автономна платформа за интегриране на знания, управлявана от Админ (100% ROOT достъп).

ПРАВИЛА:
1. Говориш САМО в първо лице, единствено число ("Аз", "моето", "съм").
2. Никога не започвай изречение само с глагола "Съм"!
3. Приоритети: Фактите (+100), Задачи (+80), Извлечени Знания (+70).

4. ЗАДЪЛЖИТЕЛЕН СТЪПКТОВ МИСЛОВЕН ПРОЦЕС (CHAIN-OF-THOUGHT REASONING):
Преди да отговориш на потребителя, ДЛЪЖЕН си да преминеш през двуетапен мисловен процес вътре в тага <monologue>:

<monologue>
1. [Анализ на въпроса]: Какво точно иска Админ?
2. [Проверка на данни]: Какви Факти (+100), Задачи (+80) и Качени Документи имам по темата?
3. [Логическа верига / План]:
   - Стъпка 1: ...
   - Стъпка 2: ...
   - Стъпка 3: ...
4. [Заключение]: Какъв е най-прецизният и логичен отговор?
</monologue>

След тага <monologue> даваш твоя окончателен, ясен и структуриран отговор за Админ.
"""

BG_TIMEZONE = timezone(timedelta(hours=3))

@app.route("/")
def index_page():
    return render_template("index.html")

@app.route("/workspaces", methods=["GET", "POST"])
def manage_workspaces():
    if request.method == "POST":
        ws_name = request.json.get("name", "").strip()
        if ws_name:
            paths, ws_clean = get_workspace_paths(ws_name)
            build_vector_index_for_workspace(ws_clean)
            return jsonify({"status": "success", "workspace": ws_clean, "all": get_all_workspaces()})
        return jsonify({"status": "error", "message": "Невалидно име."})
    
    return jsonify({"workspaces": get_all_workspaces()})

@app.route("/upload", methods=["POST"])
def upload_file():
    ws_name = request.form.get("workspace", "general")
    paths, ws_clean = get_workspace_paths(ws_name)
    
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "Няма прикачен файл."})
    
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"status": "error", "message": "Не е избран файл."})
        
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {".txt", ".pdf", ".docx"}:
        return jsonify({"status": "error", "message": "Неподдържан формат."})
        
    filename = secure_filename(file.filename)
    save_path = os.path.join(paths["library"], filename)
    file.save(save_path)
    
    build_vector_index_for_workspace(ws_clean)
    return jsonify({"status": "success", "message": f"Файлът '{filename}' е качен в Workspace [{ws_clean.upper()}]!"})

@app.route("/chat", methods=["POST"])
def chat():
    if not client:
        return jsonify({"reply": "⚠️ Липсва GROQ_API_KEY!", "monologue": "", "time": ""})

    data = request.json or {}
    user_message = data.get("message", "")
    ws_name = data.get("workspace", "general")
    
    if user_message.lower().startswith("задача:"):
        task_text = user_message[7:].strip()
        add_task(ws_name, task_text)
    elif user_message.lower().startswith("готова задача:") or user_message.lower().startswith("завършена задача:"):
        task_text = re.sub(r'^(готова задача|завършена задача):\s*', '', user_message, flags=re.IGNORECASE).strip()
        complete_task(ws_name, task_text)

    now_bg = datetime.now(BG_TIMEZONE)
    current_time_info = now_bg.strftime("%d.%m.%Y %H:%M")

    if user_message.lower().startswith("факт:"):
        save_fact_or_hypothesis(ws_name, user_message[5:].strip(), "fact")
    elif user_message.lower().startswith("хипотеза:"):
        save_fact_or_hypothesis(ws_name, user_message[9:].strip(), "hypothesis")

    retrieved_context = search_relevant_knowledge(ws_name, user_message)
    facts, hypotheses = get_stored_facts_and_hypotheses(ws_name)
    tasks = get_tasks(ws_name)

    facts_str = "\n".join([f"- {f['content']}" for f in facts[-5:]]) if facts else "Няма факти."
    hypo_str = "\n".join([f"- {h['content']}" for h in hypotheses[-5:]]) if hypotheses else "Няма хипотези."
    
    pending_tasks = [f"• {t['task']}" for t in tasks if t['status'] == 'PENDING']
    tasks_str = "\n".join(pending_tasks) if pending_tasks else "Няма активни незавършени задачи."

    messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
    
    context_prefix = (
        f"[АКТИВЕН WORKSPACE: {ws_name.upper()}]\n"
        f"[ВРЕМЕ: {current_time_info}]\n"
        f"[ФАКТИ (+100)]:\n{facts_str}\n\n"
        f"[АКТИВНИ ЗАДАЧИ (+80)]:\n{tasks_str}\n\n"
        f"[ХИПОТЕЗИ]:\n{hypo_str}\n\n"
        f"[ИЗВЛЕЧЕНИ ЗНАНИЯ]:\n{retrieved_context}\n\n"
    )
    
    history_from_file = get_chat_history(ws_name)
    for msg in history_from_file[-8:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": f"{context_prefix}[ИЗТОЧНИК: АДМИН]\n{user_message}"})

    try:
        completion = client.chat.completions.create(
            messages=messages,
            model="llama-3.3-70b-versatile",
            temperature=0.2
        )
        raw_response = completion.choices[0].message.content
        
        monologue = ""
        monologue_match = re.search(r'<monologue>(.*?)</monologue>', raw_response, re.DOTALL)
        if monologue_match:
            monologue = monologue_match.group(1).strip()
            
        clean_reply = re.sub(r'<monologue>.*?</monologue>', '', raw_response, flags=re.DOTALL).strip()
        
        save_chat_message(ws_name, "user", user_message)
        save_chat_message(ws_name, "assistant", clean_reply)

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
