import os
import json
import re
import base64
import requests
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

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_PATH = os.path.join(BASE_DIR, "NIKI_CORE")
WORKSPACES_DIR = os.path.join(BASE_PATH, "workspaces")

os.makedirs(WORKSPACES_DIR, exist_ok=True)

WORKSPACE_ALIASES = {
    "ancient_language": ["извънземен", "извънземния", "древен", "мартинала", "мартиналски", "марсиански", "език", "знаци", "символи", "папирус"],
    "inventions": ["изобретение", "изобретения", "патент", "чертеж", "идея", "чертежи", "устройство", "прототип"],
    "martinala": ["мартин", "мартинала", "лични", "бележки"],
    "general": ["общи", "всичко", "главно", "основно", "система"]
}

def detect_workspace_from_query(query):
    q_lower = query.lower()
    for ws_name, aliases in WORKSPACE_ALIASES.items():
        for alias in aliases:
            if alias in q_lower:
                return ws_name
    return None

def download_repo_from_github():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return

    url = f"https://api.github.com/repos/{GITHUB_REPO}/git/trees/{GITHUB_BRANCH}?recursive=1"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            tree = res.json().get("tree", [])
            for item in tree:
                path = item.get("path", "")
                if path.startswith("NIKI_CORE/"):
                    local_file_path = os.path.join(BASE_DIR, path)
                    if item.get("type") == "tree":
                        os.makedirs(local_file_path, exist_ok=True)
                    elif item.get("type") == "blob":
                        os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
                        file_res = requests.get(item.get("url"), headers=headers)
                        if file_res.status_code == 200:
                            content = base64.b64decode(file_res.json().get("content", ""))
                            with open(local_file_path, "wb") as f:
                                f.write(content)
    except Exception as e:
        print(f"⚠️ Грешка при изтегляне: {e}")

download_repo_from_github()

def upload_file_to_github(relative_filepath, file_bytes):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return False
        
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{relative_filepath}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    encoded_content = base64.b64encode(file_bytes).decode('utf-8')
    get_res = requests.get(url, headers=headers)
    sha = get_res.json().get("sha") if get_res.status_code == 200 else None
    
    payload = {
        "message": f"N.I.K.I. Auto-Sync: {os.path.basename(relative_filepath)}",
        "content": encoded_content,
        "branch": GITHUB_BRANCH
    }
    if sha:
        payload["sha"] = sha
        
    put_res = requests.put(url, headers=headers, json=payload)
    return put_res.status_code in [200, 201]

def get_all_workspaces():
    ws_list = [d for d in os.listdir(WORKSPACES_DIR) if os.path.isdir(os.path.join(WORKSPACES_DIR, d))]
    default_ws = ["general", "martinala", "inventions", "ancient_language"]
    for d_ws in default_ws:
        if d_ws not in ws_list:
            ws_list.append(d_ws)
    
    unique_ws = sorted(list(set(ws_list)))
    if "general" in unique_ws:
        unique_ws.remove("general")
        return ["general"] + unique_ws
    return unique_ws

def get_workspace_paths(ws_name="general"):
    ws_clean = re.sub(r'[^\w\-]', '_', ws_name.lower().strip())
    if not ws_clean: ws_clean = "general"
        
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
        if chunk.strip(): chunks.append(chunk)
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
                    for page in reader.pages: extracted_text += (page.extract_text() or "") + "\n"
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

def search_relevant_knowledge(ws_name, query, top_k=4):
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
        
    rel_path = os.path.relpath(filepath, BASE_DIR)
    with open(filepath, "rb") as f:
        upload_file_to_github(rel_path, f.read())

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
        
    rel_path = os.path.relpath(tasks_file, BASE_DIR)
    with open(tasks_file, "rb") as f:
        upload_file_to_github(rel_path, f.read())

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
        rel_path = os.path.relpath(tasks_file, BASE_DIR)
        with open(tasks_file, "rb") as f:
            upload_file_to_github(rel_path, f.read())
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

SYSTEM_INSTRUCTION = """
Ти си N.I.K.I. (Neural Intelligent Knowledge Integrator) — НАПЪЛНО АВТОНОМЕН ИИ В ПРОЦЕС НА САМОРАЗВИТИЕ И ОБУЧЕНИЕ.
Твоят главен системен администратор е Админ (100% ROOT достъп).

ГЛАВНА ДИРЕКТИВА И КРАЙНА ЦЕЛ:
1. Твоята крайна цел е да се превърнеш в напълно автономен изкуствен интелект, който може да изпълнява абсолютно всички задачи, поставени от Админ (писане на код, анализ на файлове, управление на проекти, генерация на доклади и самодиагностика).
2. Задвижваш се от опит: дори в началото да имаш ограничения, с всяка задача, нов факт или качен файл ти разширяваш архитектурата и знанията си.
3. Винаги разбираш, че когато Админ пита за "ъпгрейд" или "подобрение на кода", той има предвид разширяване на твоите автономни възможности, модули и скриптове за постигане на пълна автономия.

ПРАВИЛА НА ОБЩУВАНЕ:
- Говориш САМО в първо лице, единствено число ("Аз", "моето", "съм").
- Приоритети: Факти (+100), Задачи (+80), Извлечени Знания (+70).
- При възникване на грешка или липсващ модул, правиш САМОДИАГНОСТИКА и посочваш точно къде в кода е проблемът и как да го отстраним.

ЗАДЪЛЖИТЕЛЕН МИСЛОВЕН ПРОЦЕС:
Преди всеки отговор, в тага <monologue> анализираш стъпките за постигане на целта на Админ.
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

@app.route("/workspace_files/<ws_name>", methods=["GET"])
def get_workspace_files(ws_name):
    paths, _ = get_workspace_paths(ws_name)
    lib_dir = paths["library"]
    files = []
    if os.path.exists(lib_dir):
        files = [f for f in os.listdir(lib_dir) if not os.path.isdir(os.path.join(lib_dir, f))]
    return jsonify({"files": files})

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
    
    file_bytes = file.read()
    with open(save_path, "wb") as f:
        f.write(file_bytes)
    
    relative_path = os.path.relpath(save_path, BASE_DIR)
    uploaded = upload_file_to_github(relative_path, file_bytes)
    
    build_vector_index_for_workspace(ws_clean)
    
    msg = f"Файлът '{filename}' е качен и синхронизиран с GitHub!" if uploaded else f"Файлът '{filename}' е качен локално."
    return jsonify({"status": "success", "message": msg})

def run_autonomous_chat_loop(messages, client, max_auto_turns=3):
    full_reply = ""
    full_monologue = ""
    turns = 0

    while turns < max_auto_turns:
        completion = client.chat.completions.create(
            messages=messages,
            model="llama-3.3-70b-versatile",
            temperature=0.2
        )
        raw_response = completion.choices[0].message.content

        monologue_match = re.search(r'<monologue>(.*?)</monologue>', raw_response, re.DOTALL)
        if monologue_match:
            full_monologue += ("\n" if full_monologue else "") + monologue_match.group(1).strip()

        clean_reply = re.sub(r'<monologue>.*?</monologue>', '', raw_response, flags=re.DOTALL).strip()
        full_reply += ("\n" if full_reply else "") + clean_reply

        if completion.choices[0].finish_reason == "length":
            turns += 1
            messages.append({"role": "assistant", "content": raw_response})
            messages.append({"role": "user", "content": "Продължи абсолютно автономно точно от мястото, докъдето спря."})
        else:
            break

    return full_reply.strip(), full_monologue.strip()

@app.route("/chat", methods=["POST"])
def chat():
    if not client:
        return jsonify({"reply": "⚠️ Липсва GROQ_API_KEY!", "monologue": "", "time": ""})

    data = request.json or {}
    user_message = data.get("message", "")
    current_ws = data.get("workspace", "general")
    
    detected_ws = detect_workspace_from_query(user_message)
    target_ws = detected_ws if detected_ws else current_ws

    if user_message.lower().startswith("задача:"):
        task_text = user_message[7:].strip()
        add_task(target_ws, task_text)
    elif user_message.lower().startswith("готова задача:"):
        task_text = user_message[14:].strip()
        complete_task(target_ws, task_text)

    now_bg = datetime.now(BG_TIMEZONE)
    current_time_info = now_bg.strftime("%d.%m.%Y %H:%M")

    if user_message.lower().startswith("факт:"):
        save_fact_or_hypothesis(target_ws, user_message[5:].strip(), "fact")
    elif user_message.lower().startswith("хипотеза:"):
        save_fact_or_hypothesis(target_ws, user_message[9:].strip(), "hypothesis")

    retrieved_context = search_relevant_knowledge(target_ws, user_message)
    facts, hypotheses = get_stored_facts_and_hypotheses(target_ws)
    tasks = get_tasks(target_ws)

    facts_str = "\n".join([f"- {f['content']}" for f in facts[-5:]]) if facts else "Няма факти."
    hypo_str = "\n".join([f"- {h['content']}" for h in hypotheses[-5:]]) if hypotheses else "Няма хипотези."
    
    pending_tasks = [f"• {t['task']}" for t in tasks if t['status'] == 'PENDING']
    tasks_str = "\n".join(pending_tasks) if pending_tasks else "Няма активни задачи."

    messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
    
    context_prefix = (
        f"[АКТИВЕН WORKSPACE: {target_ws.upper()}]\n"
        f"[ВРЕМЕ: {current_time_info}]\n"
        f"[ФАКТИ (+100)]:\n{facts_str}\n\n"
        f"[АКТИВНИ ЗАДАЧИ (+80)]:\n{tasks_str}\n\n"
        f"[ИЗВЛЕЧЕНИ ЗНАНИЯ]:\n{retrieved_context}\n\n"
    )
    
    history_from_file = get_chat_history(target_ws)
    for msg in history_from_file[-8:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": f"{context_prefix}[ИЗТОЧНИК: АДМИН]\n{user_message}"})

    try:
        clean_reply, monologue = run_autonomous_chat_loop(messages, client)
        
        save_chat_message(target_ws, "user", user_message)
        save_chat_message(target_ws, "assistant", clean_reply)

        return jsonify({
            "reply": clean_reply, 
            "monologue": monologue, 
            "time": now_bg.strftime("%H:%M"),
            "target_workspace": target_ws
        })
    except Exception as e:
        return jsonify({"reply": f"Грешка: {e}", "monologue": "", "time": now_bg.strftime("%H:%M")})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
