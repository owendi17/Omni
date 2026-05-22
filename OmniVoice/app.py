import streamlit as st
from audio_recorder_streamlit import audio_recorder
import speech_recognition as sr
from gtts import gTTS
import base64
import os

# --- 🎯 INVENTORY DATABASE ENGINE (Mocking your SQLite data) ---
# You can change these quantities right here to whatever you want to show the judges!
def check_inventory(item_name):
    db = {
        "sugar": "120 kilograms", 
        "beans": "45 packets", 
        "rice": "200 bags",
        "maize": "85 bags",
        "cooking oil": "30 liters"
    }
    
    query = item_name.lower().strip()
    
    # Simple semantic matching for accessibility queries
    if "sugar" in query:
        return f"Database query complete. Your current stock for sugar is {db['sugar']}."
    elif "bean" in query:  # matches bean or beans
        return f"Database query complete. Your current stock for beans is {db['beans']}."
    elif "rice" in query:
        return f"Database query complete. Your current stock for rice is {db['rice']}."
    elif "maize" in query or "corn" in query:
        return f"Database query complete. Your current stock for maize is {db['maize']}."
    elif "oil" in query:
        return f"Database query complete. Your current stock for cooking oil is {db['cooking oil']}."
    else:
        return f"Inventory alert. I could not find '{item_name}' in the stock records. Please try another item."

# --- 🔊 TEXT-TO-SPEECH AUTO-PLAY ENGINE ---
def speak_text(text_to_say):
    # Convert text to audio file
    tts = gTTS(text=text_to_say, lang='en', slow=False)
    tts.save("response.mp3")
    
    # Encode audio file to base64 to trick the browser into autoplaying it
    with open("response.mp3", "rb") as f:
        audio_bytes = f.read()
    audio_base64 = base64.b64encode(audio_bytes).decode()
    
    # Custom HTML audio tag with autoplay enabled
    audio_html = f'<audio autoplay src="data:audio/mp3;base64,{audio_base64}">'
    st.markdown(audio_html, unsafe_allow_html=True)

# --- 🎨 ACCESSIBLE HIGH-CONTRAST UI ---
st.set_page_config(page_title="OmniVoice AI", page_icon="🎙️", layout="centered")

# Huge header for accessibility
st.markdown("<h1 style='text-align: center; color: #1E3A8A;'>🎙️ OmniVoice AI</h1>", unsafe_allow_html=True)
st.markdown("<h3 style='text-align: center; color: #4B5563;'>Voice-First Accessibility Assistant for Visually Impaired Entrepreneurs</h3>", unsafe_allow_html=True)
st.write("---")

# Instructions block designed for judges
st.info("🚨 **JUDGES PRESENTATION DEMO:**\n\n"
        "1. Click the **Green Microphone** icon below.\n"
        "2. Speak clearly into your computer mic (e.g., *'Check stock sugar'* or *'How many bags of rice do I have?'*).\n"
        "3. Click it again to stop. The app will automatically transcribe your voice, query the system, and speak the stock numbers out loud!")

st.write("##")

# Center-aligning the massive audio recording target button
col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    st.markdown("<p style='text-align: center; font-weight: bold;'>TAP MICROPHONE TO SPEAK:</p>", unsafe_allow_html=True)
    audio_bytes = audio_recorder(
        text="",
        recording_color="#ef4444",  # Red when recording
        neutral_color="#10b981",    # Bright Green when idle (high visibility target)
        icon_size="5x"               # Extra large for low-vision targets
    )

st.write("##")

# --- 🔄 VOICE PROCESSING PIPELINE ---
if audio_bytes:
    # Save the mic input temporarily
    with open("user_voice.wav", "wb") as f:
        f.write(audio_bytes)
        
    with st.spinner("⏳ Omnivoice AI is listening... processing your database command..."):
        recognizer = sr.Recognizer()
        with sr.AudioFile("user_voice.wav") as source:
            audio_data = recognizer.record(source)
            try:
                # 1. Voice to Text
                user_text = recognizer.recognize_google(audio_data)
                
                st.markdown(f"### 🗣️ What You Said:\n> **\"{user_text}\"**")
                
                # 2. Query Database
                reply_message = check_inventory(user_text)
                
                # 3. Big UI metric display block
                st.markdown("---")
                st.success("📊 **Real-Time Inventory Status:**")
                st.markdown(f"<div style='font-size:24px; font-weight:bold; background-color:#F3F4F6; padding:20px; border-radius:10px; border-left: 8px solid #1E3A8A;'>{reply_message}</div>", unsafe_allow_html=True)
                
                # 4. Voice response out loud
                speak_text(reply_message)
                
            except sr.UnknownValueError:
                error_msg = "OmniVoice audio error. I could not understand the recording. Please tap the green icon and try again clearly."
                st.error(error_msg)
                speak_text(error_msg)
            except sr.RequestError:
                st.error("Speech cloud network timeout. Please check internet connection.")