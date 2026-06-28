export const telegramWebApp = window.Telegram?.WebApp;

export function readyTelegramWebApp() {
  if (!telegramWebApp) return;
  telegramWebApp.ready();
  telegramWebApp.expand();
}

export function telegramInitData() {
  return telegramWebApp?.initData || "";
}
