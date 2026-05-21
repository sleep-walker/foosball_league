/**
 * Step 4 — Configure stage
 *
 * Two sub-cases:
 *   A) stage is `preparing`  → show rules editor + "Activate stage" button
 *   B) stage is `active` but no matches drawn yet → "Draw first round"
 *
 * The rules editor module already handles the active-stage warning and
 * the force=true override, so we can pass the stage through directly.
 */
import UI from '../../../ui.js';
import API from '../../../api.js';
import { t } from '../../../i18n.js';
import { showRulesEditor } from '../../tournament-detail/rules-editor.js';

export async function renderRulesStep(container, ctx, hooks) {
  const { tournament, currentStage } = ctx;
  if (!currentStage) return;

  const isPreparing = currentStage.status === 'preparing';
  const isElim = currentStage.stage_type === 'elimination';

  // League rules (for the rules editor presets).
  let leagueRules = null;
  if (tournament.league_id) {
    try {
      const league = await API.get(`/api/v1/leagues/${tournament.league_id}`);
      leagueRules = league?.default_game_rules || null;
    } catch (_) {}
  }

  container.appendChild(UI.html('div', { className: 'card' }, [
    UI.html('h3', {}, [t(isPreparing ? 'wizard.rules_title_prepare' : 'wizard.rules_title_draw',
                       { name: currentStage.name })]),
    UI.html('p', { className: 'meta' }, [
      t(isPreparing ? 'wizard.rules_intro_prepare' : 'wizard.rules_intro_draw'),
    ]),
  ]));

  // Inline rules editor — the existing module appends itself to the card
  // whose <h3> contains the stage name, so we need a host card with
  // that header.
  const editorCard = UI.html('div', { className: 'card' }, [
    UI.html('h3', {}, [currentStage.name]),
    UI.html('div', { className: 'meta', style: 'margin-bottom: 8px' }, [
      t(`stage.type_${currentStage.stage_type}`),
    ]),
  ]);
  container.appendChild(editorCard);

  // Auto-open the rules editor for preparing stages so the user sees
  // exactly what they're activating.
  if (isPreparing) {
    await showRulesEditor(
      tournament.uuid,
      currentStage,
      leagueRules,
      tournament.league_id,
      hooks.rerender,
    );
  }

  // Action footer — primary CTA so the next step is unmissable.
  if (isPreparing) {
    container.appendChild(UI.html('div', { className: 'wizard-cta' }, [
      UI.html('h4', {}, [t('wizard.rules_ready_title')]),
      UI.html('p', {}, [t('wizard.rules_ready_intro')]),
      UI.html('button', {
        className: 'btn btn-primary',
        onclick: () => hooks.doAction(async () => {
          await API.post(`/api/v1/tournaments/${tournament.uuid}/stages/${currentStage.uuid}/activate`);
          if (isElim) {
            // Elimination stages need a seeded bracket — generate it
            // right after activation so the user lands on Play step.
            await API.generateBracket(tournament.uuid, currentStage.uuid);
          }
        }, isElim ? t('stage.activated_bracket') : t('stage.activated')),
      }, [isElim ? t('wizard.activate_with_bracket') : t('wizard.activate_stage')]),
    ]));
  } else {
    // Active stage with no matches yet — group stages need an explicit
    // first draw; elimination is already bracketed by the activation step.
    container.appendChild(UI.html('div', { className: 'wizard-cta' }, [
      UI.html('h4', {}, [t('wizard.rules_draw_cta_title')]),
      UI.html('p', {}, [t('wizard.rules_draw_cta_intro')]),
      UI.html('button', {
        className: 'btn btn-primary',
        onclick: () => hooks.doAction(
          () => API.drawRound(tournament.uuid, currentStage.uuid),
          t('stage.round_drawn'),
        ),
      }, [t('wizard.draw_first_round')]),
    ]));
  }
}
