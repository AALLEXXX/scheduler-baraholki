const tg = window.Telegram?.WebApp;
const initData = tg?.initData || "";
const apiBase = window.location.pathname.startsWith("/scheduler") ? "/scheduler/api" : "/api";

if (tg) {
  tg.ready();
  tg.expand();
}

const state = {
  sessions: [],
  chats: [],
  posts: [],
};

function notify(message, type = "info") {
  const notice = document.querySelector("#notice");
  notice.textContent = message;
  notice.className = `notice ${type === "error" ? "error" : ""}`.trim();
  notice.hidden = false;

  if (tg?.showPopup) {
    tg.showPopup({ title: type === "error" ? "Error" : "Done", message });
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
      message = typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
    } catch {
      message = text || message;
    }
    throw new Error(message);
  }
  return response.json();
}

function item(title, meta) {
  const node = document.createElement("div");
  node.className = "item";
  node.innerHTML = `<strong></strong><span class="muted"></span>`;
  node.querySelector("strong").textContent = title;
  node.querySelector("span").textContent = meta;
  return node;
}

function render() {
  document.querySelector("#status").textContent = `${state.posts.length} posts`;

  const sessions = document.querySelector("#sessions");
  if (state.sessions.length === 0) {
    sessions.replaceChildren(
      empty("No Telegram accounts connected yet. First connect a sender account via MTProto session."),
    );
  } else {
    sessions.replaceChildren(
      ...state.sessions.map((session) => {
        const node = item(
          session.name,
          `${session.status} · @${session.username || "no username"} · ${session.phone || "no phone"}`,
        );
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "Import groups";
        button.addEventListener("click", () => syncChats(session.id));
        node.append(button);
        return node;
      }),
    );
  }

  const chats = document.querySelector("#chats");
  if (state.chats.length === 0) {
    chats.replaceChildren(empty("No destination groups yet. Import groups from an account or add a chat ID manually."));
  } else {
    chats.replaceChildren(
      ...state.chats.map((chat) =>
        item(chat.title, `${chat.type} · ${chat.telegram_chat_id}`),
      ),
    );
  }

  const select = document.querySelector("select[name=default_session_id]");
  select.replaceChildren(new Option("Choose Telegram account", ""));
  const chatSessionSelect = document.querySelector("select[name=session_id]");
  chatSessionSelect.replaceChildren(new Option("No linked account", ""));
  state.sessions.forEach((session) => {
    select.append(new Option(session.name, session.id));
    chatSessionSelect.append(new Option(session.name, session.id));
  });

  const checks = document.querySelector("#target-checkboxes");
  if (state.chats.length === 0) {
    checks.replaceChildren(empty("Add at least one destination group before scheduling."));
  } else {
    checks.replaceChildren(
      ...state.chats.map((chat) => {
        const label = document.createElement("label");
        label.innerHTML = `<input type="checkbox" name="target_chat_ids" value="${chat.id}" />`;
        label.append(document.createTextNode(chat.title));
        return label;
      }),
    );
  }

  const posts = document.querySelector("#posts");
  if (state.posts.length === 0) {
    posts.replaceChildren(empty("No posts yet."));
  } else {
    posts.replaceChildren(
      ...state.posts.map((post) =>
        item(post.title, `${post.status} · ${post.schedule_kind} · ${post.next_run_at || "no date"}`),
      ),
    );
  }
}

function empty(text) {
  const node = document.createElement("div");
  node.className = "empty";
  node.textContent = text;
  return node;
}

async function load() {
  document.querySelector("#status").textContent = "Loading...";
  const [sessions, chats, posts] = await Promise.all([
    api("sessions"),
    api("chats"),
    api("posts"),
  ]);
  state.sessions = sessions;
  state.chats = chats;
  state.posts = posts;
  render();
}

async function syncChats(sessionId) {
  clearNotice();
  try {
    const result = await api(`sessions/${sessionId}/sync-chats`, { method: "POST" });
    notify(`Imported ${result.imported} new groups from ${result.total_dialogs} dialogs.`);
    await load();
  } catch (error) {
    notify(error.message, "error");
  }
}

document.querySelector("#refresh").addEventListener("click", () => {
  clearNotice();
  load().catch((error) => {
    notify(error.message, "error");
  });
});

document.querySelector("#chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearNotice();
  const form = new FormData(event.currentTarget);
  const chatId = Number(form.get("telegram_chat_id"));

  if (!Number.isFinite(chatId)) {
    notify("Chat ID must be a number.", "error");
    return;
  }

  try {
    await api("chats", {
      method: "POST",
      body: JSON.stringify({
        title: form.get("title"),
        telegram_chat_id: chatId,
        session_id: form.get("session_id") || null,
        type: "supergroup",
        enabled: true,
      }),
    });

    event.currentTarget.reset();
    notify("Destination group added.");
    await load();
  } catch (error) {
    notify(error.message, "error");
  }
});

document.querySelector("#post-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearNotice();
  const form = new FormData(event.currentTarget);
  const nextRun = form.get("next_run_at");
  const interval = form.get("interval_minutes");
  const targetChatIds = [...document.querySelectorAll("input[name=target_chat_ids]:checked")].map(
    (input) => input.value,
  );
  const sessionId = form.get("default_session_id") || null;

  if (!sessionId) {
    notify("Choose a Telegram account first. This account will send the post.", "error");
    return;
  }

  if (targetChatIds.length === 0) {
    notify("Choose at least one destination group.", "error");
    return;
  }

  const button = document.querySelector("#save-post");
  button.disabled = true;
  button.textContent = "Saving...";
  try {
    await api("posts", {
      method: "POST",
      body: JSON.stringify({
        title: form.get("title"),
        body: form.get("body"),
        status: nextRun ? "scheduled" : "draft",
        schedule_kind: interval ? "interval" : "once",
        next_run_at: nextRun ? new Date(nextRun).toISOString() : null,
        interval_minutes: interval ? Number(interval) : null,
        default_session_id: sessionId,
        target_chat_ids: targetChatIds,
      }),
    });

    event.currentTarget.reset();
    notify(nextRun ? "Post scheduled." : "Post saved as draft.");
    await load();
  } catch (error) {
    notify(error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "Save post";
  }
});

load().catch((error) => {
  notify(error.message, "error");
});
