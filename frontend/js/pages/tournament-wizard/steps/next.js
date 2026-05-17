/**
 * Step 7 — Between stages
 *
 * Reached after a stage finishes when the tournament hasn't been
 * closed yet.  Two choices: add another stage, or finish the
 * tournament for good.
 */
import UI from '../../../ui.js';
import API from '../../../api.js';
import { t } from '../../../i18n.js';
import { buildAddStageForm } from '../../tournament-detail/add-stage-form.js';

export async function renderNextStep(container, ctx, hooks) {
  const { tournament, stages } = ctx;

  const finishedStages = stages.filter(s => s.status === 'finished');

  container.appendChild(UI.html('div', { className: 'card' }, [
    UI.html('h3', {}, [t('wizard.next_title')]),
    UI.html('p', { className: 'meta' }, [t('wizard.next_intro', { count: finishedStages.length })]),
  ]));

  // Quick summary of finished stages
  if (finishedStages.length > 0) {
    const list = UI.html('ul', { style: 'margin: 8px 0; padding-left: 20px' });
    for (const s of finishedStages) {
      list.appendChild(UI.html('li', {}, [`${s.name} (${t(`stage.type_${s.stage_type}`)})`]));
    }
    container.appendChild(UI.html('div', { className: 'card' }, [
      UI.html('h4', {}, [t('wizard.next_completed_title')]),
      list,
    ]));
  }

  // Option A: add another stage
  container.appendChild(UI.html('div', { className: 'card' }, [
    UI.html('h4', {}, [t('wizard.next_add_another')]),
    UI.html('p', { className: 'meta' }, [t('wizard.next_add_intro')]),
  ]));
  container.appendChild(buildAddStageForm(
    tournament.uuid,
    tournament.player_mode || 'singles',
    hooks.rerender,
  ));

  // Option B: finish the tournament
  container.appendChild(UI.html('div', { className: 'card', style: 'border-left: 3px solid #4caf50' }, [
    UI.html('h4', {}, [t('wizard.next_finish_title')]),
    UI.html('p', { className: 'meta' }, [t('wizard.next_finish_intro')]),
    UI.html('button', {
      className: 'btn btn-primary',
      style: 'font-size: 1.05rem; padding: 12px 24px',
      onclick: () => {
        if (!confirm(t('wizard.next_finish_confirm'))) return;
        hooks.doAction(
          () => API.finishTournament(tournament.uuid),
          t('tournament.finished'),
        );
      },
    }, [t('wizard.finish_tournament')]),
  ]));
}
