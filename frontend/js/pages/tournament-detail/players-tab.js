/**
 * Players tab — the foldable section of the tournament page that lists
 * registered players, applicants waiting for approval, and the various
 * "add player" panels (from league, from all players, brand new).
 *
 * Extracted from tournament-detail.js. The module owns the small UI state
 * that has to survive re-renders (`_activeAddTab`, `_playersExpanded`)
 * and exposes a single async builder; everything else is internal.
 *
 * Host hooks:
 *   - rerender(): full page refresh after a mutation
 *   - doAction(fn, msg): same try/toast/rerender wrapper the page uses
 *     elsewhere (we share it instead of duplicating).
 */
import UI from '../../ui.js';
import API from '../../api.js';
import { t } from '../../i18n.js';

let _activeAddTab = null;     // remember which add-player tab is open across re-renders
let _playersExpanded = null;  // null = default based on tour status; user toggle persists

let _hooks = { rerender: () => {}, doAction: async () => {} };

export async function renderPlayers(tournamentId, tour, myNickname, hooks) {
  if (hooks) _hooks = { rerender: () => {}, doAction: async () => {}, ...hooks };
  return _renderPlayers(tournamentId, tour, myNickname);
}

async function _renderPlayers(tournamentId, tour, myNickname) {
  const dash = t('common.em_dash');
  // Collapsed by default once the tournament is running/finished; user toggle persists.
  const defaultExpanded = (tour.status || 'registration') === 'registration';
  const expanded = _playersExpanded === null ? defaultExpanded : _playersExpanded;
  const chevron = expanded ? '▾' : '▸';
  const header = UI.html('h3', {
    style: 'cursor:pointer;user-select:none;margin:0',
    onclick: () => {
      _playersExpanded = !(expanded);
      _hooks.rerender();
    },
  }, [`${chevron} ${t('player.title')} (${(tour.registrations || []).length})`]);
  const body = UI.html('div', { style: expanded ? '' : 'display:none' });
  const card = UI.html('div', { className: 'card' }, [header, body]);

  // Helper: get player name from registration
  const _regName = (r) => {
    const p = r.player;
    if (p) return p.nickname || `${p.first_name || ''} ${p.last_name || ''}`.trim() || dash;
    return r.player_id?.substring(0, 8) || dash;
  };

  // List current registrations (simple player list — standings are inside each stage)
  if (tour.registrations && tour.registrations.length) {
    const sorted = [...tour.registrations].sort((a, b) => _regName(a).localeCompare(_regName(b)));
    const rows = sorted.map((r, i) => [String(i + 1), _regName(r)]);
    body.appendChild(UI.table(['#', t('live.standings_th_player')], rows));
  }

  // Add player controls (registration phase OR running tournament for late-joiners)
  if (API.isLoggedIn() && tour.status !== 'finished') {
    body.appendChild(UI.html('h4', { style: 'margin-top: 16px' }, [t('player.add')]));

    const registeredIds = new Set((tour.registrations || []).map((r) => r.player_id));
    const applicantIds = new Set((tour.applicants || []).map((a) => a.uuid));
    let allPlayers = [];
    try { allPlayers = await API.players(); } catch (_) {}
    const available = allPlayers.filter((p) => !registeredIds.has(p.uuid) && !applicantIds.has(p.uuid));

    // Tab buttons
    const tabs = UI.html('div', { style: 'display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 8px' });

    // Tab: Accept pre-registered (applicants) — always visible
    const applicants = tour.applicants || [];
    tabs.appendChild(_tabBtn('applicants', t('player.accept_count', { count: applicants.length })));

    // Tab: Add from league
    if (tour.league_id) {
      tabs.appendChild(_tabBtn('league', t('player.from_league')));
    }

    // Tab: Existing player
    tabs.appendChild(_tabBtn('existing', t('player.all_players')));

    // Tab: New player
    tabs.appendChild(_tabBtn('new', t('player.new_player')));

    body.appendChild(tabs);

    // Panel: applicants — always present, shows message when empty
    const appDiv = UI.html('div', { id: 'add-applicants-panel', className: 'striped-list', style: 'display: none' });
    if (applicants.length) {
      for (const a of applicants) {
        appDiv.appendChild(UI.html('div', {
          id: `applicant-${a.uuid}`,
          style: 'display: flex; align-items: center; justify-content: space-between; padding: 6px 8px',
        }, [
          UI.html('span', {}, [a.nickname || dash]),
          UI.html('button', {
            className: 'btn btn-primary btn-sm',
            onclick: () => acceptApplicant(tournamentId, a.uuid, a.nickname),
          }, [t('player.accept')]),
        ]));
      }
      if (applicants.length > 1) {
        appDiv.appendChild(UI.html('button', {
          className: 'btn btn-primary btn-sm', style: 'margin-top: 8px',
          onclick: () => acceptAllApplicants(tournamentId, applicants),
        }, [t('player.accept_all', { count: applicants.length })]));
      }
    } else {
      appDiv.appendChild(UI.html('p', { className: 'meta' }, [
        t('player.no_applicants'),
      ]));
    }
    body.appendChild(appDiv);

    // Panel: league players
    if (tour.league_id) {
      const leagueDiv = UI.html('div', { id: 'add-league-panel', className: 'striped-list', style: 'display: none' });
      let leaguePlayers = [];
      try { leaguePlayers = await API.leaguePlayers(tour.league_id); } catch (_) {}
      const leagueAvail = leaguePlayers.filter((p) => !registeredIds.has(p.uuid));
      if (leagueAvail.length) {
        for (const p of leagueAvail) {
          leagueDiv.appendChild(UI.html('div', { style: 'display: flex; align-items: center; justify-content: space-between; padding: 6px 8px' }, [
            UI.html('span', {}, [p.nickname || p.uuid.substring(0, 8)]),
            UI.html('button', {
              className: 'btn btn-primary btn-sm',
              onclick: () => _hooks.doAction(() => API.addPlayer(tournamentId, p.uuid), t('player.added_named', { name: p.nickname })),
            }, [t('player.add_btn')]),
          ]));
        }
        // Add all from league
        if (leagueAvail.length > 1) {
          leagueDiv.appendChild(UI.html('button', {
            className: 'btn btn-primary btn-sm', style: 'margin-top: 8px',
            onclick: () => addAllFromList(tournamentId, leagueAvail),
          }, [t('player.add_all', { count: leagueAvail.length })]));
        }
      } else {
        leagueDiv.appendChild(UI.html('p', { className: 'meta' }, [t('player.all_league_registered')]));
      }
      body.appendChild(leagueDiv);
    }

    // Panel: existing player (dropdown)
    const existingDiv = UI.html('div', { id: 'add-existing-panel', style: 'display: none' });
    if (available.length) {
      const select = UI.html('select', { id: 'add-existing-select' },
        [UI.html('option', { value: '' }, [t('common.placeholder_select_player')])].concat(
          available.map((p) => UI.html('option', { value: p.uuid }, [p.nickname || p.uuid.substring(0, 8)]))
        )
      );
      existingDiv.appendChild(select);
      existingDiv.appendChild(UI.html('button', {
        className: 'btn btn-primary btn-sm', style: 'margin-left: 8px',
        onclick: () => addExisting(tournamentId),
      }, [t('common.add')]));
    } else {
      existingDiv.appendChild(UI.html('p', { className: 'meta' }, [t('player.all_known_registered')]));
    }
    body.appendChild(existingDiv);

    // Panel: new player
    const keyHandler = (e) => { if (e.key === 'Enter') { e.preventDefault(); addNew(tournamentId); } };
    const newDiv = UI.html('div', { id: 'add-new-panel', style: 'display: none' }, [
      UI.html('div', { style: 'display: flex; gap: 8px; flex-wrap: wrap; align-items: end' }, [
        UI.html('div', { className: 'form-group', style: 'flex: 1; min-width: 120px' }, [
          UI.html('label', {}, [t('player.nickname_required')]),
          UI.html('input', { id: 'new-p-nickname', type: 'text', placeholder: t('player.placeholder_nickname'), onkeydown: keyHandler }),
        ]),
        UI.html('div', { className: 'form-group', style: 'flex: 1; min-width: 120px' }, [
          UI.html('label', {}, [t('player.first_name')]),
          UI.html('input', { id: 'new-p-first', type: 'text', onkeydown: keyHandler }),
        ]),
        UI.html('div', { className: 'form-group', style: 'flex: 1; min-width: 120px' }, [
          UI.html('label', {}, [t('player.last_name')]),
          UI.html('input', { id: 'new-p-last', type: 'text', onkeydown: keyHandler }),
        ]),
        UI.html('button', {
          className: 'btn btn-primary btn-sm', style: 'margin-bottom: 12px',
          onclick: () => addNew(tournamentId),
        }, [t('player.create_and_add')]),
      ]),
    ]);
    body.appendChild(newDiv);

    // Restore previously active tab, or auto-select
    if (_activeAddTab) showTab(_activeAddTab);
    else if (applicants.length) showTab('applicants');
    else if (tour.league_id) showTab('league');
    else showTab('applicants');
  }

  return card;
}

function _tabBtn(name, label) {
  return UI.html('button', {
    className: 'btn btn-secondary btn-sm',
    id: `tab-${name}`,
    onclick: () => showTab(name),
  }, [label]);
}

function showTab(which) {
  _activeAddTab = which;
  for (const id of ['applicants', 'league', 'existing', 'new']) {
    const el = document.getElementById(`add-${id}-panel`);
    if (el) el.style.display = id === which ? '' : 'none';
    const btn = document.getElementById(`tab-${id}`);
    if (btn) btn.style.fontWeight = id === which ? 'bold' : 'normal';
  }
}

async function addExisting(tournamentId) {
  const sel = document.getElementById('add-existing-select');
  const pid = sel?.value;
  if (!pid) { UI.toast(t('player.select_a_player'), 'error'); return; }
  await _hooks.doAction(() => API.addPlayer(tournamentId, pid), t('player.added'));
}

async function addNew(tournamentId) {
  const nickname = document.getElementById('new-p-nickname')?.value?.trim();
  if (!nickname) { UI.toast(t('player.nickname_required_msg'), 'error'); return; }
  try {
    const player = await API.createPlayer({
      nickname,
      first_name: document.getElementById('new-p-first')?.value?.trim() || undefined,
      last_name: document.getElementById('new-p-last')?.value?.trim() || undefined,
    });
    await API.addPlayer(tournamentId, player.uuid);
    UI.toast(t('player.created_added', { name: nickname }), 'success');
    _hooks.rerender();
  } catch (e) {
    UI.toast(e.message, 'error');
  }
}

async function acceptApplicant(tournamentId, playerId, nickname) {
  try {
    await API.addPlayer(tournamentId, playerId);
    UI.toast(t('player.accepted_named', { name: nickname || t('player.title') }), 'success');
    // Remove this applicant row from DOM instead of full re-render
    const row = document.getElementById(`applicant-${playerId}`);
    if (row) row.remove();
    // Update applicant count on the tab button
    const remaining = document.querySelectorAll('[id^="applicant-"]').length;
    const tabBtn = document.getElementById('tab-applicants');
    if (tabBtn) tabBtn.textContent = t('player.accept_count', { count: remaining });
    // If no more applicants, do a full re-render to clean up
    if (remaining === 0) _hooks.rerender();
  } catch (e) {
    UI.toast(e.message, 'error');
  }
}

async function acceptAllApplicants(tournamentId, applicants) {
  let count = 0;
  for (const a of applicants) {
    try { await API.addPlayer(tournamentId, a.uuid); count++; }
    catch (_) { /* skip failed */ }
  }
  UI.toast(t('player.accepted_count', { count }), 'success');
  _hooks.rerender();
}

async function addAllFromList(tournamentId, players) {
  let count = 0;
  for (const p of players) {
    try { await API.addPlayer(tournamentId, p.uuid); count++; }
    catch (_) { /* skip failed */ }
  }
  UI.toast(t('player.added_count', { count }), 'success');
  _hooks.rerender();
}
