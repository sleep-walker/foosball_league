/**
 * Tournament detail page — shows stages, standings, matches, controls.
 */
import UI from '../ui.js';
import API from '../api.js';
import WS from '../ws.js';
import { html, render as litRender } from 'lit-html';
import { t } from '../i18n.js';

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
// Match rows that are expanded for score entry (click-to-expand). DOM is the
// source of truth for typed-but-unsubmitted scores while the panel is open.
const _expanded = new Set();
// Last submission attempt that failed validation, keyed by matchUuid. Consumed
// once on the next _refreshEntry to restore all typed games for retry.
const _failedAttempt = new Map();

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

async function _showRulesEditor(tournamentId, stage, leagueRules, leagueId) {
  const r = stage.rules || {};
  const existing = document.getElementById(`rules-editor-${stage.uuid}`);
  if (existing) { existing.remove(); return; } // toggle

  const stageCard = document.querySelector(`.card h3`)?.closest('.card');
  const cards = document.querySelectorAll('.card');
  let targetCard = null;
  for (const c of cards) {
    if (c.querySelector('h3')?.textContent?.includes(stage.name)) { targetCard = c; break; }
  }
  if (!targetCard) return;

  // Build presets — fetch league presets if available
  const presets = [{ name: t('common.custom'), rules: null }];
  if (leagueId) {
    try {
      const savedPresets = await API.leagueRulePresets(leagueId);
      for (const sp of savedPresets) {
        presets.push({ name: sp.name, rules: sp.rules });
      }
    } catch (_) {}
  }
  if (leagueRules) presets.push({ name: t('rules.league_defaults'), rules: leagueRules });
  // Hardcoded fallback presets
  presets.push(
    { name: t('rules.preset_standard'), rules: { points_per_game: 6, draw_allowed: true, points_for_win: 2, points_for_draw: 1, points_for_loss: 0, margin_required: 0, score_cap: 0 }},
    { name: t('rules.preset_standard_no_draw'), rules: { points_per_game: 6, draw_allowed: false, points_for_win: 2, points_for_draw: 1, points_for_loss: 0, margin_required: 0, score_cap: 0 }},
    { name: t('rules.preset_liga_b'), rules: { points_per_game: 8, draw_allowed: false, margin_required: 2, score_cap: 10, points_for_win: 2, points_for_draw: 1, points_for_loss: 0 }},
  );

  const _applyPreset = (rules) => {
    if (!rules) return;
    const s = stage.uuid;
    document.getElementById(`re-ppg-${s}`).value = rules.points_per_game ?? 6;
    document.getElementById(`re-draw-${s}`).value = String(rules.draw_allowed ?? true);
    document.getElementById(`re-win-${s}`).value = rules.points_for_win ?? 2;
    document.getElementById(`re-drw-${s}`).value = rules.points_for_draw ?? 1;
    document.getElementById(`re-los-${s}`).value = rules.points_for_loss ?? 0;
    document.getElementById(`re-margin-${s}`).value = rules.margin_required ?? 0;
    document.getElementById(`re-cap-${s}`).value = rules.score_cap ?? 0;
    document.getElementById(`re-tables-${s}`).value = rules.table_count ?? 0;
    document.getElementById(`re-bestof-${s}`).value = rules.best_of ?? 1;
    document.getElementById(`re-decmargin-${s}`).value = rules.margin_in_decider ?? 0;
    const finalsEl = document.getElementById(`re-finalsbestof-${s}`);
    if (finalsEl) finalsEl.value = rules.finals_best_of ?? 0;
  };

  const presetSelect = UI.html('div', { className: 'form-group', style: 'margin-bottom: 12px' }, [
    UI.html('label', {}, [t('rules.preset')]),
    UI.html('select', {
      onchange: (e) => {
        const idx = parseInt(e.target.value);
        if (presets[idx].rules) _applyPreset(presets[idx].rules);
      },
    }, presets.map((p, i) => UI.html('option', { value: String(i) }, [p.name]))),
  ]);

  const isGroup = stage.stage_type === 'group';
  const isElim = stage.stage_type === 'elimination';
  const sectionStyle = 'border: 1px solid #e0e0e0; border-radius: 4px; padding: 10px; margin-bottom: 10px; background: #fff';
  const sectionHeaderStyle = 'margin: 0 0 8px 0; font-size: 0.9rem; cursor: pointer; user-select: none';

  // Section: Standings (group stages only)
  const standingsSection = isGroup ? UI.html('div', { style: sectionStyle }, [
    UI.html('h5', { style: sectionHeaderStyle }, [t('rules.standings')]),
    UI.html('div', { style: 'display: flex; gap: 12px; flex-wrap: wrap' }, [
      _ruleField(t('rules.pts_for_win'), `re-win-${stage.uuid}`, 'number', r.points_for_win ?? 2, t('rules.pts_for_win_hint')),
      _ruleField(t('rules.pts_for_draw'), `re-drw-${stage.uuid}`, 'number', r.points_for_draw ?? 1, t('rules.pts_for_draw_hint')),
      _ruleField(t('rules.pts_for_loss'), `re-los-${stage.uuid}`, 'number', r.points_for_loss ?? 0, t('rules.pts_for_loss_hint')),
    ]),
  ]) : null;

  // Section: Game Rules (always shown)
  const gameRulesSection = UI.html('div', { style: sectionStyle }, [
    UI.html('h5', { style: sectionHeaderStyle }, [t('rules.game_rules')]),
    UI.html('div', { style: 'display: flex; gap: 12px; flex-wrap: wrap' }, [
      _ruleField(t('rules.points_per_game'), `re-ppg-${stage.uuid}`, 'number', r.points_per_game || 6, t('rules.points_per_game_hint')),
      _ruleSelect(t('rules.draw_allowed'), `re-draw-${stage.uuid}`, r.draw_allowed !== false,
        t('rules.draw_allowed_hint', { n: (r.points_per_game || 6) - 1 })),
    ]),
    UI.html('div', { style: 'display: flex; gap: 12px; flex-wrap: wrap' }, [
      _ruleField(t('rules.win_margin'), `re-margin-${stage.uuid}`, 'number', r.margin_required || 0, t('rules.win_margin_hint')),
      _ruleField(t('rules.score_cap'), `re-cap-${stage.uuid}`, 'number', r.score_cap || 0, t('rules.score_cap_hint')),
    ]),
  ]);

  // Section: Match Format (elimination always, group shows tables only)
  const matchFormatSection = UI.html('div', { style: sectionStyle }, [
    UI.html('h5', { style: sectionHeaderStyle }, [t('rules.match_format')]),
    UI.html('div', { style: 'display: flex; gap: 12px; flex-wrap: wrap' }, [
      _ruleField(t('rules.best_of'), `re-bestof-${stage.uuid}`, 'number', r.best_of || 1, t('rules.best_of_hint')),
      _ruleField(t('rules.margin_decider'), `re-decmargin-${stage.uuid}`, 'number', r.margin_in_decider || 0, t('rules.margin_decider_hint')),
      ...(isElim ? [
        _ruleField(t('rules.finals_best_of'), `re-finalsbestof-${stage.uuid}`, 'number', r.finals_best_of || 0, t('rules.finals_best_of_hint')),
      ] : []),
      _ruleField(t('rules.tables'), `re-tables-${stage.uuid}`, 'number', r.table_count || 0, t('rules.tables_hint')),
    ]),
  ]);

  const editor = UI.html('div', { id: `rules-editor-${stage.uuid}`, style: 'border: 1px solid #ddd; border-radius: 6px; padding: 12px; margin: 8px 0; background: #f9f9f9' }, [
    UI.html('h4', {}, [t('rules.title')]),
    ...(stage.status === 'active' ? [
      UI.html('div', { className: 'meta', style: 'color: #e67e22; margin-bottom: 8px' }, [
        t('rules.active_warn'),
      ]),
    ] : []),
    presetSelect,
    ...(standingsSection ? [standingsSection] : []),
    gameRulesSection,
    matchFormatSection,
    UI.html('button', {
      className: 'btn btn-primary btn-sm', style: 'margin-top: 8px',
      onclick: async () => {
        const newRules = {
          points_per_game: parseInt(document.getElementById(`re-ppg-${stage.uuid}`).value) || 6,
          draw_allowed: document.getElementById(`re-draw-${stage.uuid}`).value === 'true',
          points_for_win: parseInt(document.getElementById(`re-win-${stage.uuid}`)?.value) || 2,
          points_for_draw: parseInt(document.getElementById(`re-drw-${stage.uuid}`)?.value) || 1,
          points_for_loss: parseInt(document.getElementById(`re-los-${stage.uuid}`)?.value) || 0,
          margin_required: parseInt(document.getElementById(`re-margin-${stage.uuid}`).value) || 0,
          score_cap: parseInt(document.getElementById(`re-cap-${stage.uuid}`).value) || 0,
          table_count: parseInt(document.getElementById(`re-tables-${stage.uuid}`).value) || 0,
          best_of: parseInt(document.getElementById(`re-bestof-${stage.uuid}`).value) || 1,
          margin_in_decider: parseInt(document.getElementById(`re-decmargin-${stage.uuid}`).value) || 0,
        };
        const finalsVal = document.getElementById(`re-finalsbestof-${stage.uuid}`);
        if (finalsVal) {
          const fbo = parseInt(finalsVal.value) || 0;
          if (fbo > 0) newRules.finals_best_of = fbo;
        }
        try {
          // Backend locks rule changes once the stage is active — the
          // user has already seen the orange warning banner above, so
          // submitting here means "I know what I'm doing": send force.
          const path = stage.status === 'active'
            ? `/api/v1/tournaments/${tournamentId}/stages/${stage.uuid}?force=true`
            : `/api/v1/tournaments/${tournamentId}/stages/${stage.uuid}`;
          await API.patch(path, { rules: newRules });
          const redrawCb = document.getElementById(`re-redraw-${stage.uuid}`);
          if (redrawCb && redrawCb.checked) {
            await API.post(`/api/v1/tournaments/${tournamentId}/stages/${stage.uuid}/redraw-round`);
            UI.toast(t('rules.saved_redrawn'), 'success');
          } else {
            UI.toast(t('rules.saved'), 'success');
          }
          render(_tournamentId);
        } catch (e) { UI.toast(e.message, 'error'); }
      },
    }, [t('rules.save_btn')]),
    // Checkbox: also redraw current round (only for active stage)
    ...(stage.status === 'active' ? [
      UI.html('label', {
        style: 'display: inline-flex; align-items: center; gap: 6px; margin-top: 8px; margin-left: 12px; font-size: 0.85rem; cursor: pointer',
      }, [
        UI.html('input', { type: 'checkbox', id: `re-redraw-${stage.uuid}` }),
        t('rules.redraw'),
      ]),
    ] : []),
  ]);
  targetCard.appendChild(editor);
}

function _ruleField(label, id, type, value, hint) {
  return UI.html('div', { className: 'form-group', style: 'flex: 1; min-width: 100px' }, [
    UI.html('label', { for: id }, [label]),
    UI.html('input', { id, type, value: String(value), min: '0', max: '20', style: 'width: 70px' }),
    UI.html('div', { style: 'font-size: 0.75rem; color: #888; margin-top: 2px' }, [hint]),
  ]);
}

function _ruleSelect(label, id, value, hint) {
  return UI.html('div', { className: 'form-group', style: 'flex: 1; min-width: 100px' }, [
    UI.html('label', { for: id }, [label]),
    UI.html('select', { id }, [
      UI.html('option', { value: 'true', selected: value }, [t('common.yes')]),
      UI.html('option', { value: 'false', selected: !value }, [t('common.no')]),
    ]),
    UI.html('div', { style: 'font-size: 0.75rem; color: #888; margin-top: 2px' }, [hint]),
  ]);
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
        onclick: () => _showRulesEditor(tournamentId, stage, leagueRules, leagueId),
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
              matchesCol.appendChild(_renderMatch(m, tournamentId, myPlayerId, myNickname, stage.rules || {}));
            }
          }
          continue;
        }
        const roundDone = rm.every(m => m.status === 'finished');
        const label = round === maxRound && !roundDone ? t('match.round_in_progress', { n: round }) : t('match.round', { n: round });
        matchesCol.appendChild(UI.html('h4', { style: 'margin-top: 12px; clear: both' }, [label]));
        for (const m of rm) {
          matchesCol.appendChild(_renderMatch(m, tournamentId, myPlayerId, myNickname, stage.rules || {}));
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

function _renderMatch(m, tournamentId, myPlayerId, myNickname, stageRules = {}) {
  const dash = t('common.em_dash');
  const labelA = m.team_a_name || m.player_a_nickname || m.player_a_id?.substring(0, 8) || dash;
  const labelB = m.team_b_name || m.player_b_nickname || m.player_b_id?.substring(0, 8) || dash;
  const table = (m.table_number && m.status !== 'finished') ? t('match.table', { n: m.table_number }) : '';
  const bestOf = m.best_of || stageRules.best_of || 1;
  const games = m.games || [];

  // Series wins count
  let winsA = 0, winsB = 0;
  for (const g of games) {
    if (g.score_a > g.score_b) winsA++;
    else if (g.score_b > g.score_a) winsB++;
  }

  // Score display
  let scoreText;
  if (bestOf <= 1) {
    // Single game: show game score or "vs"
    scoreText = m.status === 'finished' ? `${m.score_a ?? 0} : ${m.score_b ?? 0}` : t('match.vs');
  } else {
    // Multi-game: show series score (wins)
    scoreText = m.status === 'finished'
      ? `${winsA} : ${winsB}`
      : (games.length > 0 ? `${winsA} : ${winsB}` : t('match.vs'));
  }

  const isMyMatch = myPlayerId && (
    m.player_a_id === myPlayerId || m.player_b_id === myPlayerId
  ) || myNickname && (
    labelA.includes(myNickname) || labelB.includes(myNickname)
  );
  const highlightStyle = isMyMatch ? 'background: #e3f2fd; border-radius: 4px; padding: 6px 4px;' : 'padding: 6px 0;';

  // Score span — clickable to toggle the entry block when match isn't finished
  const scoreSpan = UI.html('span', {
    id: `score-center-${m.uuid}`,
    style: `padding: 2px 10px; border-radius: 4px; font-weight: bold; ${
      m.status === 'finished' ? 'background: #e8f5e9' : 'background: #f5f5f5; cursor: pointer'
    }`,
    ...(m.status !== 'finished' ? {
      title: t('match.click_score'),
      onclick: () => {
        const opening = !_expanded.has(m.uuid);
        if (opening) _expanded.add(m.uuid);
        else _expanded.delete(m.uuid);
        _refreshEntry(m.uuid, tournamentId, stageRules, m, null, opening);
      },
    } : {}),
  }, [scoreText]);

  const row = UI.html('div', {
    style: `display: flex; align-items: center; gap: 8px; border-bottom: 1px solid #eee; flex-wrap: wrap; ${highlightStyle}`,
  }, [
    ...(table ? [UI.html('span', { className: 'meta', style: 'min-width: 50px' }, [table])] : []),
    UI.html('strong', { style: 'flex: 1; text-align: right; min-width: 80px' }, [labelA]),
    scoreSpan,
    UI.html('strong', { style: 'flex: 1; min-width: 80px' }, [labelB]),
  ]);

  // Show individual committed game scores for multi-game matches
  if (bestOf > 1 && games.length > 0) {
    const gamesLine = UI.html('div', {
      style: 'width: 100%; padding-left: 60px; font-size: 0.8rem; color: #666; margin-top: -4px; margin-bottom: 4px',
    });
    const parts = games.map((g, i) => {
      const bold = (i === games.length - 1 && m.status !== 'finished') ? 'font-weight:bold' : '';
      return `<span style="${bold}">G${i + 1}: ${g.score_a}–${g.score_b}</span>`;
    });
    gamesLine.innerHTML = parts.join(' &nbsp; ');
    row.appendChild(gamesLine);
  }

  // Per-match entry block (collapsed by default, expands when score is clicked)
  if (m.status !== 'finished') {
    const entry = UI.html('div', { id: `entry-${m.uuid}`, style: 'width: 100%' });
    row.appendChild(entry);
    _refreshEntry(m.uuid, tournamentId, stageRules, m, entry);
  }
  return row;
}

/**
 * Client-side score validation — mirrors backend scoring.validate_game_score.
 * Returns error message string or null if valid.
 */
function _validateScore(a, b, ppg, drawAllowed, marginRequired, scoreCap) {
  if (a < 0 || b < 0) return t('match.score_negative');
  if (a === b) {
    if (!drawAllowed) return t('match.draw_not_allowed', { a, b });
    if (a !== ppg - 1) return t('match.draw_must_be', { n: ppg - 1 });
    return null;
  }
  const winner = Math.max(a, b);
  const loser = Math.min(a, b);
  if (marginRequired > 0 && scoreCap > 0) {
    // Deuce rules: win by margin, up to cap
    if (winner === scoreCap && loser === scoreCap - marginRequired) return null;
    if (winner >= ppg && (winner - loser) >= marginRequired && winner <= scoreCap) return null;
    if (winner === ppg && loser < ppg) return null;
    return t('match.invalid_deuce', { a, b, ppg, margin: marginRequired, cap: scoreCap });
  }
  // Simple mode: winner must have exactly ppg points.
  // If draws are allowed at (ppg-1):(ppg-1), loser can have at most ppg-2.
  // If draws are NOT allowed, loser can have at most ppg-1.
  if (winner !== ppg) return t('match.winner_must_reach', { ppg, a, b });
  const maxLoser = drawAllowed ? ppg - 2 : ppg - 1;
  if (loser > maxLoser) {
    return drawAllowed
      ? t('match.invalid_with_draw', { a, b, n: ppg - 1, ppg, max: maxLoser })
      : t('match.loser_max', { max: maxLoser, ppg });
  }
  return null;
}

// Count series wins from a list of game scores
function _countWins(games) {
  let a = 0, b = 0;
  for (const g of games) {
    if (g.score_a > g.score_b) a++;
    else if (g.score_b > g.score_a) b++;
  }
  return { a, b };
}

// Is the series decided given committed + pending games and best-of?
function _seriesDecided(committed, pending, bestOf) {
  const all = [...committed, ...pending];
  const { a, b } = _countWins(all);
  const need = Math.floor(bestOf / 2) + 1;
  // Series is decided only when one side has the required wins. Reaching the
  // bestOf game count without a winner (e.g. all draws) does NOT decide it —
  // extra legs are needed.
  return a >= need || b >= need;
}

// Read existing input values from the panel (used to preserve typed values
// across grow/shrink re-renders). Returns array indexed by row, with null
// entries for unfilled inputs.
function _scrapeRows(matchUuid) {
  const out = [];
  let i = 0;
  while (true) {
    const va = document.getElementById(`pe-a-${matchUuid}-${i}`);
    const vb = document.getElementById(`pe-b-${matchUuid}-${i}`);
    if (!va && !vb) break;
    out.push({
      score_a: va && va.value !== '' ? parseInt(va.value) : null,
      score_b: vb && vb.value !== '' ? parseInt(vb.value) : null,
    });
    i++;
  }
  return out;
}

// Re-render the entry block for a single match (no full page render).
// Scrapes any currently-typed values before clearing the DOM so they survive
// the grow/shrink that happens after each fill action.
// `focusActive` — when true, focus jumps to the first blank input after render.
function _refreshEntry(matchUuid, tournamentId, stageRules, m, wrapEl = null, focusActive = false) {
  const wrap = wrapEl || document.getElementById(`entry-${matchUuid}`);
  if (!wrap) return;
  let prefill = _scrapeRows(matchUuid);
  // After a failed submit the spinner has already wiped the DOM, so scraping
  // returns nothing — fall back to the last attempt so the user sees all the
  // games they tried to submit, not just an empty panel.
  if (prefill.length === 0 && _failedAttempt.has(matchUuid)) {
    prefill = _failedAttempt.get(matchUuid).map(s => ({ score_a: s.score_a, score_b: s.score_b }));
    _failedAttempt.delete(matchUuid);
  }
  wrap.innerHTML = '';

  if (!_expanded.has(matchUuid)) return;
  const committed = (m.games || []).filter(g => g.is_finished !== false);
  // If server reports match is done, drop expansion and stop — no more legs.
  if (m.status === 'finished') {
    _expanded.delete(matchUuid);
    return;
  }
  const bestOf = m.best_of || stageRules.best_of || 1;
  const ppg = stageRules.points_per_game || 6;
  const scoreCap = stageRules.score_cap || ppg + 4;
  const drawAllowed = stageRules.draw_allowed !== undefined ? stageRules.draw_allowed : true;
  const marginRequired = stageRules.margin_required || 0;
  const marginInDecider = stageRules.margin_in_decider || 0;

  const labelA = m.team_a_name || m.player_a_nickname || t('common.em_dash');
  const labelB = m.team_b_name || m.player_b_nickname || t('common.em_dash');

  // Big prominent panel — visually dominant so it's the focus of the screen
  const panel = UI.html('div', {
    className: 'score-entry-panel',
    style: 'width:100%;background:#fff;border:2px solid #1976d2;border-radius:8px;'
      + 'padding:16px;margin:8px 0;box-shadow:0 2px 12px rgba(25,118,210,0.15);'
      + 'box-sizing:border-box',
  });
  wrap.appendChild(panel);

  // Compute target row count dynamically:
  //   baseRows        = minimum legs that could still decide the series given committed wins
  //   filledFromStart = consecutive prefilled rows from the top (used for decision check)
  //   lastFilledIdx   = index of the last non-blank row (preserves typed values past gaps)
  //   if filledFromStart doesn't decide the series, add one blank row for the next leg
  const need = Math.floor(bestOf / 2) + 1;
  const cWins = _countWins(committed);
  const baseRows = Math.max(1, need - Math.max(cWins.a, cWins.b));
  const filledFromStart = [];
  let stopped = false;
  let lastFilledIdx = -1;
  for (let i = 0; i < prefill.length; i++) {
    const p = prefill[i];
    const blank = p.score_a == null && p.score_b == null;
    if (!blank) lastFilledIdx = i;
    if (!stopped && blank) stopped = true;
    if (!stopped) filledFromStart.push({ score_a: p.score_a ?? 0, score_b: p.score_b ?? 0 });
  }
  const decided = _seriesDecided(committed, filledFromStart, bestOf);
  const numRows = Math.max(baseRows, lastFilledIdx + 1 + (decided ? 0 : 1));

  // Per-row effective margin: if margin_required is set it applies to every game;
  // otherwise margin_in_decider kicks in only on the row that would decide the
  // series (both sides at need-1 wins entering this row).
  const effMargins = [];
  let aw0 = cWins.a, bw0 = cWins.b;
  for (let i = 0; i < numRows; i++) {
    let eff = marginRequired;
    if (eff === 0 && marginInDecider > 0 && aw0 === need - 1 && bw0 === need - 1) eff = marginInDecider;
    effMargins.push(eff);
    const p = prefill[i];
    if (p && (p.score_a != null || p.score_b != null)) {
      const a = p.score_a ?? 0, b = p.score_b ?? 0;
      if (a > b) aw0++; else if (b > a) bw0++;
    }
  }

  const ctx = { matchUuid, tournamentId, stageRules, m, ppg, scoreCap, drawAllowed, marginRequired, marginInDecider, bestOf, numRows, effMargins };
  for (let i = 0; i < numRows; i++) {
    panel.appendChild(_renderRow(ctx, i, labelA, labelB, committed.length, prefill[i] || null));
  }

  // OK / Cancel row
  const okBtn = UI.html('button', {
    className: 'btn btn-primary',
    style: 'flex:1;font-size:1.1rem;padding:12px;min-height:48px',
    onclick: () => _submitOK(ctx),
  }, [t('common.ok')]);
  const cancelBtn = UI.html('button', {
    className: 'btn btn-secondary',
    style: 'min-height:48px;padding:12px 18px',
    onclick: () => {
      _expanded.delete(matchUuid);
      _failedAttempt.delete(matchUuid);
      _refreshEntry(matchUuid, tournamentId, stageRules, m);
    },
  }, [t('common.cancel')]);
  panel.appendChild(UI.html('div', {
    style: 'display:flex;gap:8px;margin-top:14px',
  }, [okBtn, cancelBtn]));

  if (focusActive) {
    setTimeout(() => _focusFirstBlank(matchUuid, numRows), 0);
  }
}

// One editable game row inside the panel. All visible rows are independent
// inputs; the panel renders enough rows to potentially decide the series at
// once. DOM holds typed values until OK. Names are clickable when bestOf > 1
// to fill the row's score (winner = ppg, loser = 0). `prefill` carries values
// scraped from the previous render so they survive grow/shrink re-renders.
function _renderRow(ctx, rowIdx, labelA, labelB, committedBase, prefill) {
  const { matchUuid, tournamentId, stageRules, m, ppg, scoreCap, bestOf } = ctx;
  const aId = `pe-a-${matchUuid}-${rowIdx}`;
  const bId = `pe-b-${matchUuid}-${rowIdx}`;

  const fillFromName = (winnerSide) => {
    const va = document.getElementById(aId);
    const vb = document.getElementById(bId);
    let a = (va.value === '' || va.value == null) ? null : parseInt(va.value);
    let b = (vb.value === '' || vb.value == null) ? null : parseInt(vb.value);
    if (a == null) a = winnerSide === 'a' ? ppg : 0;
    if (b == null) b = winnerSide === 'b' ? ppg : 0;
    va.value = String(a);
    vb.value = String(b);
    _refreshEntry(matchUuid, tournamentId, stageRules, m, null, true);
  };

  const onInputKeydown = (e) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    _maybeAutoSubmit(ctx);
  };

  const aClickable = bestOf > 1;
  const bClickable = bestOf > 1;
  const nameClickStyle = 'cursor:pointer;color:#1976d2;text-decoration:underline;user-select:none';
  const aStyle = `font-size:1.15rem;padding:8px 4px;text-align:right;`
    + (aClickable ? nameClickStyle : 'color:#333');
  const bStyle = `font-size:1.15rem;padding:8px 4px;text-align:left;`
    + (bClickable ? nameClickStyle : 'color:#333');

  // Digit picker buttons for one side (0..ppg). Clicking fills this row's
  // input; see _setDigit for the auto-fill rules of the other side.
  const digitsFor = (side, alignEnd) => {
    const btns = [];
    for (let v = 0; v <= ppg; v++) {
      btns.push(UI.html('button', {
        className: 'btn', type: 'button',
        style: 'min-width:48px;min-height:48px;padding:8px 10px;font-size:1.2rem;font-weight:bold',
        onclick: () => _setDigit(ctx, rowIdx, side, v),
      }, [String(v)]));
    }
    return UI.html('div', {
      style: `display:flex;gap:6px;flex-wrap:wrap;justify-content:${alignEnd ? 'flex-end' : 'flex-start'}`,
    }, btns);
  };

  // Side column: name on top, digit buttons below, aligned to the side.
  const sideColumn = (side, label, nameStyle, clickable) => {
    const nameAttrs = { style: nameStyle };
    if (clickable) {
      nameAttrs.onclick = () => fillFromName(side);
      nameAttrs.title = t('match.click_team_won', { name: label });
    }
    return UI.html('div', {
      style: `flex:1;display:flex;flex-direction:column;align-items:${side === 'a' ? 'flex-end' : 'flex-start'};gap:4px;min-width:0`,
    }, [
      UI.html('span', nameAttrs, [label]),
      digitsFor(side, side === 'a'),
    ]);
  };

  const inputAttrs = (id, value) => {
    const a = {
      type: 'number', id, min: '0', max: String(scoreCap),
      style: 'width:56px;font-size:1.2rem;text-align:center;padding:6px',
      placeholder: '0', onkeydown: onInputKeydown,
    };
    if (value != null) a.value = String(value);
    return a;
  };
  const aPre = prefill?.score_a;
  const bPre = prefill?.score_b;

  return UI.html('div', {
    style: 'display:flex;gap:12px;align-items:center;padding:10px 0;border-bottom:1px dashed #eee',
  }, [
    UI.html('span', { style: 'min-width:32px;color:#999;font-size:0.85rem;align-self:flex-start;padding-top:14px' },
      [t('match.game_label', { n: committedBase + rowIdx + 1 })]),
    sideColumn('a', labelA, aStyle, aClickable),
    UI.html('div', { style: 'display:flex;gap:6px;align-items:center;min-width:140px;justify-content:center' }, [
      UI.html('input', inputAttrs(aId, aPre)),
      UI.html('span', { style: 'font-size:1.3rem' }, [':']),
      UI.html('input', inputAttrs(bId, bPre)),
    ]),
    sideColumn('b', labelB, bStyle, bClickable),
  ]);
}

// Set a digit value into one row's input and auto-fill the other side when
// the outcome is unambiguous (only fills if the other input is blank):
//   - draw value (ppg-1) with drawAllowed → other = ppg-1 (mirror draw)
//   - any losing score (< ppg, and not the draw case above) → other = max(value+margin, ppg)
//     (margin = effective margin for this row; uses margin_in_decider on the deciding leg)
//   - winning score (>= ppg) → leave other blank (user picks loser score)
// Submission only happens via Enter or the OK button.
function _setDigit(ctx, rowIdx, side, value) {
  const { matchUuid, tournamentId, stageRules, m, ppg, drawAllowed, effMargins } = ctx;
  const margin = effMargins[rowIdx] || 0;
  const aId = `pe-a-${matchUuid}-${rowIdx}`;
  const bId = `pe-b-${matchUuid}-${rowIdx}`;
  const va = document.getElementById(aId);
  const vb = document.getElementById(bId);
  if (!va || !vb) return;
  const target = side === 'a' ? va : vb;
  const other = side === 'a' ? vb : va;
  target.value = String(value);
  const otherBlank = (other.value === '' || other.value == null);
  if (otherBlank) {
    if (margin === 0 && drawAllowed && value === ppg - 1) {
      other.value = String(ppg - 1);
    } else if (value < ppg) {
      other.value = String(Math.max(value + (margin || 1), ppg));
    }
  }
  _refreshEntry(matchUuid, tournamentId, stageRules, m, null, true);
}

// Read all visible row inputs into a {filled, error} pair. `filled` is the
// list of validated games up to the first blank row; gaps trigger an error.
function _readRows(ctx) {
  const { matchUuid, numRows, ppg, scoreCap, drawAllowed, effMargins } = ctx;
  const filled = [];
  let seenBlank = false;
  for (let i = 0; i < numRows; i++) {
    const va = document.getElementById(`pe-a-${matchUuid}-${i}`);
    const vb = document.getElementById(`pe-b-${matchUuid}-${i}`);
    const rawA = va?.value;
    const rawB = vb?.value;
    const isBlank = (rawA === '' || rawA == null) && (rawB === '' || rawB == null);
    if (isBlank) { seenBlank = true; continue; }
    if (seenBlank) {
      return { filled: [], error: t('match.no_gaps') };
    }
    const a = (rawA === '' || rawA == null) ? 0 : parseInt(rawA);
    const b = (rawB === '' || rawB == null) ? 0 : parseInt(rawB);
    const err = _validateScore(a, b, ppg, drawAllowed, effMargins[i] || 0, scoreCap);
    if (err) {
      return { filled: [], error: `${t('match.game_label', { n: i + 1 })}: ${err}` };
    }
    filled.push({ score_a: a, score_b: b });
  }
  return { filled, error: null };
}

// Enter handler: if filled rows decide the series, submit; otherwise focus
// the next blank input. Validation errors are silent here — the OK button
// surfaces them when the user explicitly tries to submit.
function _maybeAutoSubmit(ctx) {
  const { m, bestOf, matchUuid, numRows } = ctx;
  const committed = (m.games || []).filter(g => g.is_finished !== false);
  const { filled, error } = _readRows(ctx);
  if (error) return;
  if (filled.length && _seriesDecided(committed, filled, bestOf)) {
    _submitOK(ctx);
  } else {
    _focusFirstBlank(matchUuid, numRows);
  }
}

// Focus the first input that is still blank across all visible rows.
function _focusFirstBlank(matchUuid, numRows) {
  for (let i = 0; i < numRows; i++) {
    const a = document.getElementById(`pe-a-${matchUuid}-${i}`);
    if (a && (a.value === '' || a.value == null)) { a.focus(); return; }
    const b = document.getElementById(`pe-b-${matchUuid}-${i}`);
    if (b && (b.value === '' || b.value == null)) { b.focus(); return; }
  }
}

// OK handler: read all visible rows, validate consecutively, submit in order.
async function _submitOK(ctx) {
  const { matchUuid, tournamentId } = ctx;
  const { filled, error } = _readRows(ctx);
  if (error) { UI.toast(error, 'error'); return; }
  if (!filled.length) return;
  await _submitPending(matchUuid, tournamentId, filled);
}

// Replace the entry panel content with a spinner + "submitting" label.
function _showSubmitting(matchUuid) {
  const wrap = document.getElementById(`entry-${matchUuid}`);
  if (!wrap) return;
  wrap.innerHTML = '';
  wrap.appendChild(UI.html('div', {
    className: 'score-entry-panel',
    style: 'width:100%;background:#fff;border:2px solid #1976d2;border-radius:8px;'
      + 'padding:24px;margin:8px 0;box-shadow:0 2px 12px rgba(25,118,210,0.15);'
      + 'box-sizing:border-box;display:flex;align-items:center;justify-content:center;gap:12px',
  }, [
    UI.html('span', { className: 'spinner' }),
    UI.html('span', { style: 'font-size:1.1rem;color:#1976d2' }, [t('match.submitting')]),
  ]));
}

// Send the given games to the server in a single batched request. Shows a
// spinner immediately. On success the page re-renders; on error the attempted
// scores are stashed in _failedAttempt so the next render restores the full
// dialog (all games, including the ones that were correct) for retry.
async function _submitPending(matchUuid, tournamentId, scores) {
  if (!scores || !scores.length) return;
  _suppressUntil = Date.now() + 5000;
  _showSubmitting(matchUuid);
  try {
    await API.submitScores(matchUuid, scores);
    _failedAttempt.delete(matchUuid);
    UI.toast(t('match.score_submitted'), 'success');
  } catch (e) {
    _failedAttempt.set(matchUuid, scores);
    UI.toast(e.message, 'error');
  }
  // render() either collapses the panel (match finished) or re-draws the
  // remaining rows. _expanded is preserved so the panel stays open if needed.
  render(_tournamentId);
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
    if (_expanded.size > 0) return;
    _debouncedRender();
  }
}

function cleanup() { WS.disconnect(); WS.offEvent(onLiveEvent); }

const TournamentDetailPage = { render, cleanup };
export default TournamentDetailPage;