# Name-based Gender Detector — Render Deploy

Flask API that guesses gender from an Instagram username/full name
(Korean + Japanese + global names). See the chat for the full step-by-step
Render + Google Sheets setup guide.

## Render settings (paste these into the Render dashboard — no Dockerfile needed)

- **Environment:** Python 3
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`

## Endpoints (once deployed, your URL looks like `https://your-app-name.onrender.com`)

- `GET /health` — check it's alive
- `POST /predict` — `{"username": "...", "full_name": "..."}`
- `POST /predict_batch` — `{"rows": [{"username":.., "full_name":..}, ...]}` (max 200/call)

## Note on Render's free tier

Free Web Services "sleep" after ~15 minutes of no traffic. The **first**
request after sleeping takes 30-50 seconds to wake up — this is normal, not
an error. Subsequent requests are fast.
