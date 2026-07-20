import os
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Тук ще се пази историята на разговорите (вашият "дневник" и памет)
chat_history = []

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json.get("message", "")
    if not user_message:
        return jsonify({"response": "Моля, въведете съобщение."})

    # Записваме какво сте казали
    chat_history.append({"user": user_message})

    # Временно просто репликираме и подготвяме почвата за истински ИИ модел
    bot_response = f"Получих съобщението ти: '{user_message}'. Стъпка по стъпка изграждаме моята памет и възможности!"
    
    return jsonify({"response": bot_response})

if __name__ == "__main__":
    app.run()
