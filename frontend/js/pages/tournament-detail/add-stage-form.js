/**
 * "Add new stage" form — appears on the tournament detail page when the
 * organiser wants to add another group/elimination round.
 *
 * Extracted from tournament-detail.js. Self-contained: builds its own
 * DOM, validates input on submit, posts to /stages/ and asks the host
 * to re-render via `rerender` hook.
 */
import UI from '../../ui.js';
import API from '../../api.js';
import { t } from '../../i18n.js';

export function buildAddStageForm(tournamentId, playerMode = 'singles', rerender = () => {}) {
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
          rerender();
        } catch (e) { UI.toast(e.message, 'error'); }
      },
    }, [t('stage.create')]),
  ]);
}
