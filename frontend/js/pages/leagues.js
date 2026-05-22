/**
 * Leagues list page with create form.
 */
import UI from '../ui.js';
import API from '../api.js';
import { html } from 'lit-html';
import { t } from '../i18n.js';

// --- Templates ---

function leagueStandingsTemplate(rows) {
  // League standings are aggregated across the league's finished
  // tournaments using its scoring_type + scoring_config. The shape
  // comes from LeagueStandingRowOutput on the backend.
  const dash = t('common.em_dash');
  if (!rows || !rows.length) {
    return html`
      <div class="card" style="margin-top: 4px">
        <p class="meta">${t('league.standings_empty')}</p>
      </div>
    `;
  }
  return html`
    <div class="card" style="margin-top: 4px">
      <h4>${t('league.standings_title')}</h4>
      <table class="standings-table">
        <thead>
          <tr>
            <th>#</th>
            <th>${t('live.standings_th_player')}</th>
            <th>${t('league.standings_th_score')}</th>
            <th>${t('league.standings_th_tournaments')}</th>
            <th>${t('standings.th_w')}</th>
            <th>${t('standings.th_d')}</th>
            <th>${t('standings.th_l')}</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((r, i) => html`
            <tr>
              <td>${i + 1}</td>
              <td>${r.nickname || r.participant_id?.substring(0, 8) || dash}</td>
              <td><strong>${(r.score ?? 0).toFixed(1)}</strong></td>
              <td>${r.tournaments_played ?? 0}</td>
              <td>${r.wins ?? 0}</td>
              <td>${r.draws ?? 0}</td>
              <td>${r.losses ?? 0}</td>
            </tr>
          `)}
        </tbody>
      </table>
    </div>
  `;
}


function leagueDetailTemplate(leagueId, members, available, handlers) {
  const onEnter = (e) => { if (e.key === 'Enter') { e.preventDefault(); handlers.createAndAdd(); } };
  const dash = t('common.em_dash');
  return html`
    <div class="card" style="margin-top: 4px">
      <h4>${t('league.members_count', { count: members.length })}</h4>
      ${members.length ? html`
        <table class="data-table">
          <thead><tr><th>#</th><th>${t('player.nickname')}</th><th>${t('common.name')}</th></tr></thead>
          <tbody>
            ${members.map((p, i) => html`
              <tr>
                <td>${i + 1}</td>
                <td>${p.nickname || dash}</td>
                <td>${`${p.first_name || ''} ${p.last_name || ''}`.trim() || dash}</td>
              </tr>
            `)}
          </tbody>
        </table>
      ` : ''}
      <h4 style="margin-top: 12px">${t('league.add_player')}</h4>
      ${available.length ? html`
        <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 8px">
          <select id="add-lp-${leagueId}">
            <option value="">${t('league.select_existing')}</option>
            ${available.map((p) => html`<option value=${p.uuid}>${p.nickname || p.uuid.substring(0, 8)}</option>`)}
          </select>
          <button class="btn btn-primary btn-sm" @click=${handlers.addExisting}>${t('player.add_btn')}</button>
        </div>
      ` : ''}
      <div style="display: flex; gap: 8px; flex-wrap: wrap; align-items: end">
        <div class="form-group" style="flex: 1; min-width: 100px">
          <label>${t('player.nickname_required')}</label>
          <input id="new-lp-nick-${leagueId}" type="text" placeholder=${t('player.placeholder_nickname')} @keydown=${onEnter}>
        </div>
        <div class="form-group" style="flex: 1; min-width: 100px">
          <label>${t('player.first_name')}</label>
          <input id="new-lp-first-${leagueId}" type="text" @keydown=${onEnter}>
        </div>
        <div class="form-group" style="flex: 1; min-width: 100px">
          <label>${t('player.last_name')}</label>
          <input id="new-lp-last-${leagueId}" type="text" @keydown=${onEnter}>
        </div>
        <button class="btn btn-primary btn-sm" style="margin-bottom: 12px" @click=${handlers.createAndAdd}>${t('player.create_and_add')}</button>
      </div>
    </div>
  `;
}

function createLeagueTemplate(onSubmit) {
  const onEnter = (e) => { if (e.key === 'Enter') { e.preventDefault(); onSubmit(); } };
  return html`
    <div class="card">
      <h3>${t('league.new')}</h3>
      <div class="form-group">
        <label>${t('common.name')}</label>
        <input id="new-l-name" type="text" placeholder=${t('league.name_placeholder')} @keydown=${onEnter}>
      </div>
      <div class="form-group">
        <label>${t('common.description')}</label>
        <input id="new-l-desc" type="text" placeholder=${t('league.description_placeholder')} @keydown=${onEnter}>
      </div>
      <div class="form-group">
        <label>${t('league.scoring')}</label>
        <select id="new-l-scoring">
          <option value="placement_points">${t('league.placement_points')}</option>
          <option value="elo">${t('league.elo')}</option>
          <option value="win_loss">${t('league.win_loss')}</option>
        </select>
      </div>
      <fieldset style="border: 1px solid #ddd; border-radius: 6px; padding: 12px; margin-top: 8px">
        <legend style="font-weight: 600; font-size: 0.9rem">${t('league.default_rules')}</legend>
        <div style="display: flex; gap: 12px; flex-wrap: wrap">
          <div class="form-group" style="flex: 1; min-width: 100px">
            <label>${t('rules.points_per_game')}</label>
            <input id="new-l-ppg" type="number" min="1" max="20" value="6" @keydown=${onEnter}>
          </div>
          <div class="form-group" style="flex: 1; min-width: 100px">
            <label>${t('rules.draw_allowed')}</label>
            <select id="new-l-draw">
              <option value="true" selected>${t('common.yes')}</option>
              <option value="false">${t('common.no')}</option>
            </select>
          </div>
        </div>
      </fieldset>
      <button class="btn btn-primary" style="margin-top: 12px" @click=${onSubmit}>${t('common.create')}</button>
    </div>
  `;
}

// --- Logic ---

let _showForm = false;
let _expandedLeague = null;  // currently expanded league detail
let _detailData = null;      // { members, available }
// Standings are tracked per-league so opening one doesn't collapse
// another and so the toggle is a stable per-card UI element. The map
// stores either an array of rows or null while loading / collapsed.
const _standingsByLeague = new Map();  // leagueId -> rows[] | null

async function loadDetailData(leagueId) {
  let members = [];
  try { members = await API.leaguePlayers(leagueId); } catch (_) {}
  let allPlayers = [];
  try { allPlayers = await API.players(); } catch (_) {}
  const memberIds = new Set(members.map((m) => m.uuid));
  const available = allPlayers.filter((p) => !memberIds.has(p.uuid));
  return { members, available };
}

const LeaguesPage = {
  async render() {
    UI.title(t('league.title'));
    UI.loading();
    try {
      const items = await API.leagues();
      const rerender = () => this._renderList(items);
      rerender();
    } catch (e) {
      UI.error(e.message);
    }
  },

  async _renderList(items) {
    const leagueCards = items.map((l) => {
      const isExpanded = _expandedLeague === l.uuid;
      const standingsRows = _standingsByLeague.get(l.uuid);
      const standingsShown = standingsRows !== undefined;
      return html`
        <div class="card">
          <h3>${l.name || t('league.unnamed')}</h3>
          <div class="meta">${t('league.scoring_label', { type: l.scoring_type || t('common.em_dash') })}  |  ${l.description || ''}</div>
          <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px">
            <button class="btn btn-secondary btn-sm"
              @click=${() => this._toggleDetail(l.uuid, items)}>${t('league.manage_players')}</button>
            <button class="btn btn-secondary btn-sm"
              @click=${() => this._toggleStandings(l.uuid, items)}>${
                standingsShown ? t('league.hide_standings') : t('league.show_standings')
              }</button>
          </div>
        </div>
        ${isExpanded && _detailData ? leagueDetailTemplate(l.uuid, _detailData.members, _detailData.available, {
          addExisting: () => this._addExisting(l.uuid, items),
          createAndAdd: () => this._createAndAdd(l.uuid, items),
        }) : ''}
        ${standingsShown ? leagueStandingsTemplate(standingsRows) : ''}
      `;
    });

    UI.renderPage(html`
      <div>
        <button class="btn btn-primary" style="margin-bottom: 12px"
          @click=${() => { _showForm = !_showForm; this._renderList(items); }}>${t('league.new_btn')}</button>
        ${_showForm ? createLeagueTemplate(() => this._doCreate(items)) : ''}
        ${!items.length ? html`<p class="loading">${t('league.none_yet')}</p>` : ''}
        ${leagueCards}
      </div>
    `);
  },

  async _toggleDetail(leagueId, items) {
    if (_expandedLeague === leagueId) {
      _expandedLeague = null;
      _detailData = null;
    } else {
      _expandedLeague = leagueId;
      _detailData = await loadDetailData(leagueId);
    }
    this._renderList(items);
  },

  async _toggleStandings(leagueId, items) {
    if (_standingsByLeague.has(leagueId)) {
      // Already shown — collapse.
      _standingsByLeague.delete(leagueId);
      this._renderList(items);
      return;
    }
    // Show with an empty array first so the button flips immediately,
    // then re-render once the fetch resolves.
    _standingsByLeague.set(leagueId, []);
    this._renderList(items);
    try {
      const rows = await API.leagueStandings(leagueId);
      _standingsByLeague.set(leagueId, rows || []);
      this._renderList(items);
    } catch (e) {
      _standingsByLeague.delete(leagueId);
      UI.toast(e.message, 'error');
      this._renderList(items);
    }
  },

  async _addExisting(leagueId, items) {
    const pid = document.getElementById(`add-lp-${leagueId}`)?.value;
    if (!pid) { UI.toast(t('player.select_a_player'), 'error'); return; }
    try {
      await API.post(`/api/v1/leagues/${leagueId}/players/?player_id=${pid}`);
      UI.toast(t('player.added'), 'success');
      _detailData = await loadDetailData(leagueId);
      this._renderList(items);
    } catch (e) { UI.toast(e.message, 'error'); }
  },

  async _createAndAdd(leagueId, items) {
    const nickname = document.getElementById(`new-lp-nick-${leagueId}`)?.value?.trim();
    if (!nickname) { UI.toast(t('player.nickname_required_msg'), 'error'); return; }
    try {
      const player = await API.createPlayer({
        nickname,
        first_name: document.getElementById(`new-lp-first-${leagueId}`)?.value?.trim() || undefined,
        last_name: document.getElementById(`new-lp-last-${leagueId}`)?.value?.trim() || undefined,
      });
      await API.post(`/api/v1/leagues/${leagueId}/players/?player_id=${player.uuid}`);
      UI.toast(t('player.created_added', { name: nickname }), 'success');
      _detailData = await loadDetailData(leagueId);
      this._renderList(items);
    } catch (e) { UI.toast(e.message, 'error'); }
  },

  async _doCreate(items) {
    try {
      await API.createLeague({
        name: document.getElementById('new-l-name').value,
        description: document.getElementById('new-l-desc').value,
        scoring_type: document.getElementById('new-l-scoring').value,
        default_game_rules: {
          points_per_game: parseInt(document.getElementById('new-l-ppg')?.value) || 6,
          draw_allowed: document.getElementById('new-l-draw')?.value === 'true',
        },
      });
      UI.toast(t('league.created'), 'success');
      _showForm = false;
      this.render();
    } catch (e) { UI.toast(e.message, 'error'); }
  },
};

export default LeaguesPage;