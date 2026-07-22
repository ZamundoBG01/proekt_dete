import os
import json
import base64
import requests
import io
from flask import Flask, request, jsonify, render_template_string, send_file
from docx import Document

app = Flask(__name__)

# Config
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO_NAME = os.environ.get("REPO_NAME", "ZamundoBG01/proekt_N.I.K.I.")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

WORKSPACES_DIR = "NIKI_CORE/workspaces"

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

def get_github_file(path, raw_bytes=False):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{path}"
    res = requests.get(url, headers=github_headers())
    if res.status_code == 200:
        data = res.json()
        decoded = base64.b64decode(data['content'])
        if raw_bytes:
            return decoded, data['sha']
        return decoded.decode('utf-8', errors='ignore'), data['sha']
    return None, None

def save_github_file(path, content_bytes_or_str, commit_message, sha=None, is_binary=False):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{path}"
    if is_binary or isinstance(content_bytes_or_str, bytes):
        encoded_content = base64.b64encode(content_bytes_or_str).decode('utf-8')
    else:
        encoded_content = base64.b64encode(content_bytes_or_str.encode('utf-8')).decode('utf-8')
        
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
            return f"Грешка от Llama AI: {response.status_code}"
    except Exception as e:
        return f"Грешка при връзка с AI: {str(e)}"

def extract_docx_text(file_bytes):
    try:
        doc = Document(io.BytesIO(file_bytes))
        full_text = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        return "\n".join(full_text)
    except Exception as e:
        return f"Грешка при четене: {str(e)}"

def create_docx_file(title, text_content):
    doc = Document()
    doc.add_heading(title, 0)
    for line in text_content.split("\n"):
        if line.strip():
            doc.add_paragraph(line)
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
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        body { background-color: #0b132b; color: #e0e1dd; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; height: 100vh; overflow: hidden; margin: 0; }
        .app-container { display: flex; height: 100vh; }
        
        .sidebar-left { width: 260px; background-color: #1c2541; padding: 20px; border-right: 1px solid #3a506b; display: flex; flex-direction: column; }
        .sidebar-right { width: 340px; background-color: #1c2541; padding: 15px; border-left: 1px solid #3a506b; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; }
        .chat-main { flex: 1; display: flex; flex-direction: column; background-color: #0b132b; height: 100vh; }
        
        .brand-header { font-weight: bold; font-size: 1.2rem; color: #4cc9f0; display: flex; align-items: center; gap: 10px; margin-bottom: 20px; }
        .ws-btn { display: block; width: 100%; text-align: left; margin-bottom: 8px; background-color: #0b132b; color: #a5a5a5; border: 1px solid #3a506b; padding: 10px; border-radius: 6px; transition: all 0.2s; }
        .ws-btn.active { background-color: #4361ee; color: #ffffff; font-weight: bold; border-color: #4361ee; }
        
        .chat-header { padding: 15px 20px; background: #1c2541; border-bottom: 1px solid #3a506b; display: flex; justify-content: space-between; align-items: center; }
        .chat-box { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; }
        
        .msg-user { background: #4361ee; color: white; padding: 10px 14px; border-radius: 10px; max-width: 80%; align-self: flex-end; border-bottom-right-radius: 2px; }
        .msg-bot { background: #1c2541; color: #e0e1dd; padding: 10px 14px; border-radius: 10px; max-width: 85%; align-self: flex-start; border-bottom-left-radius: 2px; border: 1px solid #3a506b; }
        
        .chat-input-area { padding: 15px; background: #1c2541; border-top: 1px solid #3a506b; display: flex; gap: 10px; }
        .chat-input { background: #0b132b; border: 1px solid #3a506b; color: white; border-radius: 8px; padding: 12px; flex: 1; }
        .chat-input:focus { background: #0b132b; color: white; outline: none; border-color: #4361ee; }

        .collapsible-card { background: #0b132b; border: 1px solid #3a506b; border-radius: 8px; overflow: hidden; }
        .collapsible-header { padding: 10px 12px; background: #131b2e; color: #4cc9f0; cursor: pointer; font-size: 0.85rem; font-weight: bold; display: flex; justify-content: space-between; align-items: center; }
        .collapsible-body { padding: 10px; max-height: 200px; overflow-y: auto; font-size: 0.8rem; }
        
        .file-item { display: flex; justify-content: space-between; align-items: center; background: #1c2541; padding: 6px 10px; margin-bottom: 6px; border-radius: 6px; border: 1px solid #3a506b; }
    </style>
</head>
<body>

<div class="app-container">
    <!-- Лява лента -->
    <div class="sidebar-left">
        <div class="brand-header"><i class="fa-solid fa-brain"></i> N.I.K.I. CORE</div>
        <small class="text-muted mb-2">ПРОЕКТИ (WORKSPACES)</small>
        <div id="workspace-list">
            {% for ws in workspaces %}
            <button class="ws-btn {% if ws == current_ws %}active{% endif %}" onclick="switchWorkspace('{{ ws }}')">{{ ws }}</button>
            {% endfor %}
        </div>
        <button class="btn btn-outline-primary btn-sm w-100 mt-2" onclick="createNewWorkspace()"><i class="fa-solid fa-plus"></i> Нов Проект</button>
        
        <hr class="border-secondary my-3">
        <small class="text-muted mb-2">КАЧВАНЕ НА ДОКУМЕНТ</small>
        <form id="uploadForm" enctype="multipart/form-data">
            <input type="file" id="fileInput" name="file" class="form-control form-control-sm mb-2" accept=".txt,.pdf,.docx">
            <button type="button" class="btn btn-success btn-sm w-100" onclick="uploadDocument()"><i class="fa-solid fa-cloud-arrow-up"></i> Синхронизирай</button>
        </form>
    </div>

    <!-- Чат център -->
    <div class="chat-main">
        <div class="chat-header">
            <div>Активно пространство: <strong class="text-info">{{ current_ws }}</strong></div>
            <span class="badge bg-success">ROOT Access Active</span>
        </div>

        <div class="chat-box" id="chatBox">
            <div class="msg-bot">Здравей! Аз съм N.I.K.I. Системата е напълно готова за работа.</div>
        </div>

        <div class="chat-input-area">
            <!-- Оправено за предотвратяване на автопопълване на пароли -->
            <input type="text" id="userInput" name="niki_chat_input" autocomplete="off" class="chat-input" placeholder="Въведете инструкция или команда към N.I.K.I..." onkeypress="if(event.key==='Enter') sendMessage()">
            <button class="btn btn-primary" onclick="sendMessage()"><i class="fa-solid fa-paper-plane"></i> Изпрати</button>
        </div>
    </div>

    <!-- Дясна лента със сгъваеми панели -->
    <div class="sidebar-right">
        
        <!-- Панел Факти -->
        <div class="collapsible-card">
            <div class="collapsible-header" onclick="toggleSection('factsBody')">
                <span>🧠 ВЕРИФИЦИРАНИ ФАКТИ</span>
                <i class="fa-solid fa-chevron-down"></i>
            </div>
            <div class="collapsible-body" id="factsBody">
                <ul class="ps-3 mb-0 text-light">
                    {% for fact in facts %}
                    <li class="mb-1">{{ fact }}</li>
                    {% else %}
                    <span class="text-muted">Няма регистрирани факти.</span>
                    {% endfor %}
                </ul>
            </div>
        </div>

        <!-- Панел Задачи -->
        <div class="collapsible-card">
            <div class="collapsible-header" onclick="toggleSection('tasksBody')">
                <span>🎼 АКТИВНИ ЗАДАЧИ</span>
                <i class="fa-solid fa-chevron-down"></i>
            </div>
            <div class="collapsible-body" id="tasksBody">
                <ul class="ps-3 mb-0 text-light">
                    {% for task in tasks %}
                    <li class="mb-1">{{ task }}</li>
                    {% else %}
                    <span class="text-muted">Няма активни задачи.</span>
                    {% endfor %}
                </ul>
            </div>
        </div>

        <!-- Панел Файлове -->
        <div class="collapsible-card">
            <div class="collapsible-header" onclick="toggleSection('filesBody')">
                <span>📁 ФАЙЛОВЕ В БИБЛИОТЕКАТА</span>
                <i class="fa-solid fa-chevron-down"></i>
            </div>
            <div class="collapsible-body" id="filesBody" style="max-height: 300px;">
                {% for file in files %}
                <div class="file-item">
                    <span class="text-truncate" style="max-width: 160px;" title="{{ file.name }}">📄 {{ file.name }}</span>
                    <div>
                        <!-- Бутон за сваляне -->
                        <a href="/api/download_file?file_name={{ file.name }}&workspace={{ current_ws }}" class="btn btn-primary btn-sm py-0 px-2 me-1" title="Свали файл">📥</a>
                        <!-- Бутон за изтриване -->
                        <button class="btn btn-danger btn-sm py-0 px-2" onclick="deleteFile('{{ file.name }}')" title="Изтрий файл">🗑️</button>
                    </div>
                </div>
                {% else %}
                <span class="text-muted">Няма качени файлове.</span>
                {% endfor %}
            </div>
        </div>

    </div>
</div>

<script>
    let currentWorkspace = "{{ current_ws }}";

    function toggleSection(id) {
        let el = document.getElementById(id);
        el.style.display = el.style.display === 'none' ? 'block' : 'none';
    }

    function switchWorkspace(ws) {
        window.location.href = "/?ws=" + ws;
    }

    function createNewWorkspace() {
        let name = prompt("Въведете име на новия проект (на латиница):");
        if (name) {
            fetch('/api/create_workspace', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ name: name })
            }).then(() => window.location.href = "/?ws=" + name.toUpperCase());
        }
    }

    function sendMessage() {
        let input = document.getElementById('userInput');
        let text = input.value.trim();
        if (!text) return;

        let chatBox = document.getElementById('chatBox');
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
                setTimeout(() => location.reload(), 1200);
            }
        });
    }

    function uploadDocument() {
        let fileInput = document.getElementById('fileInput');
        if (!fileInput.files[0]) return alert("Моля, изберете файл!");

        let formData = new FormData();
        formData.append('file', fileInput.files[0]);
        formData.append('workspace', currentWorkspace);

        let chatBox = document.getElementById('chatBox');
        chatBox.innerHTML += `<div class="msg-bot">⏳ Обработвам и качвам файла...</div>`;

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
    
    lib_path = f"{WORKSPACES_DIR}/{current_ws.lower()}/library"
    raw_files = list_github_folder(lib_path)
    files = [{"name": f["name"]} for f in raw_files if isinstance(f, dict) and f.get("type") == "file"]

    facts_path = f"{WORKSPACES_DIR}/{current_ws.lower()}/facts/verified_facts.json"
    facts_str, _ = get_github_file(facts_path)
    facts = json.loads(facts_str) if facts_str else []

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

    gh_path = f"{WORKSPACES_DIR}/{workspace}/library/{file_name}"
    save_github_file(gh_path, file_bytes, f"N.I.K.I. Auto-Sync: {file_name}", is_binary=True)

    extracted_text = ""
    if file_name.endswith('.docx'):
        extracted_text = extract_docx_text(file_bytes)
    elif file_name.endswith('.txt'):
        extracted_text = file_bytes.decode('utf-8', errors='ignore')

    if extracted_text:
        system_prompt = "Ти си N.I.K.I. Извлечи ключови факти и задачи от текста. Върни ВИНАГИ чист JSON: {\"facts\": [\"факт 1\"], \"tasks\": [\"задача 1\"]}"
        ai_res = call_groq_llm([{"role": "user", "content": extracted_text[:4000]}], system_prompt)
        try:
            parsed = json.loads(ai_res)
            
            facts_path = f"{WORKSPACES_DIR}/{workspace}/facts/verified_facts.json"
            facts_str, sha_f = get_github_file(facts_path)
            facts = json.loads(facts_str) if facts_str else []
            facts.extend(parsed.get("facts", []))
            save_github_file(facts_path, json.dumps(facts, ensure_ascii=False, indent=2), "Update facts", sha=sha_f)

            tasks_path = f"{WORKSPACES_DIR}/{workspace}/tasks/backlog.json"
            tasks_str, sha_t = get_github_file(tasks_path)
            tasks = json.loads(tasks_str) if tasks_str else []
            tasks.extend(parsed.get("tasks", []))
            save_github_file(tasks_path, json.dumps(tasks, ensure_ascii=False, indent=2), "Update tasks", sha=sha_t)

        except Exception as e:
            print(f"Грешка при AI анализ: {e}")

    return jsonify({"message": f"Файлът '{file_name}' бе качен и анализиран!"})

@app.route('/api/download_file')
def download_file():
    file_name = request.args.get('file_name')
    workspace = request.args.get('workspace', 'GENERAL').lower()
    
    gh_path = f"{WORKSPACES_DIR}/{workspace}/library/{file_name}"
    file_bytes, _ = get_github_file(gh_path, raw_bytes=True)
    
    if file_bytes:
        return send_file(
            io.BytesIO(file_bytes),
            download_name=file_name,
            as_attachment=True
        )
    return "Файлът не е намерен", 404

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

    facts_path = f"{WORKSPACES_DIR}/{workspace}/facts/verified_facts.json"
    facts_str, _ = get_github_file(facts_path)
    facts = json.loads(facts_str) if facts_str else []

    system_prompt = f"Ти си N.I.K.I. - автономен AI асистент в проект '{workspace.upper()}'. Факти: {json.dumps(facts, ensure_ascii=False)}. Отговаряй точно и професионално на български език."
    
    if user_msg.lower().startswith("генерирай документ") or user_msg.lower().startswith("създай файл"):
        doc_title = f"Резюме_{workspace.upper()}"
        
        # Запитване към AI за съдържанието
        content_prompt = f"Напиши подробно и структурирано резюме за проект {workspace.upper()} въз основа на известните факти: {json.dumps(facts, ensure_ascii=False)}"
        summary_text = call_groq_llm([{"role": "user", "content": content_prompt}])
        
        doc_bytes = create_docx_file(f"РЕЗЮМЕ ПРОЕКТ {workspace.upper()}", summary_text)
        file_name = f"{doc_title}.docx"
        gh_path = f"{WORKSPACES_DIR}/{workspace}/library/{file_name}"
        save_github_file(gh_path, doc_bytes, f"N.I.K.I. Auto-Created Doc: {file_name}", is_binary=True)
        return jsonify({"response": f"📄 Генерирах файла **{file_name}** с пълно резюме и го качих в Библиотеката! Можеш да го свалиш с бутончето 📥.", "reload": True})

    ai_response = call_groq_llm([{"role": "user", "content": user_msg}], system_prompt)
    return jsonify({"response": ai_response, "reload": False})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
