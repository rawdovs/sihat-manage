# 🤖 Shaxsiy Biznes-Ekotizim Bot (Telegram)

Dasturchi uchun shaxsiy yordamchi: mijoz bilan **sotuv muzokarasi**, **loyiha boshqaruvi**,
**GitHub commit / ovozli xabar tahlili**, **avtomatik progress hisoblash**, har kuni
**09:00 risk-analitika** va **21:00 progress so'rovi**. Ichida Claude (Anthropic) ishlaydi.

---

## ⚙️ Imkoniyatlar

| Funksiya | Tavsif |
|---|---|
| **Sotuv rejimi** | Mijoz bilan dasturchi nomidan gaplashadi, loyiha/narx/muddatni aniqlaydi va kelishuvда loyihani avtomatik yaratadi (`CREATE_PROJECT`). |
| **Deep Work** | Yoqilganda mijozga to'g'ridan-to'g'ri javob bermaydi — javobni avval sizga tasdiqlashga yuboradi (✅/❌ tugmalar). |
| **Progress tahlili** | Matn, ovozli xabar yoki GitHub commit asosida bajarilgan ishni baholaydi va progressni yangilaydi (`UPDATE_PROGRESS`). |
| **09:00 analitika** | Matematik risk tahlili: vaqtning 70%+ o'tib progress 50%dan past bo'lsa — `CRITICAL RISK`. Moliya, commitlar, bitta strategik maslahat. |
| **21:00 so'rov** | Kun yakunida progress so'raydi. |

> Bot hech qachon o'zini AI/bot demaydi, Telegram komandalaridan foydalanmaydi va
> sizning ruxsatingizsiz narx tushirmaydi — bularning hammasi system prompt'da qat'iy belgilangan.

---

## 🚀 O'rnatish

```bash
# 1. Bog'liqliklarni o'rnatish
pip install -r requirements.txt

# 2. Sozlamalar faylini tayyorlash
cp .env.example .env
#   .env ichini to'ldiring (token, API key)

# 3. Ishga tushirish
python main.py
```

### Kerakli kalitlar
- **TELEGRAM_BOT_TOKEN** — [@BotFather](https://t.me/BotFather) dan bot yaratib oling.
- **ANTHROPIC_API_KEY** — https://console.anthropic.com dan.
- **DEVELOPER_CHAT_ID** — birinchi marta bo'sh qoldiring. Botni ishga tushirib, unga
  bironta xabar yozing. Terminalda `Chat ID: 123456789` chiqadi — shu raqamni `.env` ga
  yozing va botni qayta ishga tushiring. Endi 09:00/21:00 hisobotlari sizga keladi.

### Ixtiyoriy
- **Ovozli xabar:** `.env` ga `OPENAI_API_KEY` qo'shing (Whisper orqali transkripsiya).
- **GitHub commit kuzatuvi:** repozitoriy → Settings → Webhooks → `http://SERVER:8080/github`,
  Content type `application/json`, Secret = `.env` dagi `GITHUB_WEBHOOK_SECRET`.
  Loyihani GitHub repo bilan bog'lash uchun bazadagi `projects.github_repo` ustuniga
  `egasi/repo` formatида nom yozing.

---

## 🧩 Tuzilma

```
main.py        — kirish nuqtasi (polling + webhook + jadval birga)
core.py        — Bot va Dispatcher obyektlari
config.py      — .env dan barcha sozlamalar
prompts.py     — system prompt va 09:00 hisobot andozasi
database.py    — SQLite (loyihalar, to'lovlar, izohlar, approval)
llm.py         — Claude chaqiruvi + JSON action ajratish
actions.py     — CREATE_PROJECT / UPDATE_PROGRESS / SET_MODE
reports.py     — 09:00 risk-analitika matematikasi
scheduler.py   — 09:00 va 21:00 vazifalari
webhook.py     — GitHub push hodisasi
transcribe.py  — ovozli xabar (Whisper, ixtiyoriy)
```

## 🔄 Action kontrakti (Claude → backend)
Claude javob oxiriga JSON qo'shadi, backend o'qib bajaradi:
```json
{"action": "CREATE_PROJECT", "project_name": "...", "price_usd": 1500, "duration_days": 20, "tasks": ["..."]}
{"action": "UPDATE_PROGRESS", "project_name": "...", "add_progress_percent": 10, "developer_note": "..."}
{"action": "PENDING_APPROVAL", "target_client": "@username"}
{"action": "SET_MODE", "deep_work": true}
```

## ⚠️ Eslatmalar
- **Model nomi:** `ANTHROPIC_MODEL` ni joriy hujjatlar bilan tekshiring — https://docs.claude.com .
- **Xavfsizlik:** `.env` ni hech qachon git'ga qo'shmang (`.gitignore` ga kiriting).
- **Production:** webhook uchun HTTPS (masalan, nginx reverse-proxy yoki Cloudflare Tunnel) ishlating.
- Hozircha to'lov holati (`paid`) qo'lda yangilanadi — invoice/PDF integratsiyasini keyin qo'shsa bo'ladi.
