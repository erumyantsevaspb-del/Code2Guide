let config = { token: null, server: null, tracking: true };
let lastCapturedUrl = null;

// Загружаем конфиг при старте
chrome.storage.local.get(['token', 'server', 'tracking'], (data) => {
  config.token = data.token || null;
  config.server = data.server || null;
  config.tracking = data.tracking !== false;
});

// Слушаем сообщения от popup
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'SET_CONFIG') {
    config.token = msg.token;
    config.server = msg.server;
    lastCapturedUrl = null;
  }
  if (msg.type === 'SET_TRACKING') {
    config.tracking = msg.enabled;
  }
  if (msg.type === 'CAPTURE_NOW') {
    captureTab(msg.tabId, msg.url, { mustBeActive: false }).then(result => sendResponse(result));
    return true; // async
  }
  if (msg.type === 'SPA_NAVIGATION') {
    if (!config.token || !config.tracking) return;
    if (msg.url === lastCapturedUrl) return;
    // Снимаем только активную вкладку, отправившую сообщение
    if (sender.tab && sender.tab.id) {
      captureTab(sender.tab.id, msg.url, { mustBeActive: true });
    }
  }
});

// Следим за завершением загрузки страниц
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status !== 'complete') return;
  if (!config.token || !config.tracking) return;
  if (!tab.url || tab.url.startsWith('chrome://') || tab.url.startsWith('chrome-extension://')) return;
  if (tab.url === lastCapturedUrl) return;

  // Небольшая пауза чтобы страница успела отрендериться
  setTimeout(() => {
    captureTab(tabId, tab.url, { mustBeActive: true });
  }, 1500);
});

// captureTab снимает вкладку tabId.
// mustBeActive=true: снимает только если вкладка активна в своём окне (tab.active + URL совпадает).
// mustBeActive=false: активирует вкладку на время снимка, затем возвращает фокус.
async function captureTab(tabId, url, { mustBeActive = true } = {}) {
  if (!config.token || !config.server) {
    return { success: false, error: 'Не настроен токен' };
  }

  try {
    // Получаем актуальное состояние вкладки
    const tab = await chrome.tabs.get(tabId);

    // Проверяем, что URL вкладки совпадает с ожидаемым
    const tabUrl = tab.url || '';
    if (tabUrl !== url && tabUrl.split('?')[0] !== url.split('?')[0]) {
      return { success: false, error: 'URL вкладки изменился' };
    }

    if (mustBeActive && !tab.active) {
      // Вкладка фоновая — не снимаем во избежание подмены
      return { success: false, error: 'Вкладка не активна' };
    }

    let prevTabId = null;
    if (!tab.active) {
      // Запоминаем текущую активную вкладку, чтобы вернуть фокус
      const [activeTab] = await chrome.tabs.query({ active: true, windowId: tab.windowId });
      prevTabId = activeTab ? activeTab.id : null;
      await chrome.tabs.update(tabId, { active: true });
      // Даём время на перерисовку
      await new Promise(r => setTimeout(r, 300));
    }

    const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'png' });

    // Возвращаем фокус предыдущей вкладке
    if (prevTabId !== null) {
      await chrome.tabs.update(prevTabId, { active: true });
    }

    // Финальная проверка: URL вкладки не изменился пока делали снимок
    const tabAfter = await chrome.tabs.get(tabId);
    if (tabAfter.url !== tab.url) {
      return { success: false, error: 'URL изменился во время снимка' };
    }

    const blob = dataUrlToBlob(dataUrl);

    const fd = new FormData();
    fd.append('token', config.token);
    fd.append('url', url);
    fd.append('screenshot', blob, 'screenshot.png');

    const res = await fetch(`${config.server}/api/extension/screenshot/`, {
      method: 'POST',
      body: fd,
    });

    if (res.ok) {
      lastCapturedUrl = url;
      const { count } = await chrome.storage.local.get('count');
      await chrome.storage.local.set({ count: (count || 0) + 1 });
      return { success: true };
    } else {
      return { success: false, error: `Сервер: ${res.status}` };
    }
  } catch (e) {
    return { success: false, error: e.message };
  }
}

function dataUrlToBlob(dataUrl) {
  const [header, data] = dataUrl.split(',');
  const mime = header.match(/:(.*?);/)[1];
  const binary = atob(data);
  const arr = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) arr[i] = binary.charCodeAt(i);
  return new Blob([arr], { type: mime });
}
