#!/data/data/com.termux/files/usr/bin/bash
# Uso: bash reiniciar.sh [todo|flask|bot]
cd ~/pagadiario_local || exit 1
QUE="${1:-todo}"

esperar_http() {
  for i in $(seq 1 "$2"); do
    c=$(curl -s -o /dev/null -w "%{http_code}" "$1")
    [ "$c" != "000" ] && return 0
    sleep 1
  done
  return 1
}

if [ "$QUE" = "todo" ] || [ "$QUE" = "flask" ]; then
  echo "Deteniendo Flask..."
  pkill -f start_flask.sh
  pkill -9 -f app.py
fi
if [ "$QUE" = "todo" ] || [ "$QUE" = "bot" ]; then
  echo "Deteniendo bot de WhatsApp..."
  pkill -f start_bot.sh
  pkill -f "node bot.js"
  pkill -f "lib/chromium"
fi
sleep 3

if [ "$QUE" = "todo" ] || [ "$QUE" = "flask" ]; then
  nohup bash start_flask.sh > /dev/null 2>&1 &
fi
if [ "$QUE" = "todo" ] || [ "$QUE" = "bot" ]; then
  nohup bash bot_whatsapp/start_bot.sh > /dev/null 2>&1 &
fi

if [ "$QUE" = "todo" ] || [ "$QUE" = "flask" ]; then
  echo "Esperando a Flask (hasta 40 s)..."
  if esperar_http "http://127.0.0.1:5000/" 40; then echo "✅ Flask responde en :5000"; else echo "❌ Flask no responde. Revisa: tail -20 flask.log"; fi
fi
if [ "$QUE" = "todo" ] || [ "$QUE" = "bot" ]; then
  echo "Esperando al bot (hasta 90 s)..."
  if esperar_http "http://127.0.0.1:3001/qr" 90; then echo "✅ Bot escuchando en :3001"; else echo "❌ Bot no responde. Revisa: tail -20 bot_whatsapp/bot.log"; fi
  echo "--- bot.log ---"
  tail -4 bot_whatsapp/bot.log
  echo "El bot puede tardar 1-2 min más en cargar WhatsApp Web (hasta que pase 'loading')."
fi
