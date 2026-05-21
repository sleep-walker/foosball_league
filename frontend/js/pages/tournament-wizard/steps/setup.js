/**
 * Step 1 — Setup
 *
 * Lets the organiser confirm or edit the tournament basics: name,
 * league, singles/doubles, optional table count.  In MVP we only
 * show name + player_mode (read-only) + a "Next" button — full
 * editing can come later.
 *
 * The wizard auto-advances away from this step as soon as the
 * tournament has a name, so most users will only see it on first
 * creation.
 */
import UI from '../../../ui.js';
import API from '../../../api.js';
import { t } from '../../../i18n.js';

export async function renderSetupStep(container, ctx, hooks) {
  const { tournament } = ctx;

  container.appendChild(UI.html('div', { className: 'card' }, [
    UI.html('h3', {}, [t('wizard.setup_title')]),
    UI.html('p', { className: 'meta' }, [t('wizard.setup_intro')]),
    UI.html('div', { className: 'form-group' }, [
      UI.html('label', {}, [t('common.name')]),
      UI.html('input', {
        id: 'wiz-name',
        type: 'text',
        value: tournament.name || '',
        placeholder: t('tournament.name_placeholder'),
      }),
    ]),
    UI.html('div', { className: 'form-group' }, [
      UI.html('label', {}, [t('tournament.player_mode')]),
      UI.html('div', { className: 'meta' }, [t(`tournament.${tournament.player_mode || 'singles'}`)]),
    ]),
  ]));

  container.appendChild(UI.html('div', { className: 'wizard-cta' }, [
    UI.html('h4', {}, [t('wizard.setup_cta_title')]),
    UI.html('p', {}, [t('wizard.setup_cta_intro')]),
    UI.html('button', {
      className: 'btn btn-primary',
      onclick: () => hooks.doAction(async () => {
        const name = document.getElementById('wiz-name').value.trim();
        if (!name) throw new Error(t('tournament.name_required'));
        if (name !== tournament.name) {
          await API.patch(`/api/v1/tournaments/${tournament.uuid}`, { name });
        }
      }, t('wizard.setup_saved')),
    }, [t('wizard.next')]),
  ]));
}
