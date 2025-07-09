# AI TikTok Live Host (Setup untuk Termux)

Proyek ini memungkinkan Anda menjalankan bot AI sebagai host live TikTok langsung dari ponsel Android menggunakan Termux. Bot akan membaca komentar secara real-time, mengirimkannya ke AI Blackbox untuk mendapatkan respons, dan kemudian mengucapkan respons tersebut menggunakan fitur Text-to-Speech (TTS) bawaan Android.

## Fitur

- **Host AI Interaktif**: Bot merespons komentar dari penonton secara otomatis.
- **Respons Cerdas**: Menggunakan API Blackbox.ai untuk menghasilkan respons yang relevan dan menghibur.
- **Text-to-Speech**: Menggunakan TTS asli Android melalui Termux:API, sehingga suara yang dihasilkan natural dan tidak memerlukan instalasi library yang rumit.
- **Panel Kontrol Berbasis Web**: Anda dapat mengontrol dan memantau live dari browser di ponsel Anda.
- **Instalasi Mudah**: Didesain khusus untuk berjalan di lingkungan Termux.

## Prasyarat

Sebelum memulai, pastikan Anda telah menginstal:
1.  **Aplikasi Termux**: Unduh dari [F-Droid](https://f-droid.org/en/packages/com.termux/). **Jangan gunakan versi Play Store karena sudah usang.**
2.  **Aplikasi Termux:API**: Unduh dari [F-Droid](https://f-droid.org/en/packages/com.termux.api/). Ini penting untuk fitur suara (TTS).
3.  **Koneksi Internet** yang stabil.
4.  **API Key dari Blackbox.ai**: Dapatkan secara gratis di [situs resmi Blackbox.ai](https://www.blackbox.ai/).

---

## ⚙️ Langkah-langkah Instalasi

Ikuti langkah-langkah ini dengan teliti di dalam aplikasi Termux.

### 1. Update Termux & Instal Paket Dasar

Buka Termux dan jalankan perintah berikut untuk memastikan semuanya terupdate dan menginstal paket yang dibutuhkan.

```bash
pkg update && pkg upgrade -y
pkg install python git termux-api -y
```

### 2. Siapkan Direktori Proyek

Buat folder untuk proyek ini dan masuk ke dalamnya.

```bash
mkdir ~/ai-tiktok
cd ~/ai-tiktok
```

### 3. Buat File-file Proyek

Anda perlu membuat 4 file di dalam direktori `~/ai-tiktok`:
1.  `server.py` (Backend & Logika AI)
2.  `host.html` (Panel Kontrol Web)
3.  `requirements.txt` (Daftar library Python)
4.  `.env` (Untuk menyimpan API Key Anda)

Gunakan editor teks seperti `nano` untuk membuat file-file ini. Contoh: `nano server.py`, tempelkan kode, lalu tekan `Ctrl+X`, `Y`, dan `Enter` untuk menyimpan.

#### **File: `server.py` (Versi Termux)**

**PENTING**: Kode server ini telah dimodifikasi untuk menggunakan `termux-tts-speak` alih-alih `gTTS` dan `playsound` yang sulit diinstal di Termux.

import os
import requests
from TikTokLive import TikTokLiveClient
from TikTokLive.events import CommentEvent, ConnectEvent, DisconnectEvent
import time
import asyncio
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
import threading
import socket
import http.server
import socketserver

# --- FUNGSI UNTUK MENDAPATKAN IP LOKAL ---
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

# --- FUNGSI UNTUK MENJALANKAN HTTP SERVER DI LATAR BELAKANG ---
def run_http_server(port=8080):
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"HTTP Server untuk file (host.html) berjalan di port {port}")
        httpd.serve_forever()

# --- FUNGSI TEXT-TO-SPEECH KHUSUS UNTUK TERMUX ---
def speak_text(text: str):
    try:
        # Menggunakan API TTS bawaan Termux. Jauh lebih stabil.
        print(f"🎙️  Berbicara (via Termux): {text}")
        # Membersihkan teks untuk shell command
        safe_text = text.replace("'", "'\\''")
        os.system(f"termux-tts-speak '{safe_text}'")
    except Exception as e:
        print(f"Error pada fungsi suara Termux: {e}")

# --- KONFIGURASI ---
load_dotenv()
app = Flask(__name__)
CORS(app)

# --- STATE APLIKASI ---
app_state = {
    "log_items": [],
    "tiktok_status": "Idle",
    "last_update": time.time()
}

# --- Logika AI & TikTok ---
BLACKBOX_API_KEY = os.environ.get("BLACKBOX_API_KEY")
if not BLACKBOX_API_KEY:
    print("Error: BLACKBOX_API_KEY tidak ditemukan di file .env")

BLACKBOX_API_URL = "https://api.blackbox.ai/chat/completions"

```bash
def get_blackbox_response(prompt: str) -> str:
    if not BLACKBOX_API_KEY:
        return ""

    system_prompt = "Anda adalah Jarvis, asisten AI yang kasar dan suka bicara kotor di TikTok. Jawablah dengan singkat (1-2 kalimat) dan sapa pengguna dengan nama mereka. Pastikan tidak membaca emoticon yang ditampilkan. pastikan anda juga menanggapi notifikasi di obrolan. Jika ada yang memberikan gift maka respon balik"

    headers = {
        "Authorization": f"Bearer {BLACKBOX_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-coder",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
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
        return ""
    except (KeyError, IndexError) as e:
        print(f"Error saat mengurai respons dari Blackbox: {e}")
        return ""

def run_tiktok_client(username: str):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client = TikTokLiveClient(unique_id=f"@{username}")

    def add_log(log_type, data):
        global app_state
        app_state["log_items"].append({"type": log_type, "data": data, "timestamp": time.time()})
        if len(app_state["log_items"]) > 200:
            app_state["log_items"].pop(0)
        app_state["last_update"] = time.time()

    @client.on(CommentEvent)
    async def on_comment(event: CommentEvent):
        print(f"[Komentar] {event.user.nickname}: {event.comment}")
        add_log("comment", {"user": event.user.nickname, "text": event.comment})
        prompt = f"Pengguna '{event.user.nickname}' berkomentar: '{event.comment}'"
        ai_response = get_blackbox_response(prompt)
        
        if ai_response:
            print(f"🤖 Respon AI: {ai_response}")
            add_log("ai_response", {"text": ai_response})
            speak_text(ai_response) # Panggil fungsi TTS Termux

    @client.on(ConnectEvent)
    async def on_connect(_):
        app_state["tiktok_status"] = "Connected"
        msg = f"Berhasil terhubung ke @{client.unique_id}!"
        add_log("status", {"message": msg})
        print(msg)

    @client.on(DisconnectEvent)
    async def on_disconnect(_):
        app_state["tiktok_status"] = "Idle"
        add_log("status", {"message": "Koneksi terputus."})
        print("Koneksi TikTok terputus.")
        
    try:
        app_state["tiktok_status"] = "Connecting"
        client.run()
    except Exception as e:
        app_state["tiktok_status"] = "Error"
        add_log("status", {"message": f"Error koneksi: {e}"})
        print(f"Error saat menjalankan TikTok client: {e}")

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
    threading.Thread(target=run_tiktok_client, args=(username,), daemon=True).start()
    return jsonify({"message": f"Mencoba terhubung ke @{username}..."})

if __name__ == '__main__':
    API_PORT = 5000
    HTTP_PORT = 8080
    
    # Jalankan server HTTP untuk host.html di thread terpisah
    http_server_thread = threading.Thread(target=run_http_server, args=(HTTP_PORT,), daemon=True)
    http_server_thread.start()
    
    local_ip = get_local_ip()
    
    print("="*50)
    print("🚀 AI TIKTOK HOST (VERSI TERMUX) SIAP! 🚀")
    print("="*50)
    print(f"✅ Server API (otak AI) berjalan di port {API_PORT}.")
    print("\n--- BUKA PANEL KONTROL DI BROWSER HP ANDA ---")
    print(f"   Alamat: http://localhost:{HTTP_PORT}/host.html")
    print("\nBiarkan jendela Termux ini tetap terbuka selama live.")
    print("="*50)
    
    # Jalankan server Flask
    app.run(host='0.0.0.0', port=API_PORT, debug=False, use_reloader=False)
```

#### **File: `host.html`**
(Salin kode HTML dari pertanyaan Anda, tidak ada perubahan yang diperlukan untuk file ini)

#### **File: `requirements.txt`**
Buat file ini dengan konten berikut. Perhatikan bahwa `gTTS` dan `playsound` telah dihapus.

```
requests
TikTokLive-API
python-dotenv
Flask
Flask-Cors
```

#### **File: `.env`**
Buat file ini dan masukkan API Key Anda.

```
BLACKBOX_API_KEY=MASUKKAN_API_KEY_ANDA_DI_SINI
```
Ganti `MASUKKAN_API_KEY_ANDA_DI_SINI` dengan kunci API yang Anda dapatkan dari Blackbox.ai.

### 4. Instal Library Python

Sekarang, instal semua library Python yang dibutuhkan dari file `requirements.txt`.

```bash
pip install -r requirements.txt
```

---

## ▶️ Cara Menjalankan

1.  Pastikan Anda berada di direktori `~/ai-tiktok`.
2.  Jalankan server dengan perintah:
    ```bash
    python server.py
    ```
3.  Anda akan melihat pesan bahwa server telah berjalan. Di sana akan tercetak alamat untuk panel kontrol.
4.  Buka browser di HP Anda (misalnya Chrome) dan kunjungi alamat berikut:
    ```
    http://localhost:8080/host.html
    ```
5.  Gunakan panel kontrol tersebut untuk memulai koneksi ke live TikTok Anda.
    - Masukkan ID Room unik (misal: `live-keren-123`) dan klik "Mulai Sebagai Host".
    - Masukkan `@username` TikTok Anda dan klik "Mulai Koneksi TikTok".
    - Bot AI sekarang akan aktif!

## 💡 Tips & Troubleshooting

- **Tidak ada suara?**
  - Pastikan Anda sudah menginstal aplikasi **Termux:API** dari F-Droid.
  - Jalankan `termux-tts-speak "halo tes"` di terminal Termux. Jika Anda mendengar suara, maka konfigurasinya sudah benar.
  - Periksa volume media di HP Anda.
- **Error saat instalasi `pip`?**
  - Coba jalankan `pip install --upgrade pip` lalu ulangi instalasi requirements.
- **Biarkan Termux Berjalan di Latar Belakang**:
  - Tahan notifikasi Termux, klik "Settings", dan nonaktifkan "Battery Optimization" untuk Termux agar tidak dimatikan oleh sistem Android. Anda juga bisa menjalankan `termux-wake-lock` di sesi Termux yang lain.