#!/bin/bash

# Legal AI Telegram Bot - Deployment Script
# Скрипт для развертывания бота на VDS Ubuntu 22.04

set -e  # Останавливаться при ошибках

echo "🚀 Starting deployment of Legal AI Telegram Bot..."

# 1. Update system
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# 2. Install Python and dependencies
echo "🐍 Installing Python 3.11 and dependencies..."
sudo apt install -y python3.11 python3.11-venv python3-pip git

# 3. Create directory and clone/pull
echo "📁 Setting up project directory..."
cd /opt

if [ -d "legal-ai-bot" ]; then
    echo "📥 Pulling latest changes..."
    cd legal-ai-bot
    git pull
else
    echo "📥 Cloning repository..."
    git clone https://github.com/Andrew821667/legal-ai-bot.git
    cd legal-ai-bot
fi

# 4. Create virtual environment
echo "🔧 Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3.11 -m venv venv
fi

source venv/bin/activate

# 5. Install dependencies
echo "📚 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 6. Setup .env if not exists
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env file from example..."
    cp .env.example .env
    echo ""
    echo "⚠️  ВАЖНО: Отредактируйте файл .env с вашими ключами!"
    echo "   Используйте: nano /opt/legal-ai-bot/.env"
    echo ""
    echo "   Необходимо заполнить:"
    echo "   - TELEGRAM_BOT_TOKEN (получить у @BotFather)"
    echo "   - OPENAI_API_KEY (получить на platform.openai.com)"
    echo "   - ADMIN_TELEGRAM_ID (получить у @userinfobot)"
    echo ""
fi

# 7. Create data and logs directories
echo "📂 Creating data and logs directories..."
mkdir -p data logs

# 8. Initialize database
echo "💾 Initializing database..."
python3 database.py

# 9. Setup systemd service
echo "⚙️  Setting up systemd service..."
sudo cp systemd/telegram-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot

# 10. Set permissions
echo "🔐 Setting permissions..."
chmod +x bot.py
chmod +x start.sh

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📋 Следующие шаги:"
echo "1. Отредактируйте .env файл: nano /opt/legal-ai-bot/.env"
echo "2. Запустите бота: sudo systemctl start telegram-bot"
echo "3. Проверьте статус: sudo systemctl status telegram-bot"
echo "4. Просмотр логов: sudo journalctl -u telegram-bot -f"
echo ""
echo "Или запустите вручную: /opt/legal-ai-bot/start.sh"
echo ""
