/**
 * Tournaments list page (authenticated only).
 */
import UI from '../ui.js';
import API from '../api.js';
import { html } from 'lit-html';
import { t } from '../i18n.js';

// --- Templates ---

function tournamentListTemplate(items, onCreateClick) {
  return html`
    <div>
      <button class="btn btn-primary" @click=${onCreateClick}>${t('tournament.new_btn')}</button>
      ${!items.length ? html`<p class="loading">${t('tournament.none_yet')}</p>` : ''}
      ${items.map((tn) => html`
        <div class="card" @click=${() => App.navigate(API.isLoggedIn() ? 'tournament-wizard' : 'tournament-detail', tn.uuid)} style="cursor: pointer">
          <h3>${tn.name || t('tournament.unnamed')}</h3>
          <div class="meta">📅 ${tn.date}  📍 ${tn.location || t('common.em_dash')}</div>
          <div style="margin-top: 6px">
            <span class="badge badge-${tn.status || 'preparing'}">${t(`status.${tn.status || 'preparing'}`)}</span>
            <span class="meta" style="margin-left: 8px">${t('tournament.players_count', { count: (tn.registrations || []).length })}</span>
          </div>
        </div>
      `)}
    </div>
  `;
}

function createFormTemplate(leagues, onSubmit) {
  const today = new Date().toISOString().slice(0, 10);
  const onEnter = (e) => { if (e.key === 'Enter') { e.preventDefault(); onSubmit(); } };

  return html`
    <div class="card">
      <h3>${t('tournament.new')}</h3>
      <div class="form-group">
        <label for="new-t-name">${t('common.name')}</label>
        <input id="new-t-name" type="text" placeholder=${t('tournament.name_placeholder')} @keydown=${onEnter}>
      </div>
      <div class="form-group">
        <label for="new-t-date">${t('common.date')}</label>
        <input id="new-t-date" type="date" .value=${today} @keydown=${onEnter}>
      </div>
      <div class="form-group">
        <label for="new-t-location">${t('common.location')}</label>
        <input id="new-t-location" type="text" placeholder=${t('tournament.location_placeholder')} @keydown=${onEnter}>
      </div>
      <div class="form-group">
        <label for="new-t-mode">${t('tournament.player_mode')}</label>
        <select id="new-t-mode">
          <option value="singles">${t('tournament.singles')}</option>
          <option value="doubles">${t('tournament.doubles')}</option>
        </select>
      </div>
      <div class="form-group">
        <label for="new-t-league">${t('tournament.league_optional')}</label>
        <select id="new-t-league">
          <option value="">${t('common.no_league')}</option>
          ${leagues.map((l) => html`<option value=${l.uuid}>${l.name}</option>`)}
        </select>
      </div>
      <div style="margin-top: 12px">
        <button class="btn btn-primary" @click=${onSubmit}>${t('common.create')}</button>
      </div>
    </div>
  `;
}

// --- Logic ---

let _showForm = false;

async function doCreate() {
  try {
    const leagueId = document.getElementById('new-t-league')?.value || undefined;
    const data = {
      name: document.getElementById('new-t-name').value,
      date: document.getElementById('new-t-date').value || new Date().toISOString().slice(0, 10),
      location: document.getElementById('new-t-location').value,
      player_mode: document.getElementById('new-t-mode').value,
      league_id: leagueId || undefined,
    };
    const tn = await API.createTournament(data);
    UI.toast(t('tournament.created'), 'success');
    _showForm = false;
    App.navigate(API.isLoggedIn() ? 'tournament-wizard' : 'tournament-detail', tn.uuid);
  } catch (e) {
    UI.toast(e.message, 'error');
  }
}

const TournamentsPage = {
  async render() {
    UI.title(t('nav.tournaments'));
    UI.loading();
    try {
      const items = await API.tournaments();
      let allLeagues = [];
      try { allLeagues = await API.leagues(); } catch (_) {}

      const renderList = () => {
        const listTpl = tournamentListTemplate(items, () => {
          _showForm = !_showForm;
          renderList();
        });

        if (_showForm) {
          const formTpl = createFormTemplate(allLeagues, doCreate);
          UI.renderPage(html`<div>${listTpl}${formTpl}</div>`);
        } else {
          UI.renderPage(listTpl);
        }
      };

      renderList();
    } catch (e) {
      UI.error(e.message);
    }
  },
};

export default TournamentsPage;