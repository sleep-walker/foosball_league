/**
 * Stepper navigation — the top breadcrumb of the wizard.  Shows all
 * steps in order with the current one highlighted; completed steps
 * become clickable (free back-navigation).  Steps the state hasn't
 * reached yet are dimmed and inert.
 *
 * The wizard derives the "natural" step from state; this component
 * is just visualisation + click-to-go-back.
 */
import UI from '../../ui.js';
import { t } from '../../i18n.js';
import { STEPS } from './wizard-state.js';

export function renderStepper(currentStep, derivedStep, onJump) {
  const curIdx = STEPS.indexOf(currentStep);
  const derIdx = STEPS.indexOf(derivedStep);

  const labels = {
    setup:    t('wizard.step_setup'),
    players:  t('wizard.step_players'),
    stage:    t('wizard.step_stage'),
    rules:    t('wizard.step_rules'),
    play:     t('wizard.step_play'),
    advance:  t('wizard.step_advance'),
    next:     t('wizard.step_next'),
    done:     t('wizard.step_done'),
  };

  const items = STEPS.map((step, i) => {
    const reached = i <= derIdx;
    const isCurrent = step === currentStep;
    const clickable = reached && !isCurrent;
    return UI.html('button', {
      type: 'button',
      className: 'wizard-step' + (isCurrent ? ' is-current' : '') + (reached ? ' is-reached' : ''),
      disabled: !clickable,
      style: 'padding: 6px 12px; border: none; background: transparent; color: '
        + (isCurrent ? '#1976d2'
           : reached ? '#333'
           : '#aaa')
        + '; font-weight: ' + (isCurrent ? 'bold' : 'normal')
        + '; cursor: ' + (clickable ? 'pointer' : 'default')
        + '; border-bottom: 2px solid ' + (isCurrent ? '#1976d2' : 'transparent'),
      onclick: clickable ? () => onJump(step) : null,
    }, [`${i + 1}. ${labels[step] || step}`]);
  });

  return UI.html('nav', {
    className: 'wizard-stepper',
    style: 'display: flex; gap: 4px; flex-wrap: wrap; padding: 12px 0; '
      + 'border-bottom: 1px solid #eee; margin-bottom: 16px; overflow-x: auto',
  }, items);
}
