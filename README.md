# 🌙 Halol Crypto AI Bot

**Professional Telegram Kripto Tahlil va Signal Boti — To'liq O'zbek tilida**

---

## 📋 Mundarija

- [Loyiha haqida](#loyiha-haqida)
- [Xususiyatlar](#xususiyatlar)
- [O'rnatish](#ornatish)
- [Sozlash](#sozlash)
- [Ishga tushirish](#ishga-tushirish)
- [Server deployment](#server-deployment)
- [Loyiha tuzilmasi](#loyiha-tuzilmasi)
- [Texnik detallar](#texnik-detallar)

---

## Loyiha haqida

Halol Crypto AI Bot — bu O'zbek tilidagi professional kripto valyuta tahlil boti. Bot faqat halol screened kripto valyutalarni kuzatadi, texnik tahlil asosida signal beradi va kuchli imkoniyatlarni darhol xabar qiladi.

**Muhim:** Barcha signallar ta'lim maqsadida. Bu moliyaviy maslahat emas.

---

## Xususiyatlar

### Asosiy

- ✅ To'liq O'zbek tili
- 📡 Real-vaqt Binance ma'lumotlari
- 📊 10+ texnik indikator
- 🎯 Ball tizimi asosida signal
- 📈 Professional grafik (PNG)
- ⚡ Darhol alert tizimi
- 👥 Guruh qo'llab-quvvatlash

### Signal tizimi

- RSI 14 tahlili
- EMA 20/50/200 kesishish
- MACD momentum
- Hajm tahlili
- Breakout aniqlash
- Bollinger Bands
- Qo'llab-quvvatlash/Qarshilik

### Menyular

- 📡 Signal — Watchlist signallari
- 🪙 Coinlar — Barcha halol coinlar
- ⭐ Mening Coinlarim — Shaxsiy kuzatuv
- 📈 Bozor — Umumiy holat
- 🚀 O'sayotgan Coinlar — Top gainers
- 📊 Top Imkoniyatlar — Eng yaxshi signallar
- ✅ Halol Coinlar — Halol ro'yxat
- ❌ Haram Coinlar — Chiqarilganlar
- ⚠️ Meme Coinlar — Meme coinlar
- ⚙️ Sozlamalar — Alert va boshqalar
- ℹ️ Yordam — Qo'llanma

---

## O'rnatish

### 1. Talablar

```
Python 3.10 yoki undan yuqori
pip (Python paket menejeri)
```

### 2. Fayllarni olish

```bash
# Papkani yaratish
mkdir halol_crypto_bot
cd halol_crypto_bot

# Barcha fayllarni shu papkaga ko'chirish
```

### 3. Virtual muhit (tavsiya etiladi)

```bash
python -m venv venv

# Linux/Mac:
source venv/bin/activate

# Windows:
venv\Scripts\activate
```

### 4. Kutubxonalarni o'rnatish

```bash
pip install -r requirements.txt
```

### 5. Telegram Bot yaratish

1. Telegramda `@BotFather` ga o'ting
2. `/newbot` buyrug'ini yuboring
3. Bot nomini kiriting (masalan: `HalolCryptoAI`)
4. Username kiriting (masalan: `halol_crypto_ai_bot`)
5. BotFather sizga **token** beradi — uni saqlang!

---

## Sozlash

### `.env` faylini yaratish

```bash
cp .env.example .env
```

`.env` faylini oching va ma'lumotlarni kiriting:

```env
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUVwxyz
```

Binance API kerak emas — bot ommaviy API bilan ishlaydi.

---

## Ishga tushirish

### Mahalliy test

```bash
python bot.py
```

Bot ishga tushganini ko'rasiz:

```
2024-01-01 12:00:00 | INFO     | bot | 🚀 Bot ishga tushmoqda...
2024-01-01 12:00:01 | INFO     | database | ✅ Ma'lumotlar bazasi tayyor
2024-01-01 12:00:02 | INFO     | scanner | ✅ Market scan tugadi: 60 ta coin
2024-01-01 12:00:02 | INFO     | bot | 🤖 Halol Crypto AI Bot ishga tushdi!
```

Telegramda botingizga `/start` yuboring.

---

## Server Deployment

### Variant 1: Systemd (Linux server, tavsiya)

**1. Service fayl yaratish:**

```bash
sudo nano /etc/systemd/system/halol-crypto-bot.service
```

```ini
[Unit]
Description=Halol Crypto AI Telegram Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/halol_crypto_bot
ExecStart=/home/ubuntu/halol_crypto_bot/venv/bin/python bot.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

**2. Ishga tushirish:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable halol-crypto-bot
sudo systemctl start halol-crypto-bot
sudo systemctl status halol-crypto-bot
```

**3. Loglarni ko'rish:**

```bash
sudo journalctl -u halol-crypto-bot -f
```

---

### Variant 2: Docker

**Dockerfile:**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
```

**docker-compose.yml:**

```yaml
version: '3.8'

services:
  bot:
    build: .
    restart: always
    env_file: .env
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - DATABASE_PATH=/app/data/halol_crypto.db
      - LOG_FILE=/app/logs/bot.log
```

**Ishga tushirish:**

```bash
docker-compose up -d
docker-compose logs -f
```

---

### Variant 3: Screen (oddiy usul)

```bash
screen -S halol_bot
python bot.py
# Ctrl+A, D (background ga o'tish)

# Qaytish:
screen -r halol_bot
```

---

### Variant 4: PM2 (Node.js orqali)

```bash
npm install -g pm2
pm2 start bot.py --interpreter python3 --name halol-crypto-bot
pm2 startup
pm2 save
```

---

## Loyiha tuzilmasi

```
halol_crypto_bot/
├── bot.py           # Asosiy bot, handlerlar, job scheduler
├── scanner.py       # Binance API, market cache, scanner
├── signals.py       # Signal tizimi, scoring engine
├── charts.py        # Grafik generatsiya (matplotlib)
├── database.py      # SQLite, barcha DB operatsiyalar
├── config.py        # Konfiguratsiya, constantlar
├── utils.py         # Yordamchi funksiyalar, menyular
├── requirements.txt # Python kutubxonalari
├── .env.example     # Muhit o'zgaruvchilari namunasi
├── .env             # Sizning muhit o'zgaruvchilaringiz (git'ga kiritmang!)
├── README.md        # Hujjatlar
└── halol_crypto.db  # SQLite bazasi (avtomatik yaratiladi)
```

---

## Texnik detallar

### Arxitektura

```
Binance API → Scanner → MarketCache
                              ↓
                         Signals Engine
                              ↓
                    ┌─────────────────┐
                    │  Job Scheduler  │
                    │  (APScheduler)  │
                    └─────────────────┘
                              ↓
                    ┌─────────────────┐
                    │   Telegram Bot  │
                    │  (PTB + asyncio)│
                    └─────────────────┘
```

### Cache tizimi

- Narxlar: har 30 soniyada yangilanadi
- Market cache: har 60 soniyada
- Kline data: har 60 soniyada

### Job scheduler

| Vazifa | Interval | Tavsif |
|--------|----------|--------|
| Market scan | 60s | Barcha coinlar narxi |
| Kuchli signal alert | 5 min | Kuchli signallarni yuborish |
| Watchlist update | 10 min | Foydalanuvchi coinlari |
| Tozalash | Kuniga 1 | Eski yozuvlar |

### Scoring tizimi

| Indikator | Max ball |
|-----------|----------|
| RSI tahlili | ±4 |
| EMA trend | ±6 |
| EMA kesishish | ±3 |
| MACD | ±3 |
| Hajm | +3 |
| Breakout | ±2 |
| Bollinger Bands | ±2 |
| 24h o'zgarish | ±1 |

**Jami max: ±24**

Signal turlar:
- ≥8: KUCHLI SOTIB OLISH 🟢
- 4-7: SOTIB OLISH 🟢
- -3 dan +3: KUTISH 🟡
- -4 dan -7: SOTISH 🔴
- ≤-8: KUCHLI SOTISH 🔴

---

## Muammolarni hal qilish

### Bot ishlamaydi

```bash
# Token to'g'riligini tekshiring
echo $TELEGRAM_BOT_TOKEN

# Logni ko'ring
tail -f bot.log
```

### Narxlar ko'rinmaydi

Bot dastlabki scan uchun 10-60 soniya kutadi.
Internet ulanishini tekshiring.

### Grafik yaratilmaydi

```bash
pip install matplotlib --upgrade
```

### Rate limit xatosi

Binance ommaviy API limitlari mavjud. Bot avtomatik retry qiladi.

---

## Xavfsizlik

- `.env` faylini hech qachon git'ga kiritmang
- `.gitignore` ga qo'shing:
  ```
  .env
  *.db
  *.log
  __pycache__/
  venv/
  ```
- Bot tokeningizni hech kim bilan ulashmang

---

## Litsenziya

Bu loyiha ta'lim maqsadida yaratilgan. Kripto valyuta savdosi yuqori xavf talab qiladi. Barcha signallar ta'lim maqsadida bo'lib, moliyaviy maslahat emas.
