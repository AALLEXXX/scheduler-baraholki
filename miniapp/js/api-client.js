import { telegramInitData } from "./telegram-webapp.js?v=20260626-14";

const apiPrefix = window.location.pathname.startsWith("/scheduler") ? "/scheduler" : "";

export const restApiBase = `${apiPrefix}/rest/autopost`;
export const rpcApiBase = `${apiPrefix}/rpc/autopost`;

function headers() {
  return {
    "Content-Type": "application/json",
    "X-Telegram-Init-Data": telegramInitData(),
  };
}

export function apiBaseForPath(cleanPath) {
  const pathOnly = cleanPath.split("?")[0];
  if (
    pathOnly.startsWith("/account/") ||
    /^\/sessions\/[^/]+\/sync-chats$/.test(pathOnly) ||
    /^\/posts\/[^/]+\/(schedule|pause|resume|enqueue-now)$/.test(pathOnly)
  ) {
    return rpcApiBase;
  }
  return restApiBase;
}

export async function api(path, options = {}, translate = (key) => key) {
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  const response = await fetch(`${apiBaseForPath(cleanPath)}${cleanPath}`, {
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
        message = parsed.detail.map((item) => item.msg || translate("notice.genericValidation")).join("\n");
      } else {
        message = translate("notice.genericActionError");
      }
    } catch {
      message = text || message;
    }
    throw new Error(message);
  }
  return response.json();
}
