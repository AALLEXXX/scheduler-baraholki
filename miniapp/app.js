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
  posts: [],
  pendingSessionId: null,
  selectedDraftId: null,
  selectedChatIds: new Set(),
  groupSearch: "",
  groupPage: 1,
  groupPageSize: 10,
  groupsSyncedOnInit: false,
};

function activeSessions() {
  return state.sessions.filter((session) => session.status === "active");
}

function draftPosts() {
  return state.posts.filter((post) => post.status === "draft");
}

function queuePosts() {
  return state.posts.filter((post) => post.status !== "draft");
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
  button.disabled = busy;
  if (text) button.textContent = text;
}

function selectedGroups() {
  return [...state.selectedChatIds];
}

function filteredChats() {
  const query = state.groupSearch.trim().toLowerCase();
  if (!query) return state.chats;
  return state.chats.filter((chat) => chat.title.toLowerCase().includes(query));
}

function clampGroupPage() {
  const pages = Math.max(1, Math.ceil(filteredChats().length / state.groupPageSize));
  state.groupPage = Math.min(Math.max(1, state.groupPage), pages);
  return pages;
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

function render() {
  const connected = activeSessions();
  const primarySession = connected[0] || state.sessions[0];
  const hasAccount = connected.length > 0;
  const hasGroups = state.chats.length > 0;
  const drafts = draftPosts();
  const queued = queuePosts();

  document.querySelector("#posts-count").textContent = `${queued.length} постов`;
  document.querySelector("#drafts-count").textContent = `${drafts.length} постов`;
  document.querySelector("#groups-count").textContent = `${state.chats.length} групп`;

  const stateDot = document.querySelector("#account-state");
  stateDot.className = `status-dot ${hasAccount ? "online" : ""}`;
  document.querySelector("#account-title").textContent = hasAccount ? "Аккаунт подключен" : "Аккаунт не подключен";
  document.querySelector("#account-subtitle").textContent = hasAccount
    ? `${primarySession.phone || ""} ${primarySession.username ? `@${primarySession.username}` : ""}`.trim()
    : "Подключите Telegram-аккаунт для отправки";

  document.querySelector("#connect-panel").hidden = hasAccount;
  document.querySelector("#sync-groups").hidden = !hasAccount;
  document.querySelector("#logout-account").hidden = !hasAccount;
  document.querySelector("#compose-hint").textContent = hasAccount
    ? hasGroups
      ? "Выберите черновик, время и группы."
      : "Группы обновятся автоматически. Можно обновить вручную."
    : "Сначала подключите аккаунт.";

  const picker = document.querySelector("#group-picker");
  if (!hasGroups) {
    picker.replaceChildren(emptyChip(hasAccount ? "Группы пока не загружены" : "Нет подключенного аккаунта"));
  } else {
    renderGroupPicker();
  }

  const saveButton = document.querySelector("#save-post");
  saveButton.disabled = !hasAccount || !hasGroups || !state.selectedDraftId;

  renderDraftPicker();

  const posts = document.querySelector("#posts");
  if (queued.length === 0) {
    posts.replaceChildren(emptyPost("Постов пока нет"));
  } else {
    posts.replaceChildren(...queued.map(renderPost));
  }
}

function renderDraftPicker() {
  const picker = document.querySelector("#draft-picker");
  const drafts = draftPosts();
  if (!drafts.some((post) => post.id === state.selectedDraftId)) {
    state.selectedDraftId = drafts[0]?.id || null;
  }

  if (drafts.length === 0) {
    picker.replaceChildren(emptyPost("Черновиков пока нет"));
    return;
  }

  picker.replaceChildren(
    ...drafts.map((post) => {
      const card = document.createElement("button");
      card.className = `draft-card ${state.selectedDraftId === post.id ? "selected" : ""}`.trim();
      card.type = "button";
      card.addEventListener("click", () => {
        state.selectedDraftId = post.id;
        render();
      });

      const mediaCount = post.media?.length || 0;
      const preview = post.body ? stripHtml(post.body).slice(0, 180) : "Медиа без текста";
      card.innerHTML = `<strong></strong><span></span><small></small>`;
      card.querySelector("strong").textContent = post.title || "Пост из Telegram";
      card.querySelector("span").textContent = preview;
      card.querySelector("small").textContent = mediaCount ? `${mediaCount} медиа` : "Текст";
      return card;
    }),
  );
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

function renderPost(post) {
  const node = document.createElement("article");
  node.className = "post-item";
  const cleanBody = stripHtml(post.body || "");
  const preview = cleanBody.length > 120 ? `${cleanBody.slice(0, 120)}...` : cleanBody || "Медиа без текста";
  const when = post.next_run_at ? new Date(post.next_run_at).toLocaleString() : "без даты";
  const media = post.media?.length ? ` · ${post.media.length} медиа` : "";
  node.innerHTML = `<p></p><span></span>`;
  node.querySelector("p").textContent = preview;
  node.querySelector("span").textContent = `${post.status} · ${when}${media}`;
  return node;
}

function stripHtml(value) {
  const node = document.createElement("div");
  node.innerHTML = value || "";
  return node.textContent || node.innerText || "";
}

async function load(options = {}) {
  const [config, sessions, chats, posts] = await Promise.all([
    api("app-config"),
    api("sessions"),
    api("chats"),
    api("posts"),
  ]);
  state.config = config;
  state.sessions = sessions;
  state.chats = chats;
  state.posts = posts;
  const availableIds = new Set(chats.map((chat) => chat.id));
  state.selectedChatIds = new Set([...state.selectedChatIds].filter((id) => availableIds.has(id)));
  render();

  if (options.autoSyncGroups && activeSessions().length > 0 && !state.groupsSyncedOnInit) {
    state.groupsSyncedOnInit = true;
    await syncGroups({ silent: true });
  }
}

async function syncGroups(options = {}) {
  const session = activeSessions()[0];
  if (!session) {
    notify("Сначала подключите аккаунт.", "error");
    return;
  }
  const button = document.querySelector("#sync-groups");
  if (!options.silent) clearNotice();
  setBusy(button, true, "Обновляем...");
  try {
    const result = await api(`sessions/${session.id}/sync-chats`, { method: "POST" });
    if (!options.silent) notify(`Группы обновлены: ${result.total_dialogs}`);
    await load();
  } catch (error) {
    if (!options.silent) notify(error.message, "error");
  } finally {
    setBusy(button, false, "Обновить группы");
  }
}

document.querySelector("#refresh").addEventListener("click", () => {
  clearNotice();
  load({ autoSyncGroups: true }).catch((error) => notify(error.message, "error"));
});

document.querySelector("#sync-groups").addEventListener("click", syncGroups);

document.querySelector("#logout-account").addEventListener("click", async () => {
  clearNotice();
  const confirmed = window.confirm("Выйти из подключенного Telegram-аккаунта?");
  if (!confirmed) return;
  const button = document.querySelector("#logout-account");
  setBusy(button, true, "Выходим...");
  try {
    await api("account/logout", { method: "POST" });
    state.selectedDraftId = null;
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

document.querySelector("#open-bot").addEventListener("click", () => {
  const username = state.config.bot_username || "scheduler_baraholki_bot";
  const url = `https://t.me/${username}`;
  if (tg?.openTelegramLink) {
    tg.openTelegramLink(url);
  } else {
    window.open(url, "_blank");
  }
});

document.querySelector("#refresh-drafts").addEventListener("click", () => {
  clearNotice();
  load().catch((error) => notify(error.message, "error"));
});

document.querySelector("select[name=schedule_kind]").addEventListener("change", (event) => {
  document.querySelector("#interval-row").hidden = event.target.value !== "interval";
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
        api_id: Number(form.get("api_id")),
        api_hash: form.get("api_hash"),
        phone: form.get("phone"),
      }),
    });
    state.pendingSessionId = result.session_id;
    document.querySelector("#login-form").hidden = true;
    document.querySelector("#code-form").hidden = false;
    notify("Код отправлен в Telegram.");
  } catch (error) {
    notify(error.message, "error");
  } finally {
    setBusy(button, false, "Получить код");
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

  const intervalMinutes = scheduleKind === "interval" ? Number(form.get("interval_minutes")) : null;

  if (scheduleKind === "interval") {
    const confirmed = await confirmSpamRiskIfNeeded(intervalMinutes);
    if (!confirmed) return;
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
    document.querySelector("#interval-row").hidden = true;
    notify("Пост запланирован.");
    await load();
  } catch (error) {
    notify(error.message, "error");
  } finally {
    setBusy(button, false, "Запланировать");
  }
});

load({ autoSyncGroups: true }).catch((error) => notify(error.message, "error"));
