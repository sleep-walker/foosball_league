/**
 * Tournament wizard — organiser-facing stepper that walks through the
 * tournament lifecycle one phase at a time.
 *
 * Architecture:
 *   - wizard-state.js  derives the natural step from the live state
 *   - stepper.js       renders the top breadcrumb
 *   - steps/*.js       one file per step UI
 *   - this file        page glue: fetches state, picks the step, mounts
 *
 * Reuses existing extracted modules where possible:
 *   - players-tab.js     for player registration UI
 *   - rules-editor.js    for rules editing UI
 *   - add-stage-form.js  for "add new stage"
 *   - score-entry.js     for match score input
 *
 * Anonymous viewers and non-organisers should keep using the public
 * read-only view (tournament-detail.js).  This page assumes the
 * current user has organiser rights for the tournament.
 */
import UI from '../ui.js';
import API from '../api.js';
import WS from '../ws.js';
import { t } from '../i18n.js';

import { deriveStep, resolveStep } from './tournament-wizard/wizard-state.js';
import { renderStepper, renderProgress } from './tournament-wizard/stepper.js';
import { renderSetupStep } from './tournament-wizard/steps/setup.js';
import { renderPlayersStep } from './tournament-wizard/steps/players.js';
import { renderStageStep } from './tournament-wizard/steps/stage.js';
import { renderRulesStep } from './tournament-wizard/steps/rules.js';
import { renderPlayStep } from './tournament-wizard/steps/play.js';
import { renderAdvanceStep } from './tournament-wizard/steps/advance.js';
import { renderNextStep } from './tournament-wizard/steps/next.js';
import { renderDoneStep } from './tournament-wizard/steps/done.js';

let _tournamentId = null;
let _requestedStep = null;   // override from URL ?step=X (if still allowed)
let _wsConnected = false;
let _suppressUntil = 0;
let _renderTimeout = null;

const STEP_RENDERERS = {
  setup:   renderSetupStep,
  players: renderPlayersStep,
  stage:   renderStageStep,
  rules:   renderRulesStep,
  play:    renderPlayStep,
  advance: renderAdvanceStep,
  next:    renderNextStep,
  done:    renderDoneStep,
};

// Hooks handed to every step.  Pages call them when they finish a
// mutation so we re-render and (in the case of submit) suppress WS.
const _hooks = {
  rerender: () => render(_tournamentId, { keepRequestedStep: true }),
  onBeforeSubmit: () => { _suppressUntil = Date.now() + 5000; },
  doAction: async (fn, successMsg) => {
    try {
      await fn();
      UI.toast(successMsg, 'success');
      _suppressUntil = Date.now() + 2000;
      _hooks.rerender();
    } catch (e) { UI.toast(e.message, 'error'); }
  },
  navigate: (step) => {
    _requestedStep = step;
    _updateHashStep(step);
    _hooks.rerender();
  },
};

function _readStepFromHash() {
  // Hash format set by app.js: tournament-wizard/<uuid>?step=<step>
  // We accept ?step=X appended to the param part.
  const hash = window.location.hash.slice(1);
  const m = hash.match(/\?step=([a-z]+)/);
  return m ? m[1] : null;
}

function _updateHashStep(step) {
  const hash = window.location.hash.slice(1);
  const base = hash.split('?')[0];
  const next = step ? `${base}?step=${step}` : base;
  if (next !== hash) {
    history.replaceState(null, '', '#' + next);
  }
}

async function render(id, opts = {}) {
  _tournamentId = id;
  if (!opts.keepRequestedStep) {
    _requestedStep = _readStepFromHash();
  }

  const container = document.getElementById('app-content');
  if (!container) return;

  // Show a small loading hint on the first render only — re-renders
  // (post mutation) keep the old DOM until the new one is ready to
  // swap, which avoids flicker.
  if (!container.querySelector('.wizard-root')) {
    container.innerHTML = '';
    container.appendChild(UI.html('div', { className: 'wizard-root' }, [
      UI.html('p', { className: 'meta' }, [t('common.loading')]),
    ]));
  }

  // --- fetch state -------------------------------------------------------
  let tournament, stages = [], players = [], applicants = [], matches = [];
  try {
    tournament = await API.tournament(id);
  } catch (e) {
    container.innerHTML = '';
    container.appendChild(UI.html('div', { className: 'card' }, [
      UI.html('p', {}, [`${t('common.error')}: ${e.message}`]),
    ]));
    return;
  }

  // The wizard is for organisers.  Anonymous / non-organiser visitors
  // are pushed to the read-only public view.  We can't yet *prove*
  // organisership client-side (no /me/can_edit endpoint) so we use
  // logged-in as a proxy; the backend rejects unauthorised mutations
  // anyway.
  if (!API.isLoggedIn()) {
    window.App.navigate('tournament-detail', id);
    return;
  }

  // The /tournaments/{id} response already nests stages, registrations
  // and applicants, so we only need an extra request for matches.
  stages = tournament.stages || [];
  players = tournament.registrations || [];
  applicants = tournament.applicants || [];

  try {
    matches = await API.matches(id);
  } catch (_) {}

  // --- decide step -------------------------------------------------------
  const derived = deriveStep({ tournament, stages, players, applicants, matches });
  const step = resolveStep(_requestedStep, derived);

  // If the URL asked for a step we can no longer honour (e.g. tournament
  // moved past it), drop the override and surface the natural step.
  if (_requestedStep && step === derived.step && _requestedStep !== derived.step) {
    _requestedStep = null;
    _updateHashStep(null);
  } else if (step !== derived.step) {
    _updateHashStep(step);
  } else {
    _updateHashStep(null);
  }

  // --- render -----------------------------------------------------------
  const root = UI.html('div', { className: 'wizard-root' });

  // Header: tournament name + status badge + public-view link.
  // CSS class .wizard-header keeps the layout (incl. dark-mode rules)
  // out of the JS file.
  root.appendChild(UI.html('div', { className: 'wizard-header' }, [
    UI.html('h2', {}, [tournament.name || t('tournament.title')]),
    UI.html('span', {
      className: `badge badge-${tournament.status || 'registration'}`,
    }, [t(`status.${tournament.status || 'registration'}`)]),
    UI.html('a', {
      href: `#tournament-detail/${id}`,
      className: 'wizard-public-link',
    }, [t('wizard.view_public')]),
  ]));

  // Slim progress bar above the breadcrumb gives users an at-a-glance
  // sense of where they are without forcing them to count steps.
  root.appendChild(renderProgress(derived.step));

  // Stepper (renders both desktop + mobile variants; CSS picks one).
  root.appendChild(renderStepper(step, derived.step, (s) => _hooks.navigate(s)));

  // Step content
  const stepRenderer = STEP_RENDERERS[step] || STEP_RENDERERS.setup;
  const ctx = { tournament, stages, players, applicants, matches, currentStage: derived.currentStage };
  const stepBody = UI.html('div', { className: 'wizard-step-body' });
  root.appendChild(stepBody);

  // Replace old root atomically so we don't see a flash
  const old = container.querySelector('.wizard-root');
  if (old) container.replaceChild(root, old);
  else { container.innerHTML = ''; container.appendChild(root); }

  await stepRenderer(stepBody, ctx, _hooks);

  // --- ws -------------------------------------------------------------
  if (!_wsConnected) {
    WS.connect();
    WS.onEvent(onLiveEvent);
    _wsConnected = true;
  }
}

function _debouncedRender() {
  if (_renderTimeout) clearTimeout(_renderTimeout);
  _renderTimeout = setTimeout(() => render(_tournamentId, { keepRequestedStep: true }), 500);
}

function onLiveEvent(event) {
  if (Date.now() < _suppressUntil) return;
  if (['round_drawn', 'bracket_generated', 'match_finished', 'score_updated', 'applicant_registered'].includes(event.type)) {
    _debouncedRender();
  }
}

function cleanup() {
  WS.disconnect();
  WS.offEvent(onLiveEvent);
  _wsConnected = false;
  if (_renderTimeout) clearTimeout(_renderTimeout);
}

const TournamentWizardPage = { render, cleanup };
export default TournamentWizardPage;
