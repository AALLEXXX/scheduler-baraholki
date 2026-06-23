const tg = window.Telegram?.WebApp;
const initData = tg?.initData || "";
const apiBase = window.location.pathname.startsWith("/scheduler") ? "/scheduler/api" : "/api";

if (tg) {
  tg.ready();
  tg.expand();
}

const state = {
  config: { bot_username: "scheduler_baraholki_bot" },
  sessions: [],
  chats: [],
  folders: [],
  posts: [],
  audit: { items: [], page: 1, page_size: 20, total: 0 },
  auditLoading: false,
  activeTab: "posts",
  pendingSessionId: null,
  pendingPhone: "",
  selectedDraftId: null,
  selectedChatIds: new Set(),
  selectedFolderId: "all",
  draftPage: 1,
  draftPageSize: 5,
  queuePage: 1,
  queuePageSize: 5,
  auditPage: 1,
  auditPageSize: 20,
  groupSearch: "",
  groupPage: 1,
  groupPageSize: 10,
  editingPostId: null,
  editSelectedChatIds: new Set(),
  editSelectedFolderId: "all",
  editGroupSearch: "",
  editGroupPage: 1,
  editGroupPageSize: 8,
  groupsSyncedOnInit: false,
};

let smsCooldownTimer = null;

function activeSessions() {
  return state.sessions.filter((session) => session.status === "active");
}

function draftPosts() {
  return state.posts.filter((post) => post.status === "draft");
}

function queuePosts() {
  return state.posts.filter((post) => post.status !== "draft" && post.status !== "archived");
}

function notify(message, type = "info") {
  const notice = document.querySelector("#notice");
  notice.textContent = message;
  notice.className = `notice ${type === "error" ? "error" : ""}`.trim();
  notice.hidden = false;

  if (tg?.showPopup) {
    tg.showPopup({ title: type === "error" ? "Ошибка" : "Готово", message });
  }
}

function clearNotice() {
  document.querySelector("#notice").hidden = true;
}

function headers() {
  return {
    "Content-Type": "application/json",
    "X-Telegram-Init-Data": initData,
  };
}

async function api(path, options = {}) {
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  const response = await fetch(`${apiBase}${cleanPath}`, {
    ...options,
    headers: { ...headers(), ...(options.headers || {}) },
  });

  if (!response.ok) {
    let message = response.statusText;
    const text = await response.text();
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed.detail === "string") {
        message = parsed.detail;
      } else if (Array.isArray(parsed.detail)) {
        message = parsed.detail.map((item) => item.msg || "Проверьте заполнение формы").join("\n");
      } else {
        message = "Не получилось выполнить действие. Проверьте данные и попробуйте еще раз.";
      }
    } catch {
      message = text || message;
    }
    throw new Error(message);
  }
  return response.json();
}

function setBusy(button, busy, text) {
  if (!button) return;
  button.disabled = busy;
  if (text) button.textContent = text;
}

function startSmsCooldown(seconds = 90) {
  const button = document.querySelector("#resend-sms-code");
  if (!button) return;
  if (smsCooldownTimer) {
    window.clearInterval(smsCooldownTimer);
  }

  let remaining = seconds;
  const tick = () => {
    if (remaining <= 0) {
      window.clearInterval(smsCooldownTimer);
      smsCooldownTimer = null;
      setBusy(button, false, "Отправить SMS");
      return;
    }
    setBusy(button, true, `SMS через ${remaining}с`);
    remaining -= 1;
  };

  tick();
  smsCooldownTimer = window.setInterval(tick, 1000);
}

function selectedGroups() {
  return [...state.selectedChatIds];
}

function selectedEditGroups() {
  return [...state.editSelectedChatIds];
}

function folderItems() {
  return [
    { id: "all", title: "Все", telegram_chat_ids: state.chats.map((chat) => chat.telegram_chat_id) },
    ...state.folders,
  ];
}

function sortSelectedFirst(chats, selectedIds) {
  if (!selectedIds?.size) return chats;
  return [...chats].sort((left, right) => {
    const leftSelected = selectedIds.has(left.id);
    const rightSelected = selectedIds.has(right.id);
    if (leftSelected === rightSelected) return 0;
    return leftSelected ? -1 : 1;
  });
}

function filteredChats({
  folderId = state.selectedFolderId,
  query = state.groupSearch,
  selectedIds = state.selectedChatIds,
} = {}) {
  let chats = state.chats;
  if (folderId !== "all") {
    const folder = state.folders.find((item) => String(item.id) === folderId);
    const folderChatIds = new Set((folder?.telegram_chat_ids || []).map((id) => Number(id)));
    chats = chats.filter((chat) => folderChatIds.has(Number(chat.telegram_chat_id)));
  }

  const cleanQuery = query.trim().toLowerCase();
  if (cleanQuery) {
    chats = chats.filter((chat) => chat.title.toLowerCase().includes(cleanQuery));
  }
  return sortSelectedFirst(chats, selectedIds);
}

function pageCount(total, pageSize) {
  return Math.max(1, Math.ceil(total / pageSize));
}

function clampPage(page, total, pageSize) {
  const pages = pageCount(total, pageSize);
  return Math.min(Math.max(1, page), pages);
}

function pageSlice(items, page, pageSize) {
  const start = (page - 1) * pageSize;
  return items.slice(start, start + pageSize);
}

function clampGroupPage() {
  const pages = pageCount(filteredChats().length, state.groupPageSize);
  state.groupPage = clampPage(state.groupPage, filteredChats().length, state.groupPageSize);
  return pages;
}

function clampEditGroupPage() {
  const total = filteredChats({
    folderId: state.editSelectedFolderId,
    query: state.editGroupSearch,
    selectedIds: state.editSelectedChatIds,
  }).length;
  const pages = pageCount(total, state.editGroupPageSize);
  state.editGroupPage = clampPage(state.editGroupPage, total, state.editGroupPageSize);
  return pages;
}

function dateTimeLocalValue(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offsetMs = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function nextDefaultDateTimeLocal() {
  const date = new Date(Date.now() + 60 * 60 * 1000);
  date.setSeconds(0, 0);
  return dateTimeLocalValue(date.toISOString());
}

function isPastOrNow(value) {
  if (!value) return true;
  const time = new Date(value).getTime();
  return Number.isNaN(time) || time <= Date.now();
}

function chatTitleById(chatId) {
  return state.chats.find((chat) => chat.id === chatId)?.title || "Группа не найдена";
}

function statusLabel(status) {
  if (status === "scheduled") return "Запланирован";
  if (status === "paused") return "На паузе";
  if (status === "archived") return "Завершён";
  if (status === "draft") return "Черновик";
  return status;
}

function auditStatusLabel(status) {
  if (status === "done") return "Успешно";
  if (status === "failed") return "Ошибка";
  if (status === "pending") return "Ожидает";
  if (status === "processing") return "Отправляется";
  if (status === "cancelled") return "Отменено";
  return status;
}

function auditStatusIcon(status) {
  if (status === "done") return "✓";
  if (status === "failed") return "!";
  if (status === "processing") return "…";
  if (status === "cancelled") return "×";
  return "•";
}

function shortWords(value, maxWords = 8) {
  const words = stripHtml(value || "").trim().split(/\s+/).filter(Boolean);
  if (words.length <= maxWords) return words.join(" ");
  return `${words.slice(0, maxWords).join(" ")}...`;
}

function mediaCountLabel(count) {
  if (!count) return "без фото";
  if (count === 1) return "1 фото";
  return `${count} фото`;
}

function formatDateTime(value) {
  if (!value) return "нет даты";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "нет даты";
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function scheduleLabel(post) {
  const when = post.next_run_at ? formatDateTime(post.next_run_at) : "дата не выбрана";
  if (post.schedule_kind === "interval") {
    return `${when}, затем каждые ${post.interval_minutes} мин.`;
  }
  if (post.schedule_kind === "daily") return `${when}, затем каждый день`;
  if (post.schedule_kind === "weekdays") return `${when}, затем по будням`;
  if (post.schedule_kind === "weekends") return `${when}, затем по выходным`;
  if (post.schedule_kind === "every_other_day") return `${when}, затем через день`;
  if (post.schedule_kind === "weekly") return `${when}, затем раз в неделю`;
  if (post.schedule_kind === "custom_weekdays") {
    return `${when}, затем ${weekdaySummary(post.schedule_weekdays || [])}`;
  }
  return `${when}, один раз`;
}

function weekdaySummary(days) {
  const names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
  const selected = [...new Set((days || []).map((day) => Number(day)).filter((day) => day >= 0 && day <= 6))]
    .sort((left, right) => left - right)
    .map((day) => names[day]);
  return selected.length ? selected.join(", ") : "по выбранным дням";
}

function targetSummary(post) {
  const titles = (post.target_chat_ids || []).map(chatTitleById);
  if (titles.length === 0) return "Группы не выбраны";
  if (titles.length <= 2) return titles.join(", ");
  return `${titles.slice(0, 2).join(", ")} и ещё ${titles.length - 2}`;
}

function mediaLabel(post) {
  const count = post.media?.length || 0;
  if (!count) return "без медиа";
  if (count === 1) return "1 медиа";
  return `${count} медиа`;
}

function scheduleNeedsWeekdays(scheduleKind) {
  return scheduleKind === "custom_weekdays";
}

function updateScheduleControls(form, prefix = "") {
  const scheduleKind = form.elements.schedule_kind.value;
  document.querySelector(`#${prefix}interval-row`).hidden = scheduleKind !== "interval";
  document.querySelector(`#${prefix}weekday-row`).hidden = !scheduleNeedsWeekdays(scheduleKind);
}

function selectedWeekdays(form) {
  return [...form.querySelectorAll('input[name="schedule_weekdays"]:checked')].map((input) =>
    Number(input.value),
  );
}

function setSelectedWeekdays(form, days) {
  const selected = new Set((days || []).map((day) => Number(day)));
  form.querySelectorAll('input[name="schedule_weekdays"]').forEach((input) => {
    input.checked = selected.has(Number(input.value));
  });
}

async function confirmSpamRiskIfNeeded(intervalMinutes) {
  if (intervalMinutes < 20) {
    notify("Минимальный интервал повтора — 20 минут.", "error");
    return false;
  }

  if (intervalMinutes > 30) return true;

  const message =
    "За частую отправку сообщений ваш аккаунт в Telegram может быть ограничен или заблокирован.";

  if (tg?.showPopup) {
    return new Promise((resolve) => {
      tg.showPopup(
        {
          title: "Риск блокировки",
          message,
          buttons: [
            { id: "understand", type: "default", text: "Я понимаю" },
            { id: "cancel", type: "cancel", text: "Отмена" },
          ],
        },
        (buttonId) => resolve(buttonId === "understand"),
      );
    });
  }

  return window.confirm(`${message}\n\nПродолжить?`);
}

async function confirmDeletePost(post) {
  const isDraft = post.status === "draft";
  const message = isDraft
    ? "Черновик исчезнет из миниаппа. Сообщение в чате с ботом тоже будет удалено, если Telegram разрешит."
    : "Пост будет удалён из очереди. Исходное сообщение в чате с ботом тоже будет удалено, если Telegram разрешит.";

  if (tg?.showPopup) {
    return new Promise((resolve) => {
      tg.showPopup(
        {
          title: isDraft ? "Удалить черновик?" : "Удалить из очереди?",
          message,
          buttons: [
            { id: "delete", type: "destructive", text: "Удалить" },
            { id: "cancel", type: "cancel", text: "Отмена" },
          ],
        },
        (buttonId) => resolve(buttonId === "delete"),
      );
    });
  }

  return window.confirm(message);
}

function render() {
  const connected = activeSessions();
  const primarySession = connected[0] || state.sessions[0];
  const hasAccount = connected.length > 0;
  const hasGroups = state.chats.length > 0;
  const drafts = draftPosts();
  const queued = queuePosts();

  applyTabVisibility();

  document.querySelector("#posts-count").textContent = `${queued.length} постов`;
  document.querySelector("#drafts-count").textContent = `${drafts.length} постов`;
  document.querySelector("#groups-count").textContent = `${filteredChats().length} групп`;

  const stateDot = document.querySelector("#account-state");
  stateDot.className = `status-dot ${hasAccount ? "online" : ""}`;
  document.querySelector("#account-title").textContent = hasAccount ? "Аккаунт подключен" : "Аккаунт не подключен";
  document.querySelector("#account-subtitle").textContent = hasAccount
    ? `${primarySession.phone || ""} ${primarySession.username ? `@${primarySession.username}` : ""}`.trim()
    : "Подключите Telegram-аккаунт для отправки";

  document.querySelector("#connect-panel").hidden = hasAccount || state.activeTab !== "posts";
  document.querySelector("#logout-account").hidden = !hasAccount;
  document.querySelector("#compose-hint").textContent = hasAccount
    ? hasGroups
      ? "Выберите черновик, время и группы."
      : "Группы обновятся автоматически. Можно обновить вручную."
    : "Сначала подключите аккаунт.";

  const picker = document.querySelector("#group-picker");
  if (!hasGroups) {
    picker.replaceChildren(emptyChip(hasAccount ? "Группы пока не загружены" : "Нет подключенного аккаунта"));
    document.querySelector("#folder-picker").replaceChildren();
  } else {
    renderFolderPicker();
    renderGroupPicker();
  }

  const saveButton = document.querySelector("#save-post");
  saveButton.disabled = !hasAccount || !hasGroups || !state.selectedDraftId;

  renderDraftPicker();

  const posts = document.querySelector("#posts");
  if (queued.length === 0) {
    posts.replaceChildren(emptyPost("Постов пока нет"));
    renderQueuePagination(queued.length);
  } else {
    state.queuePage = clampPage(state.queuePage, queued.length, state.queuePageSize);
    posts.replaceChildren(...pageSlice(queued, state.queuePage, state.queuePageSize).map(renderPost));
    renderQueuePagination(queued.length);
  }

  renderAudit();
  applyTabVisibility();
}

function applyTabVisibility() {
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.classList.toggle("selected", button.dataset.tab === state.activeTab);
  });
  document.querySelectorAll("[data-tab-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.tabPanel !== state.activeTab;
  });
}

function renderFolderPicker() {
  const picker = document.querySelector("#folder-picker");
  const items = folderItems();
  if (!items.some((folder) => String(folder.id) === state.selectedFolderId)) {
    state.selectedFolderId = "all";
  }

  picker.replaceChildren(
    ...items.map((folder) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `folder-chip ${String(folder.id) === state.selectedFolderId ? "selected" : ""}`.trim();
      button.textContent = folder.title;
      button.addEventListener("click", () => {
        state.selectedFolderId = String(folder.id);
        state.groupPage = 1;
        render();
      });
      return button;
    }),
  );
}

function renderDraftPicker() {
  const picker = document.querySelector("#draft-picker");
  const drafts = draftPosts();
  state.draftPage = clampPage(state.draftPage, drafts.length, state.draftPageSize);
  renderDraftPagination(drafts.length);
  const visibleDrafts = pageSlice(drafts, state.draftPage, state.draftPageSize);
  if (!visibleDrafts.some((post) => post.id === state.selectedDraftId)) {
    state.selectedDraftId = visibleDrafts[0]?.id || null;
  }

  if (drafts.length === 0) {
    picker.replaceChildren(emptyPost("Черновиков пока нет"));
    return;
  }

  picker.replaceChildren(
    ...visibleDrafts.map((post) => {
      const card = document.createElement("article");
      card.className = `draft-card ${state.selectedDraftId === post.id ? "selected" : ""}`.trim();
      card.role = "button";
      card.tabIndex = 0;
      card.addEventListener("click", () => {
        state.selectedDraftId = post.id;
        render();
      });
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          state.selectedDraftId = post.id;
          render();
        }
      });

      const mediaCount = post.media?.length || 0;
      const preview = post.body ? stripHtml(post.body).slice(0, 180) : "Медиа без текста";
      card.innerHTML = `
        <div class="draft-card-main">
          <strong></strong>
          <span></span>
          <small></small>
        </div>
        <button class="danger-button compact-button" type="button">Удалить</button>
      `;
      card.querySelector("strong").textContent = post.title || "Пост из Telegram";
      card.querySelector("span").textContent = preview;
      card.querySelector("small").textContent = mediaCount ? `${mediaCount} медиа` : "Текст";
      card.querySelector("button").addEventListener("click", (event) => {
        event.stopPropagation();
        deletePost(post.id).catch((error) => notify(error.message, "error"));
      });
      return card;
    }),
  );
}

function renderDraftPagination(total) {
  const pagination = document.querySelector("#draft-pagination");
  const pages = pageCount(total, state.draftPageSize);
  pagination.hidden = total <= state.draftPageSize;
  document.querySelector("#drafts-page").textContent = `${state.draftPage} / ${pages}`;
  document.querySelector("#drafts-prev").disabled = state.draftPage <= 1;
  document.querySelector("#drafts-next").disabled = state.draftPage >= pages;
}

function renderQueuePagination(total) {
  const pagination = document.querySelector("#posts-pagination");
  const pages = pageCount(total, state.queuePageSize);
  state.queuePage = clampPage(state.queuePage, total, state.queuePageSize);
  pagination.hidden = total <= state.queuePageSize;
  document.querySelector("#queue-page").textContent = `${state.queuePage} / ${pages}`;
  document.querySelector("#posts-prev").disabled = state.queuePage <= 1;
  document.querySelector("#posts-next").disabled = state.queuePage >= pages;
}

function renderAuditPagination() {
  const pagination = document.querySelector("#audit-pagination");
  const total = state.audit.total || 0;
  const pages = pageCount(total, state.auditPageSize);
  state.auditPage = clampPage(state.audit.page || state.auditPage, total, state.auditPageSize);
  pagination.hidden = total <= state.auditPageSize;
  document.querySelector("#audit-page").textContent = `${state.auditPage} / ${pages}`;
  document.querySelector("#audit-prev").disabled = state.auditPage <= 1;
  document.querySelector("#audit-next").disabled = state.auditPage >= pages;
}

function renderAudit() {
  const total = state.audit.total || 0;
  document.querySelector("#audit-count").textContent = state.auditLoading ? "Загрузка..." : `${total} записей`;
  renderAuditPagination();

  const list = document.querySelector("#audit-list");
  if (state.auditLoading) {
    list.replaceChildren(loadingBlock("Загружаем историю отправок"));
    return;
  }
  if (total === 0) {
    list.replaceChildren(emptyPost(activeSessions().length ? "Истории отправок пока нет" : "Подключите аккаунт"));
    return;
  }

  list.replaceChildren(...state.audit.items.map(renderAuditItem));
}

function renderAuditItem(item) {
  const node = document.createElement("article");
  node.className = `audit-item ${item.status}`.trim();
  const title = shortWords(item.post_title || item.post_preview || "Пост из Telegram", 9);
  node.innerHTML = `
    <div class="audit-item-head">
      <span class="audit-status-icon" data-field="status-icon"></span>
      <div>
        <strong data-field="title"></strong>
        <p data-field="media"></p>
      </div>
    </div>
    <dl class="audit-meta">
      <div><dt>Куда</dt><dd data-field="target"></dd></div>
      <div><dt>Когда</dt><dd data-field="time"></dd></div>
      <div><dt>Результат</dt><dd data-field="result"></dd></div>
    </dl>
  `;
  node.querySelector('[data-field="title"]').textContent = title || "Пост из Telegram";
  node.querySelector('[data-field="media"]').textContent = mediaCountLabel(item.media_count || 0);
  node.querySelector('[data-field="status-icon"]').textContent = auditStatusIcon(item.status);
  node.querySelector('[data-field="target"]').textContent = item.target_chat_title || "Группа не найдена";
  node.querySelector('[data-field="time"]').textContent = formatDateTime(item.updated_at || item.due_at);
  node.querySelector('[data-field="result"]').textContent =
    item.status === "done"
      ? `Отправлено${item.telegram_message_id ? `, message id ${item.telegram_message_id}` : ""}`
      : item.last_error || auditStatusLabel(item.status);
  return node;
}

function renderGroupPicker() {
  const picker = document.querySelector("#group-picker");
  const pagination = document.querySelector("#group-pagination");
  const chats = filteredChats();
  const pages = clampGroupPage();
  const start = (state.groupPage - 1) * state.groupPageSize;
  const visible = chats.slice(start, start + state.groupPageSize);

  if (visible.length === 0) {
    picker.replaceChildren(emptyChip("Ничего не найдено"));
  } else {
    picker.replaceChildren(
      ...visible.map((chat) => {
        const label = document.createElement("label");
        label.className = "group-chip";
        label.innerHTML = `<input type="checkbox" name="target_chat_ids" value="${chat.id}" /> <span></span>`;
        const input = label.querySelector("input");
        input.checked = state.selectedChatIds.has(chat.id);
        input.addEventListener("change", () => {
          if (input.checked) {
            state.selectedChatIds.add(chat.id);
          } else {
            state.selectedChatIds.delete(chat.id);
          }
          state.groupPage = 1;
          renderGroupPicker();
        });
        label.querySelector("span").textContent = chat.title;
        return label;
      }),
    );
  }

  pagination.hidden = chats.length <= state.groupPageSize;
  document.querySelector("#groups-page").textContent = `${state.groupPage} / ${pages}`;
  document.querySelector("#groups-prev").disabled = state.groupPage <= 1;
  document.querySelector("#groups-next").disabled = state.groupPage >= pages;
}

function emptyChip(text) {
  const node = document.createElement("div");
  node.className = "empty-chip";
  node.textContent = text;
  return node;
}

function emptyPost(text) {
  const node = document.createElement("div");
  node.className = "empty-post";
  node.textContent = text;
  return node;
}

function loadingBlock(text) {
  const node = document.createElement("div");
  node.className = "loading-block";
  node.innerHTML = "<span></span><p></p>";
  node.querySelector("p").textContent = text;
  return node;
}

function renderPost(post) {
  const node = document.createElement("article");
  node.className = `post-item ${post.status}`.trim();
  const cleanBody = stripHtml(post.body || "");
  const preview = cleanBody.length > 120 ? `${cleanBody.slice(0, 120)}...` : cleanBody || "Медиа без текста";
  node.innerHTML = `
    <div class="post-item-main">
      <div class="post-title-row">
        <p></p>
        <strong></strong>
      </div>
      <dl class="post-meta">
        <div><dt>Расписание</dt><dd data-field="schedule"></dd></div>
        <div><dt>Куда</dt><dd data-field="targets"></dd></div>
        <div><dt>Медиа</dt><dd data-field="media"></dd></div>
      </dl>
    </div>
    <div class="post-actions">
      <button class="secondary-button compact-button" data-action="edit" type="button">Редактировать</button>
      <button class="secondary-button compact-button" data-action="pause" type="button"></button>
      <button class="danger-button compact-button" data-action="delete" type="button">Удалить</button>
    </div>
  `;
  node.querySelector("p").textContent = preview;
  node.querySelector("strong").textContent = statusLabel(post.status);
  node.querySelector('[data-field="schedule"]').textContent = scheduleLabel(post);
  node.querySelector('[data-field="targets"]').textContent = targetSummary(post);
  node.querySelector('[data-field="media"]').textContent = mediaLabel(post);
  node.querySelector('[data-action="pause"]').textContent =
    post.status === "paused" ? "Продолжить" : "Пауза";
  node.querySelector('[data-action="edit"]').addEventListener("click", () => openEditPost(post));
  node.querySelector('[data-action="pause"]').addEventListener("click", () => {
    togglePausePost(post).catch((error) => notify(error.message, "error"));
  });
  node.querySelector('[data-action="delete"]').addEventListener("click", () => {
    deletePost(post.id).catch((error) => notify(error.message, "error"));
  });
  return node;
}

function renderEditFolderPicker() {
  const picker = document.querySelector("#edit-folder-picker");
  const items = folderItems();
  if (!items.some((folder) => String(folder.id) === state.editSelectedFolderId)) {
    state.editSelectedFolderId = "all";
  }

  picker.replaceChildren(
    ...items.map((folder) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `folder-chip ${String(folder.id) === state.editSelectedFolderId ? "selected" : ""}`.trim();
      button.textContent = folder.title;
      button.addEventListener("click", () => {
        state.editSelectedFolderId = String(folder.id);
        state.editGroupPage = 1;
        renderEditFolderPicker();
        renderEditGroupPicker();
      });
      return button;
    }),
  );
}

function renderEditGroupPicker() {
  const picker = document.querySelector("#edit-group-picker");
  const pagination = document.querySelector("#edit-group-pagination");
  const chats = filteredChats({
    folderId: state.editSelectedFolderId,
    query: state.editGroupSearch,
    selectedIds: state.editSelectedChatIds,
  });
  const pages = clampEditGroupPage();
  const start = (state.editGroupPage - 1) * state.editGroupPageSize;
  const visible = chats.slice(start, start + state.editGroupPageSize);

  document.querySelector("#edit-groups-count").textContent = `${chats.length} групп`;

  if (visible.length === 0) {
    picker.replaceChildren(emptyChip("Ничего не найдено"));
  } else {
    picker.replaceChildren(
      ...visible.map((chat) => {
        const label = document.createElement("label");
        label.className = "group-chip";
        label.innerHTML = `<input type="checkbox" value="${chat.id}" /> <span></span>`;
        const input = label.querySelector("input");
        input.checked = state.editSelectedChatIds.has(chat.id);
        input.addEventListener("change", () => {
          if (input.checked) {
            state.editSelectedChatIds.add(chat.id);
          } else {
            state.editSelectedChatIds.delete(chat.id);
          }
          state.editGroupPage = 1;
          renderEditGroupPicker();
        });
        label.querySelector("span").textContent = chat.title;
        return label;
      }),
    );
  }

  pagination.hidden = chats.length <= state.editGroupPageSize;
  document.querySelector("#edit-groups-page").textContent = `${state.editGroupPage} / ${pages}`;
  document.querySelector("#edit-groups-prev").disabled = state.editGroupPage <= 1;
  document.querySelector("#edit-groups-next").disabled = state.editGroupPage >= pages;
}

function openEditPost(post, options = {}) {
  state.editingPostId = post.id;
  state.editSelectedChatIds = new Set(post.target_chat_ids || []);
  state.editSelectedFolderId = "all";
  state.editGroupSearch = "";
  state.editGroupPage = 1;

  const form = document.querySelector("#edit-form");
  const preview = stripHtml(post.body || "") || "Медиа без текста";
  form.elements.next_run_at.value = options.requireFutureDate
    ? nextDefaultDateTimeLocal()
    : dateTimeLocalValue(post.next_run_at);
  form.elements.schedule_kind.value = post.schedule_kind || "once";
  form.elements.interval_minutes.value = post.interval_minutes || 60;
  setSelectedWeekdays(form, post.schedule_weekdays || []);
  document.querySelector("#edit-preview").textContent = preview.length > 180 ? `${preview.slice(0, 180)}...` : preview;
  document.querySelector("#edit-group-search").value = "";
  updateScheduleControls(form, "edit-");
  document.querySelector("#edit-modal").hidden = false;
  renderEditFolderPicker();
  renderEditGroupPicker();

  if (options.requireFutureDate) {
    notify("Старая дата уже прошла. Выберите новую дату отправки и сохраните изменения.", "error");
  }
}

function closeEditPost() {
  state.editingPostId = null;
  document.querySelector("#edit-modal").hidden = true;
}

function stripHtml(value) {
  const node = document.createElement("div");
  node.innerHTML = value || "";
  return node.textContent || node.innerText || "";
}

function deletionMessage(result) {
  if (result.source_messages_found === 0) {
    return "Пост удалён из сервиса. Для этого поста не был сохранён message_id исходного сообщения, поэтому удалить его в чате нельзя.";
  }

  if (result.deleted_bot_messages === result.source_messages_found) {
    return `Пост удалён. В чате Telegram удалено сообщений: ${result.deleted_bot_messages}.`;
  }

  const firstError = result.telegram_delete_errors?.[0];
  if (firstError) {
    return `Пост удалён из сервиса. Telegram удалил ${result.deleted_bot_messages}/${result.source_messages_found}. Причина: ${firstError}`;
  }

  return `Пост удалён из сервиса. Telegram подтвердил удаление ${result.deleted_bot_messages}/${result.source_messages_found} сообщений.`;
}

async function load(options = {}) {
  const [config, sessions, chats, folders, posts] = await Promise.all([
    api("app-config"),
    api("sessions"),
    api("chats"),
    api("folders"),
    api("posts"),
  ]);
  state.config = config;
  state.sessions = sessions;
  state.chats = chats;
  state.folders = folders;
  state.posts = posts;
  if (!state.folders.some((folder) => String(folder.id) === state.selectedFolderId)) {
    state.selectedFolderId = "all";
  }
  if (!state.folders.some((folder) => String(folder.id) === state.editSelectedFolderId)) {
    state.editSelectedFolderId = "all";
  }
  const availableIds = new Set(chats.map((chat) => chat.id));
  state.selectedChatIds = new Set([...state.selectedChatIds].filter((id) => availableIds.has(id)));
  render();

  if (options.autoSyncGroups && activeSessions().length > 0 && !state.groupsSyncedOnInit) {
    state.groupsSyncedOnInit = true;
    await syncGroups({ silent: true });
  }

  if (state.activeTab === "audit") {
    await loadAudit();
  }
}

async function loadAudit(options = {}) {
  state.auditLoading = true;
  if (options.renderFirst) render();
  try {
    state.audit = await api(`audit?page=${state.auditPage}&page_size=${state.auditPageSize}`);
  } finally {
    state.auditLoading = false;
    render();
  }
}

async function syncGroups(options = {}) {
  const session = activeSessions()[0];
  if (!session) {
    notify("Сначала подключите аккаунт.", "error");
    return;
  }
  if (!options.silent) clearNotice();
  try {
    const result = await api(`sessions/${session.id}/sync-chats`, { method: "POST" });
    if (!options.silent) notify(`Группы обновлены: ${result.total_dialogs}`);
    await load();
  } catch (error) {
    if (!options.silent) notify(error.message, "error");
  }
}

async function deletePost(postId) {
  const post = state.posts.find((item) => item.id === postId);
  if (!post) return;

  clearNotice();
  const confirmed = await confirmDeletePost(post);
  if (!confirmed) return;

  const result = await api(`posts/${postId}`, { method: "DELETE" });
  if (state.selectedDraftId === postId) {
    state.selectedDraftId = null;
  }
  state.posts = state.posts.filter((item) => item.id !== postId);
  state.draftPage = clampPage(state.draftPage, draftPosts().length, state.draftPageSize);
  state.queuePage = clampPage(state.queuePage, queuePosts().length, state.queuePageSize);
  notify(deletionMessage(result));
  await load();
}

async function togglePausePost(post) {
  clearNotice();

  if (post.status === "paused") {
    if (isPastOrNow(post.next_run_at)) {
      openEditPost(post, { requireFutureDate: true });
      return;
    }

    const updated = await api(`posts/${post.id}/resume`, {
      method: "PATCH",
      body: JSON.stringify({}),
    });
    state.posts = state.posts.map((item) => (item.id === updated.id ? updated : item));
    notify("Рассылка возобновлена.");
    render();
    return;
  }

  const updated = await api(`posts/${post.id}/pause`, { method: "PATCH" });
  state.posts = state.posts.map((item) => (item.id === updated.id ? updated : item));
  notify("Рассылка поставлена на паузу.");
  render();
}

document.querySelector("#refresh").addEventListener("click", () => {
  clearNotice();
  load({ autoSyncGroups: true }).catch((error) => notify(error.message, "error"));
});

document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", () => {
    state.activeTab = button.dataset.tab;
    if (state.activeTab === "audit") {
      loadAudit({ renderFirst: true }).catch((error) => notify(error.message, "error"));
      return;
    }
    render();
  });
});

document.querySelector("#logout-account").addEventListener("click", async () => {
  clearNotice();
  const confirmed = window.confirm("Выйти из подключенного Telegram-аккаунта?");
  if (!confirmed) return;
  const button = document.querySelector("#logout-account");
  setBusy(button, true, "Выходим...");
  try {
    await api("account/logout", { method: "POST" });
    state.selectedDraftId = null;
    state.selectedFolderId = "all";
    state.selectedChatIds.clear();
    state.groupsSyncedOnInit = false;
    notify("Аккаунт отключен.");
    await load();
  } catch (error) {
    notify(error.message, "error");
  } finally {
    setBusy(button, false, "Выйти");
  }
});

document.querySelector("#post-form select[name=schedule_kind]").addEventListener("change", (event) => {
  updateScheduleControls(event.target.form);
});

document.querySelector("#edit-form select[name=schedule_kind]").addEventListener("change", (event) => {
  updateScheduleControls(event.target.form, "edit-");
});

document.querySelector("#group-search").addEventListener("input", (event) => {
  state.groupSearch = event.target.value;
  state.groupPage = 1;
  renderGroupPicker();
});

document.querySelector("#groups-prev").addEventListener("click", () => {
  state.groupPage -= 1;
  renderGroupPicker();
});

document.querySelector("#groups-next").addEventListener("click", () => {
  state.groupPage += 1;
  renderGroupPicker();
});

document.querySelector("#edit-group-search").addEventListener("input", (event) => {
  state.editGroupSearch = event.target.value;
  state.editGroupPage = 1;
  renderEditGroupPicker();
});

document.querySelector("#edit-groups-prev").addEventListener("click", () => {
  state.editGroupPage -= 1;
  renderEditGroupPicker();
});

document.querySelector("#edit-groups-next").addEventListener("click", () => {
  state.editGroupPage += 1;
  renderEditGroupPicker();
});

document.querySelector("#edit-close").addEventListener("click", closeEditPost);

document.querySelector("#edit-modal").addEventListener("click", (event) => {
  if (event.target.id === "edit-modal") {
    closeEditPost();
  }
});

document.querySelector("#drafts-prev").addEventListener("click", () => {
  state.draftPage -= 1;
  renderDraftPicker();
});

document.querySelector("#drafts-next").addEventListener("click", () => {
  state.draftPage += 1;
  renderDraftPicker();
});

document.querySelector("#posts-prev").addEventListener("click", () => {
  state.queuePage -= 1;
  render();
});

document.querySelector("#posts-next").addEventListener("click", () => {
  state.queuePage += 1;
  render();
});

document.querySelector("#audit-prev").addEventListener("click", () => {
  state.auditPage -= 1;
  loadAudit({ renderFirst: true }).catch((error) => notify(error.message, "error"));
});

document.querySelector("#audit-next").addEventListener("click", () => {
  state.auditPage += 1;
  loadAudit({ renderFirst: true }).catch((error) => notify(error.message, "error"));
});

document.querySelector("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearNotice();
  const form = new FormData(event.currentTarget);
  const button = document.querySelector("#send-code");
  setBusy(button, true, "Отправляем...");

  try {
    const result = await api("account/start-login", {
      method: "POST",
      body: JSON.stringify({
        phone: form.get("phone"),
      }),
    });
    state.pendingSessionId = result.session_id;
    state.pendingPhone = String(form.get("phone") || "");
    document.querySelector("#login-form").hidden = true;
    document.querySelector("#code-form").hidden = false;
    startSmsCooldown(90);
    notify(result.message || "Код отправлен в Telegram.");
  } catch (error) {
    notify(error.message, "error");
  } finally {
    setBusy(button, false, "Получить код");
  }
});

document.querySelector("#resend-sms-code").addEventListener("click", async (event) => {
  clearNotice();
  const button = event.currentTarget;
  const phone = state.pendingPhone || new FormData(document.querySelector("#login-form")).get("phone");
  if (!phone) {
    notify("Сначала введите номер телефона.", "error");
    return;
  }
  setBusy(button, true, "Отправляем...");
  let shouldStartCooldown = false;

  try {
    const result = await api("account/start-login", {
      method: "POST",
      body: JSON.stringify({
        phone,
        force_sms: true,
      }),
    });
    state.pendingSessionId = result.session_id;
    state.pendingPhone = String(phone);
    shouldStartCooldown = true;
    notify(result.message || "SMS-код запрошен.");
  } catch (error) {
    notify(error.message, "error");
  } finally {
    if (shouldStartCooldown) {
      startSmsCooldown(90);
    } else {
      setBusy(button, false, "Отправить SMS");
    }
  }
});

document.querySelector("#code-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearNotice();
  const form = new FormData(event.currentTarget);
  const button = event.currentTarget.querySelector("button");
  setBusy(button, true, "Проверяем...");

  try {
    const result = await api("account/confirm-code", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.pendingSessionId,
        code: form.get("code"),
      }),
    });

    if (result.status === "password_needed") {
      document.querySelector("#code-form").hidden = true;
      document.querySelector("#password-form").hidden = false;
      notify("Нужен пароль 2FA.");
      return;
    }

    notify("Аккаунт подключен.");
    await load();
    state.groupsSyncedOnInit = true;
    await syncGroups();
  } catch (error) {
    notify(error.message, "error");
  } finally {
    setBusy(button, false, "Подключить");
  }
});

document.querySelector("#password-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearNotice();
  const form = new FormData(event.currentTarget);
  const button = event.currentTarget.querySelector("button");
  setBusy(button, true, "Проверяем...");

  try {
    await api("account/confirm-password", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.pendingSessionId,
        password: form.get("password"),
      }),
    });
    notify("Аккаунт подключен.");
    await load();
    state.groupsSyncedOnInit = true;
    await syncGroups();
  } catch (error) {
    notify(error.message, "error");
  } finally {
    setBusy(button, false, "Завершить");
  }
});

document.querySelector("#edit-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearNotice();
  const form = new FormData(event.currentTarget);
  const postId = state.editingPostId;
  const post = state.posts.find((item) => item.id === postId);
  const connected = activeSessions();
  const sessionId = post?.default_session_id || connected[0]?.id;
  const checkedGroups = selectedEditGroups();
  const scheduleKind = form.get("schedule_kind");
  const nextRun = form.get("next_run_at");
  const intervalMinutes = scheduleKind === "interval" ? Number(form.get("interval_minutes")) : null;
  const scheduleWeekdays = selectedWeekdays(event.currentTarget);

  if (!post || !postId) {
    notify("Пост не найден. Обновите страницу.", "error");
    return;
  }
  if (!sessionId) {
    notify("Подключите аккаунт.", "error");
    return;
  }
  if (checkedGroups.length === 0) {
    notify("Выберите хотя бы одну группу.", "error");
    return;
  }
  if (isPastOrNow(new Date(nextRun).toISOString())) {
    notify("Выберите будущую дату отправки.", "error");
    return;
  }
  if (scheduleKind === "interval") {
    const confirmed = await confirmSpamRiskIfNeeded(intervalMinutes);
    if (!confirmed) return;
  }
  if (scheduleNeedsWeekdays(scheduleKind) && scheduleWeekdays.length === 0) {
    notify("Выберите хотя бы один день недели.", "error");
    return;
  }

  const button = document.querySelector("#edit-save");
  setBusy(button, true, "Сохраняем...");

  try {
    const updated = await api(`posts/${postId}/schedule`, {
      method: "POST",
      body: JSON.stringify({
        schedule_kind: scheduleKind,
        next_run_at: new Date(nextRun).toISOString(),
        interval_minutes: intervalMinutes,
        schedule_weekdays: scheduleWeekdays,
        spam_risk_acknowledged: scheduleKind === "interval" && intervalMinutes <= 30,
        default_session_id: sessionId,
        target_chat_ids: checkedGroups,
      }),
    });
    state.posts = state.posts.map((item) => (item.id === updated.id ? updated : item));
    closeEditPost();
    notify("Пост обновлён.");
    await load();
  } catch (error) {
    notify(error.message, "error");
  } finally {
    setBusy(button, false, "Сохранить изменения");
  }
});

document.querySelector("#post-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearNotice();
  const formElement = event.currentTarget;
  const form = new FormData(formElement);
  const checkedGroups = selectedGroups();
  const connected = activeSessions();
  const sessionId = connected[0]?.id;
  const scheduleKind = form.get("schedule_kind");
  const nextRun = form.get("next_run_at");
  const draftId = state.selectedDraftId;
  const scheduleWeekdays = selectedWeekdays(formElement);

  if (!sessionId) {
    notify("Подключите аккаунт.", "error");
    return;
  }
  if (!draftId) {
    notify("Отправьте пост боту и выберите черновик.", "error");
    return;
  }
  if (checkedGroups.length === 0) {
    notify("Выберите хотя бы одну группу.", "error");
    return;
  }
  if (isPastOrNow(new Date(nextRun).toISOString())) {
    notify("Выберите будущую дату отправки.", "error");
    return;
  }

  const intervalMinutes = scheduleKind === "interval" ? Number(form.get("interval_minutes")) : null;

  if (scheduleKind === "interval") {
    const confirmed = await confirmSpamRiskIfNeeded(intervalMinutes);
    if (!confirmed) return;
  }
  if (scheduleNeedsWeekdays(scheduleKind) && scheduleWeekdays.length === 0) {
    notify("Выберите хотя бы один день недели.", "error");
    return;
  }

  const button = document.querySelector("#save-post");
  setBusy(button, true, "Сохраняем...");

  try {
    await api(`posts/${draftId}/schedule`, {
      method: "POST",
      body: JSON.stringify({
        schedule_kind: scheduleKind,
        next_run_at: new Date(nextRun).toISOString(),
        interval_minutes: intervalMinutes,
        schedule_weekdays: scheduleWeekdays,
        spam_risk_acknowledged: scheduleKind === "interval" && intervalMinutes <= 30,
        default_session_id: sessionId,
        target_chat_ids: checkedGroups,
      }),
    });

    formElement.reset();
    state.selectedChatIds.clear();
    state.groupSearch = "";
    state.groupPage = 1;
    state.selectedDraftId = null;
    document.querySelector("#group-search").value = "";
    updateScheduleControls(formElement);
    notify("Пост запланирован.");
    await load();
  } catch (error) {
    notify(error.message, "error");
  } finally {
    setBusy(button, false, "Запланировать");
  }
});

load({ autoSyncGroups: true }).catch((error) => notify(error.message, "error"));
