/**
 * Step 3 — Add first stage
 *
 * Shown when the tournament has enough players but no stage yet.
 * Reuses add-stage-form.js for the form itself.
 */
import UI from '../../../ui.js';
import { t } from '../../../i18n.js';
import { buildAddStageForm } from '../../tournament-detail/add-stage-form.js';

export async function renderStageStep(container, ctx, hooks) {
  const { tournament } = ctx;

  container.appendChild(UI.html('div', { className: 'card' }, [
    UI.html('h3', {}, [t('wizard.stage_title')]),
    UI.html('p', { className: 'meta' }, [t('wizard.stage_intro')]),
  ]));

  container.appendChild(buildAddStageForm(
    tournament.uuid,
    tournament.player_mode || 'singles',
    hooks.rerender,
  ));
}
