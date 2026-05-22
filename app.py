import streamlit as st
from audio_recorder_streamlit import audio_recorder
import speech_recognition as sr
from gtts import gTTS
import base64
import re

# --- 📦 INITIALIZE STATEFUL DATABASE (Persists across microphone runs) ---
if "db" not in st.session_state:
    # Tracks opening/current stock and standard prices per unit
    st.session_state.db = {
        "sugar": {"opening": 120, "current": 120, "unit": "kilograms", "price": 150},
        "beans": {"opening": 45, "current": 45, "unit": "packets", "price": 200},
        "rice": {"opening": 200, "current": 200, "unit": "bags", "price": 3500},
        "maize": {"opening": 85, "current": 85, "unit": "bags", "price": 2800},
        "cooking oil": {"opening": 30, "current": 30, "unit": "liters", "price": 400}
    }

if "sales_log" not in st.session_state:
    # Tracks sales quantity and total revenue generated per item today
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

    # ----------------------------------------------------
    # INTENT 1: LOGGING A SALE (e.g., "I have sold 5 bags of rice")
    # ----------------------------------------------------
    if "sold" in query or "sell" in query:
        # Regular expression to extract numbers from the voice phrase
        numbers = re.findall(r'\d+', query)
        if not numbers:
            return "System alert. I heard you say you sold something, but I couldn't catch the exact amount. Please repeat with the number clearly."
        
        qty_sold = int(numbers[0])
        
        # Match the commodity
        matched_item = None
        for item in db.keys():
            if item in query or (item == "beans" and "bean" in query):
                matched_item = item
                break
                
        if matched_item:
            current_stock = db[matched_item]["current"]
            if qty_sold > current_stock:
                return f"Inventory warning. You cannot sell {qty_sold} {db[matched_item]['unit']} of {matched_item} because you only have {current_stock} remaining."
            
            # Perform subtraction calculations
            db[matched_item]["current"] -= qty_sold
            sales[matched_item]["qty_sold"] += qty_sold
            transaction_revenue = qty_sold * db[matched_item]["price"]
            sales[matched_item]["revenue"] += transaction_revenue
            
            return (f"Successfully logged. You have sold {qty_sold} {db[matched_item]['unit']} of {matched_item}. "
                    f"You are now remaining with {db[matched_item]['current']} {db[matched_item]['unit']}. "
                    f"That transaction brought in {transaction_revenue} shillings.")
        else:
            return "I understood the amount, but I could not identify which commodity you sold. Please specify if it was sugar, beans, rice, maize, or cooking oil."

    # ----------------------------------------------------
    # INTENT 2: DAILY PERFORMANCE / TOTAL MONEY / PROFITS
    # ----------------------------------------------------
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
        else:
            summary_details += "Excellent work, you have sold items from every category today!"
            
        return summary_details

    # ----------------------------------------------------
    # INTENT 3: BASIC STOCK LOOKUP & REMAINING QUANTITIES
    # ----------------------------------------------------
    else:
        for item in db.keys():
            if item in query or (item == "beans" and "bean" in query):
                return (f"Stock check complete. Your opening stock today for {item} was {db[item]['opening']} {db[item]['unit']}. "
                        f"You have sold {sales[item]['qty_sold']} so far, and you are remaining with {db[item]['current']} {db[item]['unit']}.")
        
        return "OmniVoice processing error. If you are checking stock, specify the item name. If you made a sale, say 'I have sold five bags of rice'. If you want totals, ask 'What is my performance today?'"

# --- 🔊 TEXT-TO-SPEECH AUTO-PLAY ENGINE ---
def speak_text(text_to_say):
    tts = gTTS(text=text_to_say, lang='en', slow=False)
    tts.save("response.mp3")
    
    with open("response.mp3", "rb") as f:
        audio_bytes = f.read()
    audio_base64 = base64.b64encode(audio_bytes).decode()
    
    audio_html = f'<audio autoplay src="data:audio/mp3;base64,{audio_base64}">'
    st.markdown(audio_html, unsafe_allow_html=True)

# --- 🎨 ACCESSIBLE HIGH-CONTRAST UI ---
st.set_page_config(page_title="OmniVoice AI", page_icon="🎙️", layout="centered")

st.markdown("<h1 style='text-align: center; color: #1E3A8A;'>🎙️ OmniVoice Pro</h1>", unsafe_allow_html=True)
st.markdown("<h3 style='text-align: center; color: #4B5563;'>Voice-First Dynamic Inventory Assistant</h3>", unsafe_allow_html=True)
st.write("---")

# Visual feedback tracker dashboard for developers/judges to see calculations working live
with st.sidebar:
    st.header("📊 Live System State")
    st.write("**Current Inventory Quantities:**")
    for k, v in st.session_state.db.items():
        st.write(f"- {k.capitalize()}: {v['current']} remaining (Opened with {v['opening']})")
    st.write("---")
    st.write("**Today's Sales Revenue:**")
    tot = sum(i['revenue'] for i in st.session_state.sales_log.values())
    st.metric("Total Money Earned", f"{tot} KSH")

# Instructions block for voice targets
st.info("💡 **Voice Instructions Examples:**\n"
        "• *'I have sold 5 bags of rice'*\n"
        "• *'What was my performance today?'*\n"
        "• *'Check stock sugar'*")

st.write("##")

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.markdown("<p style='text-align: center; font-weight: bold;'>TAP MICROPHONE TO VOICE COMMAND:</p>", unsafe_allow_html=True)
    audio_bytes = audio_recorder(
        text="",
        recording_color="#ef4444",  
        neutral_color="#10b981",    
        icon_size="5x"               
    )

if audio_bytes:
    with open("user_voice.wav", "wb") as f:
        f.write(audio_bytes)
        
    with st.spinner("⏳ Processing calculations..."):
        recognizer = sr.Recognizer()
        with sr.AudioFile("user_voice.wav") as source:
            audio_data = recognizer.record(source)
            try:
                # 1. Voice to Text
                user_text = recognizer.recognize_google(audio_data)
                st.markdown(f"### 🗣️ Detected Instruction:\n> **\"{user_text}\"**")
                
                # 2. Run Intelligent Calculations and Update Database State
                reply_message = process_voice_command(user_text)
                
                # 3. High Visibility Response Block
                st.markdown("---")
                st.success("📊 **Audio Agent Response:**")
                st.markdown(f"<div style='font-size:22px; font-weight:bold; background-color:#F3F4F6; padding:20px; border-radius:10px; border-left: 8px solid #1E3A8A;'>{reply_message}</div>", unsafe_allow_html=True)
                
                # 4. Speak response automatically
                speak_text(reply_message)
                st.rerun() # Forces sidebar metric numbers to update on-screen immediately
                
            except sr.UnknownValueError:
                error_msg = "I could not quite understand your audio command. Please speak closer to the mic."
                st.error(error_msg)
                speak_text(error_msg)
            except sr.RequestError:
                st.error("Speech cloud network timeout.")