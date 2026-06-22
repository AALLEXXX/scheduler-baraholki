const tg = window.Telegram?.WebApp;
const initData = tg?.initData || "";

if (tg) {
  tg.ready();
  tg.expand();
}

const state = {
  sessions: [],
  chats: [],
  posts: [],
};

function headers() {
  return {
    "Content-Type": "application/json",
    "X-Telegram-Init-Data": initData,
  };
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { ...headers(), ...(options.headers || {}) },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
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
  sessions.replaceChildren(
    ...state.sessions.map((session) =>
      item(session.name, `${session.status} · @${session.username || "no username"}`),
    ),
  );

  const chats = document.querySelector("#chats");
  chats.replaceChildren(
    ...state.chats.map((chat) =>
      item(chat.title, `${chat.type} · ${chat.telegram_chat_id}`),
    ),
  );

  const select = document.querySelector("select[name=default_session_id]");
  select.replaceChildren(new Option("No session", ""));
  state.sessions.forEach((session) => {
    select.append(new Option(session.name, session.id));
  });

  const checks = document.querySelector("#target-checkboxes");
  checks.replaceChildren(
    ...state.chats.map((chat) => {
      const label = document.createElement("label");
      label.innerHTML = `<input type="checkbox" name="target_chat_ids" value="${chat.id}" />`;
      label.append(document.createTextNode(chat.title));
      return label;
    }),
  );

  const posts = document.querySelector("#posts");
  posts.replaceChildren(
    ...state.posts.map((post) =>
      item(post.title, `${post.status} · ${post.schedule_kind} · ${post.next_run_at || "no date"}`),
    ),
  );
}

async function load() {
  document.querySelector("#status").textContent = "Loading...";
  const [sessions, chats, posts] = await Promise.all([
    api("/api/sessions"),
    api("/api/chats"),
    api("/api/posts"),
  ]);
  state.sessions = sessions;
  state.chats = chats;
  state.posts = posts;
  render();
}

document.querySelector("#refresh").addEventListener("click", () => {
  load().catch((error) => {
    document.querySelector("#status").textContent = error.message;
  });
});

document.querySelector("#post-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const nextRun = form.get("next_run_at");
  const interval = form.get("interval_minutes");
  const targetChatIds = [...document.querySelectorAll("input[name=target_chat_ids]:checked")].map(
    (input) => input.value,
  );

  await api("/api/posts", {
    method: "POST",
    body: JSON.stringify({
      title: form.get("title"),
      body: form.get("body"),
      status: nextRun ? "scheduled" : "draft",
      schedule_kind: interval ? "interval" : "once",
      next_run_at: nextRun ? new Date(nextRun).toISOString() : null,
      interval_minutes: interval ? Number(interval) : null,
      default_session_id: form.get("default_session_id") || null,
      target_chat_ids: targetChatIds,
    }),
  });

  event.currentTarget.reset();
  await load();
});

load().catch((error) => {
  document.querySelector("#status").textContent = error.message;
});
