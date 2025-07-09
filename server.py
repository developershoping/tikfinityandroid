# server.py (Versi Final - Disesuaikan dengan Dokumentasi Blackbox.ai Resmi)

import os
import requests
from TikTokLive import TikTokLiveClient
from TikTokLive.events import CommentEvent, GiftEvent, JoinEvent, ConnectEvent, DisconnectEvent
import time
import asyncio
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
import threading
import socket
import http.server
import socketserver
from gtts import gTTS
from playsound import playsound
import uuid

# --- FUNGSI UNTUK MENDAPATKAN IP LOKAL ---
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try: s.connect(('10.255.255.255', 1)); IP = s.getsockname()[0]
    except Exception: IP = '127.0.0.1'
    finally: s.close()
    return IP

# --- FUNGSI UNTUK MENJALANKAN HTTP SERVER DI LATAR BELAKANG ---
def run_http_server(port=8080):
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"HTTP Server untuk file (host.html, etc) berjalan di port {port}")
        httpd.serve_forever()

# --- FUNGSI BARU UNTUK TEXT-TO-SPEECH ---
def speak_text(text: str):
    try:
        print("🎙️  Mensintesis suara...")
        tts = gTTS(text=text, lang='id', slow=False)
        if not os.path.exists("temp_audio"): os.makedirs("temp_audio")
        filename = os.path.join("temp_audio", f"response_{uuid.uuid4()}.mp3")
        tts.save(filename)
        print(f"🔊 Memutar audio: {text}")
        playsound(filename)
        os.remove(filename)
    except Exception as e:
        print(f"Error pada fungsi suara: {e}")

# --- KONFIGURASI ---
load_dotenv()
app = Flask(__name__)
CORS(app)

# --- STATE APLIKASI ---
app_state = { "log_items": [], "tiktok_status": "Idle", "last_update": time.time() }

# --- Logika AI & TikTok ---

# Mengambil API Key dari file .env
BLACKBOX_API_KEY = os.environ.get("BLACKBOX_API_KEY")
if not BLACKBOX_API_KEY: print("Error: BLACKBOX_API_KEY tidak ditemukan di file .env")

# --- PERUBAHAN BERDASARKAN DOKUMENTASI ---
# Menggunakan Base URL dan Endpoint yang benar
BLACKBOX_API_URL = "https://api.blackbox.ai/chat/completions"

def get_blackbox_response(prompt: str) -> str:
    if not BLACKBOX_API_KEY: return ""

    system_prompt = "Anda adalah Jarvis, asisten AI yang kasar dan suka bicara kotor di TikTok. Jawablah dengan singkat (1-2 kalimat) dan sapa pengguna dengan nama mereka. Pastikan tidak membaca emoticon yang ditampilkan. pastikan anda juga menanggapi notifikasi di obrolan. Jika ada yang memberikan gift maka respon balik"

    # Header sesuai dokumentasi
    headers = {
        "Authorization": f"Bearer {BLACKBOX_API_KEY}",
        "Content-Type": "application/json"
    }

    # Payload sesuai dokumentasi
    payload = {
        "model": "deepseek-coder", # Kita tetap coba 'deepseek-coder'. Jika gagal, ganti ke 'blackboxai/openai/gpt-4'
        "messages": [
            { "role": "system", "content": system_prompt },
            { "role": "user", "content": prompt }
        ],
        "temperature": 0.7
    }

    try:
        response = requests.post(BLACKBOX_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        ai_message = data.get('choices', [{}])[0].get('message', {}).get('content', '')
        return ai_message.strip()
    except requests.exceptions.RequestException as e:
        print(f"Error saat memanggil Blackbox API: {e}")
        if 'response' in locals() and response.text: print(f"Response Body: {response.text}")
        return ""
    except (KeyError, IndexError) as e:
        print(f"Error saat mengurai respons dari Blackbox: {e}")
        return ""

# ... (Sisa kode dari run_tiktok_client hingga akhir tetap sama persis) ...
def run_tiktok_client(username: str):
    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    client = TikTokLiveClient(unique_id=f"@{username}")
    def add_log(log_type, data):
        global app_state
        app_state["log_items"].append({"type": log_type, "data": data, "timestamp": time.time()})
        if len(app_state["log_items"]) > 200: app_state["log_items"].pop(0)
        app_state["last_update"] = time.time()
        
    @client.on(CommentEvent)
    async def on_comment(event: CommentEvent):
        print(f"[Komentar] {event.user.nickname}: {event.comment}")
        add_log("comment", {"user": event.user.nickname, "text": event.comment})
        prompt = f"Pengguna '{event.user.nickname}' berkomentar: '{event.comment}'"
        ai_response = get_blackbox_response(prompt)
        
        if ai_response: 
            print(f"🤖 Respon Blackbox: {ai_response}")
            add_log("ai_response", {"text": ai_response})
            speak_text(ai_response)
            
    @client.on(ConnectEvent)
    async def on_connect(_): app_state["tiktok_status"] = "Connected"; add_log("status", {"message": f"Berhasil terhubung ke @{client.unique_id}!"}); print(f"Berhasil terhubung ke @{client.unique_id}!")
    
    @client.on(DisconnectEvent)
    async def on_disconnect(_): app_state["tiktok_status"] = "Idle"; add_log("status", {"message": "Koneksi terputus."}); print("Koneksi TikTok terputus.")
    
    try:
        app_state["tiktok_status"] = "Connecting"; client.run()
    except Exception as e: app_state["tiktok_status"] = "Error"; add_log("status", {"message": f"Error koneksi: {e}"}); print(f"Error saat menjalankan TikTok client: {e}")

@app.route('/api/status')
def get_status(): return jsonify(app_state)
@app.route('/api/start', methods=['POST'])
def start_tiktok():
    if app_state["tiktok_status"] in ["Connecting", "Connected"]: return jsonify({"message": "Koneksi sudah berjalan."}), 400
    data = request.get_json(); username = data.get('username')
    if not username: return jsonify({"error": "Username tidak boleh kosong"}), 400
    threading.Thread(target=run_tiktok_client, args=(username,), daemon=True).start()
    return jsonify({"message": f"Mencoba terhubung ke @{username}..."})

if __name__ == '__main__':
    API_PORT = 5000
    HTTP_PORT = 8080
    http_server_thread = threading.Thread(target=run_http_server, args=(HTTP_PORT,), daemon=True)
    http_server_thread.start()
    local_ip = get_local_ip()
    print("="*50); print("🚀 SEMUA SERVER BERJALAN DARI SATU PERINTAH! 🚀"); print("="*50)
    print(f"✅ Server API Flask (otak AI) berjalan di port {API_PORT}.")
    print("\n--- CARA MENGAKSES HALAMAN HOST ---")
    print(f"Buka browser di PC ini dan kunjungi:")
    print(f"   http://localhost:{HTTP_PORT}/host.html")
    print(f"   atau")
    print(f"   http://{local_ip}:{HTTP_PORT}/host.html")
    print("\nBiarkan terminal ini tetap terbuka.")
    print("="*50)
    app.run(host='0.0.0.0', port=API_PORT, debug=False, use_reloader=False)