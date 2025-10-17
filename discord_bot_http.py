import asyncio
import json
import re
import websockets
import logging
import time
import requests
import os
from datetime import datetime
from collections import deque
try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except:
    KEYBOARD_AVAILABLE = False
from colorama import Fore, Back, Style, init
from typing import Optional

from config import *

discord_stats = {
    'servers_processed': 0,
    'servers_sent': 0,
    'servers_filtered': 0,
    'unique_servers': set(),
    'last_server': None,
    'bot_connected': False,
    'bot_status': 'Disconnected'
}

class DiscordMonitor:

    def __init__(self, api_url):
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.heartbeat_interval = None
        self.last_sequence = None
        self.session_id = None
        self.paused = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 50
        self.api_url = api_url

        logging.basicConfig(level=logging.INFO,
                            format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)

    def log(self, message, color=Fore.WHITE):
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"[{timestamp}] {color}{message}{Style.RESET_ALL}")

    async def connect_discord(self):
        gateway_url = "wss://gateway.discord.gg/?v=10&encoding=json"

        while not self.paused:
            try:
                self.log("Connecting to Discord Gateway...", Fore.YELLOW)

                async with websockets.connect(gateway_url,
                                              ping_interval=None,
                                              close_timeout=5) as websocket:
                    self.websocket = websocket
                    self.reconnect_attempts = 0
                    await self.authenticate()

                    heartbeat_task = asyncio.create_task(self.heartbeat())

                    try:
                        async for message in websocket:
                            await self.handle_message(message)
                    except websockets.exceptions.ConnectionClosed:
                        self.log("Discord connection closed, reconnecting...",
                                 Fore.RED)
                    except Exception as e:
                        self.log(f"Discord connection error: {e}", Fore.RED)
                    finally:
                        heartbeat_task.cancel()
                        if not self.paused:
                            await self.handle_discord_reconnect()

            except Exception as e:
                self.log(f"Discord connection error: {e}", Fore.RED)
                if not self.paused:
                    await self.handle_discord_reconnect()

    async def handle_discord_reconnect(self):
        if self.paused:
            return

        self.reconnect_attempts += 1

        if self.reconnect_attempts > self.max_reconnect_attempts:
            self.log(
                f"Max reconnection attempts ({self.max_reconnect_attempts}) reached for Discord",
                Fore.RED)
            self.log("Restart the application to reconnect", Fore.YELLOW)
            return

        delay = min(
            DISCORD_RECONNECT_DELAY * (2**(self.reconnect_attempts - 1)), 300)

        self.log(
            f"Reconnecting to Discord in {delay} seconds... (Attempt {self.reconnect_attempts}/{self.max_reconnect_attempts})",
            Fore.YELLOW)
        await asyncio.sleep(delay)

    async def authenticate(self):
        payload = {
            "op": 2,
            "d": {
                "token": DISCORD_TOKEN,
                "intents": 33280,
                "properties": {
                    "$os": "linux",
                    "$browser": "discord.py",
                    "$device": "discord.py"
                }
            }
        }
        if self.websocket:
            await self.websocket.send(json.dumps(payload))
            self.log("Authentication sent to Discord", Fore.GREEN)

    async def heartbeat(self):
        while True:
            if self.heartbeat_interval:
                await asyncio.sleep(self.heartbeat_interval / 1000)
                heartbeat_payload = {"op": 1, "d": self.last_sequence}
                if self.websocket:
                    await self.websocket.send(json.dumps(heartbeat_payload))
            else:
                await asyncio.sleep(1)

    async def handle_message(self, message_raw):
        try:
            message = json.loads(message_raw)

            if message['op'] == 10:
                self.heartbeat_interval = message['d']['heartbeat_interval']

            elif message['op'] == 0 and message['t'] == 'READY':
                self.session_id = message['d']['session_id']
                self.log("Discord Ready! Session established", Fore.GREEN)
                discord_stats['bot_connected'] = True
                discord_stats['bot_status'] = 'Connected'

            elif message['op'] == 0 and message['t'] == 'MESSAGE_CREATE':
                await self.process_discord_message(message['d'])

        except json.JSONDecodeError:
            self.log("Failed to parse Discord message", Fore.RED)

    async def display_full_message_json(self, message_data):
        """Display complete JSON structure of Discord message"""
        self.log("━" * 80, Fore.MAGENTA)
        self.log("📨 FULL MESSAGE DATA (JSON):", Fore.MAGENTA + Style.BRIGHT)
        self.log("━" * 80, Fore.MAGENTA)
        
        try:
            formatted_json = json.dumps(message_data, indent=2, ensure_ascii=False)
            for line in formatted_json.split('\n'):
                self.log(f"  {line}", Fore.WHITE)
        except Exception as e:
            self.log(f"Error formatting JSON: {e}", Fore.RED)
        
        self.log("━" * 80, Fore.MAGENTA)

    async def process_discord_message(self, message_data):
        if self.paused:
            return

        channel_id = message_data.get('channel_id')
        if channel_id not in MONITORED_CHANNELS:
            return

        msg_id = message_data.get('id', 'unknown')
        
        self.log("╔" + "═" * 78 + "╗", Fore.CYAN + Style.BRIGHT)
        self.log("║" + "  🆕 NEW DISCORD MESSAGE RECEIVED".center(78) + "║", Fore.CYAN + Style.BRIGHT)
        self.log("╚" + "═" * 78 + "╝", Fore.CYAN + Style.BRIGHT)
        
        self.log(f"\n📍 Message ID: {msg_id}", Fore.YELLOW)
        self.log(f"📍 Channel ID: {channel_id}", Fore.YELLOW)
        self.log(f"📍 Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n", Fore.YELLOW)

        await self.display_full_message_json(message_data)

        if LOG_RAW_MESSAGES:
            await self.display_raw_message(message_data)

        self.log("\n🔍 STARTING PARSING PROCESS...", Fore.YELLOW + Style.BRIGHT)
        parsed_data = await self.parse_message_data(message_data)

        if parsed_data and LOG_PARSED_DATA:
            await self.display_parsed_data(parsed_data)

        if parsed_data:
            discord_stats['servers_processed'] += 1
            self.log("\n🔍 APPLYING FILTERS...", Fore.YELLOW + Style.BRIGHT)
            filter_result = await self.apply_filters(parsed_data)
            if filter_result['passed']:
                self.log(f"✅ FILTER PASSED: Sending to HTTP API", Fore.GREEN + Style.BRIGHT)
                await self.send_to_http_api(parsed_data)
            elif LOG_FILTER_RESULTS:
                discord_stats['servers_filtered'] += 1
                self.log(f"⛔ FILTER BLOCKED: {filter_result['reason']}", Fore.YELLOW + Style.BRIGHT)
        else:
            self.log("\n⚠️ NO DATA PARSED - Message format not recognized", Fore.RED + Style.BRIGHT)

        self.log("\n" + "╔" + "═" * 78 + "╗", Fore.CYAN + Style.BRIGHT)
        self.log("║" + "  ✅ MESSAGE PROCESSING COMPLETE".center(78) + "║", Fore.CYAN + Style.BRIGHT)
        self.log("╚" + "═" * 78 + "╝\n", Fore.CYAN + Style.BRIGHT)

    async def display_raw_message(self, message_data):
        self.log("RAW MESSAGE DEBUG:", Fore.MAGENTA)
        self.log("-" * 80, Fore.MAGENTA)

        self.log(f"Channel ID: {message_data.get('channel_id')}")
        self.log(
            f"Author: {message_data.get('author', {}).get('username', 'Unknown')}"
        )
        self.log(f"Content: {message_data.get('content', 'No content')}")

        embeds = message_data.get('embeds', [])
        
        if not embeds and 'message_snapshots' in message_data:
            snapshots = message_data.get('message_snapshots', [])
            if snapshots and len(snapshots) > 0:
                snapshot_message = snapshots[0].get('message', {})
                embeds = snapshot_message.get('embeds', [])
                self.log(f"📸 Found {len(embeds)} embed(s) in message_snapshots", Fore.CYAN)
        else:
            self.log(f"Found {len(embeds)} embed(s)")

        for i, embed in enumerate(embeds, 1):
            self.log(f"\n  Embed #{i}:", Fore.YELLOW)
            if 'title' in embed:
                self.log(f"    Title: {embed['title']}")
            if 'description' in embed:
                self.log(f"    Description: {embed['description']}")

            fields = embed.get('fields', [])
            self.log(f"    Fields ({len(fields)}):")
            for field in fields:
                self.log(f"      - {field['name']}: {field['value']}")

        self.log("-" * 80, Fore.MAGENTA)

    async def parse_message_data(self, message_data):
        """
        Улучшенный парсер сообщений Discord с поддержкой эмодзи и структурированных форматов
        Поддерживает: Brainrot Notify, Chilli Hub, Ice Hub и другие форматы
        """
        parsed_data = {
            'name': None,
            'money': None,
            'money_raw': None,
            'players': None,
            'job_id': None,
            'script': None,
            'join_link': None,
            'is_10m_plus': False,
            'source': 'discord'
        }

        content = message_data.get('content', '')
        embeds = message_data.get('embeds', [])

        if not embeds and 'message_snapshots' in message_data:
            snapshots = message_data.get('message_snapshots', [])
            if snapshots and len(snapshots) > 0:
                snapshot_message = snapshots[0].get('message', {})
                embeds = snapshot_message.get('embeds', [])
                if not content:
                    content = snapshot_message.get('content', '')

        if "Ice Hub Finder - Target Located" in content:
            return await self.parse_ice_hub_message(content)

        if self.has_emoji_headers(content):
            return await self.parse_emoji_formatted_message(content)

        if not embeds and content:
            lines = [line.strip() for line in content.split('\n') if line.strip()]

            i = 0
            while i < len(lines):
                line = lines[i]


                if 'Name' in line or '🏷️' in line:
                    name_parts = []
                    i += 1

                    while i < len(lines) and not self.is_field_header(lines[i]):
                        name_parts.append(lines[i])
                        i += 1
                    if name_parts:
                        parsed_data['name'] = ' '.join(name_parts).strip()
                    continue

                elif self.is_money_header(line):
                    money_result = self.parse_money_improved(lines[i + 1] if i + 1 < len(lines) else '')
                    if money_result:
                        parsed_data['money'] = money_result['value']
                        parsed_data['money_raw'] = money_result['raw']
                        parsed_data['is_10m_plus'] = money_result['is_10m_plus']
                    i += 2
                    continue

                elif self.is_players_header(line):
                    players_line = lines[i + 1] if i + 1 < len(lines) else ''
                    if '/' in players_line:
                        parsed_data['players'] = players_line.strip()
                    i += 2
                    continue

                elif self.is_job_id_header(line):
                    job_id_result = self.parse_job_id_section(lines, i)
                    if job_id_result:
                        parsed_data['job_id'] = job_id_result['job_id']
                        i = job_id_result['next_index']
                        continue
                    i += 1
                    continue

                elif self.is_script_header(line):
                    if i + 1 < len(lines):
                        script = lines[i + 1].strip()
                        if 'TeleportService' in script or 'game:' in script.lower():
                            parsed_data['script'] = script
                        i += 2
                        continue
                    i += 1
                    continue


                elif self.is_link_header(line):
                    if i + 1 < len(lines):
                        parsed_data['join_link'] = lines[i + 1].strip()
                        i += 2
                        continue
                    i += 1
                    continue

                i += 1

            return parsed_data


        if embeds:
            for embed in embeds:
                fields = embed.get('fields', [])

                for field in fields:
                    field_name = field['name']
                    field_value = field['value']

                    if any(pattern in field_name for pattern in NAME_PATTERNS):
                        parsed_data['name'] = field_value.strip()

                    if any(pattern in field_name for pattern in MONEY_PATTERNS_LABELS):
                        clean_value = field_value.replace('**', '').replace('`', '').strip()
                        money_result = self.parse_money(clean_value)
                        if money_result:
                            parsed_data['money'] = money_result['value']
                            parsed_data['money_raw'] = money_result['raw']
                            if money_result['is_10m_plus']:
                                parsed_data['is_10m_plus'] = True

                    if any(pattern in field_name for pattern in PLAYERS_PATTERNS):
                        clean_players = field_value.replace('**', '').replace('`', '').strip()
                        parsed_data['players'] = clean_players

                    if any(pattern in field_name for pattern in JOB_ID_PATTERNS):

                        clean_value = field_value.replace('```', '').strip()
                        job_id_match = re.search(r'([a-f0-9\-]{36})', clean_value)
                        if job_id_match:
                            parsed_data['job_id'] = job_id_match.group(1)

                    if any(pattern in field_name for pattern in SCRIPT_PATTERNS):
                        parsed_data['script'] = field_value.strip()

                        if not parsed_data['job_id']:
                            script_job_id = re.search(r'([a-f0-9\-]{36})', field_value)
                            if script_job_id:
                                parsed_data['job_id'] = script_job_id.group(1)

                    if any(pattern in field_name for pattern in JOIN_LINK_PATTERNS):
                        parsed_data['join_link'] = field_value.strip()


        if not parsed_data['job_id'] and parsed_data['join_link']:
            game_id_match = re.search(r'gameInstanceId=([a-f0-9\-]+)', parsed_data['join_link'])
            if game_id_match:
                parsed_data['job_id'] = game_id_match.group(1)
        

        if not parsed_data['job_id'] and embeds:
            for embed in embeds:
                fields = embed.get('fields', [])
                for field in fields:

                    field_value = field.get('value', '')
                    clean_value = field_value.replace('```', '').replace('**', '').strip()
                    job_id_match = re.search(r'([a-f0-9\-]{36})', clean_value)
                    if job_id_match:
                        parsed_data['job_id'] = job_id_match.group(1)
                        break
                if parsed_data['job_id']:
                    break

        return parsed_data

    def has_emoji_headers(self, content):
        """Проверяет, содержит ли сообщение эмодзи заголовки"""
        emoji_headers = ['🏷️', '💰', '👥', '🆔', '🌐', '📜']
        return any(emoji in content for emoji in emoji_headers)

    def is_field_header(self, line):
        """Проверяет, является ли строка заголовком поля (эмодзи или ключевое слово)"""
        emoji_headers = ['💰', '👥', '🆔', '🌐', '📜']
        keyword_headers = ['Money', 'Players', 'Job ID', 'Join Link', 'Join Script']

        return (any(emoji in line for emoji in emoji_headers) or
                any(keyword in line for keyword in keyword_headers))

    def is_money_header(self, line):
        """Проверяет, является ли строка заголовком для денег"""
        return ('Money' in line or '💰' in line)

    def is_players_header(self, line):
        """Проверяет, является ли строка заголовком для игроков"""
        return ('Players' in line or '👥' in line)

    def is_job_id_header(self, line):
        """Проверяет, является ли строка заголовком для Job ID"""
        return ('Job ID' in line or '🆔' in line)

    def is_script_header(self, line):
        """Проверяет, является ли строка заголовком для скрипта"""
        return ('Join Script' in line or '📜' in line)

    def is_link_header(self, line):
        """Проверяет, является ли строка заголовком для ссылки"""
        return ('Join Link' in line or '🌐' in line)

    def parse_money_improved(self, money_text):
        """Улучшенный парсер денег с поддержкой различных форматов"""
        if not money_text:
            return None

        try:
            money_text = money_text.replace(',', '').replace('$', '').replace('**', '').replace('`', '').strip()


            patterns = [
                (r'(\d+(?:\.\d+)?)\s*([KMB]?)/s', 'per_second'),
                (r'(\d+(?:\.\d+)?)\s*([KMB]?)', 'standard')
            ]

            for pattern, pattern_type in patterns:
                match = re.search(pattern, money_text, re.IGNORECASE)
                if match:
                    value = float(match.group(1))
                    multiplier = match.group(2).upper() if match.lastindex >= 2 and match.group(2) else ''

                    if multiplier == 'K':
                        value = value / 1000
                    elif multiplier == 'B':
                        value = value * 1000

                    return {
                        'value': value,
                        'raw': money_text,
                        'is_10m_plus': value >= 10.0
                    }

            return None
        except Exception as e:
            self.log(f"⚠️ Error parsing money (improved) '{money_text}': {e}", Fore.YELLOW)
            return None

    def parse_job_id_section(self, lines, start_index):
        """Парсит секцию Job ID, включая PC и Mobile варианты"""
        if start_index >= len(lines):
            return None

        current_line = lines[start_index]
        result = {'job_id': None, 'next_index': start_index + 1}


        is_pc_version = 'PC' in current_line
        is_mobile_version = 'Mobile' in current_line


        if start_index + 1 < len(lines):
            next_line = lines[start_index + 1].strip()
            if re.match(r'^[a-f0-9\-]{36}$', next_line):
                result['job_id'] = next_line
                result['next_index'] = start_index + 2


                if start_index + 2 < len(lines):
                    next_next_line = lines[start_index + 2].strip()
                    if re.match(r'^[a-f0-9\-]{36}$', next_next_line):

                        result['job_id'] = next_line
                        result['next_index'] = start_index + 3

        return result

    async def parse_emoji_formatted_message(self, content):
        """Парсер для сообщений с эмодзи заголовками (типа Brainrot Notify | Chilli Hub)"""
        parsed_data = {
            'name': None,
            'money': None,
            'money_raw': None,
            'players': None,
            'job_id': None,
            'script': None,
            'join_link': None,
            'is_10m_plus': False,
            'source': 'discord'
        }

        lines = [line.strip() for line in content.split('\n') if line.strip()]

        i = 0
        while i < len(lines):
            line = lines[i]


            if '🏷️' in line and 'Name' in line:
                i += 1
                if i < len(lines):
                    parsed_data['name'] = lines[i].strip()
                i += 1
                continue


            elif '💰' in line and 'Money per sec' in line:
                i += 1
                if i < len(lines):
                    money_result = self.parse_money_improved(lines[i])
                    if money_result:
                        parsed_data['money'] = money_result['value']
                        parsed_data['money_raw'] = money_result['raw']
                        parsed_data['is_10m_plus'] = money_result['is_10m_plus']
                i += 1
                continue


            elif '👥' in line and 'Players' in line:
                i += 1
                if i < len(lines):
                    players_line = lines[i]
                    if '/' in players_line:
                        parsed_data['players'] = players_line.strip()
                i += 1
                continue


            elif '🆔' in line:
                job_result = self.parse_job_id_from_emoji_section(lines, i)
                if job_result:
                    parsed_data['job_id'] = job_result['job_id']
                    i = job_result['next_index']
                    continue
                i += 1
                continue

            elif '🌐' in line and 'Join Link' in line:
                i += 1
                if i < len(lines):
                    parsed_data['join_link'] = lines[i].strip()
                i += 1
                continue


            elif '📜' in line and 'Join Script' in line:
                i += 1
                if i < len(lines):
                    script = lines[i].strip()
                    if 'TeleportService' in script or 'game:' in script.lower():
                        parsed_data['script'] = script
                i += 1
                continue

            i += 1

        return parsed_data

    def parse_job_id_from_emoji_section(self, lines, start_index):
        """Парсит Job ID из секции с эмодзи 🆔"""
        if start_index >= len(lines):
            return None

        result = {'job_id': None, 'next_index': start_index + 1}

        # Проверяем следующие строки на наличие UUID
        for j in range(start_index + 1, min(start_index + 4, len(lines))):
            line = lines[j].strip()
            if re.match(r'^[a-f0-9\-]{36}$', line):
                result['job_id'] = line
                result['next_index'] = j + 1
                break

        return result

    async def parse_ice_hub_message(self, content):
        """Парсер для Ice Hub сообщений с UUID в начале"""
        parsed_data = {
            'name': None,
            'money': None,
            'money_raw': None,
            'players': None,
            'job_id': None,
            'script': None,
            'join_link': None,
            'is_10m_plus': False,
            'source': 'ice_hub'
        }

        lines = [line.strip() for line in content.split('\n') if line.strip()]

        i = 0
        while i < len(lines):
            line = lines[i]

            if re.match(r'^[a-f0-9\-]{36}$', line):
                if i + 1 < len(lines) and '/' in lines[i + 1]:
                    player_income_info = lines[i + 1]
                    parts = player_income_info.split(' | ')

                    if len(parts) >= 3:
                        players_part = parts[0].strip()
                        if '/' in players_part:
                            parsed_data['players'] = players_part

                        income_part = parts[1].strip()
                        if income_part != 'None':
                            money_result = self.parse_money(income_part)
                            if money_result:
                                parsed_data['money'] = money_result['value']
                                parsed_data['money_raw'] = money_result['raw']
                                parsed_data['is_10m_plus'] = money_result['is_10m_plus']

                        name_part = parts[2].strip()
                        if name_part != 'Unknown':
                            parsed_data['name'] = name_part

            elif line == 'Server Info' and i + 1 < len(lines):
                i += 1
                while i < len(lines):
                    line = lines[i]
                    if line.startswith('Job ID:') and i + 1 < len(lines):
                        job_id = lines[i + 1].strip()
                        if re.match(r'^[a-f0-9\-]{36}$', job_id):
                            parsed_data['job_id'] = job_id
                        break
                    elif line.startswith('Players:') and i + 1 < len(lines):
                        players = lines[i + 1].strip()
                        if players.isdigit():
                            parsed_data['players'] = f"{players}/18"
                    elif line.startswith('Total Income:') and i + 1 < len(lines):
                        income = lines[i + 1].strip()
                        if income != '0/s':
                            money_result = self.parse_money(income)
                            if money_result:
                                parsed_data['money'] = money_result['value']
                                parsed_data['money_raw'] = money_result['raw']
                                parsed_data['is_10m_plus'] = money_result['is_10m_plus']
                    elif line.startswith('PC Script') and i + 2 < len(lines):
                        script = lines[i + 1].strip()
                        if 'TeleportService' in script:
                            parsed_data['script'] = script
                        break
                    i += 1
                break

            i += 1

        if parsed_data['job_id'] and not parsed_data['script']:
            game_id = "109983668079237"
            parsed_data['script'] = f"game:GetService('TeleportService'):TeleportToPlaceInstance({game_id}, '{parsed_data['job_id']}')"

        return parsed_data

    def parse_money(self, money_text):
        try:
            money_text = money_text.replace(',', '').replace('**', '').replace('`', '').strip()

            for pattern in MONEY_PATTERNS:
                match = re.search(pattern, money_text, re.IGNORECASE)
                if match:
                    value = float(match.group(1))
                    multiplier = match.group(2).upper() if match.lastindex and match.lastindex >= 2 else ''

                    if multiplier == 'K':
                        value = value / 1000
                    elif multiplier == 'B':
                        value = value * 1000

                    return {
                        'value': value,
                        'raw': money_text,
                        'is_10m_plus': value >= 10.0
                    }

            return None
        except Exception as e:
            self.log(f"⚠️ Error parsing money '{money_text}': {e}", Fore.YELLOW)
            return None

    async def display_parsed_data(self, parsed_data):
        self.log("\n" + "━" * 80, Fore.GREEN)
        self.log("✨ PARSED DATA RESULTS:", Fore.GREEN + Style.BRIGHT)
        self.log("━" * 80, Fore.GREEN)
        
        def format_value(key, value):
            if value:
                return f"{Fore.GREEN}{value}{Style.RESET_ALL}"
            else:
                return f"{Fore.RED}Not found{Style.RESET_ALL}"
        
        self.log(f"   🏷️  Name: {format_value('name', parsed_data['name'])}")
        
        if parsed_data['money']:
            self.log(f"   💰 Money: {Fore.GREEN}{parsed_data['money']}M/s{Style.RESET_ALL} (raw: {parsed_data['money_raw']})")
        else:
            self.log(f"   💰 Money: {Fore.RED}Not found{Style.RESET_ALL}")
        
        self.log(f"   👥 Players: {format_value('players', parsed_data['players'])}")
        self.log(f"   🆔 Job ID: {format_value('job_id', parsed_data['job_id'])}")
        self.log(f"   📜 Script: {format_value('script', parsed_data['script'])}")
        self.log(f"   🔗 Join Link: {format_value('join_link', parsed_data['join_link'])}")
        
        is_10m_icon = "⭐" if parsed_data['is_10m_plus'] else "  "
        is_10m_color = Fore.YELLOW if parsed_data['is_10m_plus'] else Fore.WHITE
        self.log(f"   {is_10m_icon} Is 10M+: {is_10m_color}{parsed_data['is_10m_plus']}{Style.RESET_ALL}")
        self.log(f"   📍 Source: {Fore.CYAN}{parsed_data.get('source', 'unknown')}{Style.RESET_ALL}")
        
        self.log("━" * 80, Fore.GREEN)

    async def apply_filters(self, parsed_data):
        if parsed_data.get(
                'source') == 'ice_hub' and ICE_HUB_FILTER['enabled']:
            if ICE_HUB_FILTER['require_job_id'] and not parsed_data['job_id']:
                return {
                    'passed': False,
                    'reason': "Ice Hub message missing required job_id"
                }

            if parsed_data['players']:
                try:
                    current_players = int(parsed_data['players'].split('/')[0])
                    if not (ICE_HUB_FILTER['min_players'] <= current_players <=
                            ICE_HUB_FILTER['max_players']):
                        return {
                            'passed':
                            False,
                            'reason':
                            f"Ice Hub players {current_players} not in range ({ICE_HUB_FILTER['min_players']}, {ICE_HUB_FILTER['max_players']})"
                        }
                except (ValueError, IndexError):
                    pass

            if ICE_HUB_FILTER['ignore_zero_income'] and parsed_data[
                    'money'] == 0:
                return {
                    'passed': False,
                    'reason': "Ice Hub server has zero income (ignored)"
                }

        if parsed_data['money'] is not None:
            if not (MONEY_THRESHOLD['min'] <= parsed_data['money'] <=
                    MONEY_THRESHOLD['max']):
                return {
                    'passed':
                    False,
                    'reason':
                    f"Money ${parsed_data['money']}M/s not in range ({MONEY_THRESHOLD['min']}, {MONEY_THRESHOLD['max']})"
                }

        if parsed_data['players']:
            try:
                current_players = int(parsed_data['players'].split('/')[0])
                if current_players >= PLAYER_THRESHOLD:
                    return {
                        'passed':
                        False,
                        'reason':
                        f"Players {current_players} >= threshold {PLAYER_THRESHOLD}"
                    }
            except (ValueError, IndexError):
                pass

        if parsed_data['name']:
            if IGNORE_UNKNOWN and parsed_data['name'].lower() == 'unknown':
                return {
                    'passed': False,
                    'reason': "Name is 'Unknown' (ignored)"
                }

            if parsed_data['name'] in IGNORE_LIST:
                return {
                    'passed': False,
                    'reason': f"Name '{parsed_data['name']}' in ignore list"
                }

            if FILTER_BY_NAME['enabled']:
                if parsed_data['name'] not in FILTER_BY_NAME['allowed_names']:
                    return {
                        'passed':
                        False,
                        'reason':
                        f"Name '{parsed_data['name']}' not in allowed list"
                    }

        if parsed_data['is_10m_plus'] and not BYPASS_10M:
            return {
                'passed': False,
                'reason': "10M+ server blocked by configuration"
            }

        return {'passed': True}

    async def send_to_http_api(self, parsed_data):
        try:
            response = requests.post(f"{self.api_url}/api/server/push",
                                     json=parsed_data,
                                     timeout=5)

            if response.status_code == 200:
                self.log("SENT TO HTTP API", Fore.GREEN)
                self.log(f"Server: {parsed_data['name']}", Fore.GREEN)
                
                discord_stats['servers_sent'] += 1
                discord_stats['last_server'] = {
                    'name': parsed_data['name'],
                    'money': parsed_data['money'],
                    'players': parsed_data['players'],
                    'timestamp': datetime.now().isoformat()
                }
                if parsed_data['name']:
                    discord_stats['unique_servers'].add(parsed_data['name'])
            else:
                self.log(f"HTTP API error: {response.status_code}", Fore.RED)

        except Exception as e:
            self.log(f"Failed to send to HTTP API: {e}", Fore.RED)

    def toggle_pause(self):
        self.paused = not self.paused
        state = "PAUSED" if self.paused else "RESUMED"
        color = Fore.RED if self.paused else Fore.GREEN
        self.log(f"MONITORING {state}", color)


def test_parsing():
    """Тестовая функция для проверки парсинга сообщений"""

    test_message = """Brainrot Notify | Chilli Hub
🏷️ Name
La Karkerkar Combinasion
💰 Money per sec
$600K/s
👥 Players
5/8
🆔 Job ID (Mobile)
8f4eee40-8091-45fd-86a2-14820a64c502
🆔 Job ID (PC)
8f4eee40-8091-45fd-86a2-14820a64c502
🌐 Join Link
Click to Join
📜 Join Script (PC)
game:GetService("TeleportService"):TeleportToPlaceInstance(109983668079237,"8f4eee40-8091-45fd-86a2-14820a64c502",game.Players.LocalPlayer)
Made by Chilli Hub•Сегодня, в 23:39, бот мог легко достать например 🆔 Job ID (PC)
8f4eee40-8091-45fd-86a2-14820a64c502 записать его как 8f4eee40-8091-45fd-86a2-14820a64c502 и отправить через апи в луа скрипт"""


    mock_message_data = {
        'content': test_message,
        'embeds': []
    }


    monitor = DiscordMonitor("http://test-api.com")


    import asyncio
    async def run_test():
        print("🧪 Тестируем парсинг сообщения...")
        print("=" * 80)

        parsed_data = await monitor.parse_message_data(mock_message_data)

        print("📊 РЕЗУЛЬТАТ ПАРСИНГА:")
        print("=" * 50)
        print(f"📛 Название: {parsed_data['name'] or 'Не найдено'}")
        print(f"💰 Деньги: {parsed_data['money']}M/s (сырые: {parsed_data['money_raw']})" if parsed_data['money'] else "💰 Деньги: Не найдено")
        print(f"👥 Игроки: {parsed_data['players'] or 'Не найдено'}")
        print(f"🆔 Job ID: {parsed_data['job_id'] or 'Не найдено'}")
        print(f"📜 Скрипт: {parsed_data['script'] or 'Не найдено'}")
        print(f"🌐 Ссылка: {parsed_data['join_link'] or 'Не найдено'}")
        print(f"💎 10M+: {parsed_data['is_10m_plus']}")
        print(f"🏷️ Источник: {parsed_data.get('source', 'discord')}")

        print("\n" + "=" * 80)
        print("✅ Тест завершен!")


        success = True
        if not parsed_data['job_id']:
            print("❌ Job ID не найден!")
            success = False
        if not parsed_data['name']:
            print("❌ Название не найдено!")
            success = False
        if not parsed_data['money']:
            print("❌ Деньги не найдены!")
            success = False

        if success:
            print("🎉 Все важные поля успешно распарсены!")
        else:
            print("⚠️ Некоторые поля не удалось распарсить")


        asyncio.run(run_test())


async def main(use_keyboard=True):
    """Основная функция Discord бота"""
    monitor = DiscordMonitor(API_URL)
    
    if use_keyboard and KEYBOARD_AVAILABLE and 'keyboard' in globals():
        keyboard.add_hotkey(PAUSE_HOTKEY, monitor.toggle_pause)

    try:
        await monitor.connect_discord()
    except KeyboardInterrupt:
        print("\nShutting down...")


def start_discord_bot_background():
    """Запуск Discord бота в фоновом режиме без keyboard"""
    discord_stats['bot_status'] = 'Starting...'
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main(use_keyboard=False))
    except Exception as e:
        print(f"Discord bot error: {e}")
        discord_stats['bot_status'] = f'Error: {e}'
        discord_stats['bot_connected'] = False


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_parsing()
    else:
        asyncio.run(main())
