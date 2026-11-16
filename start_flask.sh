#!/data/data/com.termux/files/usr/bin/bash
cd ~/pagadiario_local
termux-wake-lock
while true; do
  python -u app.py >> flask.log 2>&1
  echo "$(date) flask caido, reiniciando en 10s" >> flask.log
  sleep 10
done
