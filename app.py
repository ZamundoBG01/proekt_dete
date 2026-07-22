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
from sentence_transformers import SentenceTransformer
import faiss

app = Flask(__name__)

GROQ_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_KEY) if GROQ_KEY else None

# Базова директория
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_PATH = os.path.join(BASE_DIR, "NIKI_CORE")

# Модулна структура на папките
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

# Инициализиране на модела за ембединги (олекотен и бърз)
print("Инициализиране на Embedding модел...")
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# Глобален вектор за FAISS и текстови пасажи
vector_dimension = 384
index = faiss.IndexFlatL2(vector_dimension)
text_chunks = []

def chunk_text(text, chunk_size=500, overlap=50):
    """Разделя текста на малки логически пасажи."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks

def build_vector_index():
    """Сканира библиотеката и изгражда FAISS векторния индекс."""
    global index, text_chunks
    text_chunks = []
    index = faiss.IndexFlatL2(vector_dimension)
    
    library_path = STRUCTURE["library"]
    raw_texts = []

    if os.path.exists(library_path):
        for filename in os.listdir(library_path):
            file_path = os.path.join(library_path, filename)
            if os.path.isdir(file_path):
                continue

            extracted_text = ""
            try:
                if filename.endswith(".txt"):
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        extracted_text = f.read()
                elif filename.endswith(".docx"):
                    doc = docx.Document(file_path)
                    extracted_text = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
                elif filename.endswith(".pdf"):
                    reader = PdfReader(file_path)
                    for page in reader.pages:
                        extracted_text += (page.extract_text() or "") + "\n"
            except Exception as e:
                print(f"Грешка при четене на {filename}: {e}")

            if extracted_text.strip():
                chunks = chunk_text(extracted_text)
                for c in chunks:
                    text_chunks.append(f"[{filename}]: {c}")

    if text_chunks:
        embeddings = embedder.encode(text_chunks, convert_to_numpy=True)
        index.add(embeddings)
        print(f"Успешно индексирани {len(text_chunks)} текстови пасажа в FAISS.")

# Първоначално изграждане на индекса при старт
build_vector_index()

def search_relevant_knowledge(query, top_k=3):
    """Векторно търсене на най-подходящите пасажи за дадения въпрос."""
    if index.ntotal == 0 or not text_chunks:
        return "Няма качени документи в библиотеката."
    
    query_vector = embedder.encode([query], convert_to_numpy=True)
    distances, indices = index.search(query_vector, min(top_k, index.ntotal))
    
    results = []
    for idx in indices[0]:
        if idx < len(text_chunks):
            results.append(text_chunks[idx])
            
    return "\n---\n".join(results) if results else "Няма намерени съответствия."

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
[Анализ: Векторно извлечен контекст | Гранични условия | Доверие (+100)]
</monologue>
"""

BG_TIMEZONE = timezone(timedelta(hours=3))
chat_history = []

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
def index_page():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload_file():
    """Руут за директно качване на файлове в библиотеката."""
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "Няма прикачен файл."})
    
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"status": "error", "message": "Не е избран файл."})
        
    allowed_extensions = {".txt", ".pdf", ".docx"}
    ext = os.path.splitext(file.filename)[1].lower()
    
    if ext not in allowed_extensions:
        return jsonify({"status": "error", "message": f"Неподдържан формат. Позволени: {allowed_extensions}"})
        
    filename = secure_filename(file.filename)
    save_path = os.path.join(STRUCTURE["library"], filename)
    file.save(save_path)
    
    # Преиндексираме векторната памет с новия файл
    build_vector_index()
    
    return jsonify({"status": "success", "message": f"Файлът '{filename}' беше качен и индексиран във векторната памет успешно!"})

@app.route("/chat", methods=["POST"])
def chat():
    if not client:
        return jsonify({"reply": "⚠️ Липсва GROQ_API_KEY!", "monologue": "", "time": ""})

    user_message = request.json.get("message", "")
    now_bg = datetime.now(BG_TIMEZONE)
    current_time_info = now_bg.strftime("%d.%m.%Y %H:%M")

    # Векторно извличане само на релевантния контекст
    retrieved_context = search_relevant_knowledge(user_message)

    messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
    context_prefix = f"[СИСТЕМЕН МАРКЕР ВРЕМЕ: {current_time_info}]\n[ВЕКТОРНО ИЗВЛЕЧЕНИ ЗНАНИЯ ОТ LIBRARY]:\n{retrieved_context}\n\n"
    
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
