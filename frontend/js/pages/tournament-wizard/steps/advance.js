/**
 * Step 6 — Advance / Finish stage
 *
 * The current round is complete.  Group stages get two options:
 * draw another round, or finish the stage.  Elimination stages
 * (no consolation) auto-flow into the next bracket round and we
 * mostly just offer "Finish stage" once the final is done.
 *
 * We also surface the latest results + current standings as a
 * sanity check before the organiser commits to the next move.
 */
import UI from '../../../ui.js';
import API from '../../../api.js';
import { t } from '../../../i18n.js';

export async function renderAdvanceStep(container, ctx, hooks) {
  const { tournament, currentStage, matches } = ctx;
  if (!currentStage) return;

  const isGroup = currentStage.stage_type === 'group';
  const stageMatches = matches.filter(m => m.stage_id === currentStage.uuid);
  const maxRound = Math.max(...stageMatches.map(m => m.round_number || 1));
  const latest = stageMatches.filter(m => (m.round_number || 1) === maxRound);

  container.appendChild(UI.html('div', { className: 'card' }, [
    UI.html('h3', {}, [t('wizard.advance_title', { name: currentStage.name, round: maxRound })]),
    UI.html('p', { className: 'meta' }, [t('wizard.advance_intro')]),
  ]));

  // Round summary (last results)
  const summaryCard = UI.html('div', { className: 'card' }, [
    UI.html('h4', {}, [t('wizard.advance_results_title', { round: maxRound })]),
  ]);
  for (const m of latest) {
    const labelA = m.team_a_name || m.player_a_nickname || '?';
    const labelB = m.team_b_name || m.player_b_nickname || '?';
    summaryCard.appendChild(UI.html('div', {
      style: 'display:flex;gap:12px;align-items:center;padding:6px 0;border-bottom:1px solid #f0f0f0',
    }, [
      UI.html('span', { style: 'flex:1;text-align:right' }, [labelA]),
      UI.html('strong', { style: 'min-width:60px;text-align:center' }, [
        `${m.score_a ?? 0} : ${m.score_b ?? 0}`,
      ]),
      UI.html('span', { style: 'flex:1' }, [labelB]),
    ]));
  }
  container.appendChild(summaryCard);

  // Standings snapshot (group only)
  if (isGroup) {
    try {
      const standings = await API.standings(tournament.uuid, currentStage.uuid);
      if (standings?.length) {
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
            UI.html('td', {}, [s.nickname || '?']),
            UI.html('td', {}, [String(s.points)]),
            UI.html('td', {}, [String(s.wins)]),
            UI.html('td', {}, [String(s.draws)]),
            UI.html('td', {}, [String(s.losses)]),
            UI.html('td', {}, [`${s.goals_for || 0}:${s.goals_against || 0}`]),
          ]));
        });
        tbl.appendChild(tbody);
        container.appendChild(UI.html('div', { className: 'card' }, [
          UI.html('h4', {}, [t('match.standings')]),
          tbl,
        ]));
      }
    } catch (_) {}
  }

  // Action footer
  const actions = UI.html('div', { className: 'card' });
  actions.appendChild(UI.html('h4', {}, [t('wizard.advance_actions_title')]));

  const buttonRow = UI.html('div', { style: 'display:flex;gap:12px;flex-wrap:wrap' });

  if (isGroup) {
    buttonRow.appendChild(UI.html('button', {
      className: 'btn btn-primary',
      onclick: () => hooks.doAction(
        () => API.drawRound(tournament.uuid, currentStage.uuid),
        t('stage.round_drawn'),
      ),
    }, [t('wizard.draw_next_round')]));
  }

  buttonRow.appendChild(UI.html('button', {
    className: 'btn btn-secondary',
    onclick: () => hooks.doAction(
      () => API.post(`/api/v1/tournaments/${tournament.uuid}/stages/${currentStage.uuid}/finish`),
      t('stage.finished'),
    ),
  }, [t('wizard.finish_stage')]));

  actions.appendChild(buttonRow);
  container.appendChild(actions);
}
