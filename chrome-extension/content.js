// Уведомляет background когда SPA меняет URL без перезагрузки страницы
let lastUrl = location.href;

const observer = new MutationObserver(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    setTimeout(() => {
      chrome.runtime.sendMessage({ type: 'SPA_NAVIGATION', url: location.href });
    }, 1500);
  }
});

observer.observe(document.body, { childList: true, subtree: true });
