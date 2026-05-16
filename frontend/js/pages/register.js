/**
 * Public self-registration page — linked from QR code.
 * URL: #register/{tournament_id}
 * No login required.
 */
import UI from '../ui.js';
import API from '../api.js';
import { html } from 'lit-html';
import { t } from '../i18n.js';

// --- Templates ---

function tournamentHeader(tour) {
  return html`
    <div class="card" style="text-align: center">
      <h2>${tour.name || t('tournament.title')}</h2>
      <div class="meta">📅 ${tour.date}  📍 ${tour.location || ''}</div>
      <div style="margin-top: 8px">
        <span class="badge badge-${tour.status}">${t(`status.${tour.status}`)}</span>
        <span class="meta" style="margin-left: 8px">${t('tournament.players_count', { count: tour.player_count })}</span>
      </div>
    </div>
  `;
}

function closedTemplate(tour) {
  return html`${tournamentHeader(tour)}<div class="card"><p style="color: #c0392b">${t('register.closed')}</p></div>`;
}

function noTokenTemplate(tour) {
  return html`${tournamentHeader(tour)}<div class="card"><p style="color: #c0392b">${t('register.no_token')}</p></div>`;
}

function successTemplate(tour, nickname) {
  return html`
    ${tournamentHeader(tour)}
    <div class="card" style="text-align: center">
      <p style="font-size: 1.3rem; margin: 16px 0">✅ <strong>${nickname}</strong>${t('register.success_suffix')}</p>
      <p>${t('register.confirm_msg')}</p>
      <p style="margin-top: 16px">
        <a href="#live/${tour.uuid}" class="btn btn-primary">${t('register.watch_live')}</a>
      </p>
      <p style="margin-top: 8px">
        <a href="#login" class="btn btn-secondary">${t('register.log_in_to_follow')}</a>
      </p>
    </div>
  `;
}

function registrationTemplate(tour, onSubmit) {
  const onEnter = (e) => { if (e.key === 'Enter') { e.preventDefault(); onSubmit(); } };
  return html`
    ${tournamentHeader(tour)}
    <div class="card">
      <h3>${t('register.sign_up')}</h3>
      <div class="form-group">
        <label>${t('player.nickname_required')}</label>
        <input id="reg-nickname" type="text" placeholder=${t('auth.nickname_placeholder')} @keydown=${onEnter}>
      </div>
      <div class="form-group">
        <label>${t('player.first_name')}</label>
        <input id="reg-first" type="text" @keydown=${onEnter}>
      </div>
      <div class="form-group">
        <label>${t('player.last_name')}</label>
        <input id="reg-last" type="text" @keydown=${onEnter}>
      </div>
      <button class="btn btn-primary" @click=${onSubmit}>${t('register.play_btn')}</button>
      <div style="margin-top: 16px; text-align: center; font-size: 0.9rem">
        <a href="#login" style="color: #3498db">${t('register.have_account')}</a>
      </div>
    </div>
    ${tour.players && tour.players.length ? html`
      <div class="card">
        <h3>${t('register.already_registered')}</h3>
        <table class="data-table">
          <thead><tr><th>#</th><th>${t('live.standings_th_player')}</th></tr></thead>
          <tbody>
            ${tour.players.map((p, i) => html`<tr><td>${i + 1}</td><td>${p.nickname || t('common.em_dash')}</td></tr>`)}
          </tbody>
        </table>
      </div>
    ` : ''}
  `;
}

// --- Logic ---

let _tournamentId = null;
let _token = null;

async function doRegister() {
  const nickname = document.getElementById('reg-nickname')?.value?.trim();
  if (!nickname) { UI.toast(t('player.nickname_required_msg'), 'error'); return; }

  try {
    const res = await fetch(`/api/v1/public/tournaments/${_tournamentId}/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        nickname,
        first_name: document.getElementById('reg-first')?.value?.trim() || null,
        last_name: document.getElementById('reg-last')?.value?.trim() || null,
        token: _token,
      }),
    });
    const data = await res.json();
    if (!res.ok) { UI.toast(data.detail || t('register.failed'), 'error'); return; }
    // Show success page instead of re-rendering (re-render would lose token and show QR prompt)
    try {
      const tour = await API.publicTournament(_tournamentId);
      UI.renderPage(successTemplate(tour, nickname));
    } catch (_) {
      UI.toast(data.message || t('register.success_default'), 'success');
    }
  } catch (e) {
    UI.toast(e.message, 'error');
  }
}

const RegisterPage = {
  async render(rawId) {
    // rawId may contain query params: "UUID?token=XYZ"
    const [id, qs] = (rawId || '').split('?');
    _tournamentId = id;
    const params = new URLSearchParams(qs || '');
    _token = params.get('token') || '';
    UI.title(t('register.title'));
    UI.loading();

    try {
      const tour = await API.publicTournament(id);

      if (!tour.is_registration_open && tour.status !== 'registration') {
        UI.renderPage(closedTemplate(tour));
        return;
      }
      if (!_token) {
        UI.renderPage(noTokenTemplate(tour));
        return;
      }
      UI.renderPage(registrationTemplate(tour, doRegister));
      document.getElementById('reg-nickname')?.focus();
    } catch (e) {
      UI.error(e.message);
    }
  },
};

export default RegisterPage;