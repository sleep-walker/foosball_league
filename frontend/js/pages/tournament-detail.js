/**
 * Tournament detail page — shows stages, standings, matches, controls.
 */
import UI from '../ui.js';
import API from '../api.js';
import WS from '../ws.js';
import { html, render as litRender } from 'lit-html';
import { t } from '../i18n.js';
import { showRulesEditor } from './tournament-detail/rules-editor.js';
import { renderMatch, hasExpandedRows } from './tournament-detail/score-entry.js';

// --- Templates ---

function infoCardTemplate(tour) {
  return html`
    <div class="card">
      <h3>${tour.name || t('tournament.title')}</h3>
      <div class="meta">📅 ${tour.date}  📍 ${tour.location || t('common.em_dash')}  🎮 ${tour.player_mode}</div>
      <div style="margin-top: 8px">
        <span class="badge badge-${tour.status || 'preparing'}">${t(`status.${tour.status || 'preparing'}`)}</span>
        <span class="meta" style="margin-left: 8px">${t('tournament.players_count', { count: (tour.registrations || []).length })}</span>
      </div>
    </div>
  `;
}

function controlsTemplate(id, tour, doAction, doDelete) {
  return html`
    <div class="card">
      <h3>${t('tournament.controls')}</h3>
      ${tour.status === 'registration' ? html`
        <button class="btn btn-primary" style="margin-right: 8px"
          @click=${() => doAction(() => API.startTournament(id), t('tournament.started'))}>${t('tournament.start')}</button>
      ` : ''}
      ${tour.status === 'running' ? html`
        <button class="btn btn-danger" style="margin-right: 8px"
          @click=${() => doAction(() => API.finishTournament(id), t('tournament.finished'))}>${t('tournament.finish')}</button>
      ` : ''}
      <a class="btn btn-secondary" style="margin-right: 8px; text-decoration: none; display: inline-block"
        href="${window.location.origin}${window.location.pathname}#live/${id}"
        target="_blank" rel="noopener">${t('tournament.live_view_link')}</a>
      <button class="btn btn-danger btn-sm" style="margin-top: 8px"
        @click=${() => doDelete(id, tour.name)}>${t('tournament.delete')}</button>
    </div>
  `;
}

function exportTemplate(id) {
  return html`
    <div class="card">
      <h3>${t('tournament.export')}</h3>
      <a href="/api/v1/public/tournaments/${id}/export?format=json" class="btn btn-secondary btn-sm" style="margin-right: 8px">${t('tournament.export_json')}</a>
      <a href="/api/v1/public/tournaments/${id}/export?format=csv_standings" class="btn btn-secondary btn-sm" style="margin-right: 8px">${t('tournament.export_csv')}</a>
      <a href="/api/v1/public/tournaments/${id}/export?format=html" class="btn btn-secondary btn-sm">${t('tournament.export_html')}</a>
    </div>
  `;
}

// --- Logic ---

let _tournamentId = null;
let _roundsNewestFirst = true;
let _activeAddTab = null;  // remember which add-player tab is open across re-renders
let _playersExpanded = null;  // null = use default based on tour status; user toggle persists across re-renders
let _wsConnected = false;
let _suppressUntil = 0;
let _rendered = false;

// Hooks handed to the score-entry module so it can suppress WS-driven
// re-renders during a submit and ask us to re-render the page afterwards.
const _scoreEntryHooks = {
  onBeforeSubmit: () => { _suppressUntil = Date.now() + 5000; },
  rerender: () => render(_tournamentId),
};

async function render(id) {
  _tournamentId = id;
  if (!_rendered) UI.loading();

  try {
    const tour = API.isLoggedIn() ? await API.tournament(id) : await API.publicTournament(id);
    UI.title(tour.name || t('tournament.title'));
    _rendered = true;

    let myPlayerId = null;
    let myNickname = null;
    let isOrganizer = false;
    if (API.isLoggedIn()) {
      try {
        const user = await API.me();
        isOrganizer = (user?.id === tour.owner_id);
        if (!isOrganizer) {
          const me = await API.myPlayer();
          myPlayerId = me?.player_id;
          myNickname = me?.nickname;
        }
      } catch (_) {}
    }

    if (!_wsConnected || _tournamentId !== id) {
      WS.connect(id);
      WS.onEvent(onLiveEvent);
      _wsConnected = true;
    }

    const container = UI.html('div', {});

    // Info card (lit-html → DOM node)
    const infoEl = document.createElement('div');
    litRender(infoCardTemplate(tour), infoEl);
    container.appendChild(infoEl);

    // Controls
    if (API.isLoggedIn()) {
      const ctrlEl = document.createElement('div');
      litRender(controlsTemplate(id, tour, doAction, doDelete), ctrlEl);
      container.appendChild(ctrlEl);
    }

    // Get league default rules if tournament belongs to a league
    let leagueRules = null;
    if (tour.league_id) {
      try {
        const league = await API.league(tour.league_id);
        leagueRules = league?.default_game_rules || null;
      } catch (_) {}
    }

    // Stages — newer (higher ordering) on top, finished sink to the bottom
    // so the spotlight stays on what's currently being played.
    const sortedStages = [...(tour.stages || [])].sort((a, b) => {
      const aDone = a.status === 'finished' ? 1 : 0;
      const bDone = b.status === 'finished' ? 1 : 0;
      if (aDone !== bDone) return aDone - bDone;
      return (b.ordering ?? 0) - (a.ordering ?? 0);
    });
    for (const stage of sortedStages) {
      container.appendChild(await renderStage(id, stage, tour.status, myPlayerId, myNickname, leagueRules, tour.league_id));
    }

    // Add Stage button (organizer, running tournament)
    if (API.isLoggedIn() && tour.status === 'running') {
      const addStageBtn = UI.html('button', {
        className: 'btn btn-secondary', style: 'margin-bottom: 12px',
        id: 'add-stage-btn',
        onclick: () => {
          const existing = document.getElementById('add-stage-form');
          if (existing) { existing.remove(); return; }
          const form = _buildAddStageForm(id, tour.player_mode);
          addStageBtn.after(form);
        },
      }, [t('stage.add')]);
      container.appendChild(addStageBtn);
    }

    // Players section
    container.appendChild(await renderPlayers(id, tour, myNickname));

    // Export (lit-html → DOM node)
    const exportEl = document.createElement('div');
    litRender(exportTemplate(id), exportEl);
    container.appendChild(exportEl);

    UI.render(container);
  } catch (e) {
    UI.error(e.message);
  }
}

function _rulesHint(r) {
  const ppg = r.points_per_game || 6;
  const draw = r.draw_allowed !== false;
  const parts = [t('rulesHint.game_to', { ppg })];
  if (draw) parts.push(t('rulesHint.draw_at', { n: ppg - 1 }));
  else parts.push(t('rulesHint.no_draws'));
  if (r.margin_required > 0) parts.push(t('rulesHint.win_by', { n: r.margin_required }));
  if (r.score_cap > 0) parts.push(t('rulesHint.cap', { n: r.score_cap }));
  parts.push(`W=${r.points_for_win ?? 2} D=${r.points_for_draw ?? 1} L=${r.points_for_loss ?? 0}`);
  if (r.table_count > 0) parts.push(t('rulesHint.tables', { n: r.table_count }));
  if ((r.best_of || 1) > 1) parts.push(t('rulesHint.best_of', { n: r.best_of }));
  if (r.finals_best_of && r.finals_best_of !== r.best_of) parts.push(t('rulesHint.finals_best_of', { n: r.finals_best_of }));
  return parts.join(' · ');
}

function _buildAddStageForm(tournamentId, playerMode = 'singles') {
  const isDoubles = playerMode === 'doubles';
  const advancementGroup = UI.html('div', {
    id: 'new-stage-advancement-group',
    className: 'form-group',
    style: 'flex: 1; min-width: 120px; display: none',
  }, [
    UI.html('label', {}, [t('stage.advancement')]),
    UI.html('input', { id: 'new-stage-advancement', type: 'number', min: '2', max: '64', value: '8', style: 'width: 70px' }),
    UI.html('div', { style: 'font-size: 0.75rem; color: #888; margin-top: 2px' }, [t('stage.advancement_hint')]),
  ]);

  // Team formation — doubles only. For elimination the choice between DYP
  // (stable pairs) and Monster DYP (re-pair after each round) lives here.
  const formationGroup = UI.html('div', {
    id: 'new-stage-formation-group',
    className: 'form-group',
    style: `flex: 1; min-width: 160px; ${isDoubles ? '' : 'display: none'}`,
  }, [
    UI.html('label', {}, [t('stage.team_formation')]),
    UI.html('select', { id: 'new-stage-formation' }, [
      UI.html('option', { value: 'dyp' }, [t('stage.formation_dyp')]),
      UI.html('option', { value: 'monster_dyp' }, [t('stage.formation_monster')]),
      UI.html('option', { value: 'fixed' }, [t('stage.formation_fixed')]),
    ]),
  ]);

  const typeSelect = UI.html('select', {
    id: 'new-stage-type',
    onchange: () => {
      const isElim = document.getElementById('new-stage-type').value === 'elimination';
      const ag = document.getElementById('new-stage-advancement-group');
      if (ag) ag.style.display = isElim ? '' : 'none';
    },
  }, [
    UI.html('option', { value: 'group' }, [t('stage.type_group')]),
    UI.html('option', { value: 'elimination' }, [t('stage.type_elimination')]),
  ]);

  return UI.html('div', { id: 'add-stage-form', className: 'card' }, [
    UI.html('h3', {}, [t('stage.new')]),
    UI.html('div', { style: 'display: flex; gap: 12px; flex-wrap: wrap' }, [
      UI.html('div', { className: 'form-group', style: 'flex: 1; min-width: 120px' }, [
        UI.html('label', {}, [t('common.name')]),
        UI.html('input', { id: 'new-stage-name', type: 'text', placeholder: t('stage.name_placeholder') }),
      ]),
      UI.html('div', { className: 'form-group', style: 'flex: 1; min-width: 120px' }, [
        UI.html('label', {}, [t('stage.type')]),
        typeSelect,
      ]),
      advancementGroup,
      formationGroup,
    ]),
    UI.html('div', { className: 'meta', style: 'margin-bottom: 8px' }, [
      t('stage.rules_after'),
    ]),
    UI.html('button', {
      className: 'btn btn-primary btn-sm',
      onclick: async () => {
        try {
          const stageType = document.getElementById('new-stage-type').value;
          const payload = {
            name: document.getElementById('new-stage-name').value || t('stage.default_name'),
            stage_type: stageType,
            tournament_id: tournamentId,
          };
          if (stageType === 'elimination') {
            const adv = parseInt(document.getElementById('new-stage-advancement')?.value);
            if (adv > 0) payload.advancement_count = adv;
          }
          if (isDoubles) {
            const tf = document.getElementById('new-stage-formation')?.value;
            if (tf) payload.team_formation = tf;
          }
          await API.post(`/api/v1/tournaments/${tournamentId}/stages/`, payload);
          UI.toast(t('stage.created'), 'success');
          render(_tournamentId);
        } catch (e) { UI.toast(e.message, 'error'); }
      },
    }, [t('stage.create')]),
  ]);
}

async function renderStage(tournamentId, stage, tStatus, myPlayerId, myNickname, leagueRules, leagueId) {
  const r = stage.rules || {};
  const rulesHint = _rulesHint(r);
  const statusIcon = { preparing: '⏳', active: '▶', finished: '✅' }[stage.status] || '';

  // Two-column layout: left = controls + rounds, right = standings
  const leftCol = UI.html('div', { className: 'stage-rounds' });
  const rightCol = UI.html('div', { className: 'stage-standings' });
  const columns = UI.html('div', { className: 'stage-columns' }, [leftCol, rightCol]);
  const stageBody = UI.html('div', { id: `stage-body-${stage.uuid}` }, [columns]);
  // Alias: controls and matches go into leftCol
  const matchesCol = leftCol;

  const card = UI.html('div', { className: 'card' }, [
    UI.html('h3', {
      style: 'cursor: pointer; user-select: none',
      onclick: () => {
        const body = document.getElementById(`stage-body-${stage.uuid}`);
        if (body) body.style.display = body.style.display === 'none' ? '' : 'none';
      },
    }, [`${statusIcon} ${stage.name} (${t(`stage.type_${stage.stage_type}`)}) ▾`]),
    UI.html('div', { className: 'meta', style: 'margin-bottom: 8px' }, [rulesHint]),
    stageBody,
  ]);

  // Stage lifecycle controls (organizer only) → left column
  if (API.isLoggedIn()) {
    if (stage.status === 'active') {
      matchesCol.appendChild(UI.html('button', {
        className: 'btn btn-secondary btn-sm', style: 'margin-right: 8px; margin-bottom: 8px',
        onclick: () => doAction(
          () => API.post(`/api/v1/tournaments/${tournamentId}/stages/${stage.uuid}/finish`),
          t('stage.finished'),
        ),
      }, [t('stage.finish')]));
    }
    if (stage.status === 'preparing') {
      const isElim = stage.stage_type === 'elimination';
      matchesCol.appendChild(UI.html('button', {
        className: 'btn btn-primary btn-sm', style: 'margin-right: 8px; margin-bottom: 8px',
        onclick: () => doAction(async () => {
          await API.post(`/api/v1/tournaments/${tournamentId}/stages/${stage.uuid}/activate`);
          if (isElim) await API.generateBracket(tournamentId, stage.uuid);
        }, isElim ? t('stage.activated_bracket') : t('stage.activated')),
      }, [isElim ? t('stage.activate_with_bracket') : t('stage.activate')]));
    }
    if (stage.status !== 'finished') {
      matchesCol.appendChild(UI.html('button', {
        className: 'btn btn-secondary btn-sm', style: 'margin-bottom: 8px',
        onclick: () => showRulesEditor(tournamentId, stage, leagueRules, leagueId, () => render(_tournamentId)),
      }, [t('stage.rules_btn')]));
    }
  }

  if (API.isLoggedIn() && tStatus === 'running' && stage.status === 'active' && stage.stage_type === 'elimination') {
    matchesCol.appendChild(UI.html('button', {
      className: 'btn btn-secondary btn-sm', style: 'margin-bottom: 8px',
      onclick: () => doAction(() => API.generateBracket(tournamentId, stage.uuid), t('stage.bracket_regenerated')),
    }, [t('stage.regenerate')]));
  }

  // Matches grouped by round → left column
  try {
    const matches = await API.matches(tournamentId);
    const stageMatches = matches.filter(m => m.stage_id === stage.uuid);
    if (stageMatches.length) {
      const byRound = {};
      for (const m of stageMatches) {
        const r = m.round_number || 1;
        (byRound[r] = byRound[r] || []).push(m);
      }
      const maxRound = Math.max(...Object.keys(byRound).map(Number));
      const latestAll = byRound[maxRound] || [];
      const allDone = latestAll.length > 0 && latestAll.every(m => m.status === 'finished');

      if (API.isLoggedIn() && tStatus === 'running' && stage.status === 'active' && allDone && stage.stage_type === 'group') {
        matchesCol.appendChild(UI.html('button', {
          className: 'btn btn-primary', style: 'margin-bottom: 12px',
          onclick: () => doAction(() => API.drawRound(tournamentId, stage.uuid), t('stage.round_drawn')),
        }, [t('stage.draw_round')]));
      }

      const sortBtn = UI.html('button', {
        className: 'btn btn-secondary btn-sm', style: 'margin-bottom: 8px; float: right',
        onclick: () => { _roundsNewestFirst = !_roundsNewestFirst; render(_tournamentId); },
      }, [_roundsNewestFirst ? t('match.sort_oldest') : t('match.sort_newest')]);
      matchesCol.appendChild(sortBtn);

      const roundKeys = Object.keys(byRound).map(Number)
        .sort(_roundsNewestFirst ? (a, b) => b - a : (a, b) => a - b);
      const isElim = stage.stage_type === 'elimination';
      for (const round of roundKeys) {
        const rm = byRound[round];
        // Final round of an elimination stage with 2+ matches: split into
        // 🏆 Final (lowest bracket_position) and 🥉 3rd place (highest).
        if (isElim && round === maxRound && rm.length >= 2) {
          const sorted = [...rm].sort((a, b) =>
            (a.bracket_position ?? 0) - (b.bracket_position ?? 0));
          const consolation = sorted[sorted.length - 1];
          const finals = sorted.slice(0, -1);
          for (const [hdr, group] of [[t('match.final'), finals], [t('match.third_place'), [consolation]]]) {
            // No "in progress" suffix here — early bracket rounds would
            // otherwise label the (yet-unplayed) final as "in progress".
            matchesCol.appendChild(UI.html('h4', { style: 'margin-top: 12px; clear: both' }, [hdr]));
            for (const m of group) {
              matchesCol.appendChild(renderMatch(m, tournamentId, myPlayerId, myNickname, stage.rules || {}, _scoreEntryHooks));
            }
          }
          continue;
        }
        const roundDone = rm.every(m => m.status === 'finished');
        const label = round === maxRound && !roundDone ? t('match.round_in_progress', { n: round }) : t('match.round', { n: round });
        matchesCol.appendChild(UI.html('h4', { style: 'margin-top: 12px; clear: both' }, [label]));
        for (const m of rm) {
          matchesCol.appendChild(renderMatch(m, tournamentId, myPlayerId, myNickname, stage.rules || {}, _scoreEntryHooks));
        }
      }
    } else if (API.isLoggedIn() && tStatus === 'running' && stage.status === 'active' && stage.stage_type === 'group') {
      matchesCol.appendChild(UI.html('button', {
        className: 'btn btn-primary', style: 'margin-top: 12px',
        onclick: () => doAction(() => API.drawRound(tournamentId, stage.uuid), t('stage.round_drawn')),
      }, [t('stage.draw_round')]));
    }
  } catch (_) { /* no matches yet */ }

  // Standings table → right column (group stages only)
  if (stage.stage_type === 'group') {
    try {
      const standings = API.isLoggedIn()
        ? await API.standings(tournamentId, stage.uuid)
        : await API.publicStandings(tournamentId, stage.uuid);
      if (standings.length) {
        rightCol.appendChild(UI.html('h4', {}, [t('match.standings')]));
        const tbl = UI.html('table', { className: 'standings-table' });
        tbl.appendChild(UI.html('thead', {}, [
          UI.html('tr', {}, [
            UI.html('th', {}, ['#']),
            UI.html('th', {}, [t('live.standings_th_player')]),
            UI.html('th', {}, [t('standings.th_pts')]),
            UI.html('th', {}, [t('standings.th_w')]),
            UI.html('th', {}, [t('standings.th_d')]),
            UI.html('th', {}, [t('standings.th_l')]),
            UI.html('th', {}, [t('standings.th_gd')]),
          ]),
        ]));
        const tbody = UI.html('tbody');
        standings.forEach((s, i) => {
          tbody.appendChild(UI.html('tr', {}, [
            UI.html('td', {}, [String(i + 1)]),
            UI.html('td', {}, [s.nickname || s.participant_id?.substring(0, 8) || '?']),
            UI.html('td', {}, [String(s.points)]),
            UI.html('td', {}, [String(s.wins)]),
            UI.html('td', {}, [String(s.draws)]),
            UI.html('td', {}, [String(s.losses)]),
            UI.html('td', {}, [`${s.goals_for || 0}:${s.goals_against || 0}`]),
          ]));
        });
        tbl.appendChild(tbody);
        rightCol.appendChild(tbl);
      }
    } catch (_) { /* standings not available */ }
  }

  return card;
}



async function renderPlayers(tournamentId, tour, myNickname) {
  const dash = t('common.em_dash');
  // Collapsed by default once the tournament is running/finished; user toggle persists.
  const defaultExpanded = (tour.status || 'registration') === 'registration';
  const expanded = _playersExpanded === null ? defaultExpanded : _playersExpanded;
  const chevron = expanded ? '▾' : '▸';
  const header = UI.html('h3', {
    style: 'cursor:pointer;user-select:none;margin:0',
    onclick: () => {
      _playersExpanded = !(expanded);
      render(_tournamentId);
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
              onclick: () => doAction(() => API.addPlayer(tournamentId, p.uuid), t('player.added_named', { name: p.nickname })),
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
  await doAction(() => API.addPlayer(tournamentId, pid), t('player.added'));
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
    render(_tournamentId);
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
    if (remaining === 0) render(_tournamentId);
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
  render(_tournamentId);
}

async function addAllFromList(tournamentId, players) {
  let count = 0;
  for (const p of players) {
    try { await API.addPlayer(tournamentId, p.uuid); count++; }
    catch (_) { /* skip failed */ }
  }
  UI.toast(t('player.added_count', { count }), 'success');
  render(_tournamentId);
}

async function doDelete(id, name) {
  if (!confirm(t('tournament.delete_confirm', { name: name || id }))) return;
  try {
    await API.deleteTournament(id);
    UI.toast(t('tournament.deleted'), 'success');
    App.navigate('tournaments');
  } catch (e) {
    UI.toast(e.message, 'error');
  }
}

async function doAction(fn, successMsg) {
  try {
    await fn();
    UI.toast(successMsg, 'success');
    // Suppress WS events — we already showed feedback + will render ourselves
    _suppressUntil = Date.now() + 2000;
    render(_tournamentId);
  } catch (e) { UI.toast(e.message, 'error'); }
}

let _renderTimeout = null;
function _debouncedRender() {
  if (_renderTimeout) clearTimeout(_renderTimeout);
  _renderTimeout = setTimeout(() => render(_tournamentId), 500);
}

function onLiveEvent(event) {
  if (Date.now() < _suppressUntil) return;

  const notifyEvents = {
    applicant_registered: (e) => t('applicant.wants_to_play', { name: e.data?.nickname || t('applicant.someone') }),
  };
  const fmt = notifyEvents[event.type];
  if (fmt) UI.toast(fmt(event), 'info');

  if (['round_drawn', 'bracket_generated', 'match_finished', 'score_updated', 'applicant_registered'].includes(event.type)) {
    // Hold full re-renders while the user has any score-entry panel open;
    // input DOM values would otherwise be wiped mid-edit.
    if (hasExpandedRows()) return;
    _debouncedRender();
  }
}

function cleanup() { WS.disconnect(); WS.offEvent(onLiveEvent); }

const TournamentDetailPage = { render, cleanup };
export default TournamentDetailPage;