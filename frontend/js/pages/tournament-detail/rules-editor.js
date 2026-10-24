/**
 * Stage rules editor — inline panel that appears below a stage card.
 *
 * Extracted from tournament-detail.js to keep that file under control.
 * The editor is fully self-contained: it builds its own DOM via UI.html,
 * fetches league presets, validates input, and POSTs the new rules.
 *
 * The host page passes in a `rerender` callback so we don't have to
 * import the page module back (would create a cycle).
 */
import UI from '../../ui.js';
import API from '../../api.js';
import { t } from '../../i18n.js';

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

export async function showRulesEditor(tournamentId, stage, leagueRules, leagueId, rerender) {
  const r = stage.rules || {};
  const existing = document.getElementById(`rules-editor-${stage.uuid}`);
  if (existing) { existing.remove(); return; } // toggle

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
            const redrawPath = `/api/v1/tournaments/${tournamentId}/stages/${stage.uuid}/redraw-round`;
            try {
              await API.post(redrawPath);
            } catch (redrawErr) {
              // The backend refuses to redraw a round that already has
              // finished matches unless the owner confirms, because the
              // redraw deletes those results.  Relay its message and
              // repeat the request only if the user says yes.
              if (!/force=true/i.test(redrawErr.message || '')) throw redrawErr;
              if (!window.confirm(redrawErr.message)) throw redrawErr;
              await API.post(`${redrawPath}?force=true`);
            }
            UI.toast(t('rules.saved_redrawn'), 'success');
          } else {
            UI.toast(t('rules.saved'), 'success');
          }
          if (typeof rerender === 'function') rerender();
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
