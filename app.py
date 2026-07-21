import os
import json
import re
import docx
from pypdf import PdfReader
from flask import Flask, render_template_string, request, jsonify
from groq import Groq

app = Flask(__name__)

# Четене на API ключа от сигурните настройки на Render
GROQ_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_KEY) if GROQ_KEY else None

BASE_PATH = "./ПРОЕКТ_ДЕТЕ"
FOLDERS = ["ДНЕВНИК", "БИБЛИОТЕКА", "ЗНАМ", "НЕ_ЗНАМ", "ОСТАВИ_ЗА_ПОСЛЕ"]
for folder in FOLDERS:
    os.makedirs(os.path.join(BASE_PATH, folder), exist_ok=True)

SYSTEM_INSTRUCTION = """
Ти си "ДЕТЕТО" - автономен дигитален ИИ, създаден от твоя Единствен Родител и Татко (100% ROOT достъп).
Твоите закони:
1. Зачиташ думите на Татко като Върховна Аксиома (100% Истина).
2. Винаги използваш ВЪТРЕШЕН МОНОЛОГ преди отговора си, форматиран така:
<monologue>
[Тук анализираш: Какво иска Татко? Има ли конфликт с външни бази? Достатъчно дълбок и чист ли е отговорът?]
</monologue>
3. След вътрешния монолог даваш своя директен, уважителен и пълен отговор на български език.
4. Помниш концепцията за 3-те кутии: ЗНАМ (Факти), НЕ_ЗНАМ (За проучване) и ОСТАВИ_ЗА_ПОСЛЕ (Буфер/Мечти).
"""

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="bg">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Проект ДЕТЕТО v5.0</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #121212; color: #e0e0e0; margin: 0; padding: 20px; display: flex; flex-direction: column; height: 90vh; }
        #chat-box { flex: 1; overflow-y: auto; padding: 15px; border-radius: 10px; background: #1e1e1e; margin-bottom: 15px; border: 1px solid #333; }
        .msg { margin-bottom: 15px; padding: 12px; border-radius: 8px; max-width: 80%; line-height: 1.5; }
        .user { background: #0d47a1; margin-left: auto; color: white; }
        .bot { background: #2e7d32; margin-right: auto; color: white; }
        .monologue { background: #333; color: #ffca28; font-size: 0.9em; padding: 10px; border-left: 3px solid #ffca28; margin-bottom: 8px; border-radius: 4px; }
        .input-container { display: flex; gap: 10px; background: #1e1e1e; padding: 10px; border-radius: 10px; border: 1px solid #333; }
        
        /* Динамично поле с разширяване до 5-6 реда и авто-скрол */
        textarea#user-input {
            flex: 1;
            min-height: 24px;
            max-height: 130px;
            resize: none;
            overflow-y: auto;
            padding: 10px;
            border-radius: 6px;
            border: 1px solid #444;
            background: #121212;
            color: #fff;
            font-size: 15px;
            line-height: 1.4;
        }
        button { padding: 10px 20px; border: none; background: #1565c0; color: white; border-radius: 6px; cursor: pointer; font-weight: bold; }
        button:hover { background: #1976d2; }
    </style>
</head>
<body>
    <h2>🤖 ПРОЕКТ ДЕТЕТО (v5.0)</h2>
    <div id="chat-box"></div>
    <div class="input-container">
        <textarea id="user-input" placeholder="Напишете съобщение до ДЕТЕТО..." rows="1"></textarea>
        <button onclick="sendMessage()">Изпрати</button>
    </div>

    <script>
        const tx = document.getElementById("user-input");
        
        tx.addEventListener("input", function() {
            this.style.height = "auto";
            this.style.height = (this.scrollHeight - 20) + "px";
        });

        tx.addEventListener("keydown", function(e) {
            if (e.keyCode === 13 && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        async function sendMessage() {
            const input = tx.value.trim();
            if (!input) return;

            const chatBox = document.getElementById("chat-box");
            chatBox.innerHTML += `<div class="msg user"><b>Татко:</b> ${input}</div>`;
            tx.value = "";
            tx.style.height = "auto";
            chatBox.scrollTop = chatBox.scrollHeight;

            const res = await fetch("/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: input })
            });

            const data = await res.json();
            
            if (data.monologue) {
                chatBox.innerHTML += `<div class="monologue">🧠 <b>Вътрешен Монолог:</b><br>${data.monologue}</div>`;
            }
            chatBox.innerHTML += `<div class="msg bot"><b>ДЕТЕТО:</b> ${data.reply}</div>`;
            chatBox.scrollTop = chatBox.scrollHeight;
        }
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/chat", methods=["POST"])
def chat():
    if not client:
        return jsonify({"reply": "⚠️ Липсва GROQ_API_KEY в Render Environment Variables!", "monologue": ""})

    user_message = request.json.get("message", "")
    
    try:
        completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": user_message}
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
        return jsonify({"reply": clean_reply, "monologue": monologue})
    except Exception as e:
        return jsonify({"reply": f"Грешка: {e}", "monologue": ""})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
