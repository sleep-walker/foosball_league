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
import { renderPlayers } from './tournament-detail/players-tab.js';
import { buildAddStageForm } from './tournament-detail/add-stage-form.js';

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
          const form = buildAddStageForm(id, tour.player_mode, () => render(_tournamentId));
          addStageBtn.after(form);
        },
      }, [t('stage.add')]);
      container.appendChild(addStageBtn);
    }

    // Players section
    container.appendChild(await renderPlayers(id, tour, myNickname, {
      rerender: () => render(_tournamentId),
      doAction,
    }));

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