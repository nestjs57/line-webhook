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
# Path to service account json (or set env var in Render)
credentials_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', '/etc/secrets/serviceAccountKey.json')

# LINE API
LINE_API_PROFILE_URL = "https://api.line.me/v2/bot/profile"
LINE_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')  # set this in Render env

# ---------- Initialize Firestore ----------
db = None
try:
    credentials = service_account.Credentials.from_service_account_file(credentials_path)
    db = firestore.Client(credentials=credentials)
    print("✅ Firestore initialized successfully")
except Exception as e:
    print(f"❌ Failed to initialize Firestore: {e}")
    db = None

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
    - บันทึกข้อความลง Firestore
    - ดึง displayName โดยเรียก Profile API ของ LINE (ต้องมี LINE_CHANNEL_ACCESS_TOKEN)
    """
    # Ensure we always respond to LINE with 200 quickly when possible
    if db is None:
        return jsonify({'status': 'error', 'message': 'Firestore not connected'}), 500

    try:
        body = request.get_json()
        if not body:
            return jsonify({'status': 'error', 'message': 'No data'}), 400

        print(f"📥 Received webhook: {json.dumps(body, indent=2, ensure_ascii=False)}")

        events = body.get('events', [])

        for event in events:
            # Only process message events (you can expand to follow, join, postback, etc.)
            if event.get('type') != 'message':
                continue

            # Some events may not have source.userId (e.g., group if bot not allowed), guard it
            source = event.get('source', {})
            user_id = source.get('userId')
            if not user_id:
                print("⚠️ No userId in event.source, skipping")
                continue

            message = event.get('message', {})
            message_type = message.get('type')
            message_id = message.get('id')
            timestamp = event.get('timestamp')

            # Try to get displayName from LINE Profile API
            display_name = None
            if LINE_ACCESS_TOKEN:
                try:
                    headers = {
                        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
                    }
                    resp = requests.get(f"{LINE_API_PROFILE_URL}/{user_id}", headers=headers, timeout=5)
                    if resp.status_code == 200:
                        profile = resp.json()
                        display_name = profile.get('displayName')
                        # profile may also include pictureUrl, statusMessage
                        print(f"👤 DisplayName: {display_name}")
                    else:
                        print(f"⚠️ Failed to fetch profile ({resp.status_code}): {resp.text}")
                except Exception as e:
                    print(f"⚠️ Exception when fetching profile: {e}")
            else:
                print("⚠️ LINE_CHANNEL_ACCESS_TOKEN not set — skipping profile lookup")

            # Build document
            data = {
                'user_id': user_id,
                'display_name': display_name,
                'message_type': message_type,
                'message_id': message_id,
                'timestamp': timestamp,
                'created_at': firestore.SERVER_TIMESTAMP,
                'status': 'pending',
                'printed': False
            }

            # Add content depending on type
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
                # stickerId might be under message['stickerId'] or message['packageId']
                sticker_id = message.get('stickerId') or message.get('sticker_id')
                data['content'] = f"sticker_{sticker_id}"
                print("😀 Sticker")
            else:
                # For other types like audio, file, location, save raw message payload to content for inspection
                data['content'] = json.dumps(message, ensure_ascii=False)
                print(f"ℹ️ Other message type: {message_type}")

            # Save to Firestore
            try:
                doc_ref = db.collection('messages').add(data)
                # doc_ref is (write_result, document_reference) in google-cloud-firestore
                doc_id = None
                try:
                    doc_id = doc_ref[1].id
                except Exception:
                    # fallback if shape differs
                    doc_id = str(doc_ref)
                print(f"✅ Saved message doc: {doc_id}")
            except Exception as e:
                print(f"❌ Failed to save to Firestore: {e}")
                traceback.print_exc()

        # Important: respond 200 to LINE so it doesn't retry
        return jsonify({'status': 'success'}), 200

    except Exception as e:
        print(f"❌ Error in /webhook: {e}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    # In production (Render) use the default host 0.0.0.0
    app.run(host='0.0.0.0', port=port)
