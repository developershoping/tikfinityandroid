# server.py - Complete Fixed Version
import os
import time
import asyncio
import re
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
import threading
import socket
import http.server
import socketserver
from TikTokLive import TikTokLiveClient
from TikTokLive.events import (
    CommentEvent, GiftEvent, JoinEvent, ConnectEvent,
    DisconnectEvent, LikeEvent, ShareEvent, FollowEvent,
    SubscribeEvent, QuestionNewEvent, PollEvent, LiveEndEvent
)

# Helper Functions
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

def run_http_server(port=8000):
    os.chdir(os.path.dirname(os.path.abspath(__file__)) or '.')
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"HTTP Server running on port {port}")
        httpd.serve_forever()

# App Configuration
app = Flask(__name__)
CORS(app)
app_state = {
    "log_items": [],
    "tiktok_status": "Idle",
    "last_update": time.time(),
    "host_nickname": "Host",
    "settings": {
        "tts_enabled": True,
        "read_comments": True,
        "read_joins": True,
        "read_follows": True,
        "read_gifts": True,
        "read_shares": True,
        "read_subscribes": True,
        "read_questions": True,
        "read_polls": True,
        "filter_commands": True,
        "filter_host": True,
        "reminder_interval": 20,  # minutes
        "min_gift_value": 0,      # minimum gift diamonds
        "blacklist": [],
        "whitelist": []
    }
}

# TikTok Client Logic
def run_tiktok_client(username: str):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client = TikTokLiveClient(unique_id=f"@{username}")

    liked_users = set()
    shared_users = set()
    reminder_task = None
    last_gift_time = time.time()

    def add_log(log_type, data):
        timestamp = datetime.now().strftime("%H:%M:%S")
        if len(app_state["log_items"]) > 500:
            app_state["log_items"].pop(0)
        app_state["log_items"].append({
            "type": log_type,
            "data": data,
            "timestamp": timestamp,
            "datetime": time.time()
        })
        app_state["last_update"] = time.time()
    
    def add_tts_message(text_to_speak, priority=False):
        if not app_state["settings"]["tts_enabled"]:
            return
        print(f"🎤 TTS: '{text_to_speak}'")
        add_log("tts", {"text": text_to_speak, "priority": priority})

    async def timed_reminder_task():
        while True:
            await asyncio.sleep(app_state["settings"]["reminder_interval"] * 60)
            if time.time() - last_gift_time > 300:  # Only remind if no gifts in 5 mins
                add_tts_message(
                    f"Sudah {app_state['settings']['reminder_interval']} menit berlalu, "
                    f"ada yang mau kasih hadiah untuk {app_state['host_nickname']}?",
                    True
                )

    @client.on(ConnectEvent)
    async def on_connect(_: ConnectEvent):
        nonlocal reminder_task
        app_state["tiktok_status"] = "Connected"
        try:
            app_state["host_nickname"] = client.room_info.get('owner', {}).get('nickname', "Host")
        except Exception as e:
            print(f"⚠️ Failed to get host nickname: {e}")
            app_state["host_nickname"] = "Host"
        
        message = f"Connected to @{client.unique_id}!"
        add_log("status", {"message": message})
        add_tts_message(f"Notifikasi live {app_state['host_nickname']} siap dibacakan!", True)
        
        if reminder_task is None:
            reminder_task = asyncio.create_task(timed_reminder_task())
            print(f"✅ Reminder task started ({app_state['settings']['reminder_interval']} mins)")

    @client.on(DisconnectEvent)
    async def on_disconnect(_: DisconnectEvent):
        nonlocal reminder_task
        app_state["tiktok_status"] = "Idle"
        add_log("status", {"message": "Disconnected"})
        add_tts_message("Koneksi terputus", True)
        if reminder_task:
            reminder_task.cancel()
            reminder_task = None
            print("❌ Reminder task stopped")

    @client.on(GiftEvent)
    async def on_gift(event: GiftEvent):
        try:
            user_name = event.user.nickname
            gift_name = getattr(event.gift.info, 'name', 'Hadiah')
            gift_count = getattr(event.gift, 'count', 1)
            gift_value = getattr(event.gift.info, 'diamond_count', 0) * gift_count

            if gift_value < app_state["settings"]["min_gift_value"]:
                return

            print(f"[Gift] {user_name} -> {gift_count}x {gift_name} (Value: {gift_value})")
            add_log("gift", {
                "user": user_name,
                "gift_name": gift_name,
                "count": gift_count,
                "value": gift_value
            })

            global last_gift_time
            last_gift_time = time.time()
            
            if app_state["settings"]["read_gifts"]:
                tts_message = (f"{user_name} memberikan {gift_name} sebanyak {gift_count}" 
                              if gift_count > 1 
                              else f"{user_name} memberikan {gift_name}")
                add_tts_message(tts_message, True)
        except Exception as e:
            print(f"❌ [Gift Error]: {str(e)}")
            print(f"Gift Data: {vars(event)}")

    @client.on(CommentEvent)
    async def on_comment(event: CommentEvent):
        try:
            user_name = event.user.nickname
            comment_text = event.comment
            
            # Check blacklist
            if user_name.lower() in [x.lower() for x in app_state["settings"]["blacklist"]]:
                return
                
            # Check whitelist (if not empty)
            if (app_state["settings"]["whitelist"] and 
                user_name.lower() not in [x.lower() for x in app_state["settings"]["whitelist"]]):
                return
                
            print(f"[Comment] {user_name}: {comment_text}")
            add_log("comment", {
                "user": user_name,
                "text": comment_text
            })
            
            # Skip commands if filtering enabled
            if (app_state["settings"]["filter_commands"] and 
                re.match(r'^[!/]', comment_text)):
                return
                
            if app_state["settings"]["read_comments"]:
                add_tts_message(f"Pesan dari {user_name}, {comment_text}")
        except Exception as e:
            print(f"❌ [Comment Error]: {e}")

    @client.on(JoinEvent)
    async def on_join(event: JoinEvent):
        try:
            user_name = event.user.nickname
            
            # Skip host if filtering enabled
            if (app_state["settings"]["filter_host"] and 
                user_name.lower() == app_state["host_nickname"].lower()):
                return
                
            print(f"[Join] {user_name}")
            add_log("join", {"user": user_name})
            
            if app_state["settings"]["read_joins"]:
                add_tts_message(f"Selamat datang, {user_name}")
        except Exception as e:
            print(f"❌ [Join Error]: {e}")

    @client.on(FollowEvent)
    async def on_follow(event: FollowEvent):
        try:
            user_name = event.user.nickname
            print(f"[Follow] {user_name}")
            add_log("follow", {"user": user_name})
            
            if app_state["settings"]["read_follows"]:
                add_tts_message(f"Terima kasih sudah follow, {user_name}")
        except Exception as e:
            print(f"❌ [Follow Error]: {e}")

    @client.on(ShareEvent)
    async def on_share(event: ShareEvent):
        try:
            if event.user.unique_id in shared_users:
                return
            shared_users.add(event.user.unique_id)
            user_name = event.user.nickname
            print(f"[Share] {user_name}")
            add_log("share", {"user": user_name})
            
            if app_state["settings"]["read_shares"]:
                add_tts_message(f"Terima kasih {user_name} sudah membagikan live ini")
        except Exception as e:
            print(f"❌ [Share Error]: {e}")

    @client.on(LikeEvent)
    async def on_like(event: LikeEvent):
        try:
            if event.user.unique_id in liked_users:
                return
            liked_users.add(event.user.unique_id)
            print(f"[Like] {event.user.nickname}")
            add_log("like", {"user": event.user.nickname})
        except Exception as e:
            print(f"❌ [Like Error]: {e}")

    @client.on(SubscribeEvent)
    async def on_subscribe(event: SubscribeEvent):
        try:
            user_name = event.user.nickname
            print(f"[Subscribe] {user_name} subscribed!")
            add_log("subscribe", {"user": user_name})
            
            if app_state["settings"]["read_subscribes"]:
                add_tts_message(f"Luar biasa! {user_name} baru saja berlangganan! Terima kasih banyak!", True)
        except Exception as e:
            print(f"❌ [Subscribe Error]: {e}")

    @client.on(QuestionNewEvent)
    async def on_question(event: QuestionNewEvent):
        try:
            user_name = event.user.nickname
            question_text = event.question.text
            print(f"[Question] {user_name}: {question_text}")
            add_log("question", {
                "user": user_name,
                "text": question_text
            })
            
            if app_state["settings"]["read_questions"]:
                add_tts_message(f"{user_name} bertanya, {question_text}")
        except Exception as e:
            print(f"❌ [Question Error]: {e}")

    @client.on(PollEvent)
    async def on_poll(event: PollEvent):
        try:
            poll_options = ", ".join([option.title for option in event.poll.options])
            print(f"[Poll] Options: {poll_options}")
            add_log("poll", {"options": poll_options})
            
            if app_state["settings"]["read_polls"]:
                add_tts_message(f"Polling baru. Pilihannya: {poll_options}")
        except Exception as e:
            print(f"❌ [Poll Error]: {e}")

    @client.on(LiveEndEvent)
    async def on_live_end(event: LiveEndEvent):
        try:
            print("[Live End]")
            add_log("live_end", {"message": "Live ended"})
            add_tts_message("Siaran langsung telah berakhir. Terima kasih semuanya.", True)
        except Exception as e:
            print(f"❌ [LiveEnd Error]: {e}")

    try:
        app_state["tiktok_status"] = "Connecting"
        client.run()
    except Exception as e:
        app_state["tiktok_status"] = "Error"
        add_log("status", {"message": f"Connection error: {e}"})
        print(f"❌ Client Error: {e}")

# API Endpoints
@app.route('/api/status')
def get_status():
    return jsonify(app_state)

@app.route('/api/start', methods=['POST'])
def start_tiktok():
    if app_state["tiktok_status"] in ["Connecting", "Connected"]:
        return jsonify({"message": "Already connected"}), 400
    
    data = request.get_json()
    username = data.get('username')
    
    if not username:
        return jsonify({"error": "Username required"}), 400
    
    threading.Thread(target=run_tiktok_client, args=(username,), daemon=True).start()
    return jsonify({"message": f"Connecting to @{username}..."})

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    if request.method == 'POST':
        new_settings = request.get_json()
        for key in new_settings:
            if key in app_state["settings"]:
                app_state["settings"][key] = new_settings[key]
        return jsonify({"message": "Settings updated"})
    return jsonify(app_state["settings"])

@app.route('/api/blacklist', methods=['GET', 'POST', 'DELETE'])
def handle_blacklist():
    if request.method == 'POST':
        username = request.get_json().get('username')
        if username and username not in app_state["settings"]["blacklist"]:
            app_state["settings"]["blacklist"].append(username)
    elif request.method == 'DELETE':
        username = request.args.get('username')
        if username in app_state["settings"]["blacklist"]:
            app_state["settings"]["blacklist"].remove(username)
    return jsonify(app_state["settings"]["blacklist"])

@app.route('/api/whitelist', methods=['GET', 'POST', 'DELETE'])
def handle_whitelist():
    if request.method == 'POST':
        username = request.get_json().get('username')
        if username and username not in app_state["settings"]["whitelist"]:
            app_state["settings"]["whitelist"].append(username)
    elif request.method == 'DELETE':
        username = request.args.get('username')
        if username in app_state["settings"]["whitelist"]:
            app_state["settings"]["whitelist"].remove(username)
    return jsonify(app_state["settings"]["whitelist"])

# Main Execution
if __name__ == '__main__':
    API_PORT = 5000
    HTTP_PORT = 8000
    
    # Start HTTP server for static files
    http_server_thread = threading.Thread(
        target=run_http_server,
        args=(HTTP_PORT,),
        daemon=True
    )
    http_server_thread.start()
    
    local_ip = get_local_ip()
    
    print("="*50)
    print("🚀 TIKTOK LIVE NOTIFICATION READER 🚀")
    print("="*50)
    print(f"✅ API Server: http://{local_ip}:{API_PORT}")
    print(f"✅ Web Interface: http://{local_ip}:{HTTP_PORT}/host.html")
    print("\n⚠️ Remember to enable TTS in the host page")
    print("="*50)
    
    app.run(host='0.0.0.0', port=API_PORT, debug=False, use_reloader=False)
