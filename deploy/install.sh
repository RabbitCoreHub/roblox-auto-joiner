#!/bin/bash

set -e

echo "🚀 Установка Roblox Auto-Joiner на Ubuntu"
echo "=========================================="

if [ "$EUID" -ne 0 ]; then 
    echo "⚠️  Пожалуйста, запустите с правами root (sudo ./install.sh)"
    exit 1
fi

PROJECT_DIR="/opt/roblox-auto-joiner"
VENV_DIR="$PROJECT_DIR/venv"

echo "📦 Обновление системы и установка зависимостей..."
apt update
apt install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx ufw git

echo "📁 Создание директории проекта..."
mkdir -p $PROJECT_DIR
cd $PROJECT_DIR

echo "🐍 Создание виртуального окружения Python..."
python3 -m venv $VENV_DIR
source $VENV_DIR/bin/activate

echo "📥 Установка Python зависимостей..."
pip install --upgrade pip
pip install flask==3.0.0 flask-cors==4.0.0 websockets==12.0 colorama==0.4.6 requests==2.31.0 gunicorn==23.0.0 python-dotenv

echo "📝 Создание .env файла..."
if [ ! -f "$PROJECT_DIR/.env" ]; then
    cat > $PROJECT_DIR/.env << EOF
# Опциональный Discord токен (раскомментируйте и укажите токен для включения Discord мониторинга)
# DISCORD_TOKEN=your_discord_token_here

# API URL (будет автоматически установлен на домен)
API_URL=https://icehub.work.gd
EOF
    echo "✅ Создан файл .env - отредактируйте его при необходимости"
fi

echo "🔧 Создание systemd сервисов..."

cat > /etc/systemd/system/roblox-api.service << 'EOF'
[Unit]
Description=Roblox Auto-Joiner HTTP API
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/roblox-auto-joiner
Environment="PATH=/opt/roblox-auto-joiner/venv/bin"
EnvironmentFile=/opt/roblox-auto-joiner/.env
ExecStart=/opt/roblox-auto-joiner/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 --reuse-port main:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/roblox-websocket.service << 'EOF'
[Unit]
Description=Roblox Auto-Joiner WebSocket Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/roblox-auto-joiner
Environment="PATH=/opt/roblox-auto-joiner/venv/bin"
EnvironmentFile=/opt/roblox-auto-joiner/.env
ExecStart=/opt/roblox-auto-joiner/venv/bin/python websocket_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/roblox-discord.service << 'EOF'
[Unit]
Description=Roblox Auto-Joiner Discord Bot
After=network.target
ConditionPathExists=/opt/roblox-auto-joiner/.env

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/roblox-auto-joiner
Environment="PATH=/opt/roblox-auto-joiner/venv/bin"
EnvironmentFile=/opt/roblox-auto-joiner/.env
ExecStart=/opt/roblox-auto-joiner/venv/bin/python discord_bot_http.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "🌐 Настройка Nginx..."
cat > /etc/nginx/sites-available/roblox << 'EOF'
server {
    listen 80;
    server_name icehub.work.gd;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
EOF

if [ ! -L /etc/nginx/sites-enabled/roblox ]; then
    ln -s /etc/nginx/sites-available/roblox /etc/nginx/sites-enabled/
fi

rm -f /etc/nginx/sites-enabled/default

echo "🔍 Проверка конфигурации Nginx..."
nginx -t

echo "🔐 Настройка firewall..."
ufw --force enable
ufw allow ssh
ufw allow http
ufw allow https

echo "🔄 Перезагрузка Nginx..."
systemctl reload nginx

echo "✅ Установка завершена!"
echo ""
echo "📋 Следующие шаги:"
echo "1. Скопируйте файлы проекта в $PROJECT_DIR"
echo "2. Настройте DNS: A запись для icehub.work.gd → 78.153.130.35"
echo "3. Отредактируйте $PROJECT_DIR/.env (добавьте DISCORD_TOKEN при необходимости)"
echo "4. Установите SSL сертификат: sudo certbot --nginx -d icehub.work.gd"
echo "5. Запустите сервисы:"
echo "   sudo systemctl enable roblox-api roblox-websocket"
echo "   sudo systemctl start roblox-api roblox-websocket"
echo "   sudo systemctl status roblox-api"
echo ""
echo "🎉 Готово!"
