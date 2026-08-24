# Модель данных

Кратко и схематично: ключевые сущности, их поля и связи. Имена — как в `backend/app/models.py`
(SQLAlchemy, SQLite). Один backend-процесс, без отдельного слоя миграций (см. `migrations.py`).

## Диаграмма

```mermaid
erDiagram
  DEPARTMENT {
    int id PK
    string name
  }
  EMPLOYEE {
    int id PK
    string full_name
    string role
    int department_id FK
    string email
  }
  RESOURCE {
    int id PK
    string name
    string category
    string unit
    float rate
    int team_lead_id FK
  }
  INITIATIVE {
    int id PK
    string title
    text description
    int champion_id FK
    int department_id FK
    date start_date
    date end_date
    bool is_approved
    string approval_stage
  }
  RESOURCE_ENTRY {
    int id PK
    int initiative_id FK
    int resource_id FK
    float quantity
    bool is_planned
  }
  BENEFIT {
    int id PK
    int initiative_id FK
    int resource_id FK
    float quantity
  }
  COST_LOG {
    int id PK
    int initiative_id FK
    int resource_id FK
    int champion_id FK
    float quantity
  }
  APPROVAL {
    int id PK
    int initiative_id FK
    int actor_id FK
    string status
    text comment
  }
  PENDING_APPROVER {
    int id PK
    int initiative_id FK
    int employee_id FK
    int resource_id FK
    string status
  }
  COMMENT {
    int id PK
    int initiative_id FK
    int author_id FK
    text text
  }
  ATTACHMENT {
    int id PK
    int initiative_id FK
    int uploader_id FK
    string filename
    string stored_name
    int size
  }
  NOTIFICATION {
    int id PK
    int recipient_id FK
    string message
    string type
    bool is_read
  }
  REMINDER_RUN {
    int id PK
    date run_date
  }

  DEPARTMENT ||--o{ EMPLOYEE : "department_id"
  DEPARTMENT ||--o{ INITIATIVE : "department_id"
  EMPLOYEE ||--o{ INITIATIVE : "champion_id"
  EMPLOYEE |o--o| RESOURCE : "team_lead_id (role=teamlead)"

  INITIATIVE ||--o{ RESOURCE_ENTRY : "has"
  RESOURCE ||--o{ RESOURCE_ENTRY : "used in"
  INITIATIVE ||--o{ BENEFIT : "has"
  RESOURCE ||--o{ BENEFIT : "used in"
  INITIATIVE ||--o{ COST_LOG : "has"
  RESOURCE ||--o{ COST_LOG : "used in"
  EMPLOYEE ||--o{ COST_LOG : "champion_id"
  INITIATIVE ||--o{ APPROVAL : "has"
  EMPLOYEE ||--o{ APPROVAL : "actor_id"
  INITIATIVE ||--o{ PENDING_APPROVER : "has"
  EMPLOYEE ||--o{ PENDING_APPROVER : "employee_id"
  RESOURCE ||--o{ PENDING_APPROVER : "used in"
  INITIATIVE ||--o{ COMMENT : "has"
  EMPLOYEE ||--o{ COMMENT : "author_id"
  INITIATIVE ||--o{ ATTACHMENT : "has"
  EMPLOYEE ||--o{ ATTACHMENT : "uploader_id"
  EMPLOYEE ||--o{ NOTIFICATION : "recipient_id"
```

`REMINDER_RUN` не связана ни с чем — это просто отметка «в этот календарный день напоминания уже
разосланы» (см. `PRODUCT_OVERVIEW.md`, раздел 5).

## Сущности вкратце

| Сущность | Что это | Ключевые связи |
|---|---|---|
| **Department** | Подразделение | ← Employee, ← Initiative |
| **Employee** | Сотрудник; `role` = champion/head/pm/top/teamlead | → Department; ← Initiative (чемпион), ← Resource (team_lead) |
| **Resource** | Специализация человеческих ресурсов или технический ресурс; `category` = human/tech, `rate` — ₽/ед. | → Employee (team_lead, только для human) |
| **Initiative** | Инициатива: заявка + текущий статус цепочки согласования (`is_approved`, `approval_stage`) | → Employee (champion), → Department; ← всё остальное ниже |
| **ResourceEntry** | Одна строка плановых ресурсов инициативы («Человеко-часы» / «Плановые технические ресурсы»); `is_planned` отличает план от факта | → Initiative, → Resource |
| **Benefit** | Одна строка ожидаемой выгоды («Ожидаемая выгода») | → Initiative, → Resource |
| **CostLog** | Запись фактически потраченных часов | → Initiative, → Resource, → Employee (champion) |
| **Approval** | Запись в истории согласований (одно решение: approved/rejected/revision) | → Initiative, → Employee (actor) |
| **PendingApprover** | Кто именно должен согласовать инициативу на текущем круге TeamLead-этапа | → Initiative, → Employee, → Resource |
| **Comment** | Комментарий к карточке инициативы | → Initiative, → Employee (author) |
| **Attachment** | Прикреплённый файл (сам файл — на диске в `DATA_DIR/attachments/`) | → Initiative, → Employee (uploader) |
| **Notification** | Уведомление сотруднику (`type` = info/reminder) | → Employee (recipient) |
| **ReminderRun** | Отметка «напоминания за эту дату уже отправлены» | — |

## Что стоит помнить

- **Initiative — центр модели**: почти все остальные сущности (кроме Department/Employee/Resource)
  существуют только в привязке к конкретной инициативе и удаляются каскадно вместе с ней.
- **Employee — единственная сущность с ролями**: одна таблица на все пять ролей, разделение
  поведения — на уровне приложения (`role`), не отдельными таблицами.
- **Resource — общий на весь портал справочник**, а не часть инициативы: ставка (`rate`) и
  привязка TeamLead-а (`team_lead_id`) меняются глобально и сразу влияют на все инициативы,
  которые этот ресурс используют.
- **ResourceEntry vs Benefit vs CostLog** — три разных «среза» вокруг одной пары
  (Initiative, Resource): план (`ResourceEntry.is_planned=True`), ожидаемая выгода (`Benefit`),
  факт (`CostLog`, только человеческие ресурсы).
- **Approval — история (append-only), PendingApprover — текущее состояние.** Approval никогда не
  удаляется (аудит); PendingApprover пересоздаётся заново на каждом круге согласования.
