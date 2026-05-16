/**
 * Login & Registration page.
 */
import UI from '../ui.js';
import API from '../api.js';
import { html } from 'lit-html';
import { t } from '../i18n.js';

// --- Templates ---

function loginTemplate(onSubmit, onSwitchToRegister) {
  const onEnter = (e) => { if (e.key === 'Enter') { e.preventDefault(); onSubmit(); } };
  return html`
    <div class="card">
      <h3>${t('auth.sign_in')}</h3>
      <div class="form-group">
        <label for="login-email">${t('auth.email')}</label>
        <input id="login-email" type="email" placeholder=${t('auth.email_placeholder')} @keydown=${onEnter}>
      </div>
      <div class="form-group">
        <label for="login-pass">${t('auth.password')}</label>
        <input id="login-pass" type="password" @keydown=${onEnter}>
      </div>
      <button class="btn btn-primary" @click=${onSubmit}>${t('auth.login')}</button>
      <p style="margin-top: 16px; font-size: 0.9rem">
        ${t('auth.no_account')}
        <a href="#" style="color: #0f3460; font-weight: 600" @click=${onSwitchToRegister}>${t('auth.register_here')}</a>
      </p>
    </div>
  `;
}

function registerTemplate(onSubmit, onSwitchToLogin) {
  const onEnter = (e) => { if (e.key === 'Enter') { e.preventDefault(); onSubmit(); } };
  return html`
    <div class="card">
      <h3>${t('auth.create_account')}</h3>
      <div class="form-group">
        <label for="reg-email">${t('auth.email')}</label>
        <input id="reg-email" type="email" placeholder=${t('auth.email_placeholder')} @keydown=${onEnter}>
      </div>
      <div class="form-group">
        <label for="reg-pass">${t('auth.password_min')}</label>
        <input id="reg-pass" type="password" @keydown=${onEnter}>
      </div>
      <div class="form-group">
        <label for="reg-pass2">${t('auth.password_confirm')}</label>
        <input id="reg-pass2" type="password" @keydown=${onEnter}>
      </div>
      <div class="form-group">
        <label for="reg-nickname">${t('auth.nickname_player')}</label>
        <input id="reg-nickname" type="text" placeholder=${t('auth.nickname_placeholder')} @keydown=${onEnter}>
      </div>
      <button class="btn btn-primary" @click=${onSubmit}>${t('auth.register')}</button>
      <p style="margin-top: 16px; font-size: 0.9rem">
        ${t('auth.have_account')}
        <a href="#" style="color: #0f3460; font-weight: 600" @click=${onSwitchToLogin}>${t('auth.sign_in_link')}</a>
      </p>
    </div>
  `;
}

function loggedInTemplate(user, onLogout) {
  return html`
    <div class="card">
      <h3>${t('auth.hello', { email: user.email })}</h3>
      <p class="meta">${user.is_superuser ? t('auth.administrator') : t('auth.user')}</p>
      <button class="btn btn-secondary" style="margin-top: 12px" @click=${onLogout}>${t('auth.logout')}</button>
    </div>
  `;
}

// --- Logic ---

let _mode = 'login';

async function doLogin() {
  const email = document.getElementById('login-email').value;
  const pass = document.getElementById('login-pass').value;
  if (!email || !pass) { UI.toast(t('auth.fill_all_fields'), 'error'); return; }
  try {
    await API.login(email, pass);
    UI.toast(t('auth.logged_in'), 'success');
    App.navigate('tournaments');
  } catch (e) {
    UI.toast(t('auth.login_failed', { msg: e.message }), 'error');
  }
}

async function doRegister() {
  const email = document.getElementById('reg-email').value;
  const pass = document.getElementById('reg-pass').value;
  const pass2 = document.getElementById('reg-pass2').value;
  const nickname = document.getElementById('reg-nickname').value;

  if (!email || !pass) { UI.toast(t('auth.fill_email_pass'), 'error'); return; }
  if (pass.length < 8) { UI.toast(t('auth.pass_too_short'), 'error'); return; }
  if (pass !== pass2) { UI.toast(t('auth.pass_mismatch'), 'error'); return; }

  try {
    await API.register(email, pass);
    UI.toast(t('auth.account_created'), 'success');
    try {
      await API.login(email, pass);
      if (nickname) {
        try { await API.post('/api/v1/players/', { nickname }); } catch (_) {}
      }
      App.navigate('tournaments');
    } catch (_) {
      UI.toast(t('auth.register_needs_verification'), 'info');
      _mode = 'login';
      LoginPage.render();
    }
  } catch (e) {
    UI.toast(t('auth.register_failed', { msg: e.message }), 'error');
  }
}

const LoginPage = {
  async render() {
    UI.title(_mode === 'login' ? t('auth.sign_in') : t('auth.register'));

    if (API.isLoggedIn()) {
      try {
        const user = await API.me();
        UI.renderPage(loggedInTemplate(user, () => {
          API.logout(); _mode = 'login'; App.navigate('login');
        }));
      } catch (e) {
        API.logout(); _mode = 'login'; this.render();
      }
      return;
    }

    const switchTo = (mode) => (e) => { e.preventDefault(); _mode = mode; this.render(); };

    if (_mode === 'register') {
      UI.renderPage(registerTemplate(doRegister, switchTo('login')));
    } else {
      UI.renderPage(loginTemplate(doLogin, switchTo('register')));
    }
  },
};

export default LoginPage;