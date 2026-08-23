from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from . import models


def seed_data(db: Session) -> None:
    if db.query(models.Department).count() > 0:
        return  # already seeded

    # --- Departments ---
    dept_names = ["Разработка", "Аналитика", "Инфраструктура"]
    departments = {}
    for name in dept_names:
        d = models.Department(name=name)
        db.add(d)
        db.flush()
        departments[name] = d

    # --- Resources ---
    human_resources = [
        ("Разработчик", "чел-часы"),
        ("СисАдмин", "чел-часы"),
        ("Тестировщик", "чел-часы"),
        ("Аналитик", "чел-часы"),
        ("ML-инженер", "чел-часы"),
    ]
    tech_resources = [
        ("CPU", "ядра"),
        ("GPU", "ядра (H100-экв.)"),
        ("RAM", "ГБ"),
        ("Disk", "ТБ"),
    ]
    resources = {}
    for name, unit in human_resources:
        r = models.Resource(name=name, category="human", unit=unit)
        db.add(r)
        db.flush()
        resources[name] = r
    for name, unit in tech_resources:
        r = models.Resource(name=name, category="tech", unit=unit)
        db.add(r)
        db.flush()
        resources[name] = r

    # --- Employees ---
    champion1 = models.Employee(
        full_name="Анна Иванова", position="AI-евангелист", department_id=departments["Разработка"].id,
        email="a.ivanova@company.ru", role="champion",
    )
    champion2 = models.Employee(
        full_name="Дмитрий Смирнов", position="Ведущий аналитик", department_id=departments["Аналитика"].id,
        email="d.smirnov@company.ru", role="champion",
    )
    head1 = models.Employee(
        full_name="Ольга Петрова", position="Руководитель разработки", department_id=departments["Разработка"].id,
        email="o.petrova@company.ru", role="head",
    )
    head2 = models.Employee(
        full_name="Павел Волков", position="Руководитель аналитики", department_id=departments["Аналитика"].id,
        email="p.volkov@company.ru", role="head",
    )
    pm = models.Employee(
        full_name="Мария Кузнецова", position="Portfolio Manager", department_id=None,
        email="m.kuznetsova@company.ru", role="pm",
    )
    top = models.Employee(
        full_name="Игорь Соколов", position="Директор по цифровизации", department_id=None,
        email="i.sokolov@company.ru", role="top",
    )
    db.add_all([champion1, champion2, head1, head2, pm, top])
    db.commit()

    today = date.today()

    def d(offset_days):
        return today + timedelta(days=offset_days)

    def make_initiative(title, description, champion, department, start, end, planned, benefits_list):
        ini = models.Initiative(
            title=title,
            description=description,
            champion_id=champion.id,
            department_id=department.id,
            start_date=start,
            end_date=end,
        )
        db.add(ini)
        db.flush()
        for resource_name, qty in planned:
            db.add(models.ResourceEntry(
                initiative_id=ini.id, resource_id=resources[resource_name].id,
                quantity=qty, is_planned=True,
            ))
        for resource_name, qty in benefits_list:
            db.add(models.Benefit(initiative_id=ini.id, resource_id=resources[resource_name].id, quantity=qty))
        return ini

    ini1 = make_initiative(
        "Чат-бот поддержки клиентов",
        "Автоматизация первичной обработки обращений клиентов с помощью LLM-ассистента.",
        champion1, departments["Разработка"], d(-60), d(30),
        [("Разработчик", 400), ("Тестировщик", 80), ("GPU", 2), ("RAM", 64)],
        [("Разработчик", 50)],
    )
    db.flush()
    db.add(models.Approval(
        initiative_id=ini1.id, actor_id=head1.id, status="approved",
        comment="Согласовано, метрики окупаемости устраивают.",
        created_at=datetime.utcnow() - timedelta(days=50),
    ))
    ini1.is_approved = True

    ini2 = make_initiative(
        "Автоматизация отчётности",
        "Генерация еженедельных аналитических отчётов без ручной сборки данных.",
        champion2, departments["Аналитика"], d(-20), d(60),
        [("Аналитик", 200), ("ML-инженер", 100), ("CPU", 4)],
        [("Аналитик", 60)],
    )
    db.flush()
    db.add(models.Approval(
        initiative_id=ini2.id, actor_id=head2.id, status="revision",
        comment="Нужно уточнить объём исходных данных и источники.",
        created_at=datetime.utcnow() - timedelta(days=5),
    ))

    ini3 = make_initiative(
        "Прогнозирование оттока клиентов",
        "ML-модель для предсказания оттока и таргетированного удержания.",
        champion2, departments["Аналитика"], d(10), d(120),
        [("ML-инженер", 300), ("Аналитик", 100), ("GPU", 4), ("RAM", 128), ("Disk", 2)],
        [("Аналитик", 40), ("CPU", 2)],
    )

    ini4 = make_initiative(
        "Оптимизация облачной инфраструктуры",
        "Пересмотр конфигурации кластеров для снижения расходов на инфраструктуру.",
        champion1, departments["Разработка"], d(-90), d(-10),
        [("СисАдмин", 150), ("CPU", 8), ("RAM", 256)],
        [("CPU", 10), ("RAM", 64), ("Disk", 1)],
    )
    db.flush()
    db.add(models.Approval(
        initiative_id=ini4.id, actor_id=head1.id, status="approved",
        comment="Хороший ROI, согласовано.",
        created_at=datetime.utcnow() - timedelta(days=85),
    ))
    ini4.is_approved = True

    ini5 = make_initiative(
        "Внедрение LLM-ассистента для junior-разработчиков",
        "Ассистент для code review и онбординга младших разработчиков.",
        champion1, departments["Разработка"], d(0), d(150),
        [("Разработчик", 500), ("ML-инженер", 200), ("GPU", 8)],
        [],
    )
    db.flush()
    db.add(models.Approval(
        initiative_id=ini5.id, actor_id=head1.id, status="rejected",
        comment="Слишком дорого при текущем ROI, вернуться к идее через квартал.",
        created_at=datetime.utcnow() - timedelta(days=2),
    ))

    db.commit()

    # --- Comments ---
    db.add_all([
        models.Comment(initiative_id=ini1.id, author_id=head1.id,
                        text="Отличная инициатива, поддерживаю.",
                        created_at=datetime.utcnow() - timedelta(days=50)),
        models.Comment(initiative_id=ini1.id, author_id=champion1.id,
                        text="Спасибо, готовы начинать пилот.",
                        created_at=datetime.utcnow() - timedelta(days=49)),
        models.Comment(initiative_id=ini2.id, author_id=head2.id,
                        text="Пришлите, пожалуйста, список источников данных для отчётов.",
                        created_at=datetime.utcnow() - timedelta(days=5)),
        models.Comment(initiative_id=ini5.id, author_id=head1.id,
                        text="Предлагаю пересмотреть охват и вернуться с уменьшенным бюджетом GPU.",
                        created_at=datetime.utcnow() - timedelta(days=2)),
    ])

    # --- Notifications ---
    db.add_all([
        models.Notification(recipient_id=head1.id,
                             message="Новая инициатива «Чат-бот поддержки клиентов» от Анны Ивановой ожидает согласования.",
                             is_read=True, created_at=datetime.utcnow() - timedelta(days=60)),
        models.Notification(recipient_id=head2.id,
                             message="Новая инициатива «Автоматизация отчётности» от Дмитрия Смирнова ожидает согласования.",
                             is_read=False, created_at=datetime.utcnow() - timedelta(days=20)),
        models.Notification(recipient_id=champion2.id,
                             message="Инициатива «Автоматизация отчётности» отправлена на пересмотр.",
                             is_read=False, created_at=datetime.utcnow() - timedelta(days=5)),
        models.Notification(recipient_id=champion1.id,
                             message="Инициатива «Внедрение LLM-ассистента для junior-разработчиков» отклонена.",
                             is_read=False, created_at=datetime.utcnow() - timedelta(days=2)),
        models.Notification(recipient_id=head2.id,
                             message="Новая инициатива «Прогнозирование оттока клиентов» от Дмитрия Смирнова ожидает согласования.",
                             is_read=False, created_at=datetime.utcnow()),
    ])

    db.commit()
