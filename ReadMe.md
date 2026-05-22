# 🎙️ OmniVoice Pro

An accessible, voice-first dynamic inventory management assistant designed specifically for visually impaired and partially blind entrepreneurs to track stock, log sales, and monitor daily business performance hands-free.

---

## 👥 Team Members

* **Sarah Owendi**
* **Briannah Chelangat**
* **Abel Aleu Chol Garang**

---

## 💡 The Problem & Core Concept

Small business owners who are visually impaired face significant hurdles when interacting with traditional visual digital tools like spreadsheets or complex point-of-sale applications. 

**OmniVoice Pro** solves this accessibility gap by offering a seamless **Voice-In, Voice-Out pipeline**. Instead of peering at small text blocks or typing out quantities, an entrepreneur can simply tap an extra-large, high-contrast microphone target, speak their shop activities naturally, and listen as the application instantly handles the mathematical calculations and speaks the operational metrics right back to them.

---

## 🛠️ Key Features

* **Natural Voice Processing:** Converts spoken natural audio input into actionable backend database queries and commands.
* **Stateful Inventory Tracking:** Automatically tracks changes from initial opening stock values to real-time current levels across dynamic database adjustments.
* **Dynamic Sales & Math Engine:** Automatically extracts product names and numeric quantities to subtract remaining inventory and add up transactions on the fly.
* **Real-Time Business Intelligence Summary:** Computes key metrics on command including *total daily revenue*, *highest-selling products*, and *unsold inventory groups*.
* **Accessibility First Interface:** Engineered using massive targets, high-contrast layouts, and a text-to-speech loop designed to completely complement device screen readers.

---

## 💻 Tech Stack

* **Frontend Interface:** Streamlit (Python-driven high-contrast web app framework)
* **Audio Recording Capture:** Streamlit Audio Recorder Component
* **Speech-to-Text (STT) Engine:** SpeechRecognition API
* **Text-to-Speech (TTS) Engine:** gTTS (Google Text-to-Speech)
* **Core Logic Language:** Python 3

---

## 🚀 Installation & Quick Start

Follow these steps to run OmniVoice Pro locally on your machine:

### 1. Clone the Repository
```bash
git clone <your-repository-url>
cd omnivoice-pro