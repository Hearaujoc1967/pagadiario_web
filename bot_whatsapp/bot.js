const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const QRCode = require('qrcode');
const express = require('express');

const app = express();
app.use(express.json());

const CHROME_PATH = process.env.PREFIX + '/bin/chromium-browser';
let qrActual = null;
let clienteListo = false;

const client = new Client({
    authStrategy: new LocalAuth({ clientId: 'pagadiario', dataPath: './.wwebjs_auth' }),
    pairWithPhoneNumber: {
        phoneNumber: process.env.PAIR_NUMBER || '',
        showNotification: true
    },
    webVersionCache: {
        type: 'remote',
        remotePath: 'https://raw.githubusercontent.com/wppconnect-team/wa-version/main/html/2.3000.1054292354-alpha.html'
    },
    puppeteer: {
        headless: true,
        executablePath: CHROME_PATH,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote',
            '--disable-gpu',
            '--disable-software-rasterizer',
            '--disable-extensions',
            '--disable-features=site-per-process',
            '--disable-features=IsolateOrigins',
            '--disable-site-isolation-trials',
            '--disable-web-security',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
            '--disable-ipc-flooding-protection',
            '--no-crash-upload',
            '--no-default-browser-check',
            '--no-pings'
        ]
    }
});

client.on('code', (code) => {
    console.log('\n🔑 CODIGO DE VINCULACION: ' + code + '\n');
    require('fs').writeFileSync('codigo.txt', code);
});

client.on('authenticated', () => console.log('🔐 authenticated'));
client.on('loading_screen', (pct, msg) => console.log('⏳ loading ' + pct + '% ' + msg));
client.on('change_state', (st) => console.log('🔄 estado: ' + st));

client.on('qr', async (qr) => {
    qrActual = qr;
    console.log('\n✅ QR generado. Abre en el celular: http://127.0.0.1:3002/qr\n');
    qrcode.generate(qr, { small: true });
});

client.on('ready', () => {
    clienteListo = true;
    qrActual = null;
    console.log('\n✅ ¡Cliente WhatsApp conectado!');
});

client.on('auth_failure', (msg) => {
    console.error('❌ Error de autenticación:', msg);
});

client.on('disconnected', (reason) => {
    console.log('⚠️ Desconectado:', reason);
    clienteListo = false;
});

client.on('message', async (message) => {
    console.log(`📩 Mensaje: ${message.body}`);
    if (message.body === 'ping') {
        await message.reply('pong');
    }
});

// ============================================
// ENDPOINT: Ver QR
// ============================================
app.get('/qr', async (req, res) => {
    if (clienteListo) {
        return res.send('<html><body style="background:#1e1e2d;text-align:center;padding:50px;font-family:sans-serif;"><h1 style="color:#50cd89;">✅ WhatsApp ya está conectado</h1></body></html>');
    }
    if (!qrActual) {
        return res.send('<html><body style="background:#1e1e2d;text-align:center;padding:50px;font-family:sans-serif;"><h1 style="color:#ffa800;">⏳ Esperando QR...</h1><meta http-equiv="refresh" content="2"></body></html>');
    }
    try {
        const dataUrl = await QRCode.toDataURL(qrActual, { width: 500, margin: 2 });
        res.send(`<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="refresh" content="30"></head><body style="background:#1e1e2d;text-align:center;padding:20px;font-family:sans-serif;">
            <h1 style="color:#50cd89;font-size:1.3em;">Escanea este QR con WhatsApp</h1>
            <img src="${dataUrl}" style="border:8px solid white;border-radius:15px;max-width:90%;" />
            <p style="color:#a1a5b7;font-size:0.9em;">WhatsApp → Dispositivos Vinculados → Vincular dispositivo</p>
        </body></html>`);
    } catch (e) {
        res.status(500).send('Error generando QR: ' + e.message);
    }
});

// ============================================
// ENDPOINT: Enviar mensaje
// ============================================
app.post('/send', async (req, res) => {
    try {
        if (!process.env.BOT_TOKEN || req.headers['x-bot-token'] !== process.env.BOT_TOKEN) {
            return res.status(401).json({ error: 'no autorizado' });
        }
        if (!clienteListo) {
            return res.status(503).json({ error: 'WhatsApp no conectado' });
        }
        const { numero, mensaje } = req.body;
        if (!numero || !mensaje) {
            return res.status(400).json({ error: 'Faltan numero o mensaje' });
        }
        let jid = numero.replace(/\D/g, '');
        if (!jid.endsWith('@c.us')) {
            jid = jid + '@c.us';
        }
        await client.sendMessage(jid, mensaje);
        console.log(`✅ Mensaje enviado a ${jid}`);
        res.json({ success: true, jid });
    } catch (e) {
        console.error('Error enviando:', e.message);
        const sinWa = /No LID|not registered|invalid wid/i.test(String(e.message));
        res.status(sinWa ? 404 : 500).json({ error: sinWa ? 'sin_whatsapp' : e.message });
    }
});

app.listen(3002, '127.0.0.1', () => {
    console.log('🚀 API WhatsApp escuchando en http://127.0.0.1:3002');
    console.log('📱 QR en: http://127.0.0.1:3002/qr');
});

client.initialize();
