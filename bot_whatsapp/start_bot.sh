#!/data/data/com.termux/files/usr/bin/bash
cd "$(dirname "$(readlink -f "$0")")" || exit 1
termux-wake-lock
export BOT_TOKEN=$(cat .bot_token)
while true; do
  pkill -f 'lib/chromium' 2>/dev/null
  rm -f .wwebjs_auth/session-pagadiario/SingletonLock 2>/dev/null
  node bot.js >> bot.log 2>&1
  echo "$(date) bot caido, reiniciando en 10s" >> bot.log
  sleep 10
done
