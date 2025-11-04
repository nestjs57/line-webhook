# app.py
from flask import Flask, request, jsonify
from google.cloud import firestore
from google.oauth2 import service_account
import os
import json
import requests
import traceback

app = Flask(__name__)

# ---------- Config ----------
credentials_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', '/etc/secrets/serviceAccountKey.json')
LINE_API_PROFILE_URL = "https://api.line.me/v2/bot/profile"
LINE_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')  # ต้องตั้งใน env

# ---------- Initialize Firestore ----------
db = None
credentials = None
try:
    credentials = service_account.Credentials.from_service_account_file(credentials_path)
    db = firestore.Client(credentials=credentials)
    print("✅ Firestore initialized successfully")
except Exception as e:
    print(f"❌ Failed to initialize Firestore: {e}")
    db = None

# ---------- Helper: fetch profile (supports user/group/room) ----------
def fetch_line_profile(source, user_id):
    """
    Return profile dict (may include displayName, pictureUrl) or None.
    Handles source types: user, group, room (uses appropriate endpoint).
    """
    if not LINE_ACCESS_TOKEN:
        print("⚠️ LINE_CHANNEL_ACCESS_TOKEN not set.")
        return None

    headers = {"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    try:
        src_type = source.get('type')  # 'user', 'group', 'room'
        if src_type == 'user':
            url = f"{LINE_API_PROFILE_URL}/{user_id}"
        elif src_type == 'group':
            group_id = source.get('groupId')
            if not group_id:
                print("⚠️ groupId missing in source")
                return None
            url = f"https://api.line.me/v2/bot/group/{group_id}/member/{user_id}"
        elif src_type == 'room':
            room_id = source.get('roomId')
            if not room_id:
                print("⚠️ roomId missing in source")
                return None
            url = f"https://api.line.me/v2/bot/room/{room_id}/member/{user_id}"
        else:
            print(f"⚠️ Unknown source type: {src_type}")
            return None

        resp = requests.get(url, headers=headers, timeout=6)
        print(f"🔍 Profile API: GET {url} -> {resp.status_code}")
        if resp.status_code == 200:
            profile = resp.json()
            print(f"🔎 profile: {profile}")
            return profile
        else:
            # Log response text for debugging (may be 404, 401, etc.)
            print(f"⚠️ Profile fetch failed: {resp.status_code} {resp.text}")
            return None
    except Exception as e:
        print(f"⚠️ Exception fetching profile: {e}")
        return None

# ---------- Health endpoint ----------
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'status': 'ok',
        'message': 'LINE Webhook is running!',
        'firestore_connected': db is not None
    })

# ---------- Webhook endpoint ----------
@app.route('/webhook', methods=['POST'])
def webhook():
    """
    รับ webhook events จาก LINE Messaging API
    - ดึง profile ของผู้ส่ง (displayName, pictureUrl) ถ้าเรียกได้
    - เพิ่ม fields display_name, display_picture ลงใน Firestore document
    """
    if db is None:
        return jsonify({'status': 'error', 'message': 'Firestore not connected'}), 500

    try:
        body = request.get_json()
        if not body:
            return jsonify({'status': 'error', 'message': 'No data'}), 400

        print(f"📥 Received webhook: {json.dumps(body, indent=2, ensure_ascii=False)}")

        events = body.get('events', [])

        for event in events:
            if event.get('type') != 'message':
                continue

            source = event.get('source', {})
            user_id = source.get('userId')
            if not user_id:
                print("⚠️ No userId in event.source, skipping")
                continue

            message = event.get('message', {})
            message_type = message.get('type')
            message_id = message.get('id')
            timestamp = event.get('timestamp')

            # --- Fetch profile (displayName, pictureUrl) ---
            display_name = None
            display_picture = None
            profile = fetch_line_profile(source, user_id)
            if profile:
                # typical profile fields: displayName, pictureUrl, statusMessage
                display_name = profile.get('displayName') or profile.get('display_name')
                display_picture = profile.get('pictureUrl') or profile.get('picture_url')
                if not display_name:
                    print("⚠️ displayName missing or null in profile response")
                if not display_picture:
                    print("⚠️ pictureUrl missing or null in profile response")
            else:
                print("⚠️ profile is None or fetch failed")

            # --- Build document to save ---
            data = {
                'user_id': user_id,
                'display_name': display_name,
                'display_picture': display_picture,
                'message_type': message_type,
                'message_id': message_id,
                'timestamp': timestamp,
                'created_at': firestore.SERVER_TIMESTAMP,
                'status': 'pending',
                'printed': False
            }

            if message_type == 'text':
                data['content'] = message.get('text')
                print(f"💬 Text: {data['content']}")
            elif message_type == 'image':
                data['content'] = f"image_{message_id}"
                print(f"🖼️ Image: {message_id}")
            elif message_type == 'video':
                data['content'] = f"video_{message_id}"
                print(f"🎥 Video: {message_id}")
            elif message_type == 'sticker':
                sticker_id = message.get('stickerId') or message.get('sticker_id')
                data['content'] = f"sticker_{sticker_id}"
                print("😀 Sticker")
            else:
                data['content'] = json.dumps(message, ensure_ascii=False)
                print(f"ℹ️ Other message type: {message_type}")

            # --- Save to Firestore ---
            try:
                doc_ref = db.collection('messages').add(data)
                try:
                    doc_id = doc_ref[1].id
                except Exception:
                    doc_id = str(doc_ref)
                print(f"✅ Saved message doc: {doc_id}")
            except Exception as e:
                print(f"❌ Failed to save to Firestore: {e}")
                traceback.print_exc()

        # Respond 200 to LINE
        return jsonify({'status': 'success'}), 200

    except Exception as e:
        print(f"❌ Error in /webhook: {e}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
