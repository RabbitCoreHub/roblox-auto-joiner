import os
import socket

def get_api_url():
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if render_url:
        return render_url.rstrip('/')

    api_url = os.getenv("API_URL")
    if api_url:
        return api_url.rstrip('/')

    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)

        if os.getenv("REPLIT_DOMAINS"):
            domains = os.getenv("REPLIT_DOMAINS", "").split(',')
            if domains and domains[0]:
                return f"https://{domains[0]}"

        if local_ip.startswith("127.") or local_ip.startswith("192.168.") or local_ip.startswith("10."):
            return "http://localhost:5000"

    except Exception:
        pass

    return "http://localhost:5000"

API_URL = get_api_url()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
DISCORD_RECONNECT_DELAY = 5

MONITORED_CHANNELS = [
    "1266358579934269463",
    "1266358579934269464",
    "1422270976632160316",
]

LOG_RAW_MESSAGES = True
LOG_PARSED_DATA = True
LOG_FILTER_RESULTS = True

PAUSE_HOTKEY = 'f9'

NAME_PATTERNS = ['Name', 'Server Name', 'name']
MONEY_PATTERNS_LABELS = ['Money', 'Money per sec', 'Income', 'money']
PLAYERS_PATTERNS = ['Players', 'players']
JOB_ID_PATTERNS = ['Job ID', 'JobID', 'job_id']
SCRIPT_PATTERNS = ['Script', 'Join Script', 'script']
JOIN_LINK_PATTERNS = ['Join Link', 'Link', 'join_link']

MONEY_PATTERNS = [
    r'(\d+(?:\.\d+)?)\s*M',
    r'(\d+(?:\.\d+)?)\s*K',
    r'(\d+(?:\.\d+)?)\s*B'
]

ICE_HUB_FILTER = {
    'enabled': True,
    'require_job_id': True,
    'min_players': 1,
    'max_players': 18,
    'ignore_zero_income': True
}

MONEY_THRESHOLD = {
    'min': 0.0,
    'max': 999999.0
}

PLAYER_THRESHOLD = 18

IGNORE_UNKNOWN = False
IGNORE_LIST = []

FILTER_BY_NAME = {
    'enabled': False,
    'allowed_names': []
}

BYPASS_10M = True

WEBSOCKET_HOST = '0.0.0.0'
WEBSOCKET_PORT = 8765
WEBSOCKET_RECONNECT_DELAY = 5

print(f"🔗 API URL: {API_URL}")
