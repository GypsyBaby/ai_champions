# Схема

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'fontSize': '20px'}, 'flowchart': {'nodeSpacing': 50, 'rankSpacing': 70}}}%%
flowchart TB
    Browser["🖥️ Браузер сотрудника"]

    subgraph DC["Docker-compose стек (наша инфраструктура)"]
        direction TB
        Nginx["nginx контейнер\nстатика + reverse proxy /api/*"]
        Backend["backend контейнер\nFastAPI + фоновый asyncio-таск\n(еженедельные напоминания,\nсобытия согласования)"]
        DB[("SQLite\ndata/app.db")]
        Files[("Файлы вложений\ndata/attachments/")]
    end

    SMTP["✉️ Корпоративный SMTP-сервер\n(внешний, не наш)"]
    Mailbox["📬 Почтовый ящик\nсотрудника"]

    Browser -- "HTTP" --> Nginx
    Nginx -- "статика" --> Browser
    Nginx -- "/api/* proxy_pass" --> Backend
    Backend -- "SQL (чтение/запись)" --> DB
    Backend -- "чтение/запись файлов" --> Files
    Backend -- "SMTP" --> SMTP
    SMTP -- "доставка письма" --> Mailbox

    classDef plain fill:#f4f6f8,stroke:#6b7785,stroke-width:1px,color:#1f2933;
    classDef ours fill:#eef2ff,stroke:#4f46e5,stroke-width:1px,color:#1e1b4b;
    classDef external fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#78350f;

    class Browser plain;
    class Nginx,Backend,DB,Files ours;
    class SMTP,Mailbox external;
```

*(синий — наш docker-compose стек; жёлтый — внешние системы вне нашего контроля)*

## Стек

Backend: Python 3.11, FastAPI, SQLAlchemy (ORM), SQLite (файл на диске), Uvicorn (ASGI), openpyxl (Excel), python-multipart (загрузка файлов). 

БД — SQLite встроен в backend-контейнер.

Frontend: чистый JS/HTML/CSS, без фреймворка и без сборки — один файл script.js. Графики — на <canvas>, самописные, без библиотек.

Инфраструктура: nginx (отдаёт статику + проксирует /api/*), Docker/docker-compose (2 контейнера: backend, frontend).