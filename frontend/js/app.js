/**
 * Main application — routing, navigation, initialization.
 */
const App = (() => {
  const PAGES = {
    'landing': LandingPage,
    'tournaments': TournamentsPage,
    'tournament-detail': TournamentDetailPage,
    'leagues': LeaguesPage,
    'players': PlayersPage,
    'live': LivePage,
    'register': RegisterPage,
    'login': LoginPage,
  };

  let _currentPage = null;

  function updateAuthUI() {
    const loggedIn = API.isLoggedIn();
    const sidebar = document.getElementById('sidebar');
    const menuBtn = document.getElementById('menu-toggle');

    // Sidebar: only visible for logged-in users
    if (loggedIn) {
      sidebar.classList.remove('hidden');
    } else {
      sidebar.classList.add('hidden');
      sidebar.classList.remove('open');
    }
    menuBtn.style.display = loggedIn ? '' : 'none';
  }

  function navigate(pageName, param = null) {
    // Cleanup previous page
    if (_currentPage && _currentPage.cleanup) _currentPage.cleanup();

    // Guests can only see landing, login, and live pages
    if (!API.isLoggedIn() && !['landing', 'login', 'live', 'register'].includes(pageName)) {
      pageName = 'landing';
    }

    const page = PAGES[pageName];
    if (!page) { UI.error(`Page "${pageName}" not found`); return; }

    _currentPage = page;
    updateAuthUI();

    // Update nav links
    document.querySelectorAll('.nav-link').forEach((el) => {
      el.classList.toggle('active', el.dataset.page === pageName);
    });

    // Close mobile sidebar
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('overlay').classList.add('hidden');

    // Update URL hash — landing gets clean URL (no hash)
    if (pageName === 'landing') {
      history.replaceState(null, '', '/');
    } else {
      window.location.hash = param ? `${pageName}/${param}` : pageName;
    }

    // Render page
    if (param) page.render(param);
    else page.render();
  }

  function init() {
    // Sidebar toggle
    document.getElementById('menu-toggle').addEventListener('click', () => {
      const sidebar = document.getElementById('sidebar');
      const overlay = document.getElementById('overlay');
      sidebar.classList.toggle('open');
      sidebar.classList.remove('hidden');
      overlay.classList.toggle('hidden');
    });

    document.getElementById('overlay').addEventListener('click', () => {
      document.getElementById('sidebar').classList.remove('open');
      document.getElementById('overlay').classList.add('hidden');
    });

    // Nav links
    document.querySelectorAll('.nav-link').forEach((el) => {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        navigate(el.dataset.page);
      });
    });

    // Handle URL hash
    function handleHash() {
      const hash = window.location.hash.slice(1);
      const defaultPage = API.isLoggedIn() ? 'tournaments' : 'landing';
      if (!hash) { navigate(defaultPage); return; }
      const [page, param] = hash.split('/');
      if (PAGES[page]) navigate(page, param);
      else navigate(defaultPage);
    }

    window.addEventListener('hashchange', handleHash);

    // Update user info in header
    if (API.isLoggedIn()) {
      API.me().then((user) => {
        document.getElementById('user-info').textContent = user.email;
      }).catch(() => {});
    }

    // PWA install prompt
    let deferredPrompt = null;
    window.addEventListener('beforeinstallprompt', (e) => {
      e.preventDefault();
      deferredPrompt = e;
      document.getElementById('install-banner').classList.remove('hidden');
    });
    document.getElementById('install-btn')?.addEventListener('click', () => {
      if (deferredPrompt) { deferredPrompt.prompt(); deferredPrompt = null; }
      document.getElementById('install-banner').classList.add('hidden');
    });
    document.getElementById('install-dismiss')?.addEventListener('click', () => {
      document.getElementById('install-banner').classList.add('hidden');
    });

    // Register service worker
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => {});
    }

    // Initial navigation
    handleHash();
  }

  // Boot
  document.addEventListener('DOMContentLoaded', init);

  return { navigate };
})();
