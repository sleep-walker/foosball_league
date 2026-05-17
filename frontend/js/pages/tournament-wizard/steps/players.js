/**
 * Step 2 — Players
 *
 * Reuses the players-tab module from tournament-detail/.  Adds a big
 * "Start tournament" button at the bottom that lights up once enough
 * players have registered (no applicants pending).
 */
import UI from '../../../ui.js';
import API from '../../../api.js';
import { t } from '../../../i18n.js';
import { renderPlayers } from '../../tournament-detail/players-tab.js';
import { MIN_PLAYERS_SINGLES, MIN_PLAYERS_DOUBLES } from '../wizard-state.js';

export async function renderPlayersStep(container, ctx, hooks) {
  const { tournament, players, applicants } = ctx;
  const minPlayers = (tournament.player_mode === 'doubles') ? MIN_PLAYERS_DOUBLES : MIN_PLAYERS_SINGLES;

  container.appendChild(UI.html('div', { className: 'card' }, [
    UI.html('h3', {}, [t('wizard.players_title')]),
    UI.html('p', { className: 'meta' }, [t('wizard.players_intro', { n: minPlayers })]),
  ]));

  // Embed the existing players-tab module — it already has all the
  // tabs (applicants / from league / all players / new), drag-drop
  // for doubles team formation, etc.
  const playersBlock = await renderPlayers(tournament.uuid, tournament, null, {
    rerender: hooks.rerender,
    doAction: hooks.doAction,
  });
  container.appendChild(playersBlock);

  // Footer: start-tournament action when we're ready, or guidance otherwise.
  const ready = players.length >= minPlayers && applicants.length === 0
    && tournament.status === 'registration';

  if (ready) {
    container.appendChild(UI.html('div', { className: 'card' }, [
      UI.html('h4', {}, [t('wizard.players_ready_title')]),
      UI.html('p', { className: 'meta' }, [t('wizard.players_ready_intro')]),
      UI.html('button', {
        className: 'btn btn-primary',
        style: 'font-size: 1.05rem; padding: 12px 24px',
        onclick: () => hooks.doAction(
          () => API.startTournament(tournament.uuid),
          t('tournament.started'),
        ),
      }, [t('wizard.start_tournament')]),
    ]));
  } else if (applicants.length > 0) {
    container.appendChild(UI.html('div', { className: 'card', style: 'border-left: 3px solid #e67e22' }, [
      UI.html('p', { className: 'meta' }, [
        t('wizard.players_pending_applicants', { count: applicants.length }),
      ]),
    ]));
  } else if (players.length < minPlayers) {
    container.appendChild(UI.html('div', { className: 'card', style: 'border-left: 3px solid #e67e22' }, [
      UI.html('p', { className: 'meta' }, [
        t('wizard.players_need_more', { have: players.length, need: minPlayers }),
      ]),
    ]));
  }
}
