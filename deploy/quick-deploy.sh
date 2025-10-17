#!/bin/bash

echo "🚀 Быстрое развертывание Roblox Auto-Joiner"
echo "============================================"
echo ""
echo "Этот скрипт скопирует проект на ваш Ubuntu сервер"
echo ""

read -p "IP адрес сервера (по умолчанию 78.153.130.35): " SERVER_IP
SERVER_IP=${SERVER_IP:-78.153.130.35}

read -p "Пользователь SSH (по умолчанию root): " SSH_USER
SSH_USER=${SSH_USER:-root}

echo ""
echo "📦 Копирование файлов на $SSH_USER@$SERVER_IP..."

cd ..

scp -r config.py main.py websocket_server.py discord_bot_http.py index.html requirements.txt deploy $SSH_USER@$SERVER_IP:/tmp/roblox-project/

echo ""
echo "📡 Подключение к серверу и запуск установки..."

ssh $SSH_USER@$SERVER_IP << 'ENDSSH'
    sudo mkdir -p /opt/roblox-auto-joiner
    sudo cp -r /tmp/roblox-project/* /opt/roblox-auto-joiner/
    cd /opt/roblox-auto-joiner/deploy
    sudo chmod +x install.sh
    sudo ./install.sh
ENDSSH

echo ""
echo "✅ Развертывание завершено!"
echo ""
echo "📋 Следующие шаги на СЕРВЕРЕ:"
echo "1. Настройте DNS: A запись icehub.work.gd → $SERVER_IP"
echo "2. Подождите 5-10 минут для распространения DNS"
echo "3. Подключитесь к серверу: ssh $SSH_USER@$SERVER_IP"
echo "4. Установите SSL: sudo certbot --nginx -d icehub.work.gd"
echo "5. Запустите сервисы:"
echo "   sudo systemctl start roblox-api roblox-websocket"
echo "6. Откройте https://icehub.work.gd в браузере"
echo ""
