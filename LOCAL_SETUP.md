# FitAI Backend — Local Setup (no Docker, no Ollama)

## Prerequisites

- **Python 3.11+** — `brew install python@3.11`
- **Groq API key** — free at [console.groq.com](https://console.groq.com) → Create API Key

No model downloads. No Ollama. AI runs in the cloud via Groq's free tier.

---

## 1. Get your free Groq API key

**Website:** https://console.groq.com

Step-by-step:

1. Open **https://console.groq.com** in your browser
2. Click **Sign Up** (top right) — use Google, GitHub, or email
3. After logging in, click **API Keys** in the left sidebar
4. Click **Create API Key**
5. Give it any name (e.g. `fitai`)
6. Copy the key — it starts with `gsk_...`
7. Open `fitai-backend/.env` and paste it:

```env
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> Free tier gives you 14,400 requests/day and 500,000 tokens/minute — more than enough.

---

## 2. Set up Python environment

```bash
cd fitai-backend

python3.11 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

---

## 3. Add your API key to `.env`

Open `fitai-backend/.env` and replace the placeholder:

```env
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 4. Run the backend

```bash
cd fitai-backend
source .venv/bin/activate

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

API available at `http://localhost:8000` — Swagger docs at `http://localhost:8000/docs`

---

## 5. Update the app API URL

Find your Mac's local IP:
```bash
ipconfig getifaddr en0
```

Set it in `FitAI/.env.development`:
```env
EXPO_PUBLIC_API_URL=http://<your-mac-ip>:8000
```

---

## Daily workflow

```bash
# Terminal 1 — Backend
cd fitai-backend
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Expo app
cd FitAI
npx expo start
```

---

## AI models used (Groq free tier)

| Task | Model |
|------|-------|
| Chat, nutrition text, workout plans | `llama-3.1-8b-instant` |
| Food photo recognition | `llama-3.2-11b-vision-preview` |

Fast, free, no local RAM usage.
