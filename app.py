import streamlit as st
from audio_recorder_streamlit import audio_recorder
import whisper
import anthropic
import json
import re

# --- 🎙️ LOAD WHISPER ONCE (cached so it doesn't reload every interaction) ---
@st.cache_resource
def load_whisper_model():
    return whisper.load_model("base")  # "small" gives better accuracy if you have the compute

whisper_model = load_whisper_model()

# --- 🤖 CLAUDE CLIENT FOR INTENT PARSING ---
client = anthropic.Anthropic()


def parse_command(transcribed_text):
    """Use Claude to extract structured intent from flexible natural speech."""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": f"""Extract the intent and details from this voice command for a small business stock management system.

Command: "{transcribed_text}"

Known items: sugar, beans, rice, maize, cooking oil.

Respond ONLY with valid JSON, nothing else:
{{
  "intent": "restock" | "check_stock" | "sale" | "performance" | "other",
  "item": "<one of the known items, or null>",
  "quantity": <number or null>,
  "branch": "<branch name or null>"
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


# --- 📦 INITIALIZE STATEFUL DATABASE (Persists across microphone runs) ---
if "db" not in st.session_state:
    st.session_state.db = {
        "sugar": {"opening": 120, "current": 120, "unit": "kilograms", "price": 150},
        "beans": {"opening": 45, "current": 45, "unit": "packets", "price": 200},
        "rice": {"opening": 200, "current": 200, "unit": "bags", "price": 3500},
        "maize": {"opening": 85, "current": 85, "unit": "bags", "price": 2800},
        "cooking oil": {"opening": 30, "current": 30, "unit": "liters", "price": 400}
    }

if "sales_log" not in st.session_state:
    st.session_state.sales_log = {
        "sugar": {"qty_sold": 0, "revenue": 0},
        "beans": {"qty_sold": 0, "revenue": 0},
        "rice": {"qty_sold": 0, "revenue": 0},
        "maize": {"qty_sold": 0, "revenue": 0},
        "cooking oil": {"qty_sold": 0, "revenue": 0}
    }

if "restock_log" not in st.session_state:
    st.session_state.restock_log = {item: 0 for item in st.session_state.db.keys()}


# --- 🧠 VOICE INTENT PROCESSING ENGINE (now powered by Claude for flexible phrasing) ---
def process_voice_command(text_input):
    db = st.session_state.db
    sales = st.session_state.sales_log
    restocks = st.session_state.restock_log

    parsed = parse_command(text_input)
    intent = parsed.get("intent")
    item = parsed.get("item")
    quantity = parsed.get("quantity")

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

        return (f"Successfully logged. You have sold {quantity} {db[item]['unit']} of {item}. "
                f"You are now remaining with {db[item]['current']} {db[item]['unit']}. "
                f"That transaction brought in {revenue} shillings.")

    # --- RESTOCK (NEW) ---
    elif intent == "restock":
        if not item or item not in db:
            return "I understood that as a restock, but I couldn't tell which item. Please say the item name clearly — sugar, beans, rice, maize, or cooking oil."
        if not quantity:
            return f"I heard a restock for {item}, but I couldn't catch the quantity. Please repeat, for example: 'I have restocked 50 bags of {item}'."

        db[item]["current"] += quantity
        db[item]["opening"] += quantity  # so today's opening reflects the new total
        restocks[item] += quantity

        return (f"Restock recorded. You have added {quantity} {db[item]['unit']} of {item}. "
                f"Your current stock for {item} is now {db[item]['current']} {db[item]['unit']}.")

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

    # --- CHECK STOCK ---
    elif intent == "check_stock":
        if not item or item not in db:
            return "Please specify which item's stock you'd like to check — sugar, beans, rice, maize, or cooking oil."
        return (f"Stock check complete. Your opening stock today for {item} was {db[item]['opening']} {db[item]['unit']}. "
                f"You have sold {sales[item]['qty_sold']} so far, and you are remaining with {db[item]['current']} {db[item]['unit']}.")

    # --- FALLBACK ---
    else:
        return ("I didn't quite catch that. You can say things like: "
                "'I have sold 5 bags of rice', 'I have restocked 50 bags of rice', "
                "'What's my rice stock?', or 'How have I performed today?'")


# --- 🔊 BROWSER-NATIVE TEXT-TO-SPEECH ---
def speak_text(text_to_say):
    safe_text = text_to_say.replace("'", "\\'")
    js_speech = f"""
    <script>
        var msg = new SpeechSynthesisUtterance('{safe_text}');
        msg.lang = 'en-US';
        var voices = window.speechSynthesis.getVoices();
        if(voices.length > 0) {{
            msg.voice = voices.filter(function(voice) {{ return voice.lang.includes('en'); }})[0];
        }}
        window.speechSynthesis.speak(msg);
    </script>
    """
    st.components.v1.html(js_speech, height=0, width=0)


# --- 🎨 ACCESSIBLE HIGH-CONTRAST UI ---
st.set_page_config(page_title="OmniVoice AI", page_icon="🎙️", layout="centered")

st.markdown("<h1 style='text-align: center; color: #1E3A8A;'>🎙️ OmniVoice Pro</h1>", unsafe_allow_html=True)
st.markdown("<h3 style='text-align: center; color: #4B5563;'>Voice-First Dynamic Inventory Assistant</h3>", unsafe_allow_html=True)
st.write("---")

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
            # Whisper handles a wide range of accents much better than cloud STT
            result = whisper_model.transcribe("user_voice.wav", language="en")
            user_text = result["text"].strip()

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

        except Exception as e:
            status_container.empty()
            transcription_container.error(f"⚠️ Something went wrong processing the audio: {e}")
