import streamlit as st
from audio_recorder_streamlit import audio_recorder
import openai
import anthropic
import json
import re
import sqlite3
from datetime import datetime

# --- 🎙️ OPENAI CLIENT FOR WHISPER TRANSCRIPTION (cloud-based, accent-robust) ---
openai_client = openai.OpenAI()

# --- 🤖 CLAUDE CLIENT FOR INTENT PARSING ---
client = anthropic.Anthropic()


# --- 🗄️ PERSISTENT STORAGE (SQLite) ---
def get_db_connection():
    conn = sqlite3.connect("omnivoice.db", check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            type TEXT NOT NULL,        -- 'sale' or 'restock'
            item TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            revenue INTEGER NOT NULL DEFAULT 0,
            spoken_command TEXT,
            speaker TEXT DEFAULT 'Unknown'
        )
    """)
    conn.commit()
    return conn


def log_transaction(tx_type, item, quantity, revenue=0, spoken_command="", speaker="Unknown"):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO transactions (timestamp, type, item, quantity, revenue, spoken_command, speaker) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (datetime.now().isoformat(), tx_type, item, quantity, revenue, spoken_command, speaker)
    )
    conn.commit()
    conn.close()


def get_last_transaction():
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM transactions ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return row


def delete_transaction(tx_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    conn.commit()
    conn.close()


def check_low_stock(db, item):
    """Return a spoken alert if the item's stock has dropped to or below its threshold, else None."""
    current = db[item]["current"]
    threshold = db[item].get("low_threshold", 0)
    if current <= threshold:
        return (f"Low stock alert. Your {item} is down to {current} {db[item]['unit']}, "
                f"which is at or below your restock threshold of {threshold}. "
                f"You may want to restock {item} soon.")
    return None


# --- 📡 OFFLINE QUEUE ---
def init_queue_table():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            audio_path TEXT,
            transcribed_text TEXT,
            status TEXT DEFAULT 'pending'  -- 'pending' or 'processed'
        )
    """)
    conn.commit()
    conn.close()


def queue_command(audio_path=None, transcribed_text=None):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO pending_commands (timestamp, audio_path, transcribed_text, status) VALUES (?, ?, ?, 'pending')",
        (datetime.now().isoformat(), audio_path, transcribed_text)
    )
    conn.commit()
    conn.close()


def get_pending_commands():
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM pending_commands WHERE status = 'pending' ORDER BY id ASC").fetchall()
    conn.close()
    return rows


def mark_command_processed(cmd_id):
    conn = get_db_connection()
    conn.execute("UPDATE pending_commands SET status = 'processed' WHERE id = ?", (cmd_id,))
    conn.commit()
    conn.close()


# --- 🗂️ DYNAMIC ITEM CATALOG (persisted in SQLite) ---
def init_items_table():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            name TEXT PRIMARY KEY,
            unit TEXT NOT NULL,
            price INTEGER NOT NULL,
            low_threshold INTEGER NOT NULL DEFAULT 0
        )
    """)
    # Seed with defaults if empty
    count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    if count == 0:
        defaults = [
            ("sugar", "kilograms", 150, 20),
            ("beans", "packets", 200, 10),
            ("rice", "bags", 3500, 20),
            ("maize", "bags", 2800, 15),
            ("cooking oil", "liters", 400, 5),
        ]
        conn.executemany("INSERT INTO items (name, unit, price, low_threshold) VALUES (?, ?, ?, ?)", defaults)
    conn.commit()
    conn.close()


def get_all_items():
    conn = get_db_connection()
    rows = conn.execute("SELECT name, unit, price, low_threshold FROM items").fetchall()
    conn.close()
    return rows


def add_item(name, unit, price, low_threshold=0):
    conn = get_db_connection()
    conn.execute(
        "INSERT OR REPLACE INTO items (name, unit, price, low_threshold) VALUES (?, ?, ?, ?)",
        (name, unit, price, low_threshold)
    )
    conn.commit()
    conn.close()


def set_item_threshold(name, low_threshold):
    conn = get_db_connection()
    cur = conn.execute("UPDATE items SET low_threshold = ? WHERE name = ?", (low_threshold, name))
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def get_item_names():
    return [row[0] for row in get_all_items()]


def parse_command(transcribed_text):
    """Use Claude to extract structured intent from flexible natural speech."""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": f"""Extract the intent and details from this voice command for a small business stock management system.

Command: "{transcribed_text}"

Known items: {", ".join(get_item_names())}.

If the speaker identifies themselves (e.g. "This is John" or "John here"), extract their name.
If the speaker wants to add a new item (e.g. "Add a new item called soap, price 80 shillings per bar"), use intent "add_item" and extract item, price, and unit (e.g. "bar").
If the speaker wants to set or change a low-stock alert threshold (e.g. "Alert me when rice goes below 30 bags" or "Set rice threshold to 30"), use intent "set_threshold" and extract item and quantity (the new threshold).

Respond ONLY with valid JSON, nothing else:
{{
  "intent": "restock" | "check_stock" | "sale" | "performance" | "undo" | "daily_report" | "add_item" | "set_threshold" | "help" | "other",
  "item": "<item name, or null>",
  "quantity": <number or null>,
  "branch": "<branch name or null>",
  "speaker": "<name if stated, or null>",
  "unit": "<unit for new item, or null>",
  "price": <price for new item, or null>
}}"""
        }]
    )
    raw = response.content[0].text.strip()
    # Claude sometimes wraps JSON in ```json fences — strip them just in case
    raw = re.sub(r"^```json|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"intent": "other", "item": None, "quantity": None, "branch": None}


init_queue_table()
init_items_table()

# --- 📦 INITIALIZE STATEFUL DATABASE FROM ITEM CATALOG ---
if "db" not in st.session_state:
    st.session_state.db = {}
    for name, unit, price, low_threshold in get_all_items():
        st.session_state.db[name] = {
            "opening": 0, "current": 0, "unit": unit, "price": price, "low_threshold": low_threshold
        }
    # Seed starting stock for the default items only (first run)
    starting_stock = {"sugar": 120, "beans": 45, "rice": 200, "maize": 85, "cooking oil": 30}
    for name, qty in starting_stock.items():
        if name in st.session_state.db:
            st.session_state.db[name]["opening"] = qty
            st.session_state.db[name]["current"] = qty

if "sales_log" not in st.session_state:
    st.session_state.sales_log = {item: {"qty_sold": 0, "revenue": 0} for item in st.session_state.db.keys()}

if "restock_log" not in st.session_state:
    st.session_state.restock_log = {item: 0 for item in st.session_state.db.keys()}

# --- 📅 AUTOMATIC DAILY RESET ---
if "last_date" not in st.session_state:
    st.session_state.last_date = datetime.now().date()

current_date = datetime.now().date()
if current_date != st.session_state.last_date:
    # New day detected — reset daily counters automatically
    st.session_state.sales_log = {item: {"qty_sold": 0, "revenue": 0} for item in st.session_state.db.keys()}
    st.session_state.restock_log = {item: 0 for item in st.session_state.db.keys()}
    st.session_state.last_date = current_date


# --- 🧠 VOICE INTENT PROCESSING ENGINE (now powered by Claude for flexible phrasing) ---
def process_voice_command(text_input):
    db = st.session_state.db
    sales = st.session_state.sales_log
    restocks = st.session_state.restock_log

    parsed = parse_command(text_input)
    intent = parsed.get("intent")
    item = parsed.get("item")
    quantity = parsed.get("quantity")
    speaker = parsed.get("speaker") or "Unknown"

    # Normalize item name in case Claude returns slightly different casing
    if item:
        item = item.lower().strip()

    # --- SALE ---
    if intent == "sale":
        if not item or item not in db:
            return "I understood that as a sale, but I couldn't tell which item. Please say the item name clearly — sugar, beans, rice, maize, or cooking oil."
        if not quantity:
            return f"I heard a sale of {item}, but I couldn't catch the quantity. Please repeat with the number, for example: 'I have sold 5 bags of {item}'."

        current_stock = db[item]["current"]
        if quantity > current_stock:
            return f"Inventory warning. You cannot sell {quantity} {db[item]['unit']} of {item} because you only have {current_stock} remaining."

        db[item]["current"] -= quantity
        sales[item]["qty_sold"] += quantity
        revenue = quantity * db[item]["price"]
        sales[item]["revenue"] += revenue
        log_transaction("sale", item, quantity, revenue, text_input, speaker)

        message = (f"Successfully logged. You have sold {quantity} {db[item]['unit']} of {item}. "
                    f"You are now remaining with {db[item]['current']} {db[item]['unit']}. "
                    f"That transaction brought in {revenue} shillings.")

        alert = check_low_stock(db, item)
        if alert:
            message += " " + alert

        return message

    # --- RESTOCK (NEW) ---
    elif intent == "restock":
        if not item or item not in db:
            return "I understood that as a restock, but I couldn't tell which item. Please say the item name clearly — sugar, beans, rice, maize, or cooking oil."
        if not quantity:
            return f"I heard a restock for {item}, but I couldn't catch the quantity. Please repeat, for example: 'I have restocked 50 bags of {item}'."

        db[item]["current"] += quantity
        db[item]["opening"] += quantity  # so today's opening reflects the new total
        restocks[item] += quantity
        log_transaction("restock", item, quantity, 0, text_input, speaker)

        return (f"Restock recorded. You have added {quantity} {db[item]['unit']} of {item}. "
                f"Your current stock for {item} is now {db[item]['current']} {db[item]['unit']}.")

    # --- UNDO (NEW) ---
    elif intent == "undo":
        last_tx = get_last_transaction()
        if not last_tx:
            return "There is nothing to undo. No transactions have been recorded yet."

        tx_id, _, tx_type, tx_item, tx_qty, tx_revenue, _ = last_tx

        if tx_item not in db:
            delete_transaction(tx_id)
            return "I removed the last record, but the item was no longer in the system."

        if tx_type == "sale":
            db[tx_item]["current"] += tx_qty
            sales[tx_item]["qty_sold"] -= tx_qty
            sales[tx_item]["revenue"] -= tx_revenue
            delete_transaction(tx_id)
            return (f"Undone. I have reversed the sale of {tx_qty} {db[tx_item]['unit']} of {tx_item}. "
                    f"Your stock is now back to {db[tx_item]['current']} {db[tx_item]['unit']}.")

        elif tx_type == "restock":
            db[tx_item]["current"] -= tx_qty
            db[tx_item]["opening"] -= tx_qty
            restocks[tx_item] -= tx_qty
            delete_transaction(tx_id)
            return (f"Undone. I have reversed the restock of {tx_qty} {db[tx_item]['unit']} of {tx_item}. "
                    f"Your stock is now back to {db[tx_item]['current']} {db[tx_item]['unit']}.")

        delete_transaction(tx_id)
        return "I have removed the last record."

    # --- ADD NEW ITEM (NEW) ---
    elif intent == "add_item":
        new_item = parsed.get("item")
        unit = parsed.get("unit") or "units"
        price = parsed.get("price")

        if not new_item:
            return "I understood you want to add a new item, but I couldn't catch its name. Please repeat with the item name."
        new_item = new_item.lower().strip()
        if not price:
            return f"I understood you want to add {new_item}, but I couldn't catch the price. Please repeat including the price."

        add_item(new_item, unit, int(price), 0)

        # Add to live session state too
        db[new_item] = {"opening": 0, "current": 0, "unit": unit, "price": int(price), "low_threshold": 0}
        sales[new_item] = {"qty_sold": 0, "revenue": 0}
        restocks[new_item] = 0

        return (f"New item added. {new_item.capitalize()} has been added to your catalog, priced at {price} shillings per {unit}. "
                f"You can now restock, sell, or check stock for {new_item}.")

    # --- SET LOW-STOCK THRESHOLD (NEW) ---
    elif intent == "set_threshold":
        if not item or item not in db:
            return "Please specify which item's alert threshold you'd like to set, and the item must already exist in your catalog."
        if quantity is None:
            return f"I understood you want to set an alert threshold for {item}, but I couldn't catch the number. Please repeat, for example: 'Alert me when {item} goes below 30 {db[item]['unit']}'."

        db[item]["low_threshold"] = int(quantity)
        set_item_threshold(item, int(quantity))

        return (f"Got it. I will now alert you when {item} drops to {quantity} {db[item]['unit']} or below.")

    # --- PERFORMANCE / SUMMARY ---
    elif intent == "performance":
        total_revenue = sum(s["revenue"] for s in sales.values())
        if total_revenue == 0:
            return "Performance update. You have not recorded any sales yet today. Your current total revenue is zero shillings."

        sold_items_list = []
        highest_item = None
        highest_qty = 0
        unsold_items = []

        for it, data in sales.items():
            if data["qty_sold"] > 0:
                sold_items_list.append(f"{data['qty_sold']} {db[it]['unit']} of {it} for {data['revenue']} shillings")
                if data["qty_sold"] > highest_qty:
                    highest_qty = data["qty_sold"]
                    highest_item = it
            else:
                unsold_items.append(it)

        summary = "Here is your business performance for today. "
        summary += "Today, you have sold: " + ", and ".join(sold_items_list) + ". "
        summary += f"In total, you have made {total_revenue} shillings today. "
        if highest_item:
            summary += f"The commodity you have sold the most is {highest_item}. "
        if unsold_items:
            summary += "Items not sold today: " + ", ".join(unsold_items) + "."
        return summary

    # --- DAILY OPENING/CLOSING REPORT (NEW) ---
    elif intent == "daily_report":
        total_revenue = sum(s["revenue"] for s in sales.values())
        lines = ["Here is your daily report. "]

        # Opening stock summary
        opening_parts = [f"{db[it]['opening']} {db[it]['unit']} of {it}" for it in db.keys()]
        lines.append("Opening stock today was: " + ", ".join(opening_parts) + ". ")

        # Restocks
        restocked_items = [(it, qty) for it, qty in restocks.items() if qty > 0]
        if restocked_items:
            restock_parts = [f"{qty} {db[it]['unit']} of {it}" for it, qty in restocked_items]
            lines.append("You restocked: " + ", ".join(restock_parts) + ". ")
        else:
            lines.append("No restocks were made today. ")

        # Sales
        sold_items = [(it, data) for it, data in sales.items() if data["qty_sold"] > 0]
        if sold_items:
            sale_parts = [f"{data['qty_sold']} {db[it]['unit']} of {it} for {data['revenue']} shillings" for it, data in sold_items]
            lines.append("You sold: " + ", and ".join(sale_parts) + ". ")
        else:
            lines.append("No sales were recorded today. ")

        lines.append(f"Your total revenue today is {total_revenue} shillings. ")

        # Current/closing stock
        closing_parts = [f"{db[it]['current']} {db[it]['unit']} of {it}" for it in db.keys()]
        lines.append("Your current closing stock is: " + ", ".join(closing_parts) + ". ")

        # Low stock alerts
        alerts = [check_low_stock(db, it) for it in db.keys()]
        alerts = [a for a in alerts if a]
        if alerts:
            lines.append(" ".join(alerts))
        else:
            lines.append("All stock levels are currently healthy.")

        return "".join(lines)

    # --- CHECK STOCK ---
    elif intent == "check_stock":
        if not item or item not in db:
            return "Please specify which item's stock you'd like to check — sugar, beans, rice, maize, or cooking oil."
        return (f"Stock check complete. Your opening stock today for {item} was {db[item]['opening']} {db[item]['unit']}. "
                f"You have sold {sales[item]['qty_sold']} so far, and you are remaining with {db[item]['current']} {db[item]['unit']}.")

    # --- HELP (NEW) ---
    elif intent == "help":
        return HELP_MESSAGE
    else:
        return ("I didn't quite catch that. You can say things like: "
                "'I have sold 5 bags of rice', 'I have restocked 50 bags of rice', "
                "'What's my rice stock?', or 'How have I performed today?'")


# --- 🔊 BROWSER-NATIVE TEXT-TO-SPEECH ---
def speak_text(text_to_say):
    safe_text = text_to_say.replace("'", "\\'").replace("\n", " ")
    js_speech = f"""
    <script>
        function speakNow() {{
            var msg = new SpeechSynthesisUtterance('{safe_text}');
            msg.lang = 'en-US';
            msg.rate = 0.95;
            msg.pitch = 1.0;
            msg.volume = 1.0;

            var voices = window.speechSynthesis.getVoices();
            if (voices.length > 0) {{
                // Prefer a Google/Microsoft English voice if available — clearer than default
                var preferred = voices.find(function(v) {{
                    return v.lang.startsWith('en') && (v.name.includes('Google') || v.name.includes('Microsoft'));
                }});
                var anyEnglish = voices.find(function(v) {{ return v.lang.startsWith('en'); }});
                msg.voice = preferred || anyEnglish || voices[0];
            }}
            window.speechSynthesis.cancel();  // stop any overlapping speech first
            window.speechSynthesis.speak(msg);
        }}

        // Voices often load asynchronously — wait for them if not ready yet
        if (window.speechSynthesis.getVoices().length === 0) {{
            window.speechSynthesis.onvoiceschanged = speakNow;
        }} else {{
            speakNow();
        }}
    </script>
    """
    st.components.v1.html(js_speech, height=0, width=0)


# --- 🎨 ACCESSIBLE HIGH-CONTRAST UI ---
st.set_page_config(page_title="OmniVoice AI", page_icon="🎙️", layout="centered")

st.markdown("<h1 style='text-align: center; color: #1E3A8A;'>🎙️ OmniVoice Pro</h1>", unsafe_allow_html=True)
st.markdown("<h3 style='text-align: center; color: #4B5563;'>Voice-First Dynamic Inventory Assistant</h3>", unsafe_allow_html=True)
st.write("---")

HELP_MESSAGE = (
    "Welcome to OmniVoice. Here is what you can say. "
    "To record a sale, say: I have sold 5 bags of rice. "
    "To record new stock, say: I have restocked 50 bags of rice. "
    "To check stock for an item, just say the item's name, like: how much rice do I have. "
    "To hear how your day is going, say: what's my performance today, or, give me my daily report. "
    "To undo your last action, say: undo that. "
    "To add a brand new item, say: add a new item called soap, price 80 shillings per bar. "
    "To set a low stock alert, say: alert me when rice goes below 30 bags. "
    "You can say help at any time to hear this again. "
    "Tap the microphone, then speak your command clearly."
)

WELCOME_MESSAGE = "Hello. How may I help you? If you need help, say help."

# Speak the simple welcome message once per session, automatically
if "welcomed" not in st.session_state:
    st.session_state.welcomed = True
    speak_text(WELCOME_MESSAGE)

# --- 📊 SIDEBAR SYSTEM DASHBOARD ---
with st.sidebar:
    st.header("📊 Live System State")
    st.write("**Current Inventory:**")
    for k, v in st.session_state.db.items():
        st.write(f"- {k.capitalize()}: **{v['current']}** remaining")
    st.write("---")
    st.write("**Restocked Today:**")
    for k, v in st.session_state.restock_log.items():
        if v > 0:
            st.write(f"- {k.capitalize()}: +{v} {st.session_state.db[k]['unit']}")
    st.write("---")
    tot = sum(i['revenue'] for i in st.session_state.sales_log.values())
    st.metric("Total Money Earned Today", f"{tot} KSH")
    st.write("---")
    st.write("**Recent Transactions:**")
    conn = get_db_connection()
    recent = conn.execute(
        "SELECT type, item, quantity, revenue, timestamp FROM transactions ORDER BY id DESC LIMIT 5"
    ).fetchall()
    conn.close()
    if recent:
        for r_type, r_item, r_qty, r_rev, r_time in recent:
            time_str = r_time.split("T")[1][:5]
            if r_type == "sale":
                st.write(f"- {time_str} — Sold {r_qty} {r_item} (KSH {r_rev})")
            else:
                st.write(f"- {time_str} — Restocked {r_qty} {r_item}")
    else:
        st.write("No transactions yet.")

st.info("💡 **Try Saying:** 'I have sold 5 bags of rice', 'I have restocked 50 bags of rice', or 'What was my performance today?'")
st.write("##")

# --- 🔒 STATIC CONTAINERS (Prevents Layout Shifting) ---
transcription_container = st.empty()
response_container = st.empty()

# --- 🔘 STATIONARY MICROPHONE ---
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.markdown("<p style='text-align: center; font-weight: bold;'>TAP MICROPHONE TO COMMAND:</p>", unsafe_allow_html=True)
    audio_bytes = audio_recorder(text="", recording_color="#ef4444", neutral_color="#10b981", icon_size="5x")

# --- ⏳ STATUS CONTAINER ---
status_container = st.empty()

# --- 🔄 PROCESSING PIPELINE (Now using Whisper for accent-robust transcription) ---
if audio_bytes:
    if len(audio_bytes) < 100:
        status_container.error("🚨 Recording too short! Please try again.")
    else:
        with open("user_voice.wav", "wb") as f:
            f.write(audio_bytes)

        status_container.warning("⏳ Processing... please hold steady.")

        try:
            # Whisper API handles a wide range of accents much better than cloud STT
            with open("user_voice.wav", "rb") as audio_file:
                transcript = openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="en"
                )
            user_text = transcript.text.strip()

            if not user_text:
                status_container.empty()
                transcription_container.error("I could not catch your command. Please speak closer to your device mic.")
            else:
                transcription_container.markdown(f"### 🗣️ Detected Instruction:\n> **\"{user_text}\"**")

                reply_message = process_voice_command(user_text)
                response_container.markdown(
                    f"<div style='font-size:22px; font-weight:bold; background-color:#F3F4F6; padding:20px; border-radius:10px; border-left: 8px solid #1E3A8A; margin-top:15px; margin-bottom:15px;'>🎙️ Agent Response: {reply_message}</div>",
                    unsafe_allow_html=True
                )
                status_container.empty()
                speak_text(reply_message)

        except (openai.APIConnectionError, anthropic.APIConnectionError):
            # No internet — queue the raw audio for later processing
            saved_path = f"queued_audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
            with open(saved_path, "wb") as f:
                f.write(audio_bytes)
            queue_command(audio_path=saved_path, transcribed_text=None)
            status_container.empty()
            transcription_container.warning(
                "📡 No internet connection right now. Your command has been saved and will be processed "
                "automatically once you're back online."
            )
            speak_text("No internet connection right now. I have saved your command and will process it once you are back online.")

        except Exception as e:
            status_container.empty()
            transcription_container.error(f"⚠️ Something went wrong processing the audio: {e}")


# --- 📡 PROCESS ANY QUEUED OFFLINE COMMANDS ---
pending = get_pending_commands()
if pending:
    st.write("---")
    st.warning(f"📡 {len(pending)} command(s) were saved while offline.")
    if st.button("Process queued commands now"):
        for cmd_id, ts, audio_path, transcribed_text, status in pending:
            try:
                if audio_path:
                    with open(audio_path, "rb") as audio_file:
                        transcript = openai_client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            language="en"
                        )
                    text = transcript.text.strip()
                else:
                    text = transcribed_text

                if text:
                    reply = process_voice_command(text)
                    st.write(f"✅ Processed: \"{text}\" → {reply}")

                mark_command_processed(cmd_id)
            except Exception as e:
                st.error(f"Could not process queued command {cmd_id}: {e}")
        st.rerun()
