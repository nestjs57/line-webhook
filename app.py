# inside your webhook loop, replace profile fetch with this function
import requests

def fetch_line_profile(source, user_id):
    """
    source: the event['source'] dict
    user_id: string
    returns: dict (profile) or None
    """
    if not LINE_ACCESS_TOKEN:
        print("⚠️ LINE_CHANNEL_ACCESS_TOKEN not set.")
        return None

    headers = {"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    try:
        src_type = source.get('type')  # 'user', 'group', or 'room'
        if src_type == 'user':
            url = f"https://api.line.me/v2/bot/profile/{user_id}"
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
            # log body for debugging (may contain explanation)
            print(f"⚠️ Profile fetch failed: {resp.status_code} {resp.text}")
            return None

    except Exception as e:
        print(f"⚠️ Exception fetching profile: {e}")
        return None
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
