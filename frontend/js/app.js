/**
 * Main application — routing, navigation, initialization.
 */
import UI from './ui.js';
import API from './api.js';
import { t, getLocale, setLocale, onLocaleChange } from './i18n.js';
import LandingPage from './pages/landing.js';
import TournamentsPage from './pages/tournaments.js';
import TournamentDetailPage from './pages/tournament-detail.js';
import TournamentWizardPage from './pages/tournament-wizard.js';
import LeaguesPage from './pages/leagues.js';
import PlayersPage from './pages/players.js';
import LivePage from './pages/live.js';
import RegisterPage from './pages/register.js';
import LoginPage from './pages/login.js';

const PAGES = {
  'landing': LandingPage,
  'tournaments': TournamentsPage,
  'tournament-detail': TournamentDetailPage,
  'tournament-wizard': TournamentWizardPage,
  'leagues': LeaguesPage,
  'players': PlayersPage,
  'live': LivePage,
  'register': RegisterPage,
  'login': LoginPage,
};

let _currentPage = null;
let _currentPageName = null;
let _currentParam = null;

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

function updateNavLabels() {
  const map = {
    tournaments: 'nav.tournaments',
    leagues: 'nav.leagues',
    players: 'nav.players',
    live: 'nav.live',
  };
  for (const [page, key] of Object.entries(map)) {
    const el = document.querySelector(`.nav-link[data-page="${page}"]`);
    if (el) el.textContent = t(key);
  }
  const acct = document.getElementById('nav-account');
  if (acct) acct.textContent = t('nav.account');
  const ib = document.getElementById('install-banner');
  if (ib) {
    const span = ib.querySelector('span');
    const btn = document.getElementById('install-btn');
    if (span) span.textContent = t('pwa.install_app');
    if (btn) btn.textContent = t('pwa.install_btn');
  }
  const langBtn = document.getElementById('lang-toggle');
  if (langBtn) langBtn.textContent = getLocale() === 'cs' ? '🇨🇿' : '🇬🇧';
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
  _currentPageName = pageName;
  _currentParam = param;
  updateAuthUI();
  updateNavLabels();

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
  // Hide the initial loading indicator
  const pageLoading = document.getElementById('page-loading');
  if (pageLoading) pageLoading.style.display = 'none';

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

  // Language toggle — flips between en and cs, re-renders current page.
  const langBtn = document.getElementById('lang-toggle');
  if (langBtn) {
    langBtn.addEventListener('click', () => {
      setLocale(getLocale() === 'cs' ? 'en' : 'cs');
    });
  }
  onLocaleChange(() => {
    updateNavLabels();
    if (_currentPageName) navigate(_currentPageName, _currentParam);
  });
  updateNavLabels();

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

  // PWA install prompt — respect user's dismissal
  let deferredPrompt = null;
  const installDismissed = localStorage.getItem('install-dismissed');
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    if (!installDismissed) {
      document.getElementById('install-banner').classList.remove('hidden');
    }
  });
  document.getElementById('install-btn')?.addEventListener('click', () => {
    if (deferredPrompt) { deferredPrompt.prompt(); deferredPrompt = null; }
    document.getElementById('install-banner').classList.add('hidden');
  });
  document.getElementById('install-dismiss')?.addEventListener('click', () => {
    document.getElementById('install-banner').classList.add('hidden');
    localStorage.setItem('install-dismissed', '1');
  });

  // Register service worker
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' }).catch(() => {});
  }

  // Initial navigation
  handleHash();
}

// Make App globally accessible for pages that call App.navigate()
const App = { navigate };
window.App = App;

// Boot — ES modules are deferred, so DOMContentLoaded may have already fired
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
