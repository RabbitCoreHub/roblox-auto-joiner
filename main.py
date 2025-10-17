from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import threading
import time
from datetime import datetime
from collections import deque
import os

try:
    from discord_bot_http import start_discord_bot_background, discord_stats
    DISCORD_BOT_AVAILABLE = True
except Exception as e:
    print(f"⚠️ Discord bot not available: {e}")
    DISCORD_BOT_AVAILABLE = False
    discord_stats = {
        'servers_processed': 0,
        'servers_sent': 0,
        'servers_filtered': 0,
        'unique_servers': set(),
        'last_server': None,
        'bot_connected': False,
        'bot_status': 'Not Available'
    }

app = Flask(__name__)
CORS(app)

server_queue = deque(maxlen=100)
ping_logs = deque(maxlen=50)
websocket_clients = 0

@app.route('/')
def index():
    return send_file('index.html')

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({
        'status': 'online',
        'queue_size': len(server_queue),
        'websocket_clients': websocket_clients,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/server/push', methods=['POST'])
def push_server():
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        server_data = {
            'name': data.get('name'),
            'money': data.get('money'),
            'players': data.get('players'),
            'job_id': data.get('job_id'),
            'script': data.get('script'),
            'join_link': data.get('join_link'),
            'is_10m_plus': data.get('is_10m_plus', False),
            'timestamp': datetime.now().isoformat()
        }
        
        server_queue.append(server_data)
        
        return jsonify({
            'success': True,
            'message': 'Server added to queue',
            'queue_size': len(server_queue)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/server/pull', methods=['GET'])
def pull_server():
    try:
        if len(server_queue) == 0:
            return jsonify({'status': 'success', 'data': None, 'queue_size': 0})
        
        server_data = server_queue.popleft()
        
        return jsonify({
            'status': 'success',
            'data': server_data,
            'queue_size': len(server_queue)
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/ping', methods=['POST'])
def ping():
    try:
        data = request.json or {}
        ping_entry = {
            'source': data.get('source', 'unknown'),
            'timestamp': datetime.now().isoformat()
        }
        ping_logs.append(ping_entry)
        
        return jsonify({
            'success': True,
            'message': 'Pong',
            'timestamp': ping_entry['timestamp']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/logs', methods=['GET'])
def get_logs():
    return jsonify({
        'logs': list(ping_logs),
        'count': len(ping_logs)
    })

@app.route('/api/discord/stats', methods=['GET'])
def get_discord_stats():
    try:
        stats_copy = discord_stats.copy()
        stats_copy['unique_servers'] = len(discord_stats['unique_servers'])
        return jsonify({
            'success': True,
            'stats': stats_copy
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/discord/queue', methods=['GET'])
def get_discord_queue():
    try:
        queue_list = list(server_queue)
        current_time = datetime.now()
        
        for server in queue_list:
            if 'timestamp' in server:
                server_time = datetime.fromisoformat(server['timestamp'])
                age_seconds = (current_time - server_time).total_seconds()
                server['age_seconds'] = age_seconds
                server['time_remaining'] = max(0, 10 - age_seconds)
        
        return jsonify({
            'success': True,
            'queue': queue_list,
            'total': len(queue_list)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def cleanup_old_servers():
    while True:
        try:
            time.sleep(10)
            current_time = datetime.now()
            
            cleaned_count = 0
            for _ in range(len(server_queue)):
                if len(server_queue) == 0:
                    break
                    
                server = server_queue[0]
                server_time = datetime.fromisoformat(server['timestamp'])
                age = (current_time - server_time).total_seconds()
                
                if age > 10:
                    server_queue.popleft()
                    cleaned_count += 1
                else:
                    break
            
            if cleaned_count > 0:
                print(f"🧹 Cleaned {cleaned_count} old servers from queue")
        except Exception as e:
            print(f"Error in cleanup thread: {e}")

cleanup_thread = threading.Thread(target=cleanup_old_servers, daemon=True)
cleanup_thread.start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Starting Flask server on 0.0.0.0:{port}")
    print(f"🔗 API URL: {os.environ.get('RENDER_EXTERNAL_URL', f'http://localhost:{port}')}")
    
    websocket_server_thread = None
    try:
        from websocket_server import start_websocket_server
        websocket_server_thread = threading.Thread(target=start_websocket_server, daemon=True)
        websocket_server_thread.start()
        print("✅ WebSocket server started on port 8765")
    except Exception as e:
        print(f"⚠️ WebSocket server not started: {e}")
    
    discord_bot_thread = None
    if DISCORD_BOT_AVAILABLE and os.environ.get('DISCORD_TOKEN'):
        try:
            discord_bot_thread = threading.Thread(target=start_discord_bot_background, daemon=True)
            discord_bot_thread.start()
            print("✅ Discord bot started in background")
        except Exception as e:
            print(f"⚠️ Discord bot not started: {e}")
    else:
        if not os.environ.get('DISCORD_TOKEN'):
            print("⚠️ DISCORD_TOKEN not found in environment variables")
        print("ℹ️ Discord bot monitoring disabled")
    
    app.run(host='0.0.0.0', port=port, debug=False)
