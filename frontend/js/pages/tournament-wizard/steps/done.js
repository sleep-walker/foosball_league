/**
 * Step 8 — Done
 *
 * Tournament is finished.  Show final summary + link to the public
 * view for sharing.
 */
import UI from '../../../ui.js';
import { t } from '../../../i18n.js';

export async function renderDoneStep(container, ctx, _hooks) {
  const { tournament, stages, players } = ctx;

  container.appendChild(UI.html('div', { className: 'wizard-cta wizard-cta-success' }, [
    UI.html('h3', {}, [t('wizard.done_title')]),
    UI.html('p', {}, [t('wizard.done_intro', { name: tournament.name })]),
  ]));

  // Summary stats
  container.appendChild(UI.html('div', { className: 'card' }, [
    UI.html('h4', {}, [t('wizard.done_stats_title')]),
    UI.html('ul', { style: 'margin: 8px 0; padding-left: 20px' }, [
      UI.html('li', {}, [t('wizard.done_stages_count', { count: stages.length })]),
      UI.html('li', {}, [t('wizard.done_players_count', { count: players.length })]),
    ]),
  ]));

  // Stages overview
  if (stages.length > 0) {
    const list = UI.html('ol', { style: 'margin: 8px 0; padding-left: 20px' });
    for (const s of stages) {
      list.appendChild(UI.html('li', {}, [
        `${s.name} — ${t(`stage.type_${s.stage_type}`)} (${t(`status.${s.status}`)})`,
      ]));
    }
    container.appendChild(UI.html('div', { className: 'card' }, [
      UI.html('h4', {}, [t('wizard.done_stages_title')]),
      list,
    ]));
  }

  // Share / actions
  container.appendChild(UI.html('div', { className: 'card' }, [
    UI.html('h4', {}, [t('wizard.done_share_title')]),
    UI.html('p', { className: 'meta' }, [t('wizard.done_share_intro')]),
    UI.html('a', {
      href: `#tournament-detail/${tournament.uuid}`,
      className: 'btn btn-secondary',
      style: 'margin-right: 8px',
    }, [t('wizard.view_public')]),
  ]));
}
