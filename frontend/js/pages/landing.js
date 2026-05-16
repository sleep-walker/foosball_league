/**
 * Landing page — shown to unauthenticated visitors.
 */
import UI from '../ui.js';
import { html } from 'lit-html';
import { t } from '../i18n.js';

function landingTemplate() {
  return html`
    <div class="card" style="text-align: center; padding: 32px">
      <h2 style="margin-bottom: 12px">${t('landing.welcome')}</h2>
      <p style="color: #666; margin-bottom: 20px">${t('landing.tagline')}</p>
      <div style="display: flex; gap: 12px; justify-content: center; flex-wrap: wrap">
        <button class="btn btn-primary" @click=${() => App.navigate('login')}>
          ${t('landing.sign_in_register')}
        </button>
        <button class="btn btn-secondary" @click=${() => App.navigate('live')}>
          ${t('landing.live_view')}
        </button>
      </div>
    </div>
    <div class="card">
      <h3>${t('landing.what_is_title')}</h3>
      <ul style="margin: 8px 0 0 20px; line-height: 1.8">
        <li>${t('landing.feat_tournaments')}</li>
        <li>${t('landing.feat_live')}</li>
        <li>${t('landing.feat_pwa')}</li>
        <li>${t('landing.feat_public')}</li>
        <li>${t('landing.feat_export')}</li>
        <li>${t('landing.feat_pairing')}</li>
        <li>${t('landing.feat_leagues')}</li>
      </ul>
    </div>
  `;
}

const LandingPage = {
  render() {
    UI.title(t('nav.page_title'));
    UI.renderPage(landingTemplate());
  },
};

export default LandingPage;
