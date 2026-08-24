/* ===================== Constants & state ===================== */

const API_BASE = "/api";
const SESSION_KEY = "ai_portal_v2_session";

const ROLE_LABELS = {
  champion: "AI-чемпион",
  head: "Руководитель подразделения",
  pm: "PM",
  top: "Топ-менеджмент",
  teamlead: "TeamLead",
};

// TeamLead's role label alone doesn't say which specialization they lead —
// append it (e.g. "TeamLead, ML-инженер") whenever it's known.
function roleLabel(role, specialization) {
  const label = ROLE_LABELS[role] || role;
  return role === "teamlead" && specialization ? `${label}, ${specialization}` : label;
}

// Mirrors backend/app/routers/reports.py STATUS_LABELS — must match the
// server's precedence exactly, since it's used as a filter value there.
const REPORT_STATUS_LABELS = {
  approved: "Согласовано",
  revision: "На пересмотре",
  rejected: "Отклонено",
  pending_head: "Ожидает согласования руководителя",
  pending_teamlead: "Ожидает согласования TeamLead",
  pending_top: "Ожидает согласования топ-менеджмента",
};

const state = {
  employeeId: null,
  fullName: null,
  role: null,
  specialization: null,
  departmentId: null,
  departmentName: null,
  currentTab: null,
  ref: { departments: [], resourcesHuman: [], resourcesTech: [], resourcesAll: [], employees: [] },
};

/* ===================== API helper ===================== */

async function api(path, { method = "GET", body, params } = {}) {
  let url = API_BASE + path;
  if (params) {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") qs.append(k, v);
    });
    const s = qs.toString();
    if (s) url += "?" + s;
  }
  const headers = { "Content-Type": "application/json" };
  if (state.employeeId) headers["X-Employee-ID"] = state.employeeId;

  const res = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const errBody = await res.json();
      detail = errBody.detail || detail;
    } catch (e) {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

/**
 * GETs a binary file (Excel report) with the session's auth header — a plain
 * <a href> can't carry X-Employee-ID, so this fetches it as a blob and
 * triggers the save via a temporary object URL.
 */
async function downloadFile(path, params, fallbackFilename) {
  let url = API_BASE + path;
  if (params) {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") qs.append(k, v);
    });
    const s = qs.toString();
    if (s) url += "?" + s;
  }
  const headers = {};
  if (state.employeeId) headers["X-Employee-ID"] = state.employeeId;

  const res = await fetch(url, { headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const errBody = await res.json();
      detail = errBody.detail || detail;
    } catch (e) {
      /* ignore */
    }
    throw new Error(detail);
  }

  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^";]+)"?/);
  const filename = match ? match[1] : fallbackFilename || "download";

  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(blobUrl);
}

/**
 * POSTs a file as multipart/form-data with the session's auth header.
 */
async function uploadFile(path, file) {
  const url = API_BASE + path;
  const headers = {};
  if (state.employeeId) headers["X-Employee-ID"] = state.employeeId;

  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(url, { method: "POST", headers, body: formData });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const errBody = await res.json();
      detail = errBody.detail || detail;
    } catch (e) {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

/* ===================== Small utilities ===================== */

function el(html) {
  const tpl = document.createElement("template");
  tpl.innerHTML = html.trim();
  return tpl.content.firstElementChild;
}

function esc(s) {
  if (s === null || s === undefined) return "";
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function fmtDate(d) {
  if (!d) return "—";
  const dt = new Date(d);
  if (isNaN(dt)) return d;
  return dt.toLocaleDateString("ru-RU");
}

function fmtDateTime(d) {
  if (!d) return "—";
  const dt = new Date(d + (d.endsWith("Z") ? "" : "Z"));
  if (isNaN(dt)) return d;
  return dt.toLocaleString("ru-RU");
}

function fmtNum(n) {
  if (n === null || n === undefined) return "0";
  return Number(n).toLocaleString("ru-RU", { maximumFractionDigits: 1 });
}

function fmtFileSize(bytes) {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

function pluralDays(n) {
  const mod10 = Math.abs(n) % 10;
  const mod100 = Math.abs(n) % 100;
  if (mod10 === 1 && mod100 !== 11) return "день";
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return "дня";
  return "дней";
}

/** Warning shown next to the planned end date once fewer than 14 days remain
 * (or the date has already passed). */
function deadlineWarningHtml(endDate) {
  if (!endDate) return "";
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const end = new Date(endDate);
  const diffDays = Math.round((end - today) / (1000 * 60 * 60 * 24));
  if (diffDays >= 14) return "";
  const text = diffDays >= 0
    ? `Осталось ${diffDays} ${pluralDays(diffDays)}`
    : `Просрочено на ${Math.abs(diffDays)} ${pluralDays(diffDays)}`;
  return ` <span class="deadline-warning">⚠️ <span class="muted">${text}</span></span>`;
}

function toast(msg, isError) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.toggle("error", !!isError);
  t.classList.remove("hidden");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => t.classList.add("hidden"), 3500);
}

function openModal(html) {
  const modal = document.getElementById("modal");
  modal.innerHTML = html;
  document.getElementById("modal-backdrop").classList.remove("hidden");
}

function closeModal() {
  document.getElementById("modal-backdrop").classList.add("hidden");
  document.getElementById("modal").innerHTML = "";
}

document.getElementById("modal-backdrop").addEventListener("click", (e) => {
  if (e.target.id === "modal-backdrop") closeModal();
});

/* ===================== About the product ===================== */
// Mirrors PRODUCT_OVERVIEW.md — keep the two in sync when either changes.

const ABOUT_PRODUCT_HTML = `
  <div style="display:flex; justify-content:space-between; align-items:flex-start;">
    <h2 style="margin-top:0;">Портал управления портфелем AI-инициатив</h2>
    <button class="link-btn" onclick="closeModal()">✕</button>
  </div>
  <p>Внутренний портал для ведения портфеля AI-инициатив компании: заявка инициативы AI-чемпионом,
  её многоступенчатое согласование, учёт плановых и фактических ресурсов, портфельная аналитика и
  отчётность.</p>

  <h3>1. Роли и права</h3>
  <p class="muted">Входа по паролю нет: на стартовом экране выбирается сотрудник из списка, дальше все
  действия выполняются от его имени. Всего пять ролей.</p>

  <h4>AI-чемпион</h4>
  <ul>
    <li>Создаёт инициативы: название, описание, даты начала/окончания, плановые ресурсы (человеческие
      и технические) и ожидаемую выгоду.</li>
    <li>Видит и редактирует <strong>только свои</strong> инициативы (вкладка «Мои инициативы»).</li>
    <li>Логирует фактически потраченное время по каждой специализации — фактические часы не могут
      превышать плановые (ограничение проверяется и на клиенте, и на сервере).</li>
    <li>Оставляет комментарии, прикрепляет и скачивает файлы к карточке инициативы.</li>
    <li>Раздел «Отчёты» — выгрузка в Excel/CSV, но только по своим инициативам.</li>
    <li>Раз в неделю получает в «Уведомлениях» напоминание залогировать время по инициативам (см. раздел 5).</li>
    <li>Не может согласовывать/отклонять инициативы.</li>
  </ul>

  <h4>Руководитель подразделения</h4>
  <ul>
    <li>Видит инициативы только тех AI-чемпионов, что относятся к его подразделению.</li>
    <li>Первый этап цепочки согласования: «Требуют согласования» / «Согласованные» (см. раздел 2).</li>
    <li>Раздел «Отчёты» — только по инициативам своего подразделения.</li>
    <li>Комментарии и файлы — как у любого пользователя.</li>
  </ul>

  <h4>TeamLead</h4>
  <ul>
    <li>Роль привязана к одной специализации человеческих ресурсов (ML-инженер, Аналитик, Разработчик,
      СисАдмин, Тестировщик — набор расширяемый, каждая специализация заводится PM в «Ресурсы и
      ставки» вместе с обязательным TeamLead-ом). Специализация показывается рядом с ролью везде, где
      отображается пользователь: «TeamLead, ML-инженер».</li>
    <li>Второй этап цепочки: видит инициативу только после согласования руководителем и только если её
      специализация упомянута в блоке «Человеко-часы» или «Ожидаемая выгода» карточки.</li>
    <li>Интерфейс идентичен интерфейсу руководителя — те же две вкладки «Требуют согласования» /
      «Согласованные».</li>
    <li>Доступа к «Отчётам» и «Портфелю» не имеет.</li>
  </ul>

  <h4>PM</h4>
  <ul>
    <li>Видит <strong>все</strong> инициативы портала («Все инициативы») с фильтрами по подразделению,
      чемпиону и статусу согласования.</li>
    <li>Единственная роль, управляющая справочниками:
      <ul>
        <li>«Ресурсы и ставки» — стоимость ресурса (₽/ед.), создание новых специализаций человеческих
          ресурсов (обязательно с назначением TeamLead-а), назначение/смена TeamLead-а у существующей
          специализации.</li>
        <li>«Штат» — подразделения и сотрудники (создание, назначение ролей и подразделений).</li>
      </ul>
    </li>
    <li>«Портфель» — та же дашборд-аналитика, что и у топ-менеджмента (см. раздел 4).</li>
    <li>«Отчёты» — по всем инициативам, с фильтром по подразделению.</li>
    <li>Может удалить любую инициативу. Сам не участвует в согласовании.</li>
  </ul>

  <h4>Топ-менеджмент</h4>
  <ul>
    <li>Финальный, четвёртый этап цепочки согласования: вкладка «Требуют согласования» — сюда попадают
      инициативы, дошедшие до этой стадии по всем подразделениям сразу.</li>
    <li>«Портфель» — портфельная аналитика.</li>
    <li>«Все инициативы» — просмотр всего портфеля без права редактирования/согласования вне вкладки
      «Требуют согласования».</li>
    <li>«Отчёты» — по всем инициативам, с фильтром по подразделению.</li>
  </ul>

  <h3>2. Цепочка согласования инициатив</h3>
  <p>Инициатива проходит <strong>до четырёх последовательных этапов</strong>. Текущий этап хранится в
  поле <code>approval_stage</code> (<code>head</code> → <code>teamlead</code> → <code>top</code>), а
  «полностью согласовано» — это отдельный флаг <code>is_approved</code>, который становится
  <code>True</code> только после решения топ-менеджмента.</p>

  <pre style="overflow-x:auto; font-size:0.78em; line-height:1.4; background:#f8f9fb; border:1px solid var(--border); border-radius:8px; padding:12px;">Чемпион создаёт инициативу
        │
        ▼
 ┌─────────────┐   отклонить/на пересмотр   (остаётся у руководителя,
 │ Руководитель │ ─────────────────────────►  ждёт исправлений от чемпиона)
 │ подразделения│
 └──────┬──────┘
        │ согласовать
        ▼
   есть ли специализации с TeamLead-ом
   в «Человеко-часы» или «Ожидаемая выгода»?
        │                              │
       нет                            да
        │                              ▼
        │                    ┌──────────────────┐   отклонить/на пересмотр
        │                    │  Все нужные       │ ──────────────────────►  (останавливает круг,
        │                    │  TeamLead-ы       │                           чемпион должен
        │                    │  (параллельно)    │                           исправить и переслать)
        │                    └────────┬──────────┘
        │                             │ согласовали ВСЕ
        ▼                             ▼
 ┌─────────────┐
 │Топ-менеджмент│   отклонить/на пересмотр  (остаётся у топ-менеджмента,
 │              │ ─────────────────────────►  ждёт исправлений)
 └──────┬──────┘
        │ согласовать
        ▼
   is_approved = True → «Согласовано»</pre>

  <p><strong>Детали:</strong></p>
  <ul>
    <li><strong>Кто требуется на этапе TeamLead.</strong> Собирается объединённое множество
      TeamLead-ов всех специализаций человеческих ресурсов, встречающихся либо в плановых ресурсах
      («Человеко-часы»), либо в ожидаемой выгоде («Ожидаемая выгода») — попадание в любой из двух
      блоков добавляет TeamLead-а этой специализации в цепочку. Если таких специализаций нет вовсе,
      этап TeamLead пропускается — инициатива сразу уходит топ-менеджменту.</li>
    <li><strong>Согласование TeamLead-ами идёт параллельно, не последовательно.</strong> Каждый
      TeamLead решает независимо; когда согласовали все — инициатива автоматически переходит к
      топ-менеджменту. Пока решили не все, в карточке видно, кто уже согласовал и кого ещё ждут.</li>
    <li><strong>Отклонение/пересмотр одним TeamLead-ом останавливает круг</strong>, но не «обнуляет»
      уже принятые решения других TeamLead-ов — они по-прежнему видят инициативу в своих
      «Согласованные». Дальше требуется правка чемпиона (см. раздел 3) — это запускает цепочку заново
      с руководителя.</li>
    <li><strong>Отклонённая/возвращённая на пересмотр инициатива остаётся в очереди того же этапа</strong>
      — тот же руководитель или тот же топ-менеджмент увидит её в «Требуют согласования» снова (только
      правка чемпиона запускает новый круг).</li>
    <li><strong>История согласований</strong> в карточке инициативы хранит все решения (кто, когда,
      какая роль — включая специализацию TeamLead-а, — и итог) в хронологическом порядке.</li>
  </ul>

  <h3>3. Изменение ресурсов и повторное согласование</h3>
  <p>Карточку инициативы редактирует только её чемпион. Что происходит при сохранении правок, зависит
  от того, что именно изменилось:</p>
  <ul>
    <li><strong>Название, описание, даты начала/окончания</strong> — сохраняются свободно, без
      каких-либо последствий для статуса согласования. Руководитель лишь получает уведомление, что
      инициатива была изменена.</li>
    <li><strong>Плановые ресурсы («Человеко-часы», «Плановые технические ресурсы») или «Ожидаемая
      выгода»</strong> — любое изменение количества/состава запускает полный сброс цепочки:
      <ol>
        <li>Инициатива уходит на пересогласование <strong>с самого начала</strong>, независимо от
          того, на каком этапе она была (даже если уже согласовали все TeamLead-ы или дело было за
          топ-менеджментом).</li>
        <li>Все текущие решения TeamLead-ов по этой инициативе (и «pending», и уже «approved»)
          удаляются — раз состав специализаций мог измениться, прежние согласования могли устареть и
          относиться к ресурсам, которых уже нет.</li>
        <li>В историю согласований добавляется запись «отправлено на пересмотр чемпионом» с точным
          построчным перечнем, что изменилось.</li>
        <li>Руководителю подразделения приходит уведомление, что инициатива требует повторного
          рассмотрения.</li>
      </ol>
    </li>
    <li><strong>Почему именно так.</strong> Изменение специализаций и объёмов напрямую влияет на то,
      кто вообще должен согласовывать инициативу и на экономику проекта — поэтому в отличие от
      отклонения одним TeamLead-ом (которое не трогает чужие решения), правка ресурсов чемпионом
      обнуляет вообще всё и требует прохождения всей цепочки заново.</li>
    <li><strong>Фактические часы не могут превышать плановые.</strong> При логировании фактических
      часов по специализации сервер не даст записать больше, чем осталось от планового значения.
      Проверка дублируется на клиенте для мгновенной обратной связи, но источник истины — сервер.</li>
  </ul>

  <h3>4. Функционал «Портфель»</h3>
  <p>Доступен PM и топ-менеджменту (полностью одинаковый для обеих ролей — один и тот же экран).</p>
  <ul>
    <li><strong>Счётчики портфеля</strong> («Инициатив в портфеле», «Согласовано», «Не согласовано»)
      считаются по <strong>всему</strong> портфелю независимо от статуса.</li>
    <li><strong>Все денежные и ресурсные показатели считаются только по инициативам в статусе
      «Согласовано»</strong>: плановые/фактические затраты, ожидаемая выгода, окупаемость. Инициатива,
      которая ещё не прошла все этапы (или отклонена/на пересмотре), не считается зафиксированным
      расходом или выгодой портфеля.</li>
    <li><strong>«Общая ожидаемая выгода портфеля (экономия в месяц)»</strong> — одно число вверху
      экрана: сумма денежной выгоды (₽/мес.) всех согласованных инициатив.</li>
    <li><strong>«Затраты и окупаемость»</strong> — график по подразделениям: плановые/фактические
      затраты и окупаемость, только по согласованным инициативам этого подразделения.</li>
    <li><strong>Ресурсные таблицы</strong> — суммируются <strong>раздельно по каждому ресурсу</strong>,
      с его собственной единицей измерения и ставкой (₽/ед.); разные ресурсы никогда не складываются
      в одно число.</li>
    <li><strong>Разбивка по подразделениям</strong> — количество инициатив и их статусный разрез по
      всему портфелю, а рядом — денежные показатели, посчитанные только по согласованным инициативам
      этого подразделения.</li>
    <li><strong>Окупаемость портфеля</strong> считается как <strong>сумма окупаемости каждой отдельной
      согласованной инициативы</strong> (не как отношение суммарных затрат к суммарной выгоде).</li>
  </ul>

  <h3>5. Напоминания о логировании времени</h3>
  <p>Раз в неделю AI-чемпионам автоматически приходит напоминание залогировать фактическое время по их
  инициативам.</p>
  <ul>
    <li><strong>Кому приходит.</strong> Только AI-чемпионам, и только если есть что логировать: нужна
      хотя бы одна <strong>согласованная</strong> инициатива с плановыми человеко-часами, ещё не
      покрытыми фактическими записями.</li>
    <li><strong>Периодичность и день недели.</strong> Проверка идёт в фоне раз в час; фактическая
      отправка — не чаще раза в календарный день и только в настроенный день недели. По умолчанию —
      четверг, день задаётся переменной окружения <code>REMINDER_WEEKDAY</code>: имя дня недели
      (<code>monday</code>…<code>sunday</code>) или число 0–6, где 0 — понедельник.</li>
    <li><strong>Текст напоминания</strong> перечисляет конкретные инициативы (до трёх по названию,
      дальше «и ещё N»), по которым остались нелогированные часы.</li>
    <li><strong>Где видно.</strong> Раздел «Уведомления», открывается по клику на 🔔 в шапке, вместе со
      всеми остальными уведомлениями сотрудника.</li>
  </ul>

  <div class="modal-actions">
    <button class="secondary-btn" onclick="closeModal()">Закрыть</button>
  </div>
`;

document.getElementById("about-btn").addEventListener("click", () => openModal(ABOUT_PRODUCT_HTML));

function selectOptions(items, valueKey, labelKey, selected) {
  return items
    .map(
      (i) =>
        `<option value="${i[valueKey]}" ${i[valueKey] === selected ? "selected" : ""}>${esc(i[labelKey])}</option>`
    )
    .join("");
}

/* ===================== Status badge ===================== */

function statusInfo(ini) {
  if (ini.is_approved) return { label: "Согласовано", color: "green" };
  if (ini.latest_status === "revision") return { label: "На пересмотре", color: "yellow" };
  if (ini.latest_status === "rejected") return { label: "Отклонено", color: "red" };
  if (ini.approval_stage === "teamlead") return { label: "Ожидает согласования TeamLead", color: "blue" };
  if (ini.approval_stage === "top") return { label: "Ожидает согласования топ-менеджмента", color: "blue" };
  return { label: "Ожидает согласования руководителя", color: "blue" };
}

function statusBadge(ini) {
  const s = statusInfo(ini);
  return `<span class="status-badge"><span class="dot ${s.color}"></span>${s.label}</span>`;
}

function paybackText(months) {
  if (months === null || months === undefined) return "—";
  return `${fmtNum(months)} мес.`;
}

/* ===================== Reference caches ===================== */

async function loadReferenceCaches() {
  const [departments, resources, employees] = await Promise.all([
    api("/departments"),
    api("/resources"),
    api("/employees"),
  ]);
  state.ref.departments = departments.sort((a, b) => a.name.localeCompare(b.name, "ru"));
  state.ref.resourcesHuman = resources.filter((r) => r.category === "human");
  state.ref.resourcesTech = resources.filter((r) => r.category === "tech");
  state.ref.resourcesAll = resources;
  state.ref.employees = employees;
}

function resourceName(id) {
  const r = state.ref.resourcesAll.find((x) => x.id === id);
  return r ? r.name : "—";
}

/* ===================== Session ===================== */

function saveSession() {
  sessionStorage.setItem(
    SESSION_KEY,
    JSON.stringify({
      employeeId: state.employeeId,
      fullName: state.fullName,
      role: state.role,
      specialization: state.specialization,
      departmentId: state.departmentId,
      departmentName: state.departmentName,
    })
  );
}

function restoreSession() {
  const raw = sessionStorage.getItem(SESSION_KEY);
  if (!raw) return false;
  try {
    Object.assign(state, JSON.parse(raw));
    return !!state.employeeId;
  } catch (e) {
    return false;
  }
}

function clearSession() {
  sessionStorage.removeItem(SESSION_KEY);
  location.reload();
}

/* ===================== Employee selection screen ===================== */

(async function initRoleScreen() {
  if (restoreSession()) {
    startApp();
    return;
  }
  try {
    const employees = await api("/employees");
    const select = document.getElementById("employee-select");
    select.innerHTML = employees
      .map(
        (e) =>
          `<option value="${e.id}">${esc(e.full_name)} — ${esc(roleLabel(e.role, e.specialization))}${e.department_name ? ", " + esc(e.department_name) : ""}</option>`
      )
      .join("");
    document.getElementById("employee-continue").addEventListener("click", () => {
      const id = Number(select.value);
      const emp = employees.find((e) => e.id === id);
      if (!emp) return;
      state.employeeId = emp.id;
      state.fullName = emp.full_name;
      state.role = emp.role;
      state.specialization = emp.specialization;
      state.departmentId = emp.department_id;
      state.departmentName = emp.department_name;
      saveSession();
      startApp();
    });
  } catch (e) {
    document.getElementById("role-error").textContent = "Ошибка загрузки сотрудников: " + e.message;
  }
})();

/* ===================== App shell ===================== */

const TAB_DEFS = {
  champion: [
    { id: "my", label: "Мои инициативы", render: renderChampionInitiatives },
    { id: "reports", label: "Отчёты", render: renderReportsTab },
  ],
  head: [
    { id: "pending", label: "Требуют согласования", render: renderHeadPending },
    { id: "approved", label: "Согласованные", render: renderHeadApproved },
    { id: "reports", label: "Отчёты", render: renderReportsTab },
  ],
  teamlead: [
    { id: "pending", label: "Требуют согласования", render: renderHeadPending },
    { id: "approved", label: "Согласованные", render: renderHeadApproved },
  ],
  pm: [
    { id: "all", label: "Все инициативы", render: renderPmInitiatives },
    { id: "rates", label: "Ресурсы и ставки", render: renderResourceRatesTab },
    { id: "staff", label: "Штат", render: renderStaffTab },
    { id: "portfolio", label: "Портфель", render: renderTopDashboard },
    { id: "reports", label: "Отчёты", render: renderReportsTab },
  ],
  top: [
    { id: "pending", label: "Требуют согласования", render: renderTopPending },
    { id: "portfolio", label: "Портфель", render: renderTopDashboard },
    { id: "all", label: "Все инициативы", render: renderTopInitiatives },
    { id: "reports", label: "Отчёты", render: renderReportsTab },
  ],
};

async function startApp() {
  document.getElementById("role-screen").classList.add("hidden");
  document.getElementById("app-screen").classList.remove("hidden");
  document.getElementById("who-name").textContent = state.fullName || "";
  document.getElementById("who-role").textContent =
    roleLabel(state.role, state.specialization) + (state.departmentName ? ` · ${state.departmentName}` : "");

  try {
    await loadReferenceCaches();
  } catch (e) {
    toast("Не удалось загрузить справочники: " + e.message, true);
  }

  const tabs = TAB_DEFS[state.role] || [];
  const tabsNav = document.getElementById("tabs");
  tabsNav.innerHTML = tabs.map((t) => `<button class="tab-btn" data-tab="${t.id}">${t.label}</button>`).join("");
  tabsNav.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  if (tabs.length) switchTab(tabs[0].id);
  refreshNotifBadge();
}

function switchTab(tabId) {
  state.currentTab = tabId;
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tabId));
  const def = (TAB_DEFS[state.role] || []).find((t) => t.id === tabId);
  const content = document.getElementById("content");
  content.innerHTML = `<p class="muted">Загрузка...</p>`;
  if (def) def.render(content);
}

document.getElementById("logout-btn").addEventListener("click", clearSession);

/* ===================== Notifications ===================== */

async function refreshNotifBadge() {
  try {
    const list = await api("/notifications");
    const unread = list.filter((n) => !n.is_read).length;
    const badge = document.getElementById("notif-badge");
    badge.textContent = unread;
    badge.classList.toggle("hidden", unread === 0);
  } catch (e) {
    /* silent */
  }
}

async function renderNotifPanel() {
  const list = await api("/notifications");
  const box = document.getElementById("notif-list");
  if (!list.length) {
    box.innerHTML = `<p class="muted">Уведомлений нет.</p>`;
    return;
  }
  box.innerHTML = list
    .map(
      (n) => `
      <div class="notif-item ${n.is_read ? "" : "unread"}" data-id="${n.id}">
        <div>${esc(n.message)}</div>
        <div class="time">${fmtDateTime(n.created_at)}</div>
      </div>`
    )
    .join("");
  box.querySelectorAll(".notif-item").forEach((item) => {
    item.addEventListener("click", async () => {
      await api(`/notifications/${item.dataset.id}/read`, { method: "POST" });
      item.classList.remove("unread");
      refreshNotifBadge();
    });
  });
}

document.getElementById("notif-btn").addEventListener("click", async () => {
  document.getElementById("notif-panel").classList.remove("hidden");
  await renderNotifPanel();
});
document.getElementById("notif-close").addEventListener("click", () => {
  document.getElementById("notif-panel").classList.add("hidden");
});

/* ===================== Dynamic resource-row form rows ===================== */

function mountResourceRows(container, resourceOptions, initialRows) {
  function addRow(resourceId, quantity) {
    const row = el(`
      <div class="resource-row">
        <div>
          <label>Ресурс</label>
          <select class="row-resource">${resourceOptions
            .map((r) => `<option value="${r.id}" ${r.id === resourceId ? "selected" : ""}>${esc(r.name)} (${esc(r.unit)})</option>`)
            .join("")}</select>
        </div>
        <div>
          <label>Количество</label>
          <input type="number" step="0.1" min="0" class="row-quantity" value="${quantity ?? ""}" placeholder="0">
        </div>
        <button type="button" class="resource-row-remove" title="Удалить">✕</button>
      </div>
    `);
    row.querySelector(".resource-row-remove").addEventListener("click", () => row.remove());
    container.appendChild(row);
  }
  (initialRows || []).forEach((r) => addRow(r.resource_id, r.quantity));
  if (!initialRows || !initialRows.length) addRow(resourceOptions[0]?.id, "");

  return {
    addRow,
    getValues() {
      return [...container.querySelectorAll(".resource-row")]
        .map((row) => ({
          resource_id: Number(row.querySelector(".row-resource").value),
          quantity: parseFloat(row.querySelector(".row-quantity").value),
        }))
        .filter((r) => r.resource_id && !isNaN(r.quantity) && r.quantity > 0);
    },
  };
}

/* ===================== Initiatives: shared list view ===================== */

function renderInitiativesTable(container, items, opts) {
  if (!items.length) {
    container.innerHTML = `<p class="muted">Инициативы не найдены.</p>`;
    return;
  }
  const table = el(`
    <table class="clickable">
      <thead><tr>
        <th>Название</th>
        ${opts.showDepartment ? "<th>Подразделение</th>" : ""}
        ${opts.showChampion ? "<th>Чемпион</th>" : ""}
        <th>Срок (план)</th>
        <th>Срок окупаемости</th>
        <th>Статус</th>
      </tr></thead>
      <tbody>${items
        .map(
          (i) => `<tr data-id="${i.id}">
            <td>${esc(i.title)}</td>
            ${opts.showDepartment ? `<td>${esc(i.department_name)}</td>` : ""}
            ${opts.showChampion ? `<td>${esc(i.champion_name)}</td>` : ""}
            <td>${fmtDate(i.end_date)}${deadlineWarningHtml(i.end_date)}</td>
            <td>${paybackText(i.payback_months)}</td>
            <td>${statusBadge(i)}</td>
          </tr>`
        )
        .join("")}</tbody>
    </table>
  `);
  container.appendChild(table);
  table.querySelectorAll("tbody tr").forEach((row) => {
    row.addEventListener("click", () => openInitiativeDetail(Number(row.dataset.id), opts));
  });
}

/**
 * config: { fixedParams, showFilters:[...], showDepartment, showChampion,
 *           canCreate, canEdit(ini), canDelete(ini), canAct(ini) }
 */
function renderInitiativesView(container, config) {
  const filters = {};
  container.innerHTML = "";

  const panel = el(`<div class="panel"></div>`);
  const header = el(`<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
      <h2 style="margin:0;">Инициативы</h2>
      ${config.canCreate ? `<button class="primary-btn" id="create-ini-btn">+ Новая инициатива</button>` : ""}
    </div>`);
  panel.appendChild(header);

  if (config.showFilters && config.showFilters.length) {
    const filterBar = el(`<div class="filters"></div>`);
    if (config.showFilters.includes("department")) {
      filterBar.appendChild(
        el(`<div class="field"><label>Подразделение</label>
          <select id="f-department"><option value="">Все</option>${selectOptions(state.ref.departments, "id", "name")}</select></div>`)
      );
    }
    if (config.showFilters.includes("champion")) {
      const champions = state.ref.employees.filter((e) => e.role === "champion");
      filterBar.appendChild(
        el(`<div class="field"><label>Чемпион</label>
          <select id="f-champion"><option value="">Все</option>${selectOptions(champions, "id", "full_name")}</select></div>`)
      );
    }
    if (config.showFilters.includes("is_approved")) {
      filterBar.appendChild(
        el(`<div class="field"><label>Статус</label>
          <select id="f-approved">
            <option value="">Все</option>
            <option value="true">Согласованные</option>
            <option value="false">Не согласованные</option>
          </select></div>`)
      );
    }
    filterBar.appendChild(el(`<button class="secondary-btn" id="f-apply">Показать</button>`));
    panel.appendChild(filterBar);
  }

  const tableBox = el(`<div id="ini-table-box"></div>`);
  panel.appendChild(tableBox);
  container.appendChild(panel);

  async function load() {
    tableBox.innerHTML = `<p class="muted">Загрузка...</p>`;
    const params = { ...config.fixedParams, ...filters };
    const data = await api("/initiatives", { params });
    tableBox.innerHTML = "";
    renderInitiativesTable(tableBox, data.items, config);
  }

  const applyBtn = panel.querySelector("#f-apply");
  if (applyBtn) {
    applyBtn.addEventListener("click", () => {
      // Only set a filter key when its dropdown actually exists in this view —
      // otherwise `{...fixedParams, ...filters}` below would overwrite a fixed
      // param (e.g. the champion's own id) with `undefined` and drop it from
      // the request entirely.
      const fd = panel.querySelector("#f-department");
      const fc = panel.querySelector("#f-champion");
      const fa = panel.querySelector("#f-approved");
      if (fd) filters.department_id = fd.value;
      if (fc) filters.champion_id = fc.value;
      if (fa) filters.is_approved = fa.value;
      load();
    });
  }

  const createBtn = panel.querySelector("#create-ini-btn");
  if (createBtn) createBtn.addEventListener("click", () => openInitiativeForm(null, config, load));

  load();
}

/* ---------- Detail modal ---------- */

async function openInitiativeDetail(id, config) {
  openModal(`<p class="muted">Загрузка...</p>`);
  try {
    const ini = await api(`/initiatives/${id}`);
    renderInitiativeDetail(ini, config);
  } catch (e) {
    openModal(`<p>Ошибка: ${esc(e.message)}</p><div class="modal-actions"><button class="secondary-btn" onclick="closeModal()">Закрыть</button></div>`);
  }
}

function resourceTableRows(list) {
  return list
    .map((r) => `<tr><td>${esc(r.resource_name)}</td><td>${fmtNum(r.quantity)}</td><td>${esc(r.unit)}</td></tr>`)
    .join("");
}

function humanResourceRows(list) {
  return list
    .map((r) => {
      const overrun = r.fact_quantity > r.quantity;
      return `<tr>
        <td>${esc(r.resource_name)}</td>
        <td>${fmtNum(r.quantity)}</td>
        <td>${fmtNum(r.fact_quantity)}${overrun ? ` <span class="overrun-warning">⚠️ Плановое значение превышено</span>` : ""}</td>
      </tr>`;
    })
    .join("");
}

/**
 * A section that starts collapsed and expands on click — used for blocks that
 * can grow long (history/comments) so they don't dominate the card by default.
 */
function collapsibleSection(id, title, count, bodyHtml) {
  return `
    <div class="collapsible">
      <button type="button" class="collapsible-header" data-target="collapsible-body-${id}">
        <span class="collapsible-arrow">▸</span>
        <h3>${esc(title)}${count !== undefined ? ` <span class="muted">(${count})</span>` : ""}</h3>
      </button>
      <div class="collapsible-body hidden" id="collapsible-body-${id}">
        ${bodyHtml}
      </div>
    </div>
  `;
}

function renderInitiativeDetail(ini, config) {
  const canEdit = config.canEdit && config.canEdit(ini);
  const canDelete = config.canDelete && config.canDelete(ini);
  const canAct = config.canAct && config.canAct(ini);

  const human = ini.resources_planned.filter((r) => r.category === "human");
  const tech = ini.resources_planned.filter((r) => r.category === "tech");
  const canLogTime = !!(config.canLogTime && config.canLogTime(ini) && human.length);

  const costLogsTable = `
    <table><thead><tr><th>Дата</th><th>Специализация</th><th>Чемпион</th><th>Часы</th></tr></thead>
      <tbody>${ini.cost_logs
        .map(
          (c) => `<tr>
            <td>${fmtDateTime(c.created_at)}</td>
            <td>${esc(c.resource_name)}</td>
            <td>${esc(c.champion_name)}</td>
            <td>${fmtNum(c.quantity)} ${esc(c.unit)}</td>
          </tr>`
        )
        .join("") || `<tr><td colspan="4" class="muted">Записей нет</td></tr>`}</tbody>
    </table>
  `;

  const approvalsRows = ini.approvals
    .map(
      (a) => `<div class="comment">
        <div class="meta">${fmtDateTime(a.created_at)} · ${esc(a.actor_name)} (${esc(roleLabel(a.actor_role, a.actor_specialization))}) · <strong>${esc(approvalStatusLabel(a.status))}</strong></div>
        ${a.comment ? `<div class="text">${esc(a.comment)}</div>` : ""}
      </div>`
    )
    .join("");

  const commentsRows = ini.comments
    .map(
      (c) => `<div class="comment">
        <div class="meta">${esc(c.author_name)} · ${fmtDateTime(c.created_at)}</div>
        <div class="text">${esc(c.text)}</div>
      </div>`
    )
    .join("");

  const attachmentsRows = ini.attachments
    .map(
      (a) => `<div class="comment" data-attachment-id="${a.id}">
        <div class="meta">${esc(a.filename)} · ${fmtFileSize(a.size)} · загрузил(а) ${esc(a.uploader_name)}, ${fmtDateTime(a.created_at)}</div>
        <button type="button" class="secondary-btn small-btn attachment-download-btn" data-id="${a.id}" data-name="${esc(a.filename)}">Скачать</button>
      </div>`
    )
    .join("");

  openModal(`
    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
      <h2 style="margin-top:0;">${esc(ini.title)}</h2>
      <button class="link-btn" onclick="closeModal()">✕</button>
    </div>
    ${statusBadge(ini)}
    ${(() => {
      if (ini.approval_stage !== "teamlead") return "";
      const fmt = (p) => esc(p.employee_name) + (p.resource_name ? ` (${esc(p.resource_name)})` : "");
      const waiting = ini.pending_approvers.filter((p) => p.status === "pending");
      const approved = ini.pending_approvers.filter((p) => p.status === "approved");
      const lines = [];
      if (!ini.is_approved && waiting.length) lines.push(`<p class="muted">Ожидает решения: ${waiting.map(fmt).join(", ")}</p>`);
      if (approved.length) lines.push(`<p class="muted">Уже согласовали: ${approved.map(fmt).join(", ")}</p>`);
      return lines.join("");
    })()}

    <div class="form-grid" style="margin-top:16px;">
      <div><label>Подразделение</label>${esc(ini.department_name)}</div>
      <div><label>Чемпион</label>${esc(ini.champion_name)}</div>
      <div><label>Дата начала</label>${fmtDate(ini.start_date)}</div>
      <div><label>Плановая дата окончания</label>${fmtDate(ini.end_date)}${deadlineWarningHtml(ini.end_date)}</div>
      <div><label>Срок окупаемости</label>${paybackText(ini.payback_months)}</div>
      <div class="full"><label>Описание</label>${esc(ini.description || "—")}</div>
    </div>

    <div style="display:flex; justify-content:space-between; align-items:center;">
      <h3 style="margin-bottom:0;">Человеко-часы</h3>
      ${canLogTime ? `<button type="button" class="secondary-btn small-btn" id="btn-log-time">Логирование времени</button>` : ""}
    </div>
    <table><thead><tr><th>Специализация</th><th>Плановые затраты</th><th>Фактические затраты</th></tr></thead>
      <tbody>${humanResourceRows(human) || `<tr><td colspan="3" class="muted">Не заданы</td></tr>`}</tbody>
    </table>
    ${canLogTime ? `
      <form id="time-log-form" class="time-log-form hidden">
        <div class="field">
          <label>Специализация</label>
          <select id="time-log-resource">${selectOptions(human, "resource_id", "resource_name")}</select>
        </div>
        <div class="field">
          <label>Часы затрачено</label>
          <input type="number" min="0" step="0.1" id="time-log-quantity" placeholder="0">
        </div>
        <button type="submit" class="primary-btn small-btn">Записать</button>
        <button type="button" class="secondary-btn small-btn" id="btn-cancel-log-time">Отмена</button>
      </form>
    ` : ""}

    ${collapsibleSection("cost-logs", "История затрат", ini.cost_logs.length, costLogsTable)}

    <h3>Плановые технические ресурсы</h3>
    <table><thead><tr><th>Ресурс</th><th>Количество</th><th>Единица</th></tr></thead>
      <tbody>${resourceTableRows(tech) || `<tr><td colspan="3" class="muted">Не заданы</td></tr>`}</tbody>
    </table>

    <h3>Ожидаемая выгода (экономия в месяц)</h3>
    <table><thead><tr><th>Ресурс</th><th>Количество</th><th>Единица</th></tr></thead>
      <tbody>${resourceTableRows(ini.benefits) || `<tr><td colspan="3" class="muted">Не задана</td></tr>`}</tbody>
    </table>

    ${canAct ? `
      <h3>${{ teamlead: "Решение TeamLead", top: "Решение топ-менеджмента" }[state.role] || "Решение руководителя"}</h3>
      <textarea id="approval-comment" placeholder="Комментарий (обязателен для отклонения и пересмотра)"></textarea>
      <div class="modal-actions" style="justify-content:flex-start;">
        <button class="success-btn" id="btn-approve">Согласовать</button>
        <button class="warn-btn" id="btn-revision">Отправить на пересмотр</button>
        <button class="danger-btn" id="btn-reject">Отклонить</button>
      </div>
    ` : ""}

    ${collapsibleSection(
      "approvals", "История согласований", ini.approvals.length,
      approvalsRows || `<p class="muted">Пока нет решений.</p>`
    )}

    ${collapsibleSection(
      "comments", "Комментарии", ini.comments.length,
      `${commentsRows || `<p class="muted">Пока нет комментариев.</p>`}
       <form id="comment-form" style="margin-top:10px;">
         <textarea id="comment-text" placeholder="Ваш комментарий..." required></textarea>
         <div class="modal-actions" style="justify-content:flex-start; margin-top:8px;">
           <button type="submit" class="secondary-btn">Добавить комментарий</button>
         </div>
       </form>`
    )}

    ${collapsibleSection(
      "attachments", "Прикреплённые файлы", ini.attachments.length,
      `${attachmentsRows || `<p class="muted">Файлов пока нет.</p>`}
       <form id="attachment-form" style="margin-top:10px;">
         <input type="file" id="attachment-file" required>
         <div class="modal-actions" style="justify-content:flex-start; margin-top:8px;">
           <button type="submit" class="secondary-btn">Прикрепить файл</button>
         </div>
       </form>`
    )}

    <div class="modal-actions">
      ${canEdit ? `<button class="secondary-btn" id="btn-edit-ini">Редактировать</button>` : ""}
      ${canDelete ? `<button class="danger-btn" id="btn-delete-ini">Удалить</button>` : ""}
      <button class="secondary-btn" onclick="closeModal()">Закрыть</button>
    </div>
  `);

  document.querySelectorAll(".collapsible-header").forEach((btn) => {
    btn.addEventListener("click", () => {
      const body = document.getElementById(btn.dataset.target);
      const nowHidden = body.classList.toggle("hidden");
      btn.classList.toggle("open", !nowHidden);
    });
  });

  const commentForm = document.getElementById("comment-form");
  commentForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = document.getElementById("comment-text").value.trim();
    if (!text) return;
    try {
      await api(`/initiatives/${ini.id}/comments`, { method: "POST", body: { text } });
      openInitiativeDetail(ini.id, config);
    } catch (e2) {
      toast(e2.message, true);
    }
  });

  document.querySelectorAll(".attachment-download-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.id;
      const originalText = btn.textContent;
      btn.disabled = true;
      btn.textContent = "Скачивание...";
      try {
        await downloadFile(`/initiatives/${ini.id}/attachments/${id}/download`, null, btn.dataset.name);
      } catch (e2) {
        toast(e2.message, true);
      } finally {
        btn.disabled = false;
        btn.textContent = originalText;
      }
    });
  });

  const attachmentForm = document.getElementById("attachment-form");
  attachmentForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fileInput = document.getElementById("attachment-file");
    const file = fileInput.files[0];
    if (!file) {
      toast("Выберите файл", true);
      return;
    }
    try {
      await uploadFile(`/initiatives/${ini.id}/attachments`, file);
      toast("Файл прикреплён");
      openInitiativeDetail(ini.id, config);
    } catch (e2) {
      toast(e2.message, true);
    }
  });

  if (canLogTime) {
    const timeLogForm = document.getElementById("time-log-form");
    document.getElementById("btn-log-time").addEventListener("click", () => {
      timeLogForm.classList.toggle("hidden");
    });
    document.getElementById("btn-cancel-log-time").addEventListener("click", () => {
      timeLogForm.classList.add("hidden");
    });
    timeLogForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const resource_id = Number(document.getElementById("time-log-resource").value);
      const quantity = parseFloat(document.getElementById("time-log-quantity").value);
      if (!resource_id || !quantity || quantity <= 0) {
        toast("Укажите специализацию и количество часов больше нуля", true);
        return;
      }
      // Fact hours may never exceed the planned hours for that specialization —
      // check locally first so the champion gets instant feedback; the backend
      // enforces the same rule regardless.
      const planned = ini.resources_planned.find((r) => r.resource_id === resource_id);
      if (planned) {
        const remaining = planned.quantity - planned.fact_quantity;
        if (quantity > remaining) {
          toast(
            `Нельзя записать ${fmtNum(quantity)} ч. по специализации «${planned.resource_name}»: ` +
              `план — ${fmtNum(planned.quantity)} ч., уже записано — ${fmtNum(planned.fact_quantity)} ч., ` +
              `остаётся не более ${fmtNum(Math.max(remaining, 0))} ч.`,
            true
          );
          return;
        }
      }
      try {
        await api(`/initiatives/${ini.id}/cost_logs`, { method: "POST", body: { resource_id, quantity } });
        toast("Затраты зафиксированы");
        openInitiativeDetail(ini.id, config);
      } catch (e2) {
        toast(e2.message, true);
      }
    });
  }

  if (canAct) {
    const getComment = () => document.getElementById("approval-comment").value.trim();
    const act = async (action, requireComment) => {
      const comment = getComment();
      if (requireComment && !comment) {
        toast("Для этого решения нужен комментарий", true);
        return;
      }
      try {
        await api(`/initiatives/${ini.id}/${action}`, { method: "POST", body: { comment } });
        toast("Решение сохранено");
        closeModal();
        if (state.currentTab) switchTab(state.currentTab);
      } catch (e2) {
        toast(e2.message, true);
      }
    };
    document.getElementById("btn-approve").addEventListener("click", () => act("approve", false));
    document.getElementById("btn-revision").addEventListener("click", () => act("revision", true));
    document.getElementById("btn-reject").addEventListener("click", () => act("reject", true));
  }

  const editBtn = document.getElementById("btn-edit-ini");
  if (editBtn) {
    editBtn.addEventListener("click", () => openInitiativeForm(ini, config, () => openInitiativeDetail(ini.id, config)));
  }

  const deleteBtn = document.getElementById("btn-delete-ini");
  if (deleteBtn) {
    deleteBtn.addEventListener("click", async () => {
      if (!confirm(`Удалить инициативу «${ini.title}»?`)) return;
      await api(`/initiatives/${ini.id}`, { method: "DELETE" });
      toast("Инициатива удалена");
      closeModal();
      if (state.currentTab) switchTab(state.currentTab);
    });
  }
}

function approvalStatusLabel(status) {
  return { approved: "Согласовано", rejected: "Отклонено", revision: "Отправлено на пересмотр", pending: "Ожидает" }[status] || status;
}

/* ---------- Create/edit form ---------- */

function openInitiativeForm(ini, config, onSaved) {
  const isEdit = !!ini;

  openModal(`
    <h2 style="margin-top:0;">${isEdit ? "Редактирование инициативы" : "Новая инициатива"}</h2>
    <form id="ini-form">
      <div class="form-grid">
        <div class="full"><label>Название</label><input name="title" required value="${esc(ini?.title || "")}"></div>
        <div class="full"><label>Описание</label><textarea name="description">${esc(ini?.description || "")}</textarea></div>
        <div><label>Дата начала</label><input type="date" name="start_date" value="${ini?.start_date || ""}"></div>
        <div><label>Плановая дата окончания</label><input type="date" name="end_date" value="${ini?.end_date || ""}"></div>
      </div>

      ${isEdit ? `<div id="reapproval-warning" class="warning-banner hidden">⚠️ Изменены плановые ресурсы или ожидаемая выгода — инициатива будет отправлена на пересмотр руководителю</div>` : ""}

      <h3>Плановые человеческие ресурсы</h3>
      <div id="rows-human"></div>
      <button type="button" class="secondary-btn small-btn" id="add-human">+ добавить ресурс</button>

      <h3>Плановые технические ресурсы</h3>
      <div id="rows-tech"></div>
      <button type="button" class="secondary-btn small-btn" id="add-tech">+ добавить ресурс</button>

      <h3>Ожидаемая выгода (экономия в месяц)</h3>
      <div id="rows-benefit"></div>
      <button type="button" class="secondary-btn small-btn" id="add-benefit">+ добавить выгоду</button>

      <div class="modal-actions">
        <button type="button" class="secondary-btn" onclick="closeModal()">Отмена</button>
        <button type="submit" class="primary-btn">${isEdit ? "Сохранить" : "Создать"}</button>
      </div>
    </form>
  `);

  const humanRows = (ini?.resources_planned || []).filter((r) => r.category === "human");
  const techRows = (ini?.resources_planned || []).filter((r) => r.category === "tech");
  const benefitRows = ini?.benefits || [];

  const humanCtl = mountResourceRows(document.getElementById("rows-human"), state.ref.resourcesHuman, humanRows);
  const techCtl = mountResourceRows(document.getElementById("rows-tech"), state.ref.resourcesTech, techRows);
  const benefitCtl = mountResourceRows(document.getElementById("rows-benefit"), state.ref.resourcesAll, benefitRows);

  document.getElementById("add-human").addEventListener("click", () => { humanCtl.addRow(state.ref.resourcesHuman[0]?.id, ""); checkReapprovalWarning(); });
  document.getElementById("add-tech").addEventListener("click", () => { techCtl.addRow(state.ref.resourcesTech[0]?.id, ""); checkReapprovalWarning(); });
  document.getElementById("add-benefit").addEventListener("click", () => { benefitCtl.addRow(state.ref.resourcesAll[0]?.id, ""); checkReapprovalWarning(); });

  // Editing planned resources/benefits on an already-approved initiative will
  // send it back for re-approval on the backend — warn about that live, as
  // the champion edits, rather than only after they hit save.
  function rowsSignature(rows) {
    return rows
      .map((r) => `${r.resource_id}:${r.quantity}`)
      .sort()
      .join("|");
  }
  const originalResourcesSig = rowsSignature([...humanRows, ...techRows]);
  const originalBenefitsSig = rowsSignature(benefitRows);
  const warningEl = document.getElementById("reapproval-warning");

  function checkReapprovalWarning() {
    if (!warningEl) return;
    const currentResourcesSig = rowsSignature([...humanCtl.getValues(), ...techCtl.getValues()]);
    const currentBenefitsSig = rowsSignature(benefitCtl.getValues());
    const changed = currentResourcesSig !== originalResourcesSig || currentBenefitsSig !== originalBenefitsSig;
    warningEl.classList.toggle("hidden", !changed);
  }

  if (warningEl) {
    const form = document.getElementById("ini-form");
    form.addEventListener("input", checkReapprovalWarning);
    form.addEventListener("change", checkReapprovalWarning);
    form.addEventListener("click", (e) => {
      if (e.target.classList.contains("resource-row-remove")) checkReapprovalWarning();
    });
  }

  document.getElementById("ini-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const payload = {
      title: fd.get("title"),
      description: fd.get("description") || "",
      start_date: fd.get("start_date") || null,
      end_date: fd.get("end_date") || null,
      resources: [...humanCtl.getValues(), ...techCtl.getValues()],
      benefits: benefitCtl.getValues(),
    };
    try {
      if (isEdit) {
        await api(`/initiatives/${ini.id}`, { method: "PUT", body: payload });
        toast("Инициатива обновлена");
      } else {
        payload.champion_id = state.employeeId;
        await api("/initiatives", { method: "POST", body: payload });
        toast("Инициатива создана");
      }
      closeModal();
      if (onSaved) onSaved();
    } catch (e2) {
      toast(e2.message, true);
    }
  });
}

/* ===================== Champion tab ===================== */

function renderChampionInitiatives(container) {
  renderInitiativesView(container, {
    fixedParams: { champion_id: state.employeeId },
    showFilters: ["is_approved"],
    showDepartment: false,
    showChampion: false,
    canCreate: true,
    canEdit: (ini) => ini.champion_id === state.employeeId,
    canDelete: (ini) => ini.champion_id === state.employeeId,
    canAct: () => false,
    canLogTime: (ini) => ini.champion_id === state.employeeId,
  });
}

/* ===================== Head tabs ===================== */

function renderHeadPending(container) {
  renderInitiativesView(container, {
    fixedParams: { is_approved: false },
    showFilters: [],
    showDepartment: false,
    showChampion: true,
    canCreate: false,
    canEdit: () => false,
    canDelete: () => false,
    canAct: () => true,
  });
}

function renderHeadApproved(container) {
  renderInitiativesView(container, {
    fixedParams: { is_approved: true },
    showFilters: [],
    showDepartment: false,
    showChampion: true,
    canCreate: false,
    canEdit: () => false,
    canDelete: () => false,
    canAct: () => true,
  });
}

/* ===================== PM tab ===================== */

function renderPmInitiatives(container) {
  renderInitiativesView(container, {
    fixedParams: {},
    showFilters: ["department", "champion", "is_approved"],
    showDepartment: true,
    showChampion: true,
    canCreate: false,
    canEdit: () => false,
    canDelete: () => true,
    canAct: () => false,
  });
}

function rateTableRows(list, showTeamLead) {
  return list
    .map(
      (r) => `<tr data-id="${r.id}">
        <td>${esc(r.name)}</td>
        <td>${esc(r.unit)}</td>
        <td>
          <input type="number" min="0" step="0.01" class="rate-input" value="${r.rate}" style="max-width:160px;">
        </td>
        ${showTeamLead ? `<td>${esc(r.team_lead_name || "—")}</td>` : ""}
        <td><button type="button" class="secondary-btn small-btn rate-save-btn">Сохранить</button></td>
      </tr>`
    )
    .join("");
}

async function renderResourceRatesTab(container) {
  container.innerHTML = "";
  const [resources, employees] = await Promise.all([api("/resources"), api("/employees")]);
  const human = resources.filter((r) => r.category === "human");
  const tech = resources.filter((r) => r.category === "tech");
  const teamLeads = employees.filter((e) => e.role === "teamlead");

  const panel = el(`
    <div class="panel">
      <h2>Ресурсы и ставки</h2>
      <p class="muted">Стоимость одной единицы ресурса — используется для оценки затрат и выгоды инициатив в деньгах.</p>

      <div style="display:flex; justify-content:space-between; align-items:center;">
        <h3 style="margin-bottom:0;">Человеческие ресурсы</h3>
        <button type="button" class="primary-btn" id="add-human-resource-btn">+ Новая специализация</button>
      </div>
      <table>
        <thead><tr><th>Специализация</th><th>Единица</th><th>Ставка, ₽ за единицу</th><th>TeamLead</th><th></th></tr></thead>
        <tbody id="rates-human">${rateTableRows(human, true) || `<tr><td colspan="5" class="muted">Нет данных</td></tr>`}</tbody>
      </table>

      <h3>Технические ресурсы</h3>
      <table>
        <thead><tr><th>Ресурс</th><th>Единица</th><th>Стоимость обслуживания, ₽ за единицу в месяц</th><th></th></tr></thead>
        <tbody id="rates-tech">${rateTableRows(tech) || `<tr><td colspan="4" class="muted">Нет данных</td></tr>`}</tbody>
      </table>
    </div>
  `);
  container.appendChild(panel);

  async function refresh() {
    await loadReferenceCaches();
    renderResourceRatesTab(container);
  }

  panel.querySelectorAll(".rate-save-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const row = btn.closest("tr");
      const resourceId = Number(row.dataset.id);
      const rate = parseFloat(row.querySelector(".rate-input").value);
      if (isNaN(rate) || rate < 0) {
        toast("Ставка должна быть числом не меньше нуля", true);
        return;
      }
      try {
        const updated = await api(`/resources/${resourceId}`, { method: "PUT", body: { rate } });
        const cached = state.ref.resourcesAll.find((r) => r.id === resourceId);
        if (cached) cached.rate = updated.rate;
        toast("Ставка сохранена");
      } catch (e) {
        toast(e.message, true);
      }
    });
  });

  const addBtn = panel.querySelector("#add-human-resource-btn");
  if (addBtn) addBtn.addEventListener("click", () => openHumanResourceForm(teamLeads, refresh));
}

function openHumanResourceForm(teamLeads, onSaved) {
  openModal(`
    <h2 style="margin-top:0;">Новая специализация</h2>
    <form id="human-resource-form">
      <div class="form-grid">
        <div class="full"><label>Название специализации</label><input name="name" required></div>
        <div><label>Единица</label><input name="unit" value="чел-часы"></div>
        <div><label>Ставка, ₽ за единицу</label><input type="number" min="0" step="0.01" name="rate" value="0"></div>
        <div class="full">
          <label>TeamLead</label>
          <select name="team_lead_id" required>
            <option value="">— выберите сотрудника с ролью TeamLead —</option>
            ${selectOptions(teamLeads, "id", "full_name")}
          </select>
          ${
            teamLeads.length === 0
              ? `<p class="muted">Нет ни одного сотрудника с ролью TeamLead. Сначала добавьте его в разделе «Штат».</p>`
              : ""
          }
        </div>
      </div>
      <div class="modal-actions">
        <button type="button" class="secondary-btn" onclick="closeModal()">Отмена</button>
        <button type="submit" class="primary-btn">Создать</button>
      </div>
    </form>
  `);

  document.getElementById("human-resource-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    if (!fd.get("team_lead_id")) {
      toast("Для новой специализации необходимо указать TeamLead", true);
      return;
    }
    const payload = {
      name: fd.get("name"),
      category: "human",
      unit: fd.get("unit") || "",
      rate: parseFloat(fd.get("rate")) || 0,
      team_lead_id: Number(fd.get("team_lead_id")),
    };
    try {
      await api("/resources", { method: "POST", body: payload });
      toast("Специализация добавлена");
      closeModal();
      onSaved();
    } catch (err) {
      toast(err.message, true);
    }
  });
}

/* ===================== PM: Staff (departments & employees) ===================== */

async function renderStaffTab(container) {
  container.innerHTML = "";
  const [departments, employees] = await Promise.all([api("/departments"), api("/employees")]);

  async function refresh() {
    // Other tabs (champion/department filters, initiative forms) read from the
    // cached reference lists — keep them in sync with what Staff just changed.
    await loadReferenceCaches();
    renderStaffTab(container);
  }

  const deptPanel = el(`
    <div class="panel">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <h2 style="margin:0;">Подразделения</h2>
        <button type="button" class="primary-btn" id="add-department-btn">+ Новое подразделение</button>
      </div>
      <table class="clickable" style="margin-top:12px;">
        <thead><tr><th>Название</th><th>Руководитель</th><th>AI-чемпионы</th></tr></thead>
        <tbody>
          ${departments
            .map((d) => {
              const head = employees.find((e) => e.role === "head" && e.department_id === d.id);
              const champions = employees.filter((e) => e.role === "champion" && e.department_id === d.id);
              return `<tr data-id="${d.id}">
                <td>${esc(d.name)}</td>
                <td>${head ? esc(head.full_name) : `<span class="muted">не назначен</span>`}</td>
                <td>${champions.length ? esc(champions.map((c) => c.full_name).join(", ")) : `<span class="muted">нет</span>`}</td>
              </tr>`;
            })
            .join("") || `<tr><td colspan="3" class="muted">Нет подразделений</td></tr>`}
        </tbody>
      </table>
    </div>
  `);
  container.appendChild(deptPanel);

  const empPanel = el(`
    <div class="panel">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <h2 style="margin:0;">Сотрудники</h2>
        <button type="button" class="primary-btn" id="add-employee-btn">+ Новый сотрудник</button>
      </div>
      <table style="margin-top:12px;">
        <thead><tr><th>ФИО</th><th>Роль</th><th>Подразделение</th><th>Должность</th><th>Email</th></tr></thead>
        <tbody>
          ${employees
            .map(
              (e) => `<tr>
                <td>${esc(e.full_name)}</td>
                <td>${esc(roleLabel(e.role, e.specialization))}</td>
                <td>${esc(e.department_name || "—")}</td>
                <td>${esc(e.position || "—")}</td>
                <td>${esc(e.email || "—")}</td>
              </tr>`
            )
            .join("") || `<tr><td colspan="5" class="muted">Нет сотрудников</td></tr>`}
        </tbody>
      </table>
    </div>
  `);
  container.appendChild(empPanel);

  deptPanel.querySelectorAll("tbody tr[data-id]").forEach((row) => {
    row.addEventListener("click", () => {
      const dept = departments.find((d) => d.id === Number(row.dataset.id));
      openDepartmentDetail(dept, employees, refresh);
    });
  });

  deptPanel.querySelector("#add-department-btn").addEventListener("click", () => {
    openDepartmentForm(refresh);
  });
  empPanel.querySelector("#add-employee-btn").addEventListener("click", () => {
    openEmployeeForm(departments, refresh);
  });
}

function openDepartmentForm(onSaved) {
  openModal(`
    <h2 style="margin-top:0;">Новое подразделение</h2>
    <form id="dept-form">
      <div class="full"><label>Название</label><input name="name" required></div>
      <div class="modal-actions">
        <button type="button" class="secondary-btn" onclick="closeModal()">Отмена</button>
        <button type="submit" class="primary-btn">Создать</button>
      </div>
    </form>
  `);
  document.getElementById("dept-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = new FormData(e.target).get("name");
    try {
      await api("/departments", { method: "POST", body: { name } });
      toast("Подразделение создано");
      closeModal();
      onSaved();
    } catch (err) {
      toast(err.message, true);
    }
  });
}

function openEmployeeForm(departments, onSaved) {
  openModal(`
    <h2 style="margin-top:0;">Новый сотрудник</h2>
    <form id="employee-form">
      <div class="form-grid">
        <div class="full"><label>ФИО</label><input name="full_name" required></div>
        <div><label>Должность</label><input name="position"></div>
        <div><label>Email</label><input type="email" name="email"></div>
        <div>
          <label>Роль</label>
          <select name="role" id="employee-role-select">
            <option value="champion">AI-чемпион</option>
            <option value="head">Руководитель подразделения</option>
            <option value="pm">PM</option>
            <option value="top">Топ-менеджмент</option>
            <option value="teamlead">TeamLead</option>
          </select>
        </div>
        <div id="employee-department-field">
          <label>Подразделение</label>
          <select name="department_id">${selectOptions(departments, "id", "name")}</select>
        </div>
      </div>
      <div class="modal-actions">
        <button type="button" class="secondary-btn" onclick="closeModal()">Отмена</button>
        <button type="submit" class="primary-btn">Создать</button>
      </div>
    </form>
  `);

  const roleSelect = document.getElementById("employee-role-select");
  const deptField = document.getElementById("employee-department-field");
  function syncDeptVisibility() {
    const needsDept = roleSelect.value === "champion" || roleSelect.value === "head";
    deptField.classList.toggle("hidden", !needsDept);
  }
  roleSelect.addEventListener("change", syncDeptVisibility);
  syncDeptVisibility();

  document.getElementById("employee-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const role = fd.get("role");
    const needsDept = role === "champion" || role === "head";
    const payload = {
      full_name: fd.get("full_name"),
      position: fd.get("position") || "",
      email: fd.get("email") || "",
      role,
      department_id: needsDept && fd.get("department_id") ? Number(fd.get("department_id")) : null,
    };
    try {
      await api("/employees", { method: "POST", body: payload });
      toast("Сотрудник добавлен");
      closeModal();
      onSaved();
    } catch (err) {
      toast(err.message, true);
    }
  });
}

function openDepartmentDetail(dept, employees, onSaved) {
  const head = employees.find((e) => e.role === "head" && e.department_id === dept.id);
  const champions = employees.filter((e) => e.role === "champion" && e.department_id === dept.id);
  const availableHeads = employees.filter((e) => e.role === "head" && e.department_id !== dept.id);
  const availableChampions = employees.filter((e) => e.role === "champion" && e.department_id !== dept.id);

  openModal(`
    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
      <h2 style="margin-top:0;">${esc(dept.name)}</h2>
      <button class="link-btn" onclick="closeModal()">✕</button>
    </div>

    <h3>Руководитель подразделения</h3>
    <p>${head ? esc(head.full_name) : `<span class="muted">Не назначен</span>`}</p>
    <div class="filters">
      <div class="field">
        <label>Назначить руководителем</label>
        <select id="assign-head-select">
          <option value="">Выберите...</option>
          ${selectOptions(availableHeads, "id", "full_name")}
        </select>
      </div>
      <button type="button" class="secondary-btn" id="assign-head-btn">Назначить</button>
      ${head ? `<button type="button" class="danger-btn" id="unassign-head-btn">Открепить</button>` : ""}
    </div>
    ${!availableHeads.length ? `<p class="muted">Нет свободных сотрудников с ролью «Руководитель подразделения» — создайте нового во вкладке «Сотрудники».</p>` : ""}

    <h3>AI-чемпионы</h3>
    ${
      champions.length
        ? `<table><thead><tr><th>ФИО</th><th></th></tr></thead><tbody>
      ${champions
        .map(
          (c) => `<tr data-id="${c.id}"><td>${esc(c.full_name)}</td><td><button type="button" class="danger-btn small-btn detach-champion-btn">Открепить</button></td></tr>`
        )
        .join("")}
    </tbody></table>`
        : `<p class="muted">Нет прикреплённых чемпионов.</p>`
    }
    <div class="filters">
      <div class="field">
        <label>Прикрепить чемпиона</label>
        <select id="attach-champion-select">
          <option value="">Выберите...</option>
          ${selectOptions(availableChampions, "id", "full_name")}
        </select>
      </div>
      <button type="button" class="secondary-btn" id="attach-champion-btn">Прикрепить</button>
    </div>

    <div class="modal-actions">
      <button class="secondary-btn" onclick="closeModal()">Закрыть</button>
    </div>
  `);

  async function reassign(employeeId, departmentId) {
    try {
      await api(`/employees/${employeeId}`, { method: "PUT", body: { department_id: departmentId } });
      toast("Изменения сохранены");
      closeModal();
      onSaved();
    } catch (err) {
      toast(err.message, true);
    }
  }

  const assignHeadBtn = document.getElementById("assign-head-btn");
  if (assignHeadBtn) {
    assignHeadBtn.addEventListener("click", () => {
      const id = document.getElementById("assign-head-select").value;
      if (!id) return;
      reassign(Number(id), dept.id);
    });
  }
  const unassignHeadBtn = document.getElementById("unassign-head-btn");
  if (unassignHeadBtn) {
    unassignHeadBtn.addEventListener("click", () => reassign(head.id, null));
  }
  const attachBtn = document.getElementById("attach-champion-btn");
  if (attachBtn) {
    attachBtn.addEventListener("click", () => {
      const id = document.getElementById("attach-champion-select").value;
      if (!id) return;
      reassign(Number(id), dept.id);
    });
  }
  document.querySelectorAll(".detach-champion-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = Number(btn.closest("tr").dataset.id);
      reassign(id, null);
    });
  });
}

/* ===================== Top tabs ===================== */

function renderTopPending(container) {
  renderInitiativesView(container, {
    fixedParams: { awaiting_me: true },
    showFilters: [],
    showDepartment: true,
    showChampion: true,
    canCreate: false,
    canEdit: () => false,
    canDelete: () => false,
    canAct: () => true,
  });
}

function renderTopInitiatives(container) {
  renderInitiativesView(container, {
    fixedParams: {},
    showFilters: ["department", "champion", "is_approved"],
    showDepartment: true,
    showChampion: true,
    canCreate: false,
    canEdit: () => false,
    canDelete: () => false,
    canAct: () => false,
  });
}

const CHART_FONT = "12px -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif";
const CHART_GRID = "#e5e9ed";
const CHART_AXIS_TEXT = "#6b7785";
const CHART_VALUE_TEXT = "#1f2933";

async function renderTopDashboard(container) {
  const data = await api("/dashboard/top");
  container.innerHTML = "";

  container.appendChild(el(`
    <div class="stat-row">
      <div class="stat-card"><div class="value">${data.total_initiatives}</div><div class="label">Инициатив в портфеле</div></div>
      <div class="stat-card"><div class="value">${data.approved_count}</div><div class="label">Согласовано</div></div>
      <div class="stat-card"><div class="value">${data.pending_count}</div><div class="label">Не согласовано</div></div>
    </div>
  `));

  container.appendChild(el(`
    <div class="stat-row">
      <div class="stat-card"><div class="value">${fmtNum(data.total_planned_cost_money)} ₽</div><div class="label">Плановые затраты портфеля</div></div>
      <div class="stat-card"><div class="value">${fmtNum(data.total_fact_cost_money)} ₽</div><div class="label">Фактические затраты портфеля</div></div>
      <div class="stat-card"><div class="value">${paybackText(data.total_payback_months)}</div><div class="label">Срок окупаемости портфеля</div></div>
    </div>
  `));

  const totalBenefitPanel = el(`
    <div class="panel">
      <h2>Общая ожидаемая выгода портфеля (экономия в месяц)</h2>
      <div style="font-size:2em; font-weight:700;">${fmtNum(data.total_benefit_money)} ₽</div>
    </div>
  `);
  container.appendChild(totalBenefitPanel);

  // Money view: quantity × the resource rate set by PM in "Ресурсы и ставки" —
  // resources with no rate configured simply contribute 0. The payback label
  // under each department's bars is the sum of its own initiatives' payback
  // periods (planned cost ÷ monthly benefit each).
  const moneyPanel = el(`
    <div class="panel">
      <h2>Затраты и окупаемость</h2>
      <canvas id="money-chart" width="860" height="340"></canvas>
      <div class="legend">
        <span><span class="dot" style="background:#93c5fd"></span>Плановые затраты</span>
        <span><span class="dot" style="background:#1d4ed8"></span>Фактические затраты</span>
      </div>
    </div>
  `);
  container.appendChild(moneyPanel);
  drawGroupedColumnChart(moneyPanel.querySelector("#money-chart"), {
    categories: data.by_department.map((d) => d.department),
    seriesA: data.by_department.map((d) => d.planned_cost_money),
    seriesB: data.by_department.map((d) => d.fact_cost_money),
    colorA: "#93c5fd",
    colorB: "#1d4ed8",
    valueFormatter: (v) => fmtNum(v),
    subLabels: data.by_department.map((d) => paybackText(d.payback_months_sum)),
    subLabelPrefix: "Окупаемость",
  });

  // Human-hours × rate = ₽ — shown as cost so it's directly comparable across
  // specializations regardless of their differing rates.
  const humanPlanned = data.resources_planned.filter((r) => r.category === "human");
  if (humanPlanned.length) {
    const humanPanel = el(`
      <div class="panel">
        <h2>Плановые затраты по специализациям</h2>
        <canvas id="human-chart" width="860" height="300"></canvas>
      </div>
    `);
    container.appendChild(humanPanel);
    drawColumnChart(humanPanel.querySelector("#human-chart"), {
      categories: humanPlanned.map((r) => r.resource),
      values: humanPlanned.map((r) => r.total_money),
      color: "#2563eb",
      valueFormatter: (v) => fmtNum(v),
    });
  }

  // Technical resources use different units (ядра / ГБ / ТБ) — kept as a table, not blended into one chart.
  const techPlanned = data.resources_planned.filter((r) => r.category === "tech");
  const techPanel = el(`
    <div class="panel">
      <h2>Плановые технические ресурсы</h2>
      <table>
        <thead><tr><th>Ресурс</th><th>Количество</th><th>Единица</th></tr></thead>
        <tbody>${techPlanned.map((r) => `<tr><td>${esc(r.resource)}</td><td>${fmtNum(r.total)}</td><td>${esc(r.unit)}</td></tr>`).join("") || `<tr><td colspan="3" class="muted">Нет данных</td></tr>`}</tbody>
      </table>
    </div>
  `);
  container.appendChild(techPanel);

  const benefitPanel = el(`
    <div class="panel">
      <h2>Ожидаемая выгода портфеля (экономия в месяц)</h2>
      <table>
        <thead><tr><th>Ресурс</th><th>Категория</th><th>Количество / мес</th><th>Единица</th><th>Руб / месяц</th></tr></thead>
        <tbody>${data.benefits_total
          .map((r) => `<tr><td>${esc(r.resource)}</td><td>${r.category === "human" ? "Человеческий" : "Технический"}</td><td>${fmtNum(r.total)}</td><td>${esc(r.unit)}</td><td>${fmtNum(r.total_money)}</td></tr>`)
          .join("") || `<tr><td colspan="5" class="muted">Нет данных</td></tr>`}</tbody>
      </table>
    </div>
  `);
  container.appendChild(benefitPanel);

  const deptPanel = el(`
    <div class="panel">
      <h2>Инициативы по подразделениям: согласовано и не согласовано</h2>
      <canvas id="dept-chart" width="860" height="300"></canvas>
      <div class="legend">
        <span><span class="dot" style="background:#93c5fd"></span>Не согласовано</span>
        <span><span class="dot" style="background:#1d4ed8"></span>Согласовано</span>
      </div>
    </div>
  `);
  container.appendChild(deptPanel);
  drawGroupedColumnChart(deptPanel.querySelector("#dept-chart"), {
    categories: data.by_department.map((d) => d.department),
    seriesA: data.by_department.map((d) => d.pending_count),
    seriesB: data.by_department.map((d) => d.approved_count),
    colorA: "#93c5fd",
    colorB: "#1d4ed8",
    valueFormatter: (v) => String(v),
  });
}

function setupColumnChartAxes(ctx, W, H, basePadding, maxValue, valueFormatter) {
  const niceMax = maxValue > 0 ? maxValue : 1;
  const gridLines = 4;

  ctx.font = CHART_FONT;
  // Measure the widest tick label first — large numbers (7+ digits) can be
  // wider than a fixed left margin, which clips their leading digits at the
  // canvas edge instead of just crowding the plot area. Grow the margin to fit.
  let maxLabelWidth = 0;
  for (let i = 0; i <= gridLines; i++) {
    const v = (niceMax / gridLines) * i;
    maxLabelWidth = Math.max(maxLabelWidth, ctx.measureText(valueFormatter(v)).width);
  }
  const padding = { ...basePadding, left: Math.max(basePadding.left, maxLabelWidth + 20) };

  const plotW = W - padding.left - padding.right;
  const plotH = H - padding.top - padding.bottom;

  ctx.clearRect(0, 0, W, H);
  ctx.font = CHART_FONT;
  ctx.textBaseline = "middle";

  ctx.strokeStyle = CHART_GRID;
  ctx.lineWidth = 1;
  ctx.fillStyle = CHART_AXIS_TEXT;
  ctx.textAlign = "right";
  for (let i = 0; i <= gridLines; i++) {
    const v = (niceMax / gridLines) * i;
    const y = padding.top + plotH - (v / niceMax) * plotH;
    ctx.beginPath();
    ctx.moveTo(padding.left, y + 0.5);
    ctx.lineTo(padding.left + plotW, y + 0.5);
    ctx.stroke();
    ctx.fillText(valueFormatter(v), padding.left - 10, y);
  }

  ctx.strokeStyle = "#c3ccd4";
  ctx.beginPath();
  ctx.moveTo(padding.left, padding.top + plotH + 0.5);
  ctx.lineTo(padding.left + plotW, padding.top + plotH + 0.5);
  ctx.stroke();

  return { plotW, plotH, niceMax, padding };
}

const SUB_LABEL_FONT = "bold 12px -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif";
const SUB_LABEL_COLOR = "#2563eb";

function drawCategoryLabels(ctx, categories, padding, plotW, plotH, slotW, subLabels, subLabelPrefix) {
  ctx.fillStyle = CHART_AXIS_TEXT;
  ctx.font = CHART_FONT;
  const rotate = categories.some((c) => c.length > 10);
  const subLabelOffset = rotate ? 60 : 30;
  categories.forEach((cat, idx) => {
    const cx = padding.left + slotW * idx + slotW / 2;
    const cy = padding.top + plotH + 8;
    ctx.save();
    if (rotate) {
      ctx.translate(cx, cy);
      ctx.rotate(-Math.PI / 6);
      ctx.textAlign = "right";
      ctx.textBaseline = "top";
      ctx.fillText(cat, 4, 4);
    } else {
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillText(cat, cx, cy);
    }
    ctx.restore();

    if (subLabels && subLabels[idx]) {
      ctx.save();
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.font = SUB_LABEL_FONT;
      ctx.fillStyle = SUB_LABEL_COLOR;
      ctx.fillText(subLabels[idx], cx, cy + subLabelOffset);
      ctx.restore();
    }
  });

  // The row label ("Окупаемость") is drawn once on the left instead of being
  // repeated in front of every value under the bars.
  if (subLabels && subLabelPrefix) {
    ctx.save();
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.font = SUB_LABEL_FONT;
    ctx.fillStyle = SUB_LABEL_COLOR;
    ctx.fillText(subLabelPrefix, 4, padding.top + plotH + 8 + subLabelOffset);
    ctx.restore();
  }
}

function drawColumnChart(canvas, { categories, values, color, valueFormatter }) {
  const ctx = canvas.getContext("2d");
  const W = canvas.width;
  const H = canvas.height;
  const basePadding = { left: 60, right: 20, top: 16, bottom: 64 };
  const maxValue = Math.max(...values, 1);
  const { plotW, plotH, niceMax, padding } = setupColumnChartAxes(ctx, W, H, basePadding, maxValue, valueFormatter);

  if (!categories.length) return;
  const slotW = plotW / categories.length;
  const barW = Math.min(56, slotW * 0.5);

  values.forEach((v, idx) => {
    const barH = (v / niceMax) * plotH;
    const x = padding.left + slotW * idx + slotW / 2 - barW / 2;
    const y = padding.top + plotH - barH;
    ctx.fillStyle = color;
    ctx.fillRect(x, y, barW, barH);

    if (v > 0) {
      ctx.fillStyle = CHART_VALUE_TEXT;
      ctx.textAlign = "center";
      ctx.textBaseline = "bottom";
      ctx.fillText(valueFormatter(v), x + barW / 2, y - 4);
    }
  });

  drawCategoryLabels(ctx, categories, padding, plotW, plotH, slotW);
}

function drawGroupedColumnChart(canvas, { categories, seriesA, seriesB, colorA, colorB, valueFormatter, subLabels, subLabelPrefix }) {
  const ctx = canvas.getContext("2d");
  const W = canvas.width;
  const H = canvas.height;
  const basePadding = { left: 50, right: 20, top: 16, bottom: subLabels ? 110 : 64 };
  const maxValue = Math.max(...seriesA, ...seriesB, 1);
  const { plotW, plotH, niceMax, padding } = setupColumnChartAxes(ctx, W, H, basePadding, maxValue, valueFormatter);

  if (!categories.length) return;
  const slotW = plotW / categories.length;
  const barW = Math.min(30, slotW * 0.3);
  const gap = 6;

  categories.forEach((_, idx) => {
    const groupCenter = padding.left + slotW * idx + slotW / 2;
    [
      { v: seriesA[idx], color: colorA, x: groupCenter - barW - gap / 2 },
      { v: seriesB[idx], color: colorB, x: groupCenter + gap / 2 },
    ].forEach(({ v, color, x }) => {
      const barH = (v / niceMax) * plotH;
      const y = padding.top + plotH - barH;
      ctx.fillStyle = color;
      ctx.fillRect(x, y, barW, barH);
      if (v > 0) {
        ctx.fillStyle = CHART_VALUE_TEXT;
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        ctx.fillText(valueFormatter(v), x + barW / 2, y - 4);
      }
    });
  });

  drawCategoryLabels(ctx, categories, padding, plotW, plotH, slotW, subLabels, subLabelPrefix);
}

/* ===================== Reports ===================== */

function renderReportsTab(container) {
  container.innerHTML = "";
  const showDepartment = state.role === "pm" || state.role === "top";

  const scopeNote = {
    champion: "Отчёт строится только по вашим инициативам.",
    head: "Отчёт строится по инициативам AI-чемпионов вашего подразделения.",
    pm: "Отчёт строится по всем инициативам портала.",
    top: "Отчёт строится по всем инициативам портала.",
  }[state.role] || "";

  const panel = el(`
    <div class="panel">
      <h2>Отчёты</h2>
      <p class="muted">${esc(scopeNote)} Выгрузка — файл с одной строкой на инициативу и итогами внизу.</p>

      <div class="form-grid">
        <div><label>Дата начала (от)</label><input type="date" id="report-date-from"></div>
        <div><label>Дата окончания (до)</label><input type="date" id="report-date-to"></div>
        <div>
          <label>Статус инициативы</label>
          <select id="report-status">
            <option value="">Все</option>
            ${Object.entries(REPORT_STATUS_LABELS)
              .map(([value, label]) => `<option value="${value}">${esc(label)}</option>`)
              .join("")}
          </select>
        </div>
        ${
          showDepartment
            ? `<div><label>Подразделение</label>
                <select id="report-department"><option value="">Все</option>${selectOptions(state.ref.departments, "id", "name")}</select>
              </div>`
            : ""
        }
        <div>
          <label>Формат файла</label>
          <select id="report-format">
            <option value="xlsx">Excel (.xlsx)</option>
            <option value="csv">CSV (.csv)</option>
          </select>
        </div>
      </div>

      <div class="modal-actions" style="justify-content:flex-start; margin-top:16px;">
        <button type="button" class="primary-btn" id="report-download-btn">Скачать отчёт</button>
      </div>
    </div>
  `);
  container.appendChild(panel);

  const btn = panel.querySelector("#report-download-btn");
  btn.addEventListener("click", async () => {
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Формирование отчёта...";
    try {
      const params = {
        date_from: panel.querySelector("#report-date-from").value || undefined,
        date_to: panel.querySelector("#report-date-to").value || undefined,
        status: panel.querySelector("#report-status").value || undefined,
      };
      const deptEl = panel.querySelector("#report-department");
      if (deptEl) params.department_id = deptEl.value || undefined;
      const format = panel.querySelector("#report-format").value;
      await downloadFile(`/reports/initiatives.${format}`, params, `report.${format}`);
      toast("Отчёт сформирован");
    } catch (e) {
      toast(e.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  });
}
