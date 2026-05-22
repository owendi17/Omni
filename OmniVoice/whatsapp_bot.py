"""
WHATSAPP VOICE INVENTORY CHATBOT (CLEAN VERSION)
"""

from flask import Flask, request, jsonify, send_from_directory
from twilio.rest import Client
import sqlite3
import os
from dotenv import load_dotenv
import logging
import whisper
from gtts import gTTS
import uuid
import requests

load_dotenv()

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== CONFIG ====================
TWILIO_SID = os.getenv('TWILIO_SID', 'ACxxxxxxxx')
TWILIO_TOKEN = os.getenv('TWILIO_TOKEN', 'token')
TWILIO_NUMBER = os.getenv('TWILIO_NUMBER', '+1234567890')

USE_MOCK = os.getenv('USE_MOCK', 'True') == 'True'

if not USE_MOCK:
    twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)

# ==================== WHISPER ====================
whisper_model = None

def get_whisper():
    global whisper_model
    if whisper_model is None:
        whisper_model = whisper.load_model("base")
    return whisper_model

# ==================== DATABASE ====================
def init_db():
    conn = sqlite3.connect('inventory.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE,
        quantity INTEGER,
        unit_price REAL,
        reorder_level INTEGER
    )''')

    if c.execute("SELECT COUNT(*) FROM inventory").fetchone()[0] == 0:
        sample = [
            ('Rice', 8, 80, 15),
            ('Sugar', 30, 120, 10),
            ('Beans', 2, 180, 10),
            ('Milk', 12, 250, 8),
        ]
        for item in sample:
            c.execute("INSERT INTO inventory VALUES (NULL,?,?,?,?)", item)

    conn.commit()
    conn.close()

init_db()

# ==================== NLP ====================
def extract_product(text):
    products = ["rice", "sugar", "beans", "milk"]
    text = text.lower()

    for p in products:
        if p in text:
            return p
    return None


def extract_product(text):
    products = {
        "rice": ["rice"],
        "sugar": ["sugar"],
        "beans": ["beans"],
        "ugali flour": ["ugali", "flour", "ugali flour"],
        "milk": ["milk"],
        "bread": ["bread"],
        "maize": ["maize"]
    }

    text_lower = text.lower()

    for key, aliases in products.items():
        if any(alias in text_lower for alias in aliases):
            return key

    return None

def detect_intent(text):
    text_lower = text.lower()

    # STOCK CHECK
    if any(w in text_lower for w in [
        'how much', 'how many', 'kiasi', 'ngapi', 'price', 'iko', 'tuna', 'kuna'
    ]):
        product_name = extract_product(text)
        return 'check_stock', product_name

    # LOW STOCK
    elif any(w in text_lower for w in [
        'low', 'running out', 'karibia', "what's low", 'kitu gani'
    ]):
        return 'low_stock', None

    # GREETING
    elif any(w in text_lower for w in [
        'hello', 'hi', 'hey', 'habari', 'jambo'
    ]):
        return 'greeting', None

    return 'unknown', None
# ==================== DB QUERIES ====================
def search_product(name):
    conn = sqlite3.connect('inventory.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM inventory WHERE LOWER(name) LIKE ?", (f"%{name}%",))
    row = c.fetchone()
    conn.close()

    return dict(row) if row else None


def get_all_inventory():
    conn = sqlite3.connect('inventory.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM inventory")
    rows = c.fetchall()
    conn.close()

    return [dict(r) for r in rows]

# ==================== VOICE ====================
def generate_voice_response(text, lang='en'):
    try:
        filename = f"audio_{uuid.uuid4().hex}.mp3"
        tts = gTTS(text=text, lang='en' if lang == 'en' else 'sw')
        tts.save(filename)
        return filename
    except Exception as e:
        logger.error(e)
        return None


@app.route('/audio/<filename>')
def serve_audio(filename):
    return send_from_directory('.', filename)

# ==================== MESSAGE LOGIC ====================
def process_message(text):
    lang = "en"
    intent, product = detect_intent(text)

    if intent == "greeting":
        return "👋 Hello! Ask about inventory."

    if intent == "check_stock":
        if product:
            item = search_product(product)
            if item:
                return f"{item['name']}: {item['quantity']} units"
            return "Item not found"
        return "Please specify product"

    if intent == "low_stock":
        low = [i for i in get_all_inventory() if i['quantity'] <= i['reorder_level']]
        return "\n".join([f"{i['name']}: LOW ({i['quantity']})" for i in low])

    return "Sorry, I didn't understand"

# ==================== SEND MESSAGE ====================
def send_message(phone, text, is_voice=False):
    if USE_MOCK:
        logger.info(f"[MOCK] {phone}: {text}")
        return True

    try:
        if is_voice:
            audio_file = generate_voice_response(text)

            url = f"http://127.0.0.1:5000/audio/{audio_file}"

            twilio_client.messages.create(
                from_='whatsapp:' + TWILIO_NUMBER,
                to='whatsapp:' + phone,
                body="🔊 Voice reply",
                media_url=[url]
            )
        else:
            twilio_client.messages.create(
                from_='whatsapp:' + TWILIO_NUMBER,
                to='whatsapp:' + phone,
                body=text
            )

        return True

    except Exception as e:
        logger.error(e)
        return False

# ==================== WEBHOOK ====================
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        msg = request.values.get('Body', '').strip()
        phone = request.values.get('From', '').replace("whatsapp:", "")

        has_media = 'MediaUrl0' in request.values

        if has_media:
            msg = msg  # (Whisper can be added later cleanly)

        response = process_message(msg)

        send_message(phone, response, is_voice=True)

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        logger.error(e)
        return jsonify({"error": str(e)}), 500

# ==================== RUN ====================
if __name__ == "__main__":
    print("🚀 Bot running on http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
