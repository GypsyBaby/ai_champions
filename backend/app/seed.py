import random
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from . import models

HUMAN_RESOURCES = [
    ("Разработчик", "чел-часы"),
    ("СисАдмин", "чел-часы"),
    ("Тестировщик", "чел-часы"),
    ("Аналитик", "чел-часы"),
    ("ML-инженер", "чел-часы"),
]
TECH_RESOURCES = [
    ("CPU", "ядра"),
    ("GPU", "ядра (H100-экв.)"),
    ("RAM", "ГБ"),
    ("Disk", "ТБ"),
]
TEAM_LEAD_NAMES = {
    "Разработчик": "Кирилл Данилов",
    "СисАдмин": "Юрий Захаров",
    "Тестировщик": "Марина Соловьёва",
    "Аналитик": "Алексей Козлов",
    "ML-инженер": "Екатерина Новикова",
}
TECH_PLANNED_RANGE = {"CPU": (1, 16), "GPU": (1, 8), "RAM": (16, 512), "Disk": (1, 10)}
TECH_BENEFIT_RANGE = {"CPU": (1, 4), "GPU": (1, 2), "RAM": (8, 64), "Disk": (1, 2)}

DEPARTMENT_NAMES = [
    "Разработка", "Аналитика", "Инфраструктура", "Продажи",
    "Маркетинг", "Финансы", "Клиентский сервис",
]

HEAD_NAMES = {
    "Разработка": "Ольга Петрова",
    "Аналитика": "Павел Волков",
    "Инфраструктура": "Николай Кузьмин",
    "Продажи": "Светлана Орлова",
    "Маркетинг": "Артём Беляев",
    "Финансы": "Ирина Соколова",
    "Клиентский сервис": "Максим Титов",
}

CHAMPION_DEFS = [
    ("Анна Иванова", "Разработка"),
    ("Сергей Морозов", "Разработка"),
    ("Дмитрий Смирнов", "Аналитика"),
    ("Елена Кузнецова", "Аналитика"),
    ("Виктор Лебедев", "Инфраструктура"),
    ("Наталья Фролова", "Продажи"),
    ("Роман Гусев", "Продажи"),
    ("Ольга Никитина", "Маркетинг"),
    ("Андрей Воробьёв", "Финансы"),
    ("Татьяна Егорова", "Клиентский сервис"),
]

INITIATIVE_TITLES = [
    "Чат-бот поддержки клиентов",
    "Автоматизация отчётности",
    "Прогнозирование оттока клиентов",
    "Оптимизация облачной инфраструктуры",
    "Внедрение LLM-ассистента для junior-разработчиков",
    "Автоматическая классификация обращений",
    "Персонализация email-рассылок",
    "Скоринг лидов на основе ML",
    "Автогенерация описаний товаров",
    "Оптимизация логистических маршрутов",
    "Прогноз спроса на складе",
    "Автоматизация проверки договоров",
    "Голосовой помощник для колл-центра",
    "Детекция мошеннических транзакций",
    "Оптимизация ценообразования",
    "Автоматическое тегирование контента",
    "ML-модель прогноза выручки",
    "Ассистент для подбора персонала",
    "Автоматизация тестирования ПО",
    "Анализ тональности отзывов",
    "Рекомендательная система для сайта",
    "Автоматизация бухгалтерских проводок",
    "Прогноз оттока сотрудников",
    "Оптимизация рекламных кампаний",
    "Автоматическая модерация контента",
    "Компьютерное зрение для контроля качества",
    "Чат-бот для внутренней техподдержки",
    "Прогнозирование поломок оборудования",
    "Автоматизация онбординга клиентов",
    "ML-модель оценки кредитного риска",
    "Оптимизация штата call-центра",
    "Автосуммаризация встреч",
    "Детекция аномалий в транзакциях",
    "Персонализация витрины интернет-магазина",
    "Автоматизация закупок",
    "Прогноз загрузки склада",
    "Ассистент для юридического отдела",
    "Оптимизация расписания сотрудников",
    "Генерация отчётов для инвесторов",
    "Умный поиск по базе знаний",
]

DESCRIPTION_TEMPLATES = [
    "Применение машинного обучения для решения задачи: {t}.",
    "Пилотный проект по внедрению AI-модели: {t}.",
    "Автоматизация процесса с использованием ИИ: {t}.",
    "Разработка и внедрение AI-решения: {t}.",
]

# Hand-crafted approval histories for a handful of initiatives so their cards
# show a realistic back-and-forth instead of a single decision.
RICH_HISTORIES = {
    2: [  # revision -> revision -> approved
        ("revision", "Нужно уточнить бюджет и состав команды.", 40),
        ("revision", "Спасибо за правки, но всё ещё не хватает данных по ROI.", 28),
        ("approved", "Теперь всё устраивает, согласовано.", 15),
    ],
    9: [  # rejected -> revision -> approved (persistence pays off)
        ("rejected", "В текущем виде экономический эффект не обоснован.", 55),
        ("revision", "Ок, пересмотрели — пришлите обновлённый расчёт выгоды.", 40),
        ("approved", "Расчёт выгоды теперь убедительный, согласовано.", 20),
    ],
    16: [  # revision -> rejected (didn't make it)
        ("revision", "Слишком большой объём GPU для пилота — сократите охват.", 35),
        ("rejected", "После пересмотра всё равно не укладываемся в бюджет квартала. Вернёмся к этому позже.", 12),
    ],
    24: [  # approved -> champion edits plan (auto-revision) -> re-approved
        ("approved", "Согласовано, метрики устраивают.", 60),
        ("revision", "Отправлено на пересмотр чемпионом в связи с изменением ресурсов/выгоды.\n\n"
                      "Плановые ресурсы:\nML-инженер: 120 → 220 чел-часы\nGPU: 2 → 4 ядра (H100-экв.)", 30, "champion"),
        ("approved", "Расширенный охват обоснован, согласовано повторно.", 18),
    ],
    33: [  # rejected twice, then approved
        ("rejected", "Похожая инициатива уже в пилоте в другом подразделении — нужна дифференциация.", 70),
        ("rejected", "Дифференциация всё ещё не очевидна.", 50),
        ("approved", "Теперь позиционирование понятно, согласовано.", 25),
    ],
}

COMMENT_EXCHANGES = [
    ("head", "Отличная инициатива, поддерживаю направление."),
    ("champion", "Спасибо! Готовы стартовать пилот в ближайшие недели."),
    ("head", "Уточните, пожалуйста, сроки первых измеримых результатов."),
    ("champion", "Ожидаем первые метрики через 4-6 недель после старта."),
    ("head", "Хорошо, держите в курсе прогресса."),
    ("champion", "Обязательно, будем присылать апдейты."),
]


def seed_data(db: Session) -> None:
    if db.query(models.Department).count() > 0:
        return  # already seeded

    rng = random.Random(42)
    today = date.today()

    # --- Departments ---
    departments = {}
    for name in DEPARTMENT_NAMES:
        d = models.Department(name=name)
        db.add(d)
        db.flush()
        departments[name] = d

    # --- Resources ---
    resources = {}
    for name, unit in HUMAN_RESOURCES:
        r = models.Resource(name=name, category="human", unit=unit)
        db.add(r)
        db.flush()
        resources[name] = r
    for name, unit in TECH_RESOURCES:
        r = models.Resource(name=name, category="tech", unit=unit)
        db.add(r)
        db.flush()
        resources[name] = r

    # --- Employees ---
    heads = {}
    for dept_name, full_name in HEAD_NAMES.items():
        h = models.Employee(
            full_name=full_name, position=f"Руководитель: {dept_name}",
            department_id=departments[dept_name].id,
            email=f"{full_name.split()[0].lower()}@company.ru", role="head",
        )
        db.add(h)
        db.flush()
        heads[dept_name] = h

    champions = []  # list of (Employee, dept_name)
    for full_name, dept_name in CHAMPION_DEFS:
        c = models.Employee(
            full_name=full_name, position="AI-чемпион", department_id=departments[dept_name].id,
            email=f"{full_name.split()[0].lower()}@company.ru", role="champion",
        )
        db.add(c)
        db.flush()
        champions.append((c, dept_name))

    pm = models.Employee(
        full_name="Мария Кузнецова", position="Portfolio Manager", department_id=None,
        email="m.kuznetsova@company.ru", role="pm",
    )
    top = models.Employee(
        full_name="Игорь Соколов", position="Директор по цифровизации", department_id=None,
        email="i.sokolov@company.ru", role="top",
    )
    db.add_all([pm, top])

    # --- TeamLeads: one per human-resource specialization ---
    for resource_name, full_name in TEAM_LEAD_NAMES.items():
        lead = models.Employee(
            full_name=full_name, position=f"Тимлид: {resource_name}", department_id=None,
            email=f"{full_name.split()[0].lower()}@company.ru", role="teamlead",
        )
        db.add(lead)
        db.flush()
        resources[resource_name].team_lead_id = lead.id

    db.commit()

    def notify(recipient_id, message, created_at, is_read=False):
        db.add(models.Notification(
            recipient_id=recipient_id, message=message, is_read=is_read, created_at=created_at,
        ))

    def pick_end_date(i):
        """Spread end dates across five buckets so the deadline warnings and
        payback figures have realistic, varied data to show off."""
        bucket = i % 5
        if bucket == 0:
            return today - timedelta(days=rng.randint(3, 45))          # overdue
        if bucket == 1:
            return today + timedelta(days=rng.randint(1, 13))          # due very soon
        if bucket == 2:
            return today + timedelta(days=rng.randint(20, 60))
        if bucket == 3:
            return today + timedelta(days=rng.randint(60, 180))
        return today + timedelta(days=rng.randint(180, 300))

    initiatives = []
    for i, title in enumerate(INITIATIVE_TITLES):
        champion, dept_name = champions[i % len(champions)]
        department = departments[dept_name]
        description = DESCRIPTION_TEMPLATES[i % len(DESCRIPTION_TEMPLATES)].format(t=title[0].lower() + title[1:])

        end_date = pick_end_date(i)
        duration = rng.randint(30, 150)
        start_date = end_date - timedelta(days=duration)
        created_date = min(start_date - timedelta(days=rng.randint(2, 15)), today - timedelta(days=1))
        if i in RICH_HISTORIES:
            # These get a multi-step approval history — make sure the record is
            # old enough that none of those steps would predate its creation.
            oldest_step = max(entry[2] for entry in RICH_HISTORIES[i])
            created_date = min(created_date, today - timedelta(days=oldest_step + rng.randint(15, 40)))
        created_at = datetime.combine(created_date, datetime.min.time()) + timedelta(hours=rng.randint(8, 18))
        age_days = (today - created_date).days

        ini = models.Initiative(
            title=title, description=description, champion_id=champion.id, department_id=department.id,
            start_date=start_date, end_date=end_date, created_at=created_at, updated_at=created_at,
        )
        db.add(ini)
        db.flush()

        # Planned resources: 2-3 human specializations + 1-3 technical resources.
        human_names = rng.sample([n for n, _ in HUMAN_RESOURCES], k=rng.randint(2, 3))
        for name in human_names:
            db.add(models.ResourceEntry(
                initiative_id=ini.id, resource_id=resources[name].id,
                quantity=float(rng.randint(40, 500)), is_planned=True,
            ))
        tech_names = rng.sample([n for n, _ in TECH_RESOURCES], k=rng.randint(1, 3))
        for name in tech_names:
            lo, hi = TECH_PLANNED_RANGE[name]
            db.add(models.ResourceEntry(
                initiative_id=ini.id, resource_id=resources[name].id,
                quantity=float(rng.randint(lo, hi)), is_planned=True,
            ))

        # Benefits: most initiatives expect some monthly savings; a few
        # deliberately have none, to keep the "payback undefined" case represented.
        if i % 7 != 0:
            benefit_human = rng.sample(human_names, k=1)
            for name in benefit_human:
                db.add(models.Benefit(initiative_id=ini.id, resource_id=resources[name].id,
                                       quantity=float(rng.randint(10, 80))))
            if tech_names and rng.random() < 0.5:
                name = rng.choice(tech_names)
                lo, hi = TECH_BENEFIT_RANGE[name]
                db.add(models.Benefit(initiative_id=ini.id, resource_id=resources[name].id,
                                       quantity=float(rng.randint(lo, hi))))

        db.flush()
        initiatives.append((ini, champion, department, dept_name, human_names, created_at, age_days))

        _notify_heads_new_initiative(notify, heads, dept_name, ini, champion, created_at)

    db.commit()

    # --- Approval histories (a hand-picked few get a multi-step back-and-forth) ---
    for i, (ini, champion, department, dept_name, human_names, created_at, age_days) in enumerate(initiatives):
        head = heads[dept_name]
        cap = max(1, age_days - 1)  # never timestamp an approval before the record existed
        history = RICH_HISTORIES.get(i)
        if history:
            for entry in history:
                status, comment, days_ago = entry[0], entry[1], entry[2]
                actor = champion if len(entry) > 3 and entry[3] == "champion" else head
                _add_approval(db, ini, champion, actor, status, comment, min(days_ago, cap), notify)
            continue

        bucket = i % 10
        if bucket < 4:  # 40% approved
            _add_approval(db, ini, champion, head, "approved", "Согласовано, метрики устраивают.",
                          min(rng.randint(3, 60), cap), notify)
        elif bucket < 6:  # 20% never reviewed yet
            pass
        elif bucket < 8:  # 20% rejected
            _add_approval(db, ini, champion, head, "rejected",
                          "Экономический эффект пока не обоснован, к идее можно вернуться позже.",
                          min(rng.randint(3, 40), cap), notify)
        else:  # 20% sent to revision
            _add_approval(db, ini, champion, head, "revision",
                          "Пришлите, пожалуйста, более детальный расчёт плановых ресурсов.",
                          min(rng.randint(3, 40), cap), notify)

    db.commit()

    # --- Comment threads ---
    for i, (ini, champion, department, dept_name, human_names, created_at, age_days) in enumerate(initiatives):
        head = heads[dept_name]
        if i in RICH_HISTORIES:
            thread = COMMENT_EXCHANGES
        elif ini.is_approved and i % 3 == 0:
            thread = COMMENT_EXCHANGES[:2]
        else:
            continue
        cap = max(1, age_days - 1)
        for j, (who, text) in enumerate(thread):
            author = head if who == "head" else champion
            offset = min(5 + j * 3, cap)
            db.add(models.Comment(
                initiative_id=ini.id, author_id=author.id, text=text,
                created_at=created_at + timedelta(days=offset, hours=rng.randint(1, 10)),
            ))

    db.commit()

    # --- Time logging (actual human-hours) on approved initiatives ---
    for i, (ini, champion, department, dept_name, human_names, created_at, age_days) in enumerate(initiatives):
        if not ini.is_approved:
            continue
        cap = max(1, age_days - 1)
        planned_by_name = {
            e.resource_id: e.quantity for e in ini.resource_entries if e.is_planned
        }
        log_names = human_names[: rng.randint(1, len(human_names))]
        for name in log_names:
            resource = resources[name]
            planned_qty = planned_by_name.get(resource.id, 100)
            # Most logged progress stays under plan; occasionally overshoot it
            # so the "Плановое значение превышено" warning has real examples too.
            fraction = rng.uniform(1.05, 1.3) if i % 13 == 0 else rng.uniform(0.2, 0.9)
            entries = rng.randint(1, 3)
            remaining = planned_qty * fraction
            for k in range(entries):
                chunk = remaining / (entries - k) if k < entries - 1 else remaining
                chunk = max(1.0, round(chunk, 1))
                remaining -= chunk
                offset = min(10 + k * 7, cap)
                db.add(models.CostLog(
                    initiative_id=ini.id, resource_id=resource.id, champion_id=champion.id,
                    quantity=chunk,
                    created_at=created_at + timedelta(days=offset, hours=rng.randint(1, 10)),
                ))

    db.commit()


def _notify_heads_new_initiative(notify, heads, dept_name, ini, champion, created_at):
    head = heads.get(dept_name)
    if head:
        notify(
            head.id,
            f"Новая инициатива «{ini.title}» от {champion.full_name} ожидает согласования.",
            created_at, is_read=True,
        )


def _add_approval(db, ini, champion, actor, status, comment, days_ago, notify):
    when = datetime.utcnow() - timedelta(days=days_ago)
    db.add(models.Approval(
        initiative_id=ini.id, actor_id=actor.id, status=status, comment=comment,
        created_at=when, updated_at=when,
    ))
    if status == "approved":
        ini.is_approved = True
        verdict = "согласована руководителем"
    elif status == "rejected":
        ini.is_approved = False
        verdict = "отклонена руководителем"
    else:
        ini.is_approved = False
        verdict = "отправлена на пересмотр"
    notify(champion.id, f"Инициатива «{ini.title}» {verdict}.", when, is_read=days_ago > 20)
