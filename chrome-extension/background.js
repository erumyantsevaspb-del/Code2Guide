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
    captureTab(msg.tabId, msg.url).then(result => sendResponse(result));
    return true; // async
  }
  if (msg.type === 'SPA_NAVIGATION') {
    if (!config.token || !config.tracking) return;
    if (msg.url === lastCapturedUrl) return;
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]) captureTab(tabs[0].id, msg.url);
    });
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
    captureTab(tabId, tab.url);
  }, 1500);
});

async function captureTab(tabId, url) {
  if (!config.token || !config.server) {
    return { success: false, error: 'Не настроен токен' };
  }

  try {
    // Делаем скриншот активной вкладки
    const dataUrl = await chrome.tabs.captureVisibleTab(null, { format: 'png' });

    // Конвертируем dataUrl в Blob
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
      // Увеличиваем счётчик
      const { count } = await chrome.storage.local.get('count');
      await chrome.storage.local.set({ count: (count || 0) + 1 });
      return { success: true };
    } else {
      const text = await res.text();
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
