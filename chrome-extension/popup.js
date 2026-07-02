document.addEventListener('DOMContentLoaded', async () => {
  const tokenInput = document.getElementById('tokenInput');
  const serverInput = document.getElementById('serverInput');
  const saveBtn = document.getElementById('saveBtn');
  const statusMsg = document.getElementById('statusMsg');
  const setupView = document.getElementById('setupView');
  const activeView = document.getElementById('activeView');
  const statusDot = document.getElementById('statusDot');
  const countEl = document.getElementById('countEl');
  const trackingToggle = document.getElementById('trackingToggle');
  const screenshotNow = document.getElementById('screenshotNow');
  const disconnectBtn = document.getElementById('disconnectBtn');
  const activeStatus = document.getElementById('activeStatus');

  const { token, server, count, tracking } = await chrome.storage.local.get(['token', 'server', 'count', 'tracking']);

  if (token) {
    showActive(count || 0, tracking !== false);
  }

  if (server) serverInput.value = server;

  saveBtn.addEventListener('click', async () => {
    const t = tokenInput.value.trim();
    const s = serverInput.value.trim().replace(/\/$/, '');
    if (!t) { showStatus(statusMsg, 'Введите токен', 'error'); return; }
    if (!s) { showStatus(statusMsg, 'Введите URL сервера', 'error'); return; }

    saveBtn.textContent = 'Проверяем...';
    saveBtn.disabled = true;

    try {
      const fd = new FormData();
      fd.append('token', t);
      fd.append('url', window.location.href || 'ping');
      const res = await fetch(`${s}/api/extension/ping/`, { method: 'POST', body: fd });
      // 403 = сервер есть но токен неверный, 404 = нет endpoint (старая версия)
      if (res.status === 403) {
        showStatus(statusMsg, 'Неверный токен', 'error');
        saveBtn.textContent = 'Подключить'; saveBtn.disabled = false;
        return;
      }
    } catch (e) {
      // Сервер недоступен — сохраняем всё равно, покажем ошибку при отправке
    }

    await chrome.storage.local.set({ token: t, server: s, count: 0, tracking: true });
    chrome.runtime.sendMessage({ type: 'SET_CONFIG', token: t, server: s });
    showActive(0, true);
  });

  trackingToggle.addEventListener('change', async () => {
    const on = trackingToggle.checked;
    await chrome.storage.local.set({ tracking: on });
    chrome.runtime.sendMessage({ type: 'SET_TRACKING', enabled: on });
  });

  screenshotNow.addEventListener('click', async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    chrome.runtime.sendMessage({ type: 'CAPTURE_NOW', tabId: tab.id, url: tab.url }, (resp) => {
      if (resp && resp.success) {
        showStatus(activeStatus, 'Скриншот отправлен', 'success');
        updateCount();
      } else {
        showStatus(activeStatus, resp?.error || 'Ошибка', 'error');
      }
    });
  });

  disconnectBtn.addEventListener('click', async () => {
    await chrome.storage.local.clear();
    chrome.runtime.sendMessage({ type: 'SET_CONFIG', token: null, server: null });
    setupView.style.display = 'block';
    activeView.style.display = 'none';
    statusDot.classList.add('inactive');
  });

  async function updateCount() {
    const { count } = await chrome.storage.local.get('count');
    countEl.textContent = count || 0;
  }

  function showActive(cnt, isTracking) {
    setupView.style.display = 'none';
    activeView.style.display = 'block';
    statusDot.classList.remove('inactive');
    countEl.textContent = cnt;
    trackingToggle.checked = isTracking;
  }

  function showStatus(el, msg, type) {
    el.textContent = msg;
    el.className = `status ${type}`;
  }
});
