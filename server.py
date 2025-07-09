import os
import time
import asyncio
import threading
import socket
import http.server
import socketserver
import uuid # Untuk membuat nama file unik
from flask import Flask, jsonify, request
from flask_cors import CORS
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent, CommentEvent, JoinEvent, GiftEvent

# --- LIBRARY BARU UNTUK TTS ---
from gtts import gTTS
from playsound import playsound

# --- FUNGSI UTILITAS ---
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def run_http_server(port=8080):
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"HTTP Server untuk file (host.html) berjalan di port {port}")
        httpd.serve_forever()
        
# --- FUNGSI BARU UNTUK TEXT-TO-SPEECH (TTS) ---
def speak_text(text: str):
    """
    Mengubah teks menjadi suara menggunakan gTTS dan memutarnya.
    Audio akan diputar langsung dari speaker sistem.
    """
    try:
        print(f"🎙️  Mensintesis suara untuk: '{text}'")
        tts = gTTS(text=text, lang='id', slow=False)
        
        # Buat folder temp jika belum ada
        if not os.path.exists("temp_audio"):
            os.makedirs("temp_audio")
            
        # Buat nama file unik dan simpan
        filename = os.path.join("temp_audio", f"speech_{uuid.uuid4()}.mp3")
        tts.save(filename)
        
        print(f"🔊 Memutar audio...")
        playsound(filename)
        
        # Hapus file setelah selesai diputar
        os.remove(filename)
        
    except Exception as e:
        # Jika TTS gagal, program tetap berjalan, hanya menampilkan error
        print(f"❌ Error pada fungsi suara: {e}")


# --- KONFIGURASI APLIKASI FLASK ---
app = Flask(__name__)
CORS(app)

# --- STATE APLIKASI (GLOBAL) ---
app_state = {"log_items": [], "tiktok_status": "Idle"}
reminder_thread_stop_event = None
reminder_thread = None

# --- LOGIKA BOT TIKTOK ---
def add_log(log_type: str, data: dict):
    global app_state
    log_entry = {"type": log_type, "data": data, "timestamp": time.time()}
    app_state["log_items"].append(log_entry)
    if len(app_state["log_items"]) > 200:
        app_state["log_items"].pop(0)
    print(f"LOG [{log_type.upper()}]: {data.get('text') or data.get('message') or data}")

def reminder_loop(stop_event: threading.Event):
    reminders = [
        "Teman-teman, jangan lupa tap-tap layarnya ya, biar makin semangat!",
        "Ayo bantu tap-tap layar biar live kita makin rame!",
        "Buat yang baru gabung, jangan lupa follow ya. Terima kasih!"
    ]
    time.sleep(300)
    idx = 0
    while not stop_event.is_set():
        message = reminders[idx % len(reminders)]
        add_log("reminder", {"text": message})
        speak_text(message) # PANGGIL FUNGSI SUARA
        idx += 1
        stop_event.wait(300)

def run_tiktok_client(username: str):
    global reminder_thread, reminder_thread_stop_event
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client = TikTokLiveClient(unique_id=f"@{username}")

    @client.on(ConnectEvent)
    async def on_connect(_: ConnectEvent):
        global reminder_thread, reminder_thread_stop_event
        app_state["tiktok_status"] = "Connected"
        message = f"Berhasil terhubung ke siaran langsung @{client.unique_id}!"
        add_log("status", {"message": message})
        if reminder_thread is None or not reminder_thread.is_alive():
            reminder_thread_stop_event = threading.Event()
            reminder_thread = threading.Thread(target=reminder_loop, args=(reminder_thread_stop_event,), daemon=True)
            reminder_thread.start()
            print("Thread pengingat dimulai.")

    @client.on(DisconnectEvent)
    async def on_disconnect(_: DisconnectEvent):
        # ... (Tidak ada perubahan di sini) ...
        global reminder_thread_stop_event
        app_state["tiktok_status"] = "Idle"
        add_log("status", {"message": "Koneksi ke siaran langsung terputus."})
        if reminder_thread_stop_event:
            reminder_thread_stop_event.set()
            print("Thread pengingat dihentikan.")

    @client.on(JoinEvent)
    async def on_join(event: JoinEvent):
        message = f"Halo {event.user.nickname}, selamat datang anjing! Semoga betah ya."
        add_log("greeting", {"text": message})
        speak_text(message) # PANGGIL FUNGSI SUARA

    @client.on(GiftEvent)
    async def on_gift(event: GiftEvent):
        message = ""
        if event.gift.streakable and event.gift.repeat_end:
            message = f"Terima kasih banyak {event.user.nickname} untuk {event.gift.repeat_count} buah {event.gift.info.name}-nya! Luar biasa!"
        elif not event.gift.streakable:
            message = f"Wow! Terima kasih banyak {event.user.nickname} untuk gift {event.gift.info.name}-nya! Keren banget!"
        if message:
            add_log("gift", {"text": message})
            speak_text(message) # PANGGIL FUNGSI SUARA

    @client.on(CommentEvent)
    async def on_comment(event: CommentEvent):
        add_log("comment", {"user": event.user.nickname, "text": event.comment})

    try:
        app_state["tiktok_status"] = "Connecting"
        add_log("status", {"message": f"Mencoba terhubung ke @{username}..."})
        client.run()
    except Exception as e:
        app_state["tiktok_status"] = "Error"
        add_log("status", {"message": f"Gagal terhubung: {e}"})

# --- ENDPOINT API FLASK & MAIN EXECUTION ---
# ... (Tidak ada perubahan dari sini ke bawah) ...
@app.route('/api/status')
def get_status():
    return jsonify(app_state)

@app.route('/api/start', methods=['POST'])
def start_tiktok():
    if app_state["tiktok_status"] in ["Connecting", "Connected"]:
        return jsonify({"message": "Koneksi sudah berjalan."}), 400
    data = request.get_json()
    username = data.get('username')
    if not username:
        return jsonify({"error": "Username tidak boleh kosong"}), 400
    username = username.lstrip('@')
    threading.Thread(target=run_tiktok_client, args=(username,), daemon=True).start()
    return jsonify({"message": f"Permintaan koneksi ke @{username} diterima."})

if __name__ == '__main__':
    API_PORT = 5000; HTTP_PORT = 8080
    http_server_thread = threading.Thread(target=run_http_server, args=(HTTP_PORT,), daemon=True)
    http_server_thread.start()
    local_ip = get_local_ip()
    print("=" * 50); print("🚀 TIKTOK BOT SERVER SIAP! (TTS di Sisi Server) 🚀"); print("=" * 50)
    print(f"✅ Server API berjalan di port {API_PORT}."); print("\n--- CARA MENGAKSES HALAMAN KONTROL ---")
    print(f"Buka browser (Chrome/Edge) dan kunjungi:"); print(f"   http://localhost:{HTTP_PORT}/host.html"); print("\nBiarkan terminal ini tetap terbuka. Suara akan keluar dari PC ini.")
    print("=" * 50)
    app.run(host='0.0.0.0', port=API_PORT, debug=False, use_reloader=False)