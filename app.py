import streamlit as st
from audio_recorder_streamlit import audio_recorder
import speech_recognition as sr
import re

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

# --- 🧠 VOICE INTENT PARSING ENGINE ---
def process_voice_command(text_input):
    query = text_input.lower().strip()
    db = st.session_state.db
    sales = st.session_state.sales_log

    if "sold" in query or "sell" in query:
        numbers = re.findall(r'\d+', query)
        if not numbers:
            return "System alert. I heard you say you sold something, but I couldn't catch the exact amount. Please repeat with the number clearly."
        
        qty_sold = int(numbers[0])
        matched_item = None
        for item in db.keys():
            if item in query or (item == "beans" and "bean" in query):
                matched_item = item
                break
                
        if matched_item:
            current_stock = db[matched_item]["current"]
            if qty_sold > current_stock:
                return f"Inventory warning. You cannot sell {qty_sold} {db[matched_item]['unit']} of {matched_item} because you only have {current_stock} remaining."
            
            db[matched_item]["current"] -= qty_sold
            sales[matched_item]["qty_sold"] += qty_sold
            transaction_revenue = qty_sold * db[matched_item]["price"]
            sales[matched_item]["revenue"] += transaction_revenue
            
            return (f"Successfully logged. You have sold {qty_sold} {db[matched_item]['unit']} of {matched_item}. "
                    f"You are now remaining with {db[matched_item]['current']} {db[matched_item]['unit']}. "
                    f"That transaction brought in {transaction_revenue} shillings.")
        else:
            return "I understood the amount, but I could not identify which commodity you sold. Please specify if it was sugar, beans, rice, maize, or cooking oil."

    elif "performance" in query or "money" in query or "how have i performed" in query or "profit" in query:
        total_revenue = sum(item["revenue"] for item in sales.values())
        if total_revenue == 0:
            return "Performance update. You started with your opening stock and have not recorded any sales yet today. Your current total revenue is zero shillings."
        
        summary_details = "Here is your business performance for today. "
        sold_items_list = []
        highest_item = None
        highest_qty = 0
        unsold_items = []

        for item, data in sales.items():
            if data["qty_sold"] > 0:
                sold_items_list.append(f"{data['qty_sold']} {db[item]['unit']} of {item} for {data['revenue']} shillings")
                if data["qty_sold"] > highest_qty:
                    highest_qty = data["qty_sold"]
                    highest_item = item
            else:
                unsold_items.append(item)

        summary_details += "Today, you have sold: " + ", and ".join(sold_items_list) + ". "
        summary_details += f"In total, you have made {total_revenue} shillings today. "
        if highest_item:
            summary_details += f"The commodity you have sold the most is {highest_item}. "
        if unsold_items:
            summary_details += "The items you have not sold any of today are: " + ", ".join(unsold_items) + "."
        return summary_details

    else:
        for item in db.keys():
            if item in query or (item == "beans" and "bean" in query):
                return (f"Stock check complete. Your opening stock today for {item} was {db[item]['opening']} {db[item]['unit']}. "
                        f"You have sold {sales[item]['qty_sold']} so far, and you are remaining with {db[item]['current']} {db[item]['unit']}.")
        return "OmniVoice processing error. If you are checking stock, specify the item name. If you made a sale, say 'I have sold five bags of rice'."

# --- 🔊 BROWSER-NATIVE TEXT-TO-SPEECH (Eliminates Cloud gTTS Errors) ---
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
    tot = sum(i['revenue'] for i in st.session_state.sales_log.values())
    st.metric("Total Money Earned Today", f"{tot} KSH")

st.info("💡 **Try Saying:** 'I have sold 5 bags of rice' or 'What was my performance today?'")
st.write("##")

# --- 🔒 STATIC CONTAINERS (Prevents Layout Shifting) ---
transcription_container = st.empty()
response_container = st.empty()

# --- 🔘 STATIONARY MICROPHONE ---
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.markdown("<p style='text-align: center; font-weight: bold;'>TAP MICROPHONE TO COMMAND:</p>", unsafe_allow_html=True)
    audio_bytes = audio_recorder(text="", recording_color="#ef4444", neutral_color="#10b981", icon_size="5x")

# --- ⏳ STATUS CONTAINER (Kept at the absolute bottom) ---
status_container = st.empty()

# --- 🔄 SECURE PROCESSING PIPELINE ---
if audio_bytes:
    if len(audio_bytes) < 100:
        status_container.error("🚨 Recording too short! Please try again.")
    else:
        with open("user_voice.wav", "wb") as f:
            f.write(audio_bytes)
            
        status_container.warning("⏳ Processing calculations... please hold steady.")
        recognizer = sr.Recognizer()
        
        try:
            with sr.AudioFile("user_voice.wav") as source:
                audio_data = recognizer.record(source)
                
            user_text = recognizer.recognize_google(audio_data)
            transcription_container.markdown(f"### 🗣️ Detected Instruction:\n> **\"{user_text}\"**")
            
            reply_message = process_voice_command(user_text)
            response_container.markdown(
                f"<div style='font-size:22px; font-weight:bold; background-color:#F3F4F6; padding:20px; border-radius:10px; border-left: 8px solid #1E3A8A; margin-top:15px; margin-bottom:15px;'>🎙️ Agent Response: {reply_message}</div>", 
                unsafe_allow_html=True
            )
            status_container.empty()
            speak_text(reply_message)
            
        except ValueError:
            # Safe Fallback Strategy for Cloud Audio Compression Bugs
            status_container.empty()
            transcription_container.error("⚠️ Cloud Audio Format Notice: Your browser sent an alternative compressed stream.")
            
            mock_demo_text = "I have sold 5 bags of rice"
            response_container.info(f"💡 Launching Presentation Mock Fallback: \"{mock_demo_text}\"")
            
            fallback_reply = process_voice_command(mock_demo_text)
            response_container.markdown(
                f"<div style='font-size:22px; font-weight:bold; background-color:#F3F4F6; padding:20px; border-radius:10px; border-left: 8px solid #1E3A8A;'>🎙️ (Fallback Output) {fallback_reply}</div>", 
                unsafe_allow_html=True
            )
            speak_text(fallback_reply)
            
        except sr.UnknownValueError:
            status_container.empty()
            transcription_container.error("I could not catch your command. Please speak closer to your device mic.")
        except sr.RequestError:
            status_container.empty()
            transcription_container.error("Speech Cloud Server Timeout.")