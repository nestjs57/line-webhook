from flask import Flask, request, jsonify
from google.cloud import firestore
from google.oauth2 import service_account
import os
import json

app = Flask(__name__)

# Initialize Firestore with credentials
credentials_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', '/etc/secrets/serviceAccountKey.json')

try:
    credentials = service_account.Credentials.from_service_account_file(credentials_path)
    db = firestore.Client(credentials=credentials)
    print("✅ Firestore initialized successfully")
except Exception as e:
    print(f"❌ Failed to initialize Firestore: {e}")
    db = None

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'status': 'ok', 
        'message': 'LINE Webhook is running!',
        'firestore_connected': db is not None
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """รับ webhook จาก LINE"""
    
    if db is None:
        return jsonify({'status': 'error', 'message': 'Firestore not connected'}), 500
    
    try:
        body = request.get_json()
        
        if not body:
            return jsonify({'status': 'error', 'message': 'No data'}), 400
        
        print(f"📥 Received: {json.dumps(body, indent=2)}")
        
        events = body.get('events', [])
        
        for event in events:
            if event.get('type') == 'message':
                user_id = event['source']['userId']
                message_type = event['message']['type']
                timestamp = event['timestamp']
                message_id = event['message']['id']
                
                data = {
                    'user_id': user_id,
                    'message_type': message_type,
                    'message_id': message_id,
                    'timestamp': timestamp,
                    'created_at': firestore.SERVER_TIMESTAMP,
                    'status': 'pending',
                    'printed': False
                }
                
                if message_type == 'text':
                    data['content'] = event['message']['text']
                    print(f"💬 Text: {data['content']}")
                    
                elif message_type == 'image':
                    data['content'] = f"image_{message_id}"
                    print(f"🖼️ Image: {message_id}")
                    
                elif message_type == 'video':
                    data['content'] = f"video_{message_id}"
                    print(f"🎥 Video: {message_id}")
                    
                elif message_type == 'sticker':
                    data['content'] = f"sticker_{event['message']['stickerId']}"
                    print(f"😀 Sticker")
                
                doc_ref = db.collection('messages').add(data)
                print(f"✅ Saved: {doc_ref[1].id}")
        
        return jsonify({'status': 'success'}), 200
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
