#!/data/data/com.termux/files/usr/bin/bash
# Arranque independiente de pagadiario_web (no usa pagadiario_local).
# Uso: bash arrancar.sh [web|bot|todo]   (sin argumento = todo)
cd "$(dirname "$(readlink -f "$0")")" || exit 1
QUE="${1:-todo}"
termux-wake-lock 2>/dev/null

if [ "$QUE" = "todo" ] || [ "$QUE" = "web" ]; then
  echo "Reiniciando pagadiario_web (run_pw.py, https :5001)..."
  pkill -f run_pw.py
  nohup python -u run_pw.py > ~/pw.log 2>&1 &
  sleep 8
  echo "HTTP login: $(curl -sk -o /dev/null -w '%{http_code}' https://localhost:5001/login)"
fi

if [ "$QUE" = "todo" ] || [ "$QUE" = "bot" ]; then
  if pgrep -f "node bot.js" > /dev/null; then
    echo "Ya hay un bot corriendo (node bot.js). No lo toco: dos bots no pueden compartir sesión."
    echo "Detén el otro primero y repite:  bash arrancar.sh bot"
  else
    echo "Iniciando el bot de ESTA carpeta (bot_whatsapp)..."
    nohup bash bot_whatsapp/start_bot.sh > /dev/null 2>&1 &
    echo "Revisa:  tail -n 20 bot_whatsapp/bot.log"
  fi
fi
