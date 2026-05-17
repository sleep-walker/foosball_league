/**
 * Wizard step derivation — pure function over the current tournament
 * state. No DOM, no API; the host fetches data once per render and
 * calls deriveStep() to figure out which step to display.
 *
 * Step IDs are stable strings (not numbers) so reordering doesn't
 * silently mess with bookmarks (?step=play stays meaningful).
 *
 * Step flow:
 *   setup    → tournament basics (name, league, mode)
 *   players  → registration / approving applicants
 *   stage    → add first stage when there are enough players
 *   rules    → configure the active stage's rules + draw first round
 *   play     → score entry for the current round
 *   advance  → between rounds: draw next, or finish the stage
 *   next     → stage finished: add another or close the tournament
 *   done     → tournament finished
 */

export const STEPS = ['setup', 'players', 'stage', 'rules', 'play', 'advance', 'next', 'done'];

export const MIN_PLAYERS_SINGLES = 2;
export const MIN_PLAYERS_DOUBLES = 4;

/**
 * Decide the natural step to land on, given the live state.
 *
 * @param {object} ctx
 * @param {object} ctx.tournament      Tournament summary (has .status, .player_mode).
 * @param {Array}  ctx.stages          Stage list (status, ordering).
 * @param {Array}  ctx.players         Registered players (excluding applicants).
 * @param {Array}  ctx.applicants      Pending applicants.
 * @param {Array}  ctx.matches         All matches (used to check round progress).
 * @returns {{ step: string, currentStage: object|null, reason: string }}
 */
export function deriveStep(ctx) {
  const { tournament, stages = [], players = [], applicants = [], matches = [] } = ctx;
  const tStatus = tournament?.status || 'registration';

  if (tStatus === 'finished') {
    return { step: 'done', currentStage: null, reason: 'tournament finished' };
  }

  const minPlayers = (tournament?.player_mode === 'doubles') ? MIN_PLAYERS_DOUBLES : MIN_PLAYERS_SINGLES;

  // --- registration phase --------------------------------------------------
  if (tStatus === 'registration') {
    if (!tournament?.name) {
      return { step: 'setup', currentStage: null, reason: 'no tournament name yet' };
    }
    if (players.length < minPlayers || applicants.length > 0) {
      return { step: 'players', currentStage: null, reason: 'collecting players / applicants' };
    }
    if (stages.length === 0) {
      return { step: 'stage', currentStage: null, reason: 'enough players, no stage yet' };
    }
    // Players ok + stage exists but tournament not started → still on players
    // step (organiser needs to hit "Start tournament" which lives there).
    return { step: 'players', currentStage: null, reason: 'ready to start' };
  }

  // --- running phase -------------------------------------------------------
  const active = stages.find(s => s.status === 'active');
  const preparing = stages.find(s => s.status === 'preparing');

  if (active) {
    const stageMatches = matches.filter(m => m.stage_id === active.uuid);
    if (stageMatches.length === 0) {
      // Just-activated stage with no matches drawn yet.
      return { step: 'rules', currentStage: active, reason: 'stage active, no matches drawn' };
    }
    const maxRound = Math.max(...stageMatches.map(m => m.round_number || 1));
    const latest = stageMatches.filter(m => (m.round_number || 1) === maxRound);
    const allDone = latest.length > 0 && latest.every(m => m.status === 'finished');
    if (allDone) {
      return { step: 'advance', currentStage: active, reason: 'round complete' };
    }
    return { step: 'play', currentStage: active, reason: 'matches in progress' };
  }

  if (preparing) {
    return { step: 'rules', currentStage: preparing, reason: 'stage prepared, awaiting activation' };
  }

  // No active or preparing stage but tournament still running → all stages
  // are finished, organiser must decide next move.
  return { step: 'next', currentStage: null, reason: 'between stages' };
}

/**
 * Validate a step name from URL query and return either it (when allowed
 * given current state) or the natural derived step.
 *
 * Locking rule: we only "down-shift" — if the user asks for a step the
 * state hasn't reached yet (e.g. ?step=play but tournament is still in
 * registration), we ignore the override.  Going backwards is always OK.
 */
export function resolveStep(requestedStep, derived) {
  if (!requestedStep || !STEPS.includes(requestedStep)) return derived.step;
  const reqIdx = STEPS.indexOf(requestedStep);
  const derIdx = STEPS.indexOf(derived.step);
  return reqIdx <= derIdx ? requestedStep : derived.step;
}
