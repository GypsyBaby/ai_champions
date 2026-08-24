# Портал управления портфелем AI-инициатив (v2)

## Запуск

```bash
docker compose up -d --build
```

- Портал: http://localhost:8080
- API напрямую: http://localhost:8000/docs


Пересобрать и пересоздать контейнеры с нуля:

```bash
docker compose up -d --build --force-recreate
```

Полностью сбросить данные: `docker compose down && rm -rf ./data`.

## Локальная разработка без Docker

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DATA_DIR=./data uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
python3 -m http.server 8080
```

При запуске без nginx-прокси поменяйте `API_BASE` в `frontend/script.js` с `/api` на
`http://localhost:8000`.
