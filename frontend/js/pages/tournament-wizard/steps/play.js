/**
 * Step 5 — Play
 *
 * Score entry for the current (in-progress) round.  Shows only the
 * latest round on the wizard surface — earlier rounds are accessible
 * via the public view.  Standings render on the side for group stages.
 */
import UI from '../../../ui.js';
import API from '../../../api.js';
import { t } from '../../../i18n.js';
import { renderMatch } from '../../tournament-detail/score-entry.js';

export async function renderPlayStep(container, ctx, hooks) {
  const { tournament, currentStage, matches } = ctx;
  if (!currentStage) return;

  const stageMatches = matches.filter(m => m.stage_id === currentStage.uuid);
  if (stageMatches.length === 0) {
    container.appendChild(UI.html('div', { className: 'card' }, [
      UI.html('p', {}, [t('wizard.play_no_matches')]),
    ]));
    return;
  }

  const maxRound = Math.max(...stageMatches.map(m => m.round_number || 1));
  const latest = stageMatches.filter(m => (m.round_number || 1) === maxRound);

  // Score entry hooks: bridge to the wizard's WS-suppression + rerender.
  const seHooks = {
    onBeforeSubmit: hooks.onBeforeSubmit,
    rerender: hooks.rerender,
  };

  // Header card
  container.appendChild(UI.html('div', { className: 'card' }, [
    UI.html('h3', {}, [t('wizard.play_title', { name: currentStage.name, round: maxRound })]),
    UI.html('p', { className: 'meta' }, [t('wizard.play_intro')]),
  ]));

  // Two-column layout: matches on the left, standings on the right.
  const matchesCol = UI.html('div', { className: 'stage-rounds' });
  const standingsCol = UI.html('div', { className: 'stage-standings' });
  const columns = UI.html('div', { className: 'stage-columns' }, [matchesCol, standingsCol]);
  container.appendChild(columns);

  // Identify "my player" so the score-entry module can highlight my match.
  let myPlayerId = null, myNickname = null;
  try {
    const me = await API.myPlayer(tournament.uuid);
    if (me) { myPlayerId = me.uuid; myNickname = me.nickname; }
  } catch (_) {}

  for (const m of latest) {
    matchesCol.appendChild(renderMatch(
      m, tournament.uuid, myPlayerId, myNickname,
      currentStage.rules || {}, seHooks,
    ));
  }

  // Group stages: live standings table.
  if (currentStage.stage_type === 'group') {
    try {
      const standings = await API.standings(tournament.uuid, currentStage.uuid);
      if (standings?.length) {
        standingsCol.appendChild(UI.html('h4', {}, [t('match.standings')]));
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
        standingsCol.appendChild(tbl);
      }
    } catch (_) { /* no standings yet */ }
  }
}
