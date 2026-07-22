import os
import json
import base64
import requests
from flask import Flask, request, jsonify, render_template_string
from docx import Document
import io

app = Flask(__name__)

# Config
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO_NAME = os.environ.get("REPO_NAME", "ZamundoBG01/proekt_N.I.K.I.")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

WORKSPACES_DIR = "NIKI_CORE/workspaces"
GLOBAL_INDEX_FILE = "NIKI_CORE/глобален_индекс.json"

DEFAULT_WORKSPACES = [
    "GENERAL",
    "ANCIENT_LANGUAGE",
    "INVENTIONS",
    "MARTINALA"
]

def github_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

def get_github_file(path):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{path}"
    res = requests.get(url, headers=github_headers())
    if res.status_code == 200:
        data = res.json()
        content = base64.b64decode(data['content']).decode('utf-8')
        return content, data['sha']
    return None, None

def save_github_file(path, content_str, commit_message, sha=None, is_binary=False):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{path}"
    if is_binary:
        encoded_content = base64.b64encode(content_str).decode('utf-8')
    else:
        encoded_content = base64.b64encode(content_str.encode('utf-8')).decode('utf-8')
        
    payload = {
        "message": commit_message,
        "content": encoded_content
    }
    if sha:
        payload["sha"] = sha
    res = requests.put(url, headers=github_headers(), json=payload)
    return res.status_code in [200, 201]

def delete_github_file(path, sha, commit_message):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{path}"
    payload = {
        "message": commit_message,
        "sha": sha
    }
    res = requests.delete(url, headers=github_headers(), json=payload)
    return res.status_code == 200

def list_github_folder(path):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{path}"
    res = requests.get(url, headers=github_headers())
    if res.status_code == 200:
        return res.json()
    return []

def init_environment():
    for ws in DEFAULT_WORKSPACES:
        facts_path = f"{WORKSPACES_DIR}/{ws.lower()}/facts/verified_facts.json"
        content, _ = get_github_file(facts_path)
        if content is None:
            save_github_file(facts_path, json.dumps([], ensure_ascii=False, indent=2), f"Init facts for {ws}")

        tasks_path = f"{WORKSPACES_DIR}/{ws.lower()}/tasks/backlog.json"
        content, _ = get_github_file(tasks_path)
        if content is None:
            save_github_file(tasks_path, json.dumps([], ensure_ascii=False, indent=2), f"Init tasks for {ws}")

try:
    init_environment()
except Exception as e:
    print(f"Init Error: {e}")

def call_groq_llm(messages, system_prompt=""):
    if not GROQ_API_KEY:
        return "Грешка: Липсва GROQ_API_KEY."
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    formatted_messages = []
    if system_prompt:
        formatted_messages.append({"role": "system", "content": system_prompt})
    formatted_messages.extend(messages)
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": formatted_messages,
        "temperature": 0.3,
        "max_tokens": 3000
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=45)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return f"Грешка от Llama AI API: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Грешка при връзка с AI: {str(e)}"

def extract_docx_text(file_bytes):
    try:
        doc = Document(io.BytesIO(file_bytes))
        full_text = []
        for para in doc.paragraphs:
            if para.text.strip():
                full_text.append(para.text.strip())
        return "\n".join(full_text)
    except Exception as e:
        return f"Грешка при четене на DOCX: {str(e)}"

def create_docx_file(title, paragraphs_list):
    doc = Document()
    doc.add_heading(title, 0)
    for p in paragraphs_list:
        doc.add_paragraph(p)
    out_stream = io.BytesIO()
    doc.save(out_stream)
    return out_stream.getvalue()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="bg">
<head>
    <meta charset="UTF-8">
    <title>N.I.K.I. CORE</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #0f172a; color: #f8fafc; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        .sidebar { background-color: #1e293b; min-height: 100vh; padding: 20px; border-right: 1px solid #334155; }
        .main-content { padding: 20px; }
        .right-panel { background-color: #1e293b; min-height: 100vh; padding: 20px; border-left: 1px solid #334155; }
        .chat-box { height: 60vh; overflow-y: auto; background-color: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 15px; margin-bottom: 15px; }
        .ws-btn { display: block; width: 100%; text-align: left; margin-bottom: 8px; background-color: #334155; color: #fff; border: none; padding: 10px; border-radius: 5px; }
        .ws-btn.active { background-color: #2563eb; font-weight: bold; }
        .card-custom { background-color: #334155; border: none; color: #fff; margin-bottom: 15px; }
        .msg-user { background-color: #2563eb; color: white; padding: 8px 12px; border-radius: 8px; margin-bottom: 8px; max-width: 80%; float: right; clear: both; }
        .msg-bot { background-color: #1e293b; border: 1px solid #334155; color: white; padding: 8px 12px; border-radius: 8px; margin-bottom: 8px; max-width: 85%; float: left; clear: both; }
        .file-item { display: flex; justify-content: space-between; align-items: center; background: #0f172a; padding: 6px 10px; margin-bottom: 5px; border-radius: 4px; font-size: 0.85rem; }
    </style>
</head>
<body>
<div class="container-fluid">
    <div class="row">
        <!-- Лява лента: Работни пространства -->
        <div class="col-md-2 sidebar">
            <h5>🤖 N.I.K.I. CORE</h5>
            <hr>
            <h6>ПРОЕКТИ (WORKSPACES)</h6>
            <div id="workspace-list">
                {% for ws in workspaces %}
                <button class="ws-btn {% if ws == current_ws %}active{% endif %}" onclick="switchWorkspace('{{ ws }}')">{{ ws }}</button>
                {% endfor %}
            </div>
            <hr>
            <button class="btn btn-outline-light btn-sm w-100" onclick="createNewWorkspace()">+ Нов Проект</button>
            <br><br>
            <h6>КАЧВАНЕ НА ДОКУМЕНТ</h6>
            <form id="upload-form" enctype="multipart/form-data">
                <input type="file" id="file-input" name="file" class="form-control form-control-sm mb-2">
                <button type="button" class="btn btn-success btn-sm w-100" onclick="uploadDocument()">☁️ Синхронизирай</button>
            </form>
        </div>

        <!-- Централен панел: Чатов интерфейс -->
        <div class="col-md-7 main-content">
            <div class="d-flex justify-content-between align-items-center mb-2">
                <h5>Активно пространство: <span class="text-primary">{{ current_ws }}</span></h5>
                <span class="badge bg-success">ROOT Access Active</span>
            </div>
            
            <div class="chat-box" id="chat-box">
                <div class="msg-bot">Здравей, Аз съм N.I.K.I. Системата е напълно готова за работа.</div>
            </div>

            <div class="input-group">
                <input type="text" id="user-input" class="form-control" placeholder="Въведете инструкция или команда към N.I.K.I..." onkeypress="if(event.key==='Enter') sendMessage()">
                <button class="btn btn-primary" onclick="sendMessage()">🚀 Изпрати</button>
            </div>
        </div>

        <!-- Дясна лента: База знания & Задачи -->
        <div class="col-md-3 right-panel">
            <div class="card card-custom">
                <div class="card-body">
                    <h6>🧠 ВЕРИФИЦИРАНИ ФАКТИ (FACTS)</h6>
                    <ul id="facts-list" class="small ps-3 mb-0">
                        {% for fact in facts %}
                        <li>{{ fact }}</li>
                        {% else %}
                        <span class="text-muted">Няма намерени факти.</span>
                        {% endfor %}
                    </ul>
                </div>
            </div>

            <div class="card card-custom">
                <div class="card-body">
                    <h6>🎼 АКТИВНИ ЗАДАЧИ</h6>
                    <ul id="tasks-list" class="small ps-3 mb-0">
                        {% for task in tasks %}
                        <li>{{ task }}</li>
                        {% else %}
                        <span class="text-muted">Няма намерени задачи.</span>
                        {% endfor %}
                    </ul>
                </div>
            </div>

            <div class="card card-custom">
                <div class="card-body">
                    <h6>📁 ФАЙЛОВЕ В БИБЛИОТЕКАТА</h6>
                    <div id="files-list">
                        {% for file in files %}
                        <div class="file-item">
                            <span class="text-truncate" style="max-width: 170px;">📄 {{ file.name }}</span>
                            <button class="btn btn-danger btn-sm py-0 px-1" onclick="deleteFile('{{ file.name }}')">🗑️</button>
                        </div>
                        {% else %}
                        <span class="text-muted">Няма качен документ.</span>
                        {% endfor %}
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
    let currentWorkspace = "{{ current_ws }}";

    function switchWorkspace(ws) {
        window.location.href = "/?ws=" + ws;
    }

    function createNewWorkspace() {
        let name = prompt("Въведете име на новото работно пространство (на латиница):");
        if (name) {
            fetch('/api/create_workspace', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ name: name })
            }).then(() => window.location.href = "/?ws=" + name.toUpperCase());
        }
    }

    function sendMessage() {
        let input = document.getElementById('user-input');
        let text = input.value.trim();
        if (!text) return;

        let chatBox = document.getElementById('chat-box');
        chatBox.innerHTML += `<div class="msg-user">${text}</div>`;
        input.value = '';
        chatBox.scrollTop = chatBox.scrollHeight;

        fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ message: text, workspace: currentWorkspace })
        })
        .then(res => res.json())
        .then(data => {
            chatBox.innerHTML += `<div class="msg-bot">${data.response}</div>`;
            chatBox.scrollTop = chatBox.scrollHeight;
            if(data.reload) {
                setTimeout(() => location.reload(), 1500);
            }
        });
    }

    function uploadDocument() {
        let fileInput = document.getElementById('file-input');
        if (!fileInput.files[0]) return alert("Моля, изберете файл!");

        let formData = new FormData();
        formData.append('file', fileInput.files[0]);
        formData.append('workspace', currentWorkspace);

        let chatBox = document.getElementById('chat-box');
        chatBox.innerHTML += `<div class="msg-bot">⏳ Обработвам, качвам и анализирам документа...</div>`;

        fetch('/api/upload', {
            method: 'POST',
            body: formData
        })
        .then(res => res.json())
        .then(data => {
            alert(data.message);
            location.reload();
        });
    }

    function deleteFile(fileName) {
        if (confirm("Сигурни ли сте, че искате да изтриете файла '" + fileName + "'?")) {
            fetch('/api/delete_file', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ file_name: fileName, workspace: currentWorkspace })
            })
            .then(res => res.json())
            .then(data => {
                alert(data.message);
                location.reload();
            });
        }
    }
</script>
</body>
</html>
"""

@app.route('/')
def index():
    current_ws = request.args.get('ws', 'GENERAL').upper()
    
    # Извличане на наличните файлове
    lib_path = f"{WORKSPACES_DIR}/{current_ws.lower()}/library"
    raw_files = list_github_folder(lib_path)
    files = [{"name": f["name"]} for f in raw_files if isinstance(f, dict) and f.get("type") == "file"]

    # Извличане на факти
    facts_path = f"{WORKSPACES_DIR}/{current_ws.lower()}/facts/verified_facts.json"
    facts_str, _ = get_github_file(facts_path)
    facts = json.loads(facts_str) if facts_str else []

    # Извличане на задачи
    tasks_path = f"{WORKSPACES_DIR}/{current_ws.lower()}/tasks/backlog.json"
    tasks_str, _ = get_github_file(tasks_path)
    tasks = json.loads(tasks_str) if tasks_str else []

    return render_template_string(HTML_TEMPLATE, 
                                 workspaces=DEFAULT_WORKSPACES, 
                                 current_ws=current_ws, 
                                 files=files, 
                                 facts=facts, 
                                 tasks=tasks)

@app.route('/api/create_workspace', methods=['POST'])
def create_workspace():
    data = request.json
    ws_name = data.get('name', '').upper().strip()
    if ws_name and ws_name not in DEFAULT_WORKSPACES:
        DEFAULT_WORKSPACES.append(ws_name)
        facts_path = f"{WORKSPACES_DIR}/{ws_name.lower()}/facts/verified_facts.json"
        save_github_file(facts_path, json.dumps([], ensure_ascii=False), f"Init ws {ws_name}")
    return jsonify({"status": "ok"})

@app.route('/api/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({"message": "Липсва файл"}), 400
    file = request.files['file']
    workspace = request.form.get('workspace', 'GENERAL').lower()

    file_bytes = file.read()
    file_name = file.filename

    # Качване в библиотека
    gh_path = f"{WORKSPACES_DIR}/{workspace}/library/{file_name}"
    save_github_file(gh_path, file_bytes, f"N.I.K.I. Auto-Sync: {file_name}", is_binary=True)

    # Авто-извличане на текст за анализиране
    extracted_text = ""
    if file_name.endswith('.docx'):
        extracted_text = extract_docx_text(file_bytes)
    elif file_name.endswith('.txt'):
        extracted_text = file_bytes.decode('utf-8', errors='ignore')

    if extracted_text:
        system_prompt = "Ти си N.I.K.I. Анализирай текста и извлечи ключови факти и задачи. Върни ги ВИНАГИ в JSON формат: {\"facts\": [\"факт 1\"], \"tasks\": [\"задача 1\"]}"
        ai_res = call_groq_llm([{"role": "user", "content": extracted_text[:4000]}], system_prompt)
        try:
            parsed = json.loads(ai_res)
            
            # Обновяване на факти
            facts_path = f"{WORKSPACES_DIR}/{workspace}/facts/verified_facts.json"
            facts_str, sha_f = get_github_file(facts_path)
            facts = json.loads(facts_str) if facts_str else []
            facts.extend(parsed.get("facts", []))
            save_github_file(facts_path, json.dumps(facts, ensure_ascii=False, indent=2), "Update facts", sha=sha_f)

            # Обновяване на задачи
            tasks_path = f"{WORKSPACES_DIR}/{workspace}/tasks/backlog.json"
            tasks_str, sha_t = get_github_file(tasks_path)
            tasks = json.loads(tasks_str) if tasks_str else []
            tasks.extend(parsed.get("tasks", []))
            save_github_file(tasks_path, json.dumps(tasks, ensure_ascii=False, indent=2), "Update tasks", sha=sha_t)

        except Exception as e:
            print(f"Грешка при обработка с AI: {e}")

    return jsonify({"message": f"Файлът '{file_name}' бе качен и анализиран успешно!"})

@app.route('/api/delete_file', methods=['POST'])
def delete_file():
    data = request.json
    file_name = data.get('file_name')
    workspace = data.get('workspace', 'GENERAL').lower()

    gh_path = f"{WORKSPACES_DIR}/{workspace}/library/{file_name}"
    _, sha = get_github_file(gh_path)
    
    if sha:
        success = delete_github_file(gh_path, sha, f"N.I.K.I. Delete File: {file_name}")
        if success:
            return jsonify({"message": f"Файлът '{file_name}' беше изтрит успешно!"})
    
    return jsonify({"message": f"Грешка при изтриването на '{file_name}'"}), 400

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    user_msg = data.get('message', '')
    workspace = data.get('workspace', 'GENERAL').lower()

    # Зареждане на контекста
    facts_path = f"{WORKSPACES_DIR}/{workspace}/facts/verified_facts.json"
    facts_str, _ = get_github_file(facts_path)
    facts = json.loads(facts_str) if facts_str else []

    system_prompt = f"Ти си N.I.K.I. - автономен AI асистент. Работиш в проект '{workspace.upper()}'. Известни факти за този проект: {json.dumps(facts, ensure_ascii=False)}. Отговаряй точно, компетентно и професионално на български език."
    
    # Запитване за авто-създаване на документ
    if user_msg.lower().startswith("генерирай документ") or user_msg.lower().startswith("създай файл"):
        doc_title = f"Документ_{workspace.upper()}"
        doc_bytes = create_docx_file(doc_title, [user_msg, "Автоматично генерирано съдържание от N.I.K.I. CORE."])
        file_name = f"{doc_title}.docx"
        gh_path = f"{WORKSPACES_DIR}/{workspace}/library/{file_name}"
        save_github_file(gh_path, doc_bytes, f"N.I.K.I. Auto-Created Doc: {file_name}", is_binary=True)
        return jsonify({"response": f"📄 Успешно генерирах и качих документа **{file_name}** в Библиотеката!", "reload": True})

    ai_response = call_groq_llm([{"role": "user", "content": user_msg}], system_prompt)
    return jsonify({"response": ai_response, "reload": False})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
