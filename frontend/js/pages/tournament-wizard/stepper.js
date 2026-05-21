/**
 * Stepper navigation — the top breadcrumb of the wizard.
 *
 * Two modes (swapped by CSS media query at 768px):
 *   - desktop: horizontal list of all 8 steps
 *   - mobile:  "Step X of 8: <Label>" with Back/Next pills
 *
 * Both modes are built unconditionally; CSS hides the one that
 * doesn't fit.  This way the user can resize freely without us
 * having to listen for breakpoints.
 *
 * The wizard derives the "natural" step from state; this component
 * is just visualisation + click-to-go-back.
 */
import UI from '../../ui.js';
import { t } from '../../i18n.js';
import { STEPS } from './wizard-state.js';

function _labels() {
  return {
    setup:    t('wizard.step_setup'),
    players:  t('wizard.step_players'),
    stage:    t('wizard.step_stage'),
    rules:    t('wizard.step_rules'),
    play:     t('wizard.step_play'),
    advance:  t('wizard.step_advance'),
    next:     t('wizard.step_next'),
    done:     t('wizard.step_done'),
  };
}

function _desktopStepper(currentStep, derivedIdx, labels, onJump) {
  const items = STEPS.map((step, i) => {
    const reached = i <= derivedIdx;
    const isCurrent = step === currentStep;
    const clickable = reached && !isCurrent;
    const cls = ['wizard-step'];
    if (reached) cls.push('is-reached');
    if (isCurrent) cls.push('is-current');
    return UI.html('button', {
      type: 'button',
      className: cls.join(' '),
      disabled: !clickable,
      onclick: clickable ? () => onJump(step) : null,
    }, [`${i + 1}. ${labels[step] || step}`]);
  });
  return UI.html('nav', { className: 'wizard-stepper' }, items);
}

function _mobileStepper(currentStep, derivedIdx, labels, onJump) {
  const curIdx = STEPS.indexOf(currentStep);
  const prev = curIdx > 0 ? STEPS[curIdx - 1] : null;
  const next = curIdx < derivedIdx ? STEPS[curIdx + 1] : null;

  const backBtn = UI.html('button', {
    type: 'button',
    className: 'btn btn-secondary btn-sm',
    disabled: !prev,
    onclick: prev ? () => onJump(prev) : null,
  }, ['← ' + t('wizard.back')]);

  const center = UI.html('span', {}, [
    t('wizard.step_x_of_n', { x: curIdx + 1, n: STEPS.length }),
    ' · ',
    UI.html('strong', {}, [labels[currentStep] || currentStep]),
  ]);

  const fwdBtn = UI.html('button', {
    type: 'button',
    className: 'btn btn-secondary btn-sm',
    disabled: !next,
    onclick: next ? () => onJump(next) : null,
  }, [t('wizard.forward') + ' →']);

  return UI.html('div', { className: 'wizard-stepper-mobile' }, [backBtn, center, fwdBtn]);
}

export function renderStepper(currentStep, derivedStep, onJump) {
  const derivedIdx = STEPS.indexOf(derivedStep);
  const labels = _labels();
  // Return a fragment-like wrapper so the host can append both
  // variants — CSS picks the right one at runtime.
  const wrap = UI.html('div', {});
  wrap.appendChild(_desktopStepper(currentStep, derivedIdx, labels, onJump));
  wrap.appendChild(_mobileStepper(currentStep, derivedIdx, labels, onJump));
  return wrap;
}

/**
 * Progress bar — slim accent above the stepper showing how far
 * along the wizard the tournament is.  Same input as renderStepper.
 */
export function renderProgress(derivedStep) {
  const derivedIdx = STEPS.indexOf(derivedStep);
  // Progress = derivedIdx / (STEPS.length - 1) — done step is 100%.
  const pct = Math.round((derivedIdx / (STEPS.length - 1)) * 100);
  return UI.html('div', { className: 'wizard-progress' }, [
    UI.html('div', { className: 'wizard-progress-fill', style: `width: ${pct}%` }),
  ]);
}
