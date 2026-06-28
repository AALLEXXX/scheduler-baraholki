import { api as requestApi } from "./js/api-client.js?v=20260626-12";

const tg = window.Telegram?.WebApp;
const riskyChatSelectionLimit = 15;
const languageStorageKey = "autopost-manager-language";
const supportedLanguages = ["en", "ru"];

const translations = {
  en: {
    "app.eyebrow": "Autoposting",
    "app.title": "Baraholki",
    "action.refresh": "Refresh",
    "action.close": "Close",
    "nav.sections": "Sections",
    "nav.posts": "Posts",
    "nav.audit": "Audit",
    "nav.settings": "Settings",
    "nav.admin": "Admin",
    "connect.title": "Connect account",
    "connect.hint": "Enter your phone number. Telegram will send the code.",
    "connect.country": "Country",
    "connect.countryCode": "Country code",
    "connect.phone": "Phone",
    "connect.getCode": "Get code",
    "connect.telegramCode": "Telegram code",
    "connect.connect": "Connect",
    "connect.sendSms": "Send SMS",
    "connect.password": "2FA password",
    "connect.finish": "Finish",
    "composer.title": "New post",
    "composer.schedule": "Schedule",
    "draftHelp.button": "How to add a draft",
    "draftHelp.title": "How to add a draft",
    "draftHelp.body": "Send the finished post to this bot in Telegram: text, photo, video, or album. Then press refresh at the top, and the post will appear here as a draft.",
    "drafts.title": "Draft",
    "form.when": "When",
    "form.repeat": "Repeat",
    "form.media": "Media",
    "form.intervalMinutes": "Interval, minutes",
    "form.weekdays": "Weekdays",
    "schedule.once": "Once",
    "schedule.interval": "Every N minutes",
    "schedule.daily": "Every day",
    "schedule.weekdays": "Weekdays only",
    "schedule.weekends": "Weekends only",
    "schedule.everyOtherDay": "Every other day",
    "schedule.customWeekdays": "Choose weekdays",
    "weekday.mon": "Mon",
    "weekday.tue": "Tue",
    "weekday.wed": "Wed",
    "weekday.thu": "Thu",
    "weekday.fri": "Fri",
    "weekday.sat": "Sat",
    "weekday.sun": "Sun",
    "groups.title": "Send to",
    "groups.search": "Find group",
    "queue.title": "Queue",
    "audit.title": "Audit log",
    "audit.hint": "Delivery history by group and result.",
    "settings.title": "Settings",
    "settings.hint": "Connection and account controls.",
    "settings.general": "General",
    "settings.limits": "Sending limits",
    "settings.account": "Account",
    "settings.languageTitle": "Language",
    "settings.languageHint": "Choose the Mini App interface language.",
    "settings.pauseTitle": "Autoposting",
    "settings.pauseEnabled": "All scheduled sends are paused. Your Telegram session stays connected.",
    "settings.pauseDisabled": "Stops all scheduled sends without deleting the Telegram session.",
    "settings.pauseButton": "Pause sending",
    "settings.resumeButton": "Resume sending",
    "settings.revokeTitle": "Telegram session",
    "settings.revokeHint": "Removes service access to the account. Telegram may ask for a code again.",
    "settings.revokeButton": "Disconnect",
    "limits.targetsLabel": "Chats per post",
    "limits.targetsValue": "15 max",
    "limits.accountIntervalLabel": "Account interval",
    "limits.accountIntervalValue": "30 sec",
    "limits.repeatLabel": "Repeat interval",
    "limits.repeatValue": "20 min min",
    "limits.queueLabel": "Queue per day",
    "limits.queueValue": "300 jobs",
    "limits.postsLabel": "Active posts",
    "limits.postsValue": "50 max",
    "limits.mediaLabel": "Media per post",
    "limits.mediaValue": "10 max",
    "admin.title": "Admin",
    "admin.hint": "Users, limits, and global delivery statistics.",
    "admin.users": "Users",
    "admin.stats": "Stats",
    "admin.audit": "Audit",
    "admin.openAudit": "Audit",
    "admin.backToUsers": "Back to users",
    "admin.auditTitle": "User audit",
    "admin.auditHint": "Delivery history visible to this user.",
    "admin.search": "Search username, phone, or ID",
    "edit.eyebrow": "Editing",
    "edit.title": "Scheduled post",
    "edit.save": "Save changes",
    "pagination.prev": "Back",
    "pagination.next": "Next",
    "loading.short": "Loading...",
    "folder.all": "All",
    "count.posts": "{count} posts",
    "count.drafts": "{count} posts",
    "count.groups": "{count} groups",
    "count.records": "{count} records",
    "status.checking": "Checking account",
    "status.connected": "Account connected",
    "status.notConnected": "Account not connected",
    "status.autopostPaused": "Autoposting paused",
    "status.connectSubtitle": "Connect a Telegram account to send posts",
    "compose.connectFirst": "Connect an account first.",
    "compose.paused": "Autoposting is paused. Resume it to change sends.",
    "compose.ready": "Choose a draft, time, and groups.",
    "compose.noGroups": "Groups will sync automatically. You can refresh manually.",
    "empty.noGroupsLoaded": "Groups are not loaded yet",
    "empty.noAccount": "No connected account",
    "empty.noQueuedPosts": "No queued posts yet",
    "empty.noDrafts": "No drafts yet",
    "empty.noSearchResults": "Nothing found",
    "empty.noAudit": "No delivery history yet",
    "empty.connectAccount": "Connect an account",
    "draft.defaultTitle": "Post from Telegram",
    "media.none": "no media",
    "media.text": "Text",
    "media.noText": "Media without text",
    "media.onePhoto": "1 photo",
    "media.photos": "{count} photos",
    "media.oneMedia": "1 media",
    "media.manyMedia": "{count} media",
    "post.status.scheduled": "Scheduled",
    "post.status.paused": "Paused",
    "post.status.archived": "Completed",
    "post.status.draft": "Draft",
    "post.schedule.noDate": "no date",
    "post.schedule.notSelected": "date not selected",
    "post.schedule.interval": "{when}, then every {minutes} min.",
    "post.schedule.daily": "{when}, then every day",
    "post.schedule.weekdays": "{when}, then on weekdays",
    "post.schedule.weekends": "{when}, then on weekends",
    "post.schedule.everyOtherDay": "{when}, then every other day",
    "post.schedule.weekly": "{when}, then weekly",
    "post.schedule.custom": "{when}, then {days}",
    "post.schedule.once": "{when}, once",
    "post.weekdaysFallback": "on selected days",
    "post.targets.none": "No groups selected",
    "post.targets.more": "{first}, {second}, and {count} more",
    "post.action.edit": "Edit",
    "post.action.pause": "Pause autoposting for this post",
    "post.action.resume": "Resume this post",
    "audit.loading": "Loading delivery history",
    "audit.status.done": "Success",
    "audit.status.failed": "Error",
    "audit.status.pending": "Pending",
    "audit.status.processing": "Sending",
    "audit.status.cancelled": "Cancelled",
    "audit.field.target": "Target",
    "audit.field.time": "Time",
    "audit.field.result": "Result",
    "audit.field.link": "Link",
    "audit.sent": "Sent",
    "audit.viewMessage": "View message",
    "audit.loadingMessage": "Loading message...",
    "audit.messageEyebrow": "Delivered message",
    "audit.messageTitle": "Message in chat",
    "audit.messageFallback": "Media message without text.",
    "audit.openInTelegram": "Open in Telegram",
    "audit.groupMissing": "Group not found",
    "admin.loadingUsers": "Loading users",
    "admin.noUsers": "No users found",
    "admin.status.banned": "Banned",
    "admin.status.paused": "Paused",
    "admin.status.noSession": "no session",
    "admin.userFallback": "User",
    "admin.id": "ID",
    "admin.phone": "Phone",
    "admin.today": "Today",
    "admin.errors": "Errors",
    "admin.limitDay": "Daily limit",
    "admin.saveLimit": "Save limit",
    "admin.ban": "Ban",
    "admin.unban": "Unban",
    "admin.pause": "Pause",
    "admin.resume": "Resume",
    "admin.statsLoading": "Loading stats",
    "admin.statsEmpty": "Stats are not loaded yet",
    "admin.deliveredTotal": "Total delivered",
    "admin.successRate": "Delivery success rate",
    "admin.errorsOfAttempts": "{failed} errors out of {total} attempts",
    "admin.activeToday": "active today",
    "admin.ofUsers": "of {count} users",
    "admin.periodToday": "Today",
    "admin.periodWeek": "Week",
    "admin.periodMonth": "Month",
    "notice.errorTitle": "Error",
    "notice.successTitle": "Done",
    "notice.genericValidation": "Check the form and try again.",
    "notice.genericActionError": "Could not complete the action. Check the data and try again.",
    "notice.adminUpdated": "User updated.",
    "notice.connectAccount": "Connect an account.",
    "notice.autopostPaused": "Autoposting is paused.",
    "notice.groupsSynced": "Groups updated: {count}",
    "notice.deleteMissingMessage": "Post removed from the service. The source message_id was not stored, so it cannot be deleted in chat.",
    "notice.deleteAll": "Post removed. Telegram messages deleted: {count}.",
    "notice.deletePartial": "Post removed from the service. Telegram deleted {deleted}/{total}. Reason: {error}",
    "notice.deleteConfirmed": "Post removed from the service. Telegram confirmed deletion of {deleted}/{total} messages.",
    "notice.postResumed": "Post resumed.",
    "notice.postPaused": "Post paused.",
    "notice.globalPaused": "Autoposting paused.",
    "notice.globalResumed": "Autoposting resumed.",
    "notice.sessionDisconnected": "Telegram session disconnected.{suffix}",
    "notice.sessionDisconnectSuffix": " Telegram may not have confirmed session logout, but service access was removed.",
    "notice.postUpdated": "Post updated.",
    "notice.postScheduled": "Post scheduled.",
    "notice.codeSent": "Code sent to Telegram.",
    "notice.smsRequested": "SMS code requested.",
    "notice.passwordNeeded": "2FA password required.",
    "notice.accountConnected": "Account connected.",
    "validation.futureDate": "Choose a future send date.",
    "validation.chooseGroup": "Choose at least one group.",
    "validation.chooseDraft": "Send a post to the bot and choose a draft.",
    "validation.chooseWeekday": "Choose at least one weekday.",
    "validation.postMissing": "Post not found. Refresh the page.",
    "validation.phoneRequired": "Enter your phone number first.",
    "validation.phoneInvalid": "Enter a valid phone number with country code.",
    "spam.minInterval": "Minimum repeat interval is 20 minutes.",
    "spam.riskMessage": "Frequent sending can limit or ban your Telegram account.",
    "spam.riskTitle": "Ban risk",
    "spam.understand": "I understand",
    "spam.cancel": "Cancel",
    "spam.continue": "Continue?",
    "spam.largeSelection": "You selected {count} chats. Sending to more than {limit} chats may be risky and can lead to a Telegram account ban. Continue at your own risk.",
    "spam.ok": "OK",
    "delete.draftTitle": "Delete draft?",
    "delete.queueTitle": "Delete from queue?",
    "delete.draftMessage": "The draft will disappear from the Mini App. The bot chat message will also be deleted if Telegram allows it.",
    "delete.queueMessage": "The post will be removed from the queue. The source message in the bot chat will also be deleted if Telegram allows it.",
    "delete.button": "Delete",
    "login.sending": "Sending...",
    "login.checking": "Checking...",
    "login.smsIn": "SMS in {seconds}s",
    "login.smsUnavailable": "SMS unavailable",
    "login.disconnectConfirm": "Disconnect the Telegram session? Telegram will ask for a code again if you reconnect.",
    "login.disconnecting": "Disconnecting...",
    "login.finish": "Finish",
    "login.connect": "Connect",
    "login.getCode": "Get code",
    "edit.pastDate": "The old date has passed. Choose a new send date and save changes.",
    "busy.pause": "Pausing...",
    "busy.resume": "Resuming...",
    "busy.save": "Saving...",
    "busy.saveChanges": "Save changes",
  },
  ru: {
    "app.eyebrow": "Автопостинг",
    "app.title": "Барахолки",
    "action.refresh": "Обновить",
    "action.close": "Закрыть",
    "nav.sections": "Разделы",
    "nav.posts": "Посты",
    "nav.audit": "Аудит",
    "nav.settings": "Настройки",
    "nav.admin": "Админка",
    "connect.title": "Подключить аккаунт",
    "connect.hint": "Введите номер телефона. Код придёт в Telegram.",
    "connect.country": "Страна",
    "connect.countryCode": "Код страны",
    "connect.phone": "Телефон",
    "connect.getCode": "Получить код",
    "connect.telegramCode": "Код из Telegram",
    "connect.connect": "Подключить",
    "connect.sendSms": "Отправить SMS",
    "connect.password": "Пароль 2FA",
    "connect.finish": "Завершить",
    "composer.title": "Новый пост",
    "composer.schedule": "Запланировать",
    "draftHelp.button": "Как добавить черновик",
    "draftHelp.title": "Как добавить черновик",
    "draftHelp.body": "Отправьте готовый пост прямо в чат с этим ботом в Telegram: текст, фото, видео или альбом. После этого нажмите кнопку обновления сверху, и пост появится здесь как черновик.",
    "drafts.title": "Черновик",
    "form.when": "Когда",
    "form.repeat": "Повтор",
    "form.media": "Медиа",
    "form.intervalMinutes": "Интервал, минут",
    "form.weekdays": "Дни недели",
    "schedule.once": "Один раз",
    "schedule.interval": "Каждые N минут",
    "schedule.daily": "Каждый день",
    "schedule.weekdays": "Только будни",
    "schedule.weekends": "Только выходные",
    "schedule.everyOtherDay": "Через день",
    "schedule.customWeekdays": "Выбрать дни недели",
    "weekday.mon": "Пн",
    "weekday.tue": "Вт",
    "weekday.wed": "Ср",
    "weekday.thu": "Чт",
    "weekday.fri": "Пт",
    "weekday.sat": "Сб",
    "weekday.sun": "Вс",
    "groups.title": "Куда отправлять",
    "groups.search": "Найти группу",
    "queue.title": "Очередь",
    "audit.title": "Аудит действий",
    "audit.hint": "История отправок по группам и результатам.",
    "settings.title": "Настройки",
    "settings.hint": "Подключение и управление аккаунтом.",
    "settings.general": "Основное",
    "settings.limits": "Лимиты отправки",
    "settings.account": "Аккаунт",
    "settings.languageTitle": "Язык",
    "settings.languageHint": "Выберите язык интерфейса Mini App.",
    "settings.pauseTitle": "Автопостинг",
    "settings.pauseEnabled": "Все запланированные отправки остановлены. Telegram-сессия остаётся подключенной.",
    "settings.pauseDisabled": "Останавливает все запланированные отправки, не удаляя Telegram-сессию.",
    "settings.pauseButton": "Остановить отправки",
    "settings.resumeButton": "Возобновить отправки",
    "settings.revokeTitle": "Telegram-сессия",
    "settings.revokeHint": "Удаляет доступ сервиса к аккаунту. После этого Telegram может снова запросить код.",
    "settings.revokeButton": "Отключить",
    "limits.targetsLabel": "Чатов на пост",
    "limits.targetsValue": "до 15",
    "limits.accountIntervalLabel": "Пауза аккаунта",
    "limits.accountIntervalValue": "30 сек",
    "limits.repeatLabel": "Повтор поста",
    "limits.repeatValue": "от 20 мин",
    "limits.queueLabel": "Очередь в день",
    "limits.queueValue": "300 задач",
    "limits.postsLabel": "Активных постов",
    "limits.postsValue": "до 50",
    "limits.mediaLabel": "Медиа в посте",
    "limits.mediaValue": "до 10",
    "admin.title": "Админка",
    "admin.hint": "Пользователи, ограничения и общая статистика отправок.",
    "admin.users": "Пользователи",
    "admin.stats": "Статистика",
    "admin.audit": "Аудит",
    "admin.openAudit": "Аудит",
    "admin.backToUsers": "К пользователям",
    "admin.auditTitle": "Аудит пользователя",
    "admin.auditHint": "История отправок, которую видит этот пользователь.",
    "admin.search": "Поиск по username, телефону или ID",
    "edit.eyebrow": "Редактирование",
    "edit.title": "Запланированный пост",
    "edit.save": "Сохранить изменения",
    "pagination.prev": "Назад",
    "pagination.next": "Дальше",
    "loading.short": "Загрузка...",
    "folder.all": "Все",
    "count.posts": "{count} постов",
    "count.drafts": "{count} постов",
    "count.groups": "{count} групп",
    "count.records": "{count} записей",
    "status.checking": "Проверяем аккаунт",
    "status.connected": "Аккаунт подключен",
    "status.notConnected": "Аккаунт не подключен",
    "status.autopostPaused": "Автопостинг на паузе",
    "status.connectSubtitle": "Подключите Telegram-аккаунт для отправки",
    "compose.connectFirst": "Сначала подключите аккаунт.",
    "compose.paused": "Пауза автопостинга включена. Снимите паузу, чтобы менять отправки.",
    "compose.ready": "Выберите черновик, время и группы.",
    "compose.noGroups": "Группы обновятся автоматически. Можно обновить вручную.",
    "empty.noGroupsLoaded": "Группы пока не загружены",
    "empty.noAccount": "Нет подключенного аккаунта",
    "empty.noQueuedPosts": "Постов пока нет",
    "empty.noDrafts": "Черновиков пока нет",
    "empty.noSearchResults": "Ничего не найдено",
    "empty.noAudit": "Истории отправок пока нет",
    "empty.connectAccount": "Подключите аккаунт",
    "draft.defaultTitle": "Пост из Telegram",
    "media.none": "без медиа",
    "media.text": "Текст",
    "media.noText": "Медиа без текста",
    "media.onePhoto": "1 фото",
    "media.photos": "{count} фото",
    "media.oneMedia": "1 медиа",
    "media.manyMedia": "{count} медиа",
    "post.status.scheduled": "Запланирован",
    "post.status.paused": "На паузе",
    "post.status.archived": "Завершён",
    "post.status.draft": "Черновик",
    "post.schedule.noDate": "нет даты",
    "post.schedule.notSelected": "дата не выбрана",
    "post.schedule.interval": "{when}, затем каждые {minutes} мин.",
    "post.schedule.daily": "{when}, затем каждый день",
    "post.schedule.weekdays": "{when}, затем по будням",
    "post.schedule.weekends": "{when}, затем по выходным",
    "post.schedule.everyOtherDay": "{when}, затем через день",
    "post.schedule.weekly": "{when}, затем раз в неделю",
    "post.schedule.custom": "{when}, затем {days}",
    "post.schedule.once": "{when}, один раз",
    "post.weekdaysFallback": "по выбранным дням",
    "post.targets.none": "Группы не выбраны",
    "post.targets.more": "{first}, {second} и ещё {count}",
    "post.action.edit": "Редактировать",
    "post.action.pause": "Поставить этот пост на паузу",
    "post.action.resume": "Возобновить этот пост",
    "audit.loading": "Загружаем историю отправок",
    "audit.status.done": "Успешно",
    "audit.status.failed": "Ошибка",
    "audit.status.pending": "Ожидает",
    "audit.status.processing": "Отправляется",
    "audit.status.cancelled": "Отменено",
    "audit.field.target": "Куда",
    "audit.field.time": "Когда",
    "audit.field.result": "Результат",
    "audit.field.link": "Ссылка",
    "audit.sent": "Отправлено",
    "audit.viewMessage": "Показать сообщение",
    "audit.loadingMessage": "Загружаем сообщение...",
    "audit.messageEyebrow": "Доставленное сообщение",
    "audit.messageTitle": "Сообщение в чате",
    "audit.messageFallback": "Медиа-сообщение без текста.",
    "audit.openInTelegram": "Открыть в Telegram",
    "audit.groupMissing": "Группа не найдена",
    "admin.loadingUsers": "Загружаем пользователей",
    "admin.noUsers": "Пользователи не найдены",
    "admin.status.banned": "Забанен",
    "admin.status.paused": "Остановлен",
    "admin.status.noSession": "без сессии",
    "admin.userFallback": "Пользователь",
    "admin.id": "ID",
    "admin.phone": "Телефон",
    "admin.today": "Сегодня",
    "admin.errors": "Ошибки",
    "admin.limitDay": "Лимит/день",
    "admin.saveLimit": "Сохранить лимит",
    "admin.ban": "Забанить",
    "admin.unban": "Разбанить",
    "admin.pause": "Остановить",
    "admin.resume": "Возобновить",
    "admin.statsLoading": "Загружаем статистику",
    "admin.statsEmpty": "Статистика пока не загружена",
    "admin.deliveredTotal": "Всего доставлено",
    "admin.successRate": "Успешность отправок",
    "admin.errorsOfAttempts": "{failed} ошибок из {total} попыток",
    "admin.activeToday": "активных сегодня",
    "admin.ofUsers": "из {count} пользователей",
    "admin.periodToday": "Сегодня",
    "admin.periodWeek": "Неделя",
    "admin.periodMonth": "Месяц",
    "notice.errorTitle": "Ошибка",
    "notice.successTitle": "Готово",
    "notice.genericValidation": "Проверьте заполнение формы",
    "notice.genericActionError": "Не получилось выполнить действие. Проверьте данные и попробуйте еще раз.",
    "notice.adminUpdated": "Пользователь обновлён.",
    "notice.connectAccount": "Подключите аккаунт.",
    "notice.autopostPaused": "Автопостинг на паузе.",
    "notice.groupsSynced": "Группы обновлены: {count}",
    "notice.deleteMissingMessage": "Пост удалён из сервиса. Для этого поста не был сохранён message_id исходного сообщения, поэтому удалить его в чате нельзя.",
    "notice.deleteAll": "Пост удалён. В чате Telegram удалено сообщений: {count}.",
    "notice.deletePartial": "Пост удалён из сервиса. Telegram удалил {deleted}/{total}. Причина: {error}",
    "notice.deleteConfirmed": "Пост удалён из сервиса. Telegram подтвердил удаление {deleted}/{total} сообщений.",
    "notice.postResumed": "Рассылка возобновлена.",
    "notice.postPaused": "Рассылка поставлена на паузу.",
    "notice.globalPaused": "Автопостинг поставлен на паузу.",
    "notice.globalResumed": "Автопостинг снова активен.",
    "notice.sessionDisconnected": "Telegram-сессия отключена.{suffix}",
    "notice.sessionDisconnectSuffix": " Telegram мог не подтвердить закрытие сессии, но доступ в сервисе удалён.",
    "notice.postUpdated": "Пост обновлён.",
    "notice.postScheduled": "Пост запланирован.",
    "notice.codeSent": "Код отправлен в Telegram.",
    "notice.smsRequested": "SMS-код запрошен.",
    "notice.passwordNeeded": "Нужен пароль 2FA.",
    "notice.accountConnected": "Аккаунт подключен.",
    "validation.futureDate": "Выберите будущую дату отправки.",
    "validation.chooseGroup": "Выберите хотя бы одну группу.",
    "validation.chooseDraft": "Отправьте пост боту и выберите черновик.",
    "validation.chooseWeekday": "Выберите хотя бы один день недели.",
    "validation.postMissing": "Пост не найден. Обновите страницу.",
    "validation.phoneRequired": "Сначала введите номер телефона.",
    "validation.phoneInvalid": "Введите корректный номер с кодом страны.",
    "spam.minInterval": "Минимальный интервал повтора — 20 минут.",
    "spam.riskMessage": "За частую отправку сообщений ваш аккаунт в Telegram может быть ограничен или заблокирован.",
    "spam.riskTitle": "Риск блокировки",
    "spam.understand": "Я понимаю",
    "spam.cancel": "Отмена",
    "spam.continue": "Продолжить?",
    "spam.largeSelection": "Вы выбрали {count} чатов. Массовая отправка больше чем в {limit} чатов может быть опасной и привести к блокировке Telegram-аккаунта. Продолжайте только на свой страх и риск.",
    "spam.ok": "Понятно",
    "delete.draftTitle": "Удалить черновик?",
    "delete.queueTitle": "Удалить из очереди?",
    "delete.draftMessage": "Черновик исчезнет из миниаппа. Сообщение в чате с ботом тоже будет удалено, если Telegram разрешит.",
    "delete.queueMessage": "Пост будет удалён из очереди. Исходное сообщение в чате с ботом тоже будет удалено, если Telegram разрешит.",
    "delete.button": "Удалить",
    "login.sending": "Отправляем...",
    "login.checking": "Проверяем...",
    "login.smsIn": "SMS через {seconds}с",
    "login.smsUnavailable": "SMS недоступна",
    "login.disconnectConfirm": "Отключить Telegram-сессию? После этого для повторного подключения Telegram снова запросит код.",
    "login.disconnecting": "Отключаем...",
    "login.finish": "Завершить",
    "login.connect": "Подключить",
    "login.getCode": "Получить код",
    "edit.pastDate": "Старая дата уже прошла. Выберите новую дату отправки и сохраните изменения.",
    "busy.pause": "Ставим...",
    "busy.resume": "Снимаем...",
    "busy.save": "Сохраняем...",
    "busy.saveChanges": "Сохранить изменения",
  },
};

if (tg) {
  tg.ready();
  tg.expand();
}

const state = {
  language: localStorage.getItem(languageStorageKey) || "en",
  config: { bot_username: "scheduler_baraholki_bot" },
  settings: { autopost_paused: false },
  sessions: [],
  chats: [],
  folders: [],
  posts: [],
  audit: { items: [], page: 1, page_size: 20, total: 0 },
  auditLoading: false,
  adminTab: "users",
  adminUsers: { items: [], page: 1, page_size: 10, total: 0 },
  adminAudit: { user: null, items: [], page: 1, page_size: 20, total: 0 },
  adminAuditLoading: false,
  adminStats: null,
  adminLoading: false,
  adminUserSearch: "",
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

if (!supportedLanguages.includes(state.language)) {
  state.language = "en";
}

function t(key, params = {}) {
  const template = translations[state.language]?.[key] || translations.en[key] || key;
  return Object.entries(params).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
    template,
  );
}

function countText(key, count) {
  return t(key, { count });
}

function applyTranslations() {
  document.documentElement.lang = state.language;
  document.title = t("app.title");
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    node.setAttribute("placeholder", t(node.dataset.i18nPlaceholder));
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((node) => {
    node.setAttribute("aria-label", t(node.dataset.i18nAriaLabel));
  });
  const languageSelect = document.querySelector("#language-select");
  if (languageSelect) {
    languageSelect.value = state.language;
  }
}

function setLanguage(language) {
  state.language = supportedLanguages.includes(language) ? language : "en";
  localStorage.setItem(languageStorageKey, state.language);
  applyTranslations();
  render();
}

function activeSessions() {
  return state.sessions.filter((session) => session.status === "active");
}

function isAutopostPaused() {
  return Boolean(state.settings?.autopost_paused);
}

function isAdmin() {
  return Boolean(state.config?.is_admin);
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
    tg.showPopup({ title: type === "error" ? t("notice.errorTitle") : t("notice.successTitle"), message });
  }
}

function clearNotice() {
  document.querySelector("#notice").hidden = true;
}

function setDraftHelpVisible(visible) {
  const button = document.querySelector("#draft-help-button");
  const tooltip = document.querySelector("#draft-help-tooltip");
  if (!button || !tooltip) return;
  tooltip.hidden = !visible;
  button.setAttribute("aria-expanded", String(visible));
}

async function api(path, options = {}) {
  return requestApi(path, options, t);
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
      setBusy(button, false, t("connect.sendSms"));
      return;
    }
    setBusy(button, true, t("login.smsIn", { seconds: remaining }));
    remaining -= 1;
  };

  tick();
  smsCooldownTimer = window.setInterval(tick, 1000);
}

function updateSmsButtonFromLoginResult(result) {
  const button = document.querySelector("#resend-sms-code");
  if (!button) return;
  if (smsCooldownTimer) {
    window.clearInterval(smsCooldownTimer);
    smsCooldownTimer = null;
  }

  if (result?.next_delivery_type) {
    setBusy(button, false, t("connect.sendSms"));
    return;
  }

  setBusy(button, true, t("login.smsUnavailable"));
}

function phoneDigits(value) {
  return String(value || "").replace(/\D/g, "");
}

function formatPhoneLocal(value) {
  const digits = phoneDigits(value).slice(0, 15);
  if (digits.length <= 3) return digits;
  if (digits.length <= 6) return `${digits.slice(0, 3)} ${digits.slice(3)}`;
  if (digits.length <= 10) {
    return `${digits.slice(0, 3)} ${digits.slice(3, 6)} ${digits.slice(6)}`;
  }
  return `${digits.slice(0, 3)} ${digits.slice(3, 6)} ${digits.slice(6, 10)} ${digits.slice(10)}`;
}

function normalizePhoneInput(input) {
  if (!input) return;
  const formatted = formatPhoneLocal(input.value);
  input.value = formatted;
}

function loginPhoneFromForm(form) {
  const countryCode = String(form.get("country_code") || "").replace(/[^\d+]/g, "");
  const rawLocalPhone = String(form.get("phone_local") || "");
  const fullPhone = rawLocalPhone.replace(/[^\d+]/g, "");
  if (fullPhone.startsWith("+")) {
    const normalized = `+${phoneDigits(fullPhone)}`;
    return normalized.length > 1 ? normalized : "";
  }

  const localPhone = phoneDigits(rawLocalPhone);
  if (!countryCode || !localPhone) {
    return "";
  }
  return `${countryCode}${localPhone}`;
}

function isValidPhone(phone) {
  return /^\+\d{8,15}$/.test(String(phone || ""));
}

function selectedGroups() {
  return [...state.selectedChatIds];
}

function selectedEditGroups() {
  return [...state.editSelectedChatIds];
}

function toggleDraftSelection(draftId) {
  state.selectedDraftId = state.selectedDraftId === draftId ? null : draftId;
}

function folderItems() {
  return [
    { id: "all", title: t("folder.all"), telegram_chat_ids: state.chats.map((chat) => chat.telegram_chat_id) },
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
  return state.chats.find((chat) => chat.id === chatId)?.title || t("audit.groupMissing");
}

function statusLabel(status) {
  if (status === "scheduled") return t("post.status.scheduled");
  if (status === "paused") return t("post.status.paused");
  if (status === "archived") return t("post.status.archived");
  if (status === "draft") return t("post.status.draft");
  return status;
}

function statusIcon(status) {
  if (status === "scheduled") return "◷";
  if (status === "paused") return "Ⅱ";
  if (status === "archived") return "□";
  return "✎";
}

function auditStatusLabel(status) {
  if (status === "done") return t("audit.status.done");
  if (status === "failed") return t("audit.status.failed");
  if (status === "pending") return t("audit.status.pending");
  if (status === "processing") return t("audit.status.processing");
  if (status === "cancelled") return t("audit.status.cancelled");
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
  if (!count) return t("media.none");
  if (count === 1) return t("media.onePhoto");
  return t("media.photos", { count });
}

function formatNumber(value) {
  return new Intl.NumberFormat(state.language === "ru" ? "ru-RU" : "en-US").format(Number(value || 0));
}

function formatDateTime(value) {
  if (!value) return t("post.schedule.noDate");
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return t("post.schedule.noDate");
  return date.toLocaleString(state.language === "ru" ? "ru-RU" : "en-US", {
    day: "2-digit",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function scheduleLabel(post) {
  const when = post.next_run_at ? formatDateTime(post.next_run_at) : t("post.schedule.notSelected");
  if (post.schedule_kind === "interval") {
    return t("post.schedule.interval", { when, minutes: post.interval_minutes });
  }
  if (post.schedule_kind === "daily") return t("post.schedule.daily", { when });
  if (post.schedule_kind === "weekdays") return t("post.schedule.weekdays", { when });
  if (post.schedule_kind === "weekends") return t("post.schedule.weekends", { when });
  if (post.schedule_kind === "every_other_day") return t("post.schedule.everyOtherDay", { when });
  if (post.schedule_kind === "weekly") return t("post.schedule.weekly", { when });
  if (post.schedule_kind === "custom_weekdays") {
    return t("post.schedule.custom", { when, days: weekdaySummary(post.schedule_weekdays || []) });
  }
  return t("post.schedule.once", { when });
}

function weekdaySummary(days) {
  const names = [
    t("weekday.mon"),
    t("weekday.tue"),
    t("weekday.wed"),
    t("weekday.thu"),
    t("weekday.fri"),
    t("weekday.sat"),
    t("weekday.sun"),
  ];
  const selected = [...new Set((days || []).map((day) => Number(day)).filter((day) => day >= 0 && day <= 6))]
    .sort((left, right) => left - right)
    .map((day) => names[day]);
  return selected.length ? selected.join(", ") : t("post.weekdaysFallback");
}

function targetSummary(post) {
  const titles = (post.target_chat_ids || []).map(chatTitleById);
  if (titles.length === 0) return t("post.targets.none");
  if (titles.length <= 2) return titles.join(", ");
  return t("post.targets.more", {
    first: titles[0],
    second: titles[1],
    count: titles.length - 2,
  });
}

function mediaLabel(post) {
  const count = post.media?.length || 0;
  if (!count) return t("media.none");
  if (count === 1) return t("media.oneMedia");
  return t("media.manyMedia", { count });
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
    notify(t("spam.minInterval"), "error");
    return false;
  }

  if (intervalMinutes > 30) return true;

  const message = t("spam.riskMessage");

  if (tg?.showPopup) {
    return new Promise((resolve) => {
      tg.showPopup(
        {
          title: t("spam.riskTitle"),
          message,
          buttons: [
            { id: "understand", type: "default", text: t("spam.understand") },
            { id: "cancel", type: "cancel", text: t("spam.cancel") },
          ],
        },
        (buttonId) => resolve(buttonId === "understand"),
      );
    });
  }

  return window.confirm(`${message}\n\n${t("spam.continue")}`);
}

function showLargeChatSelectionWarning(count) {
  const message = t("spam.largeSelection", { count, limit: riskyChatSelectionLimit });

  if (tg?.showPopup) {
    tg.showPopup({
      title: t("spam.riskTitle"),
      message,
      buttons: [{ id: "understand", type: "default", text: t("spam.ok") }],
    });
    return;
  }

  window.alert(message);
}

function warnIfLargeChatSelection(previousCount, currentCount) {
  if (previousCount <= riskyChatSelectionLimit && currentCount > riskyChatSelectionLimit) {
    showLargeChatSelectionWarning(currentCount);
  }
}

async function confirmDeletePost(post) {
  const isDraft = post.status === "draft";
  const message = isDraft ? t("delete.draftMessage") : t("delete.queueMessage");

  if (tg?.showPopup) {
    return new Promise((resolve) => {
      tg.showPopup(
        {
          title: isDraft ? t("delete.draftTitle") : t("delete.queueTitle"),
          message,
          buttons: [
            { id: "delete", type: "destructive", text: t("delete.button") },
            { id: "cancel", type: "cancel", text: t("spam.cancel") },
          ],
        },
        (buttonId) => resolve(buttonId === "delete"),
      );
    });
  }

  return window.confirm(message);
}

function render() {
  applyTranslations();
  const connected = activeSessions();
  const primarySession = connected[0] || state.sessions[0];
  const hasAccount = connected.length > 0;
  const paused = isAutopostPaused();
  const hasGroups = state.chats.length > 0;
  const drafts = draftPosts();
  const queued = queuePosts();

  if (state.activeTab === "admin" && !isAdmin()) {
    state.activeTab = "posts";
  }

  applyTabVisibility();

  document.querySelector("#posts-count").textContent = countText("count.posts", queued.length);
  document.querySelector("#drafts-count").textContent = countText("count.drafts", drafts.length);
  document.querySelector("#groups-count").textContent = countText("count.groups", filteredChats().length);

  const stateDot = document.querySelector("#account-state");
  stateDot.className = `status-dot ${hasAccount ? (paused ? "paused" : "online") : ""}`;
  document.querySelector("#account-title").textContent = hasAccount
    ? paused
      ? t("status.autopostPaused")
      : t("status.connected")
    : t("status.notConnected");
  document.querySelector("#account-subtitle").textContent = hasAccount
    ? `${primarySession.phone || ""} ${primarySession.username ? `@${primarySession.username}` : ""}`.trim()
    : t("status.connectSubtitle");

  document.querySelector("#connect-panel").hidden = hasAccount || state.activeTab !== "posts";
  document.querySelector("#account-pause").hidden = !hasAccount;
  document.querySelector("#account-pause").textContent = paused
    ? t("settings.resumeButton")
    : t("settings.pauseButton");
  document.querySelector("#compose-hint").textContent = hasAccount
    ? paused
      ? t("compose.paused")
      : hasGroups
      ? t("compose.ready")
      : t("compose.noGroups")
    : t("compose.connectFirst");

  const picker = document.querySelector("#group-picker");
  if (!hasGroups) {
    picker.replaceChildren(emptyChip(hasAccount ? t("empty.noGroupsLoaded") : t("empty.noAccount")));
    document.querySelector("#folder-picker").replaceChildren();
  } else {
    renderFolderPicker();
    renderGroupPicker();
  }

  const saveButton = document.querySelector("#save-post");
  saveButton.disabled = paused || !hasAccount || !hasGroups || !state.selectedDraftId;

  renderSettingsPanel(hasAccount, paused);

  renderDraftPicker();

  const posts = document.querySelector("#posts");
  if (queued.length === 0) {
    posts.replaceChildren(emptyPost(t("empty.noQueuedPosts")));
    renderQueuePagination(queued.length);
  } else {
    state.queuePage = clampPage(state.queuePage, queued.length, state.queuePageSize);
    posts.replaceChildren(...pageSlice(queued, state.queuePage, state.queuePageSize).map(renderPost));
    renderQueuePagination(queued.length);
  }

  renderAudit();
  renderAdmin();
  applyTabVisibility();
}

function applyTabVisibility() {
  const adminTabButton = document.querySelector("#admin-tab-button");
  if (adminTabButton) {
    adminTabButton.hidden = !isAdmin();
    adminTabButton.textContent = t("nav.admin");
    adminTabButton.classList.toggle("selected", state.activeTab === "admin");
  }
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
    state.selectedDraftId = null;
  }

  if (drafts.length === 0) {
    picker.replaceChildren(emptyPost(t("empty.noDrafts")));
    return;
  }

  picker.replaceChildren(
    ...visibleDrafts.map((post) => {
      const card = document.createElement("article");
      card.className = `draft-card ${state.selectedDraftId === post.id ? "selected" : ""}`.trim();
      card.role = "button";
      card.tabIndex = 0;
      card.addEventListener("click", () => {
        toggleDraftSelection(post.id);
        render();
      });
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          toggleDraftSelection(post.id);
          render();
        }
      });

      const mediaCount = post.media?.length || 0;
      const preview = post.body ? stripHtml(post.body).slice(0, 180) : t("media.noText");
      card.innerHTML = `
        <div class="draft-card-main">
          <strong></strong>
          <span></span>
          <small></small>
        </div>
        <button class="danger-button compact-button" type="button">${t("delete.button")}</button>
      `;
      card.querySelector("strong").textContent = post.title || t("draft.defaultTitle");
      card.querySelector("span").textContent = preview;
      card.querySelector("small").textContent = mediaCount ? t("media.manyMedia", { count: mediaCount }) : t("media.text");
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
  document.querySelector("#audit-count").textContent = state.auditLoading ? t("loading.short") : countText("count.records", total);
  renderAuditPagination();

  const list = document.querySelector("#audit-list");
  if (state.auditLoading) {
    list.replaceChildren(loadingBlock(t("audit.loading")));
    return;
  }
  if (total === 0) {
    list.replaceChildren(emptyPost(activeSessions().length ? t("empty.noAudit") : t("empty.connectAccount")));
    return;
  }

  list.replaceChildren(...state.audit.items.map((item) => renderAuditItem(item)));
}

function renderAuditItem(item, options = {}) {
  const node = document.createElement("article");
  node.className = `audit-item ${item.status}`.trim();
  const title = shortWords(item.post_title || item.post_preview || t("draft.defaultTitle"), 9);
  node.innerHTML = `
    <div class="audit-item-head">
      <span class="audit-status-icon" data-field="status-icon"></span>
      <div>
        <strong data-field="title"></strong>
        <p data-field="media"></p>
      </div>
    </div>
    <dl class="audit-meta">
      <div><dt>${t("audit.field.target")}</dt><dd data-field="target"></dd></div>
      <div><dt>${t("audit.field.time")}</dt><dd data-field="time"></dd></div>
      <div><dt>${t("audit.field.result")}</dt><dd data-field="result"></dd></div>
      <div data-field="message-link-row" hidden><dt>${t("audit.field.link")}</dt><dd><a data-field="message-link" target="_blank" rel="noreferrer"></a></dd></div>
    </dl>
    <div class="audit-actions" data-field="actions" hidden>
      <button class="secondary-button compact-button" type="button" data-action="view-message">${t("audit.viewMessage")}</button>
    </div>
  `;
  node.querySelector('[data-field="title"]').textContent = title || t("draft.defaultTitle");
  node.querySelector('[data-field="media"]').textContent = mediaCountLabel(item.media_count || 0);
  node.querySelector('[data-field="status-icon"]').textContent = auditStatusIcon(item.status);
  node.querySelector('[data-field="target"]').textContent = item.target_chat_title || t("audit.groupMissing");
  node.querySelector('[data-field="time"]').textContent = formatDateTime(item.updated_at || item.due_at);
  node.querySelector('[data-field="result"]').textContent =
    item.status === "done" ? t("audit.sent") : item.last_error || auditStatusLabel(item.status);
  const linkRow = node.querySelector('[data-field="message-link-row"]');
  const link = node.querySelector('[data-field="message-link"]');
  if (item.message_link) {
    linkRow.hidden = false;
    link.href = item.message_link;
    link.textContent = t("audit.openInTelegram");
  }
  if (item.telegram_message_id) {
    const actions = node.querySelector('[data-field="actions"]');
    const button = node.querySelector('[data-action="view-message"]');
    actions.hidden = false;
    button.addEventListener("click", () => {
      loadAuditMessage(item, button, options).catch((error) => notify(error.message, "error"));
    });
  }
  return node;
}

async function loadAuditMessage(item, button, options = {}) {
  setBusy(button, true, t("audit.loadingMessage"));
  try {
    const endpoint = options.adminUserId
      ? `admin/users/${options.adminUserId}/audit/${item.id}/message`
      : `audit/${item.id}/message`;
    const message = await api(endpoint);
    showAuditMessage(message);
  } finally {
    setBusy(button, false, t("audit.viewMessage"));
  }
}

function showAuditMessage(message) {
  const modal = document.querySelector("#audit-message-modal");
  const chat = document.querySelector("#audit-message-chat");
  const text = document.querySelector("#audit-message-text");
  const link = document.querySelector("#audit-message-link");
  chat.textContent = message.target_chat_title || t("audit.groupMissing");
  text.textContent = message.message_text || t("audit.messageFallback");
  if (message.message_link) {
    link.hidden = false;
    link.href = message.message_link;
  } else {
    link.hidden = true;
    link.removeAttribute("href");
  }
  modal.hidden = false;
}

function closeAuditMessage() {
  document.querySelector("#audit-message-modal").hidden = true;
}

function adminStatusSummary(user) {
  if (user.banned) return t("admin.status.banned");
  if (user.autopost_paused) return t("admin.status.paused");
  return user.session_status || t("admin.status.noSession");
}

function adminUserLabel(user) {
  if (!user) return t("admin.userFallback");
  return user.username ? `@${user.username}` : `${t("admin.userFallback")} ${user.telegram_user_id}`;
}

function renderAdmin() {
  const adminPanel = document.querySelector('[data-tab-panel="admin"]');
  if (!adminPanel || !isAdmin()) return;
  if (
    !document.querySelector("#admin-tabs") ||
    !document.querySelector("#admin-users") ||
    !document.querySelector("#admin-stats") ||
    !document.querySelector("#admin-audit")
  ) {
    return;
  }

  document.querySelector("#admin-tabs").hidden = state.adminTab === "audit";
  document.querySelectorAll(".admin-tab-button").forEach((button) => {
    button.classList.toggle("selected", button.dataset.adminTab === state.adminTab);
  });
  document.querySelectorAll("[data-admin-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.adminPanel !== state.adminTab;
  });

  renderAdminUsers();
  renderAdminStats();
  renderAdminAudit();
}

function renderAdminUsers() {
  const list = document.querySelector("#admin-user-list");
  const pagination = document.querySelector("#admin-users-pagination");
  if (!list || !pagination) return;

  if (state.adminLoading && state.adminTab === "users") {
    list.replaceChildren(loadingBlock(t("admin.loadingUsers")));
    return;
  }

  if (!state.adminUsers.items.length) {
    list.replaceChildren(emptyPost(t("admin.noUsers")));
  } else {
    list.replaceChildren(...state.adminUsers.items.map(renderAdminUser));
  }

  const pages = pageCount(state.adminUsers.total || 0, state.adminUsers.page_size);
  pagination.hidden = (state.adminUsers.total || 0) <= state.adminUsers.page_size;
  document.querySelector("#admin-users-page").textContent = `${state.adminUsers.page} / ${pages}`;
  document.querySelector("#admin-users-prev").disabled = state.adminUsers.page <= 1;
  document.querySelector("#admin-users-next").disabled = state.adminUsers.page >= pages;
}

function renderAdminAudit() {
  const list = document.querySelector("#admin-audit-list");
  const pagination = document.querySelector("#admin-audit-pagination");
  const title = document.querySelector("#admin-audit-title");
  const count = document.querySelector("#admin-audit-count");
  if (!list || !pagination || !title || !count) return;

  const user = state.adminAudit.user;
  title.textContent = user ? `${t("admin.auditTitle")}: ${adminUserLabel(user)}` : t("admin.auditTitle");
  const total = state.adminAudit.total || 0;
  count.textContent = state.adminAuditLoading ? t("loading.short") : countText("count.records", total);

  if (state.adminAuditLoading && state.adminTab === "audit") {
    list.replaceChildren(loadingBlock(t("audit.loading")));
  } else if (!state.adminAudit.items.length) {
    list.replaceChildren(emptyPost(t("empty.noAudit")));
  } else {
    list.replaceChildren(
      ...state.adminAudit.items.map((item) => renderAuditItem(item, { adminUserId: user?.telegram_user_id })),
    );
  }

  const pages = pageCount(total, state.adminAudit.page_size);
  pagination.hidden = total <= state.adminAudit.page_size;
  document.querySelector("#admin-audit-page").textContent = `${state.adminAudit.page} / ${pages}`;
  document.querySelector("#admin-audit-prev").disabled = state.adminAudit.page <= 1;
  document.querySelector("#admin-audit-next").disabled = state.adminAudit.page >= pages;
}

function renderAdminUser(user) {
  const node = document.createElement("article");
  node.className = `admin-user ${user.banned ? "banned" : user.autopost_paused ? "paused" : ""}`.trim();
  node.innerHTML = `
    <div class="admin-user-main">
      <div class="admin-user-title">
        <strong data-field="title"></strong>
        <span data-field="status"></span>
      </div>
      <dl class="admin-user-meta">
        <div><dt>${t("admin.id")}</dt><dd data-field="id"></dd></div>
        <div><dt>${t("admin.phone")}</dt><dd data-field="phone"></dd></div>
        <div><dt>${t("admin.today")}</dt><dd data-field="sent"></dd></div>
        <div><dt>${t("admin.errors")}</dt><dd data-field="failed"></dd></div>
      </dl>
    </div>
    <div class="admin-user-controls">
      <button class="secondary-button compact-button" type="button" data-action="audit">${t("admin.openAudit")}</button>
      <button class="danger-button compact-button" type="button" data-action="ban"></button>
      <button class="secondary-button compact-button" type="button" data-action="pause"></button>
      <label>
        ${t("admin.limitDay")}
        <input data-field="limit" type="number" min="0" inputmode="numeric" />
      </label>
      <button class="compact-button" type="button" data-action="limit">${t("admin.saveLimit")}</button>
    </div>
  `;
  node.querySelector('[data-field="title"]').textContent = adminUserLabel(user);
  node.querySelector('[data-field="status"]').textContent = adminStatusSummary(user);
  node.querySelector('[data-field="id"]').textContent = String(user.telegram_user_id);
  node.querySelector('[data-field="phone"]').textContent = user.phone || "—";
  node.querySelector('[data-field="sent"]').textContent = String(user.sent_today || 0);
  node.querySelector('[data-field="failed"]').textContent = String(user.failed_total || 0);
  const limitInput = node.querySelector('[data-field="limit"]');
  limitInput.value = user.daily_send_limit ?? "";
  node.querySelector('[data-action="ban"]').textContent = user.banned ? t("admin.unban") : t("admin.ban");
  node.querySelector('[data-action="pause"]').textContent = user.autopost_paused ? t("admin.resume") : t("admin.pause");
  node.querySelector('[data-action="audit"]').addEventListener("click", () => {
    openAdminAudit(user);
  });
  node.querySelector('[data-action="ban"]').addEventListener("click", () => {
    updateAdminUser(user.telegram_user_id, { banned: !user.banned }).catch((error) => notify(error.message, "error"));
  });
  node.querySelector('[data-action="pause"]').addEventListener("click", () => {
    updateAdminUser(user.telegram_user_id, { autopost_paused: !user.autopost_paused }).catch((error) =>
      notify(error.message, "error"),
    );
  });
  node.querySelector('[data-action="limit"]').addEventListener("click", () => {
    const rawLimit = limitInput.value.trim();
    const daily_send_limit = rawLimit === "" ? null : Number(rawLimit);
    updateAdminUser(user.telegram_user_id, { daily_send_limit }).catch((error) => notify(error.message, "error"));
  });
  return node;
}

function renderAdminStats() {
  const grid = document.querySelector("#admin-stats-grid");
  if (!grid) return;
  if (state.adminLoading && state.adminTab === "stats") {
    grid.replaceChildren(loadingBlock(t("admin.statsLoading")));
    return;
  }
  const stats = state.adminStats;
  if (!stats) {
    grid.replaceChildren(emptyPost(t("admin.statsEmpty")));
    return;
  }
  const sentTotal = Number(stats.sent_total || 0);
  const failedTotal = Number(stats.failed_total || 0);
  const deliveredTotal = sentTotal + failedTotal;
  const successRate = deliveredTotal > 0 ? Math.round((sentTotal / deliveredTotal) * 100) : 100;
  const activeShare =
    Number(stats.users_total || 0) > 0
      ? Math.round((Number(stats.daily_active_users || 0) / Number(stats.users_total || 0)) * 100)
      : 0;
  const maxPeriod = Math.max(stats.sent_today || 0, stats.sent_week || 0, stats.sent_month || 0, 1);
  const periods = [
    [t("admin.periodToday"), stats.sent_today || 0],
    [t("admin.periodWeek"), stats.sent_week || 0],
    [t("admin.periodMonth"), stats.sent_month || 0],
  ];

  grid.innerHTML = `
    <article class="admin-stat-hero">
      <span>${t("admin.deliveredTotal")}</span>
      <strong data-field="sent-total"></strong>
      <div class="stat-spark" aria-hidden="true"></div>
      <dl>
        <div><dt>${t("admin.periodToday")}</dt><dd data-field="today"></dd></div>
        <div><dt>${t("admin.periodWeek")}</dt><dd data-field="week"></dd></div>
        <div><dt>${t("admin.periodMonth")}</dt><dd data-field="month"></dd></div>
      </dl>
    </article>
    <article class="admin-stat-card">
      <div class="stat-ring" style="--value: ${successRate}">
        <strong>${successRate}%</strong>
      </div>
      <span>${t("admin.successRate")}</span>
      <p>${t("admin.errorsOfAttempts", { failed: failedTotal, total: deliveredTotal || 0 })}</p>
    </article>
    <article class="admin-stat-card">
      <div class="stat-meter">
        <span style="width: ${activeShare}%"></span>
      </div>
      <strong data-field="active-users"></strong>
      <span>${t("admin.activeToday")}</span>
      <p data-field="users-total"></p>
    </article>
    <article class="admin-stat-periods"></article>
  `;

  grid.querySelector('[data-field="sent-total"]').textContent = formatNumber(sentTotal);
  grid.querySelector('[data-field="today"]').textContent = formatNumber(stats.sent_today || 0);
  grid.querySelector('[data-field="week"]').textContent = formatNumber(stats.sent_week || 0);
  grid.querySelector('[data-field="month"]').textContent = formatNumber(stats.sent_month || 0);
  grid.querySelector('[data-field="active-users"]').textContent = formatNumber(stats.daily_active_users || 0);
  grid.querySelector('[data-field="users-total"]').textContent =
    t("admin.ofUsers", { count: formatNumber(stats.users_total || 0) });

  const periodList = grid.querySelector(".admin-stat-periods");
  periodList.replaceChildren(
    ...periods.map(([label, value]) => {
      const item = document.createElement("div");
      item.className = "period-row";
      item.innerHTML = `
        <div><span></span><strong></strong></div>
        <div class="period-bar"><span></span></div>
      `;
      item.querySelector("span").textContent = label;
      item.querySelector("strong").textContent = formatNumber(value);
      item.querySelector(".period-bar span").style.width = `${Math.max(4, Math.round((value / maxPeriod) * 100))}%`;
      return item;
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
    picker.replaceChildren(emptyChip(t("empty.noSearchResults")));
  } else {
    picker.replaceChildren(
      ...visible.map((chat) => {
        const label = document.createElement("label");
        label.className = "group-chip";
        label.innerHTML = `<input type="checkbox" name="target_chat_ids" value="${chat.id}" /> <span></span>`;
        const input = label.querySelector("input");
        input.checked = state.selectedChatIds.has(chat.id);
        input.addEventListener("change", () => {
          const previousCount = state.selectedChatIds.size;
          if (input.checked) {
            state.selectedChatIds.add(chat.id);
          } else {
            state.selectedChatIds.delete(chat.id);
          }
          warnIfLargeChatSelection(previousCount, state.selectedChatIds.size);
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
  const preview = cleanBody.length > 120 ? `${cleanBody.slice(0, 120)}...` : cleanBody || t("media.noText");
  node.innerHTML = `
    <div class="post-item-main">
      <div class="post-title-row">
        <p></p>
        <span class="post-status-icon"></span>
      </div>
      <dl class="post-meta">
        <div><dt>${t("form.when")}</dt><dd data-field="schedule"></dd></div>
        <div><dt>${t("groups.title")}</dt><dd data-field="targets"></dd></div>
        <div><dt>${t("form.media")}</dt><dd data-field="media"></dd></div>
      </dl>
    </div>
    <div class="post-actions">
      <button class="post-icon-button secondary-button" data-action="edit" type="button" aria-label="${t("post.action.edit")}" title="${t("post.action.edit")}">✎</button>
      <button class="post-icon-button secondary-button" data-action="pause" type="button"></button>
      <button class="post-icon-button danger-button" data-action="delete" type="button" aria-label="${t("delete.button")}" title="${t("delete.button")}">×</button>
    </div>
  `;
  node.querySelector("p").textContent = preview;
  const status = statusLabel(post.status);
  const statusNode = node.querySelector(".post-status-icon");
  statusNode.textContent = statusIcon(post.status);
  statusNode.title = status;
  statusNode.setAttribute("aria-label", status);
  node.querySelector('[data-field="schedule"]').textContent = scheduleLabel(post);
  node.querySelector('[data-field="targets"]').textContent = targetSummary(post);
  node.querySelector('[data-field="media"]').textContent = mediaLabel(post);
  const pauseButton = node.querySelector('[data-action="pause"]');
  const pauseLabel = post.status === "paused" ? t("post.action.resume") : t("post.action.pause");
  pauseButton.textContent = post.status === "paused" ? "▶" : "Ⅱ";
  pauseButton.setAttribute("aria-label", pauseLabel);
  pauseButton.title = pauseLabel;
  if (isAutopostPaused()) {
    node.querySelectorAll("button").forEach((button) => {
      button.disabled = true;
    });
  }
  node.querySelector('[data-action="edit"]').addEventListener("click", () => openEditPost(post));
  node.querySelector('[data-action="pause"]').addEventListener("click", () => {
    togglePausePost(post).catch((error) => notify(error.message, "error"));
  });
  node.querySelector('[data-action="delete"]').addEventListener("click", () => {
    deletePost(post.id).catch((error) => notify(error.message, "error"));
  });
  return node;
}

function renderSettingsPanel(hasAccount, paused) {
  const text = document.querySelector("#global-pause-text");
  const settingsPause = document.querySelector("#settings-pause");
  const revoke = document.querySelector("#revoke-session");
  if (!text || !settingsPause || !revoke) return;

  text.textContent = paused
    ? t("settings.pauseEnabled")
    : t("settings.pauseDisabled");
  settingsPause.textContent = paused ? t("settings.resumeButton") : t("settings.pauseButton");
  settingsPause.disabled = !hasAccount;
  revoke.disabled = !hasAccount;
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

  document.querySelector("#edit-groups-count").textContent = countText("count.groups", chats.length);

  if (visible.length === 0) {
    picker.replaceChildren(emptyChip(t("empty.noSearchResults")));
  } else {
    picker.replaceChildren(
      ...visible.map((chat) => {
        const label = document.createElement("label");
        label.className = "group-chip";
        label.innerHTML = `<input type="checkbox" value="${chat.id}" /> <span></span>`;
        const input = label.querySelector("input");
        input.checked = state.editSelectedChatIds.has(chat.id);
        input.addEventListener("change", () => {
          const previousCount = state.editSelectedChatIds.size;
          if (input.checked) {
            state.editSelectedChatIds.add(chat.id);
          } else {
            state.editSelectedChatIds.delete(chat.id);
          }
          warnIfLargeChatSelection(previousCount, state.editSelectedChatIds.size);
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
  const preview = stripHtml(post.body || "") || t("media.noText");
  form.elements.next_run_at.value = options.requireFutureDate
    ? nextDefaultDateTimeLocal()
    : dateTimeLocalValue(post.next_run_at);
  form.elements.schedule_kind.value = post.schedule_kind || "once";
  form.elements.interval_minutes.value = post.interval_minutes || 60;
  setSelectedWeekdays(form, post.schedule_weekdays || []);
  document.querySelector("#edit-preview").textContent = preview.length > 180 ? `${preview.slice(0, 180)}...` : preview;
  document.querySelector("#edit-group-search").value = "";
  updateScheduleControls(form, "edit-");
  const editPage = document.querySelector("#edit-modal");
  editPage.hidden = false;
  editPage.scrollTo({ top: 0, left: 0 });
  document.body.classList.add("editing-open");
  renderEditFolderPicker();
  renderEditGroupPicker();

  if (options.requireFutureDate) {
    notify(t("edit.pastDate"), "error");
  }
}

function closeEditPost() {
  state.editingPostId = null;
  document.querySelector("#edit-modal").hidden = true;
  document.body.classList.remove("editing-open");
}

function stripHtml(value) {
  return String(value || "")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, " ")
    .trim();
}

function deletionMessage(result) {
  if (result.source_messages_found === 0) {
    return t("notice.deleteMissingMessage");
  }

  if (result.deleted_bot_messages === result.source_messages_found) {
    return t("notice.deleteAll", { count: result.deleted_bot_messages });
  }

  const firstError = result.telegram_delete_errors?.[0];
  if (firstError) {
    return t("notice.deletePartial", {
      deleted: result.deleted_bot_messages,
      total: result.source_messages_found,
      error: firstError,
    });
  }

  return t("notice.deleteConfirmed", {
    deleted: result.deleted_bot_messages,
    total: result.source_messages_found,
  });
}

async function load(options = {}) {
  const [config, settings, sessions, chats, folders, posts] = await Promise.all([
    api("app-config"),
    api("user-settings"),
    api("sessions"),
    api("chats"),
    api("folders").catch(() => state.folders),
    api("posts"),
  ]);
  state.config = config;
  state.settings = settings;
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

  if (
    options.autoSyncGroups &&
    activeSessions().length > 0 &&
    !isAutopostPaused() &&
    !state.groupsSyncedOnInit
  ) {
    state.groupsSyncedOnInit = true;
    await syncGroups({ silent: true });
  }

  if (state.activeTab === "audit") {
    await loadAudit();
  }
  if (state.activeTab === "admin" && isAdmin()) {
    await loadAdminDashboard();
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

async function loadAdminUsers(options = {}) {
  if (!isAdmin()) return;
  state.adminLoading = true;
  if (options.renderFirst) render();
  try {
    const query = encodeURIComponent(state.adminUserSearch.trim());
    state.adminUsers = await api(`admin/users?page=${state.adminUsers.page}&page_size=${state.adminUsers.page_size}&query=${query}`);
  } finally {
    state.adminLoading = false;
    render();
  }
}

async function loadAdminStats(options = {}) {
  if (!isAdmin()) return;
  state.adminLoading = true;
  if (options.renderFirst) render();
  try {
    state.adminStats = await api("admin/stats");
  } finally {
    state.adminLoading = false;
    render();
  }
}

function openAdminAudit(user) {
  state.adminTab = "audit";
  state.adminAudit = {
    user,
    items: [],
    page: 1,
    page_size: state.adminAudit.page_size || 20,
    total: 0,
  };
  loadAdminAudit({ renderFirst: true }).catch((error) => notify(error.message, "error"));
}

function closeAdminAudit() {
  state.adminTab = "users";
  state.adminAudit = { ...state.adminAudit, user: null, items: [], page: 1, total: 0 };
  render();
}

async function loadAdminAudit(options = {}) {
  if (!isAdmin() || !state.adminAudit.user) return;
  state.adminAuditLoading = true;
  if (options.renderFirst) render();
  try {
    const telegramUserId = state.adminAudit.user.telegram_user_id;
    const page = await api(
      `admin/users/${telegramUserId}/audit?page=${state.adminAudit.page}&page_size=${state.adminAudit.page_size}`,
    );
    state.adminAudit = { ...state.adminAudit, ...page };
  } finally {
    state.adminAuditLoading = false;
    render();
  }
}

async function loadAdminDashboard(options = {}) {
  if (state.adminTab === "audit") {
    await loadAdminAudit(options);
    return;
  }
  if (state.adminTab === "stats") {
    await loadAdminStats(options);
    return;
  }
  await loadAdminUsers(options);
}

async function updateAdminUser(telegramUserId, patch) {
  const updated = await api(`admin/users/${telegramUserId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
  state.adminUsers.items = state.adminUsers.items.map((user) =>
    user.telegram_user_id === updated.telegram_user_id ? updated : user,
  );
  notify(t("notice.adminUpdated"));
  render();
}

async function syncGroups(options = {}) {
  const session = activeSessions()[0];
  if (!session) {
    notify(t("notice.connectAccount"), "error");
    return;
  }
  if (isAutopostPaused()) {
    notify(t("notice.autopostPaused"), "error");
    return;
  }
  if (!options.silent) clearNotice();
  try {
    const result = await api(`sessions/${session.id}/sync-chats`, { method: "POST" });
    if (!options.silent) notify(t("notice.groupsSynced", { count: result.total_dialogs }));
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
    notify(t("notice.postResumed"));
    render();
    return;
  }

  const updated = await api(`posts/${post.id}/pause`, { method: "PATCH" });
  state.posts = state.posts.map((item) => (item.id === updated.id ? updated : item));
  notify(t("notice.postPaused"));
  render();
}

document.querySelector("#refresh").addEventListener("click", () => {
  clearNotice();
  load({ autoSyncGroups: true }).catch((error) => notify(error.message, "error"));
});

document.querySelector("#draft-help-button").addEventListener("click", (event) => {
  event.stopPropagation();
  const tooltip = document.querySelector("#draft-help-tooltip");
  setDraftHelpVisible(Boolean(tooltip?.hidden));
});

document.addEventListener("click", (event) => {
  const tooltip = document.querySelector("#draft-help-tooltip");
  if (tooltip?.hidden) return;
  const target = event.target instanceof Element ? event.target : event.target.parentElement;
  if (target?.closest("#draft-help-tooltip") || target?.closest("#draft-help-button")) {
    return;
  }
  setDraftHelpVisible(false);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    setDraftHelpVisible(false);
    closeAuditMessage();
  }
});

document.querySelectorAll("[data-tab]").forEach((button) => {
  button.addEventListener("click", () => {
    if (button.dataset.tab === "admin" && !isAdmin()) return;
    state.activeTab = button.dataset.tab;
    if (state.activeTab === "audit") {
      loadAudit({ renderFirst: true }).catch((error) => notify(error.message, "error"));
      return;
    }
    if (state.activeTab === "admin") {
      loadAdminDashboard({ renderFirst: true }).catch((error) => notify(error.message, "error"));
      return;
    }
    render();
  });
});

document.querySelectorAll(".admin-tab-button").forEach((button) => {
  button.addEventListener("click", () => {
    state.adminTab = button.dataset.adminTab;
    loadAdminDashboard({ renderFirst: true }).catch((error) => notify(error.message, "error"));
  });
});

document.querySelector("#admin-audit-back").addEventListener("click", closeAdminAudit);

document.querySelector("#language-select").addEventListener("change", (event) => {
  setLanguage(event.target.value);
});

async function setGlobalPause(paused) {
  clearNotice();
  const endpoint = paused ? "account/pause" : "account/resume";
  const buttons = [document.querySelector("#account-pause"), document.querySelector("#settings-pause")].filter(Boolean);
  buttons.forEach((button) => setBusy(button, true, paused ? t("busy.pause") : t("busy.resume")));
  try {
    await api(endpoint, { method: "POST" });
    notify(paused ? t("notice.globalPaused") : t("notice.globalResumed"));
    await load();
  } catch (error) {
    notify(error.message, "error");
  } finally {
    render();
  }
}

document.querySelector("#account-pause").addEventListener("click", () => {
  setGlobalPause(!isAutopostPaused()).catch((error) => notify(error.message, "error"));
});

document.querySelector("#settings-pause").addEventListener("click", () => {
  setGlobalPause(!isAutopostPaused()).catch((error) => notify(error.message, "error"));
});

document.querySelector("#revoke-session").addEventListener("click", async () => {
  clearNotice();
  const confirmed = window.confirm(t("login.disconnectConfirm"));
  if (!confirmed) return;
  const button = document.querySelector("#revoke-session");
  setBusy(button, true, t("login.disconnecting"));
  try {
    const result = await api("account/revoke-session", { method: "POST" });
    state.selectedDraftId = null;
    state.selectedFolderId = "all";
    state.selectedChatIds.clear();
    state.groupsSyncedOnInit = false;
    const suffix = result.telegram_logout_errors?.length
      ? t("notice.sessionDisconnectSuffix")
      : "";
    notify(t("notice.sessionDisconnected", { suffix }));
    await load();
  } catch (error) {
    notify(error.message, "error");
  } finally {
    setBusy(button, false, t("settings.revokeButton"));
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

document.querySelector("#admin-user-search").addEventListener("input", (event) => {
  state.adminUserSearch = event.target.value;
  state.adminUsers.page = 1;
  loadAdminUsers({ renderFirst: true }).catch((error) => notify(error.message, "error"));
});

document.querySelector("#edit-groups-prev").addEventListener("click", () => {
  state.editGroupPage -= 1;
  renderEditGroupPicker();
});

document.querySelector("#edit-groups-next").addEventListener("click", () => {
  state.editGroupPage += 1;
  renderEditGroupPicker();
});

document.querySelector("#admin-users-prev").addEventListener("click", () => {
  state.adminUsers.page -= 1;
  loadAdminUsers({ renderFirst: true }).catch((error) => notify(error.message, "error"));
});

document.querySelector("#admin-users-next").addEventListener("click", () => {
  state.adminUsers.page += 1;
  loadAdminUsers({ renderFirst: true }).catch((error) => notify(error.message, "error"));
});

document.querySelector("#admin-audit-prev").addEventListener("click", () => {
  state.adminAudit.page -= 1;
  loadAdminAudit({ renderFirst: true }).catch((error) => notify(error.message, "error"));
});

document.querySelector("#admin-audit-next").addEventListener("click", () => {
  state.adminAudit.page += 1;
  loadAdminAudit({ renderFirst: true }).catch((error) => notify(error.message, "error"));
});

document.querySelector("#edit-close").addEventListener("click", closeEditPost);

document.querySelector("#audit-message-close").addEventListener("click", closeAuditMessage);

document.querySelector("#audit-message-modal").addEventListener("click", (event) => {
  if (event.target.id === "audit-message-modal") {
    closeAuditMessage();
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

document.querySelector("input[name=phone_local]").addEventListener("input", (event) => {
  normalizePhoneInput(event.currentTarget);
});

document.querySelector("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearNotice();
  const form = new FormData(event.currentTarget);
  const phone = loginPhoneFromForm(form);
  if (!phone) {
    notify(t("validation.phoneRequired"), "error");
    return;
  }
  if (!isValidPhone(phone)) {
    notify(t("validation.phoneInvalid"), "error");
    return;
  }
  const button = document.querySelector("#send-code");
  setBusy(button, true, t("login.sending"));

  try {
    const result = await api("account/start-login", {
      method: "POST",
      body: JSON.stringify({
        phone,
      }),
    });
    state.pendingSessionId = result.session_id;
    state.pendingPhone = phone;
    document.querySelector("#login-form").hidden = true;
    document.querySelector("#code-form").hidden = false;
    updateSmsButtonFromLoginResult(result);
    notify(result.message || t("notice.codeSent"));
  } catch (error) {
    notify(error.message, "error");
  } finally {
    setBusy(button, false, t("login.getCode"));
  }
});

document.querySelector("#resend-sms-code").addEventListener("click", async (event) => {
  clearNotice();
  const button = event.currentTarget;
  const phone = state.pendingPhone || loginPhoneFromForm(new FormData(document.querySelector("#login-form")));
  if (!phone) {
    notify(t("validation.phoneRequired"), "error");
    return;
  }
  if (!isValidPhone(phone)) {
    notify(t("validation.phoneInvalid"), "error");
    return;
  }
  setBusy(button, true, t("login.sending"));
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
    updateSmsButtonFromLoginResult(result);
    notify(result.message || t("notice.smsRequested"));
  } catch (error) {
    notify(error.message, "error");
  } finally {
    if (shouldStartCooldown) {
      startSmsCooldown(90);
    } else {
      setBusy(button, false, t("connect.sendSms"));
    }
  }
});

document.querySelector("#code-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearNotice();
  const form = new FormData(event.currentTarget);
  const button = event.currentTarget.querySelector("button");
  setBusy(button, true, t("login.checking"));

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
      notify(t("notice.passwordNeeded"));
      return;
    }

    notify(t("notice.accountConnected"));
    await load();
    state.groupsSyncedOnInit = true;
    await syncGroups();
  } catch (error) {
    notify(error.message, "error");
  } finally {
    setBusy(button, false, t("login.connect"));
  }
});

document.querySelector("#password-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearNotice();
  const form = new FormData(event.currentTarget);
  const button = event.currentTarget.querySelector("button");
  setBusy(button, true, t("login.checking"));

  try {
    await api("account/confirm-password", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.pendingSessionId,
        password: form.get("password"),
      }),
    });
    notify(t("notice.accountConnected"));
    await load();
    state.groupsSyncedOnInit = true;
    await syncGroups();
  } catch (error) {
    notify(error.message, "error");
  } finally {
    setBusy(button, false, t("login.finish"));
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
    notify(t("validation.postMissing"), "error");
    return;
  }
  if (!sessionId) {
    notify(t("notice.connectAccount"), "error");
    return;
  }
  if (checkedGroups.length === 0) {
    notify(t("validation.chooseGroup"), "error");
    return;
  }
  if (isPastOrNow(new Date(nextRun).toISOString())) {
    notify(t("validation.futureDate"), "error");
    return;
  }
  if (scheduleKind === "interval") {
    const confirmed = await confirmSpamRiskIfNeeded(intervalMinutes);
    if (!confirmed) return;
  }
  if (scheduleNeedsWeekdays(scheduleKind) && scheduleWeekdays.length === 0) {
    notify(t("validation.chooseWeekday"), "error");
    return;
  }

  const button = document.querySelector("#edit-save");
  setBusy(button, true, t("busy.save"));

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
    notify(t("notice.postUpdated"));
    await load();
  } catch (error) {
    notify(error.message, "error");
  } finally {
    setBusy(button, false, t("busy.saveChanges"));
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
    notify(t("notice.connectAccount"), "error");
    return;
  }
  if (!draftId) {
    notify(t("validation.chooseDraft"), "error");
    return;
  }
  if (checkedGroups.length === 0) {
    notify(t("validation.chooseGroup"), "error");
    return;
  }
  if (isPastOrNow(new Date(nextRun).toISOString())) {
    notify(t("validation.futureDate"), "error");
    return;
  }

  const intervalMinutes = scheduleKind === "interval" ? Number(form.get("interval_minutes")) : null;

  if (scheduleKind === "interval") {
    const confirmed = await confirmSpamRiskIfNeeded(intervalMinutes);
    if (!confirmed) return;
  }
  if (scheduleNeedsWeekdays(scheduleKind) && scheduleWeekdays.length === 0) {
    notify(t("validation.chooseWeekday"), "error");
    return;
  }

  const button = document.querySelector("#save-post");
  setBusy(button, true, t("busy.save"));

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
    notify(t("notice.postScheduled"));
    await load();
  } catch (error) {
    notify(error.message, "error");
  } finally {
    setBusy(button, false, t("composer.schedule"));
  }
});

load({ autoSyncGroups: true }).catch((error) => notify(error.message, "error"));
