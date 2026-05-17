/**
 * Score entry panel — inline editor that appears under each unfinished match.
 *
 * Extracted from tournament-detail.js. The module owns the per-match
 * expansion state (`_expanded`) and the failed-attempt cache so typed
 * scores survive grow/shrink re-renders and post-error retries.
 *
 * Host page wiring: renderMatch() takes a `hooks` object with:
 *   - onBeforeSubmit():  notified before the server call so the page can
 *                        suppress its WS-driven debounced re-render.
 *   - rerender():        called after submit completes to refresh the page.
 */
import UI from '../../ui.js';
import API from '../../api.js';
import { t } from '../../i18n.js';

// Match rows that are expanded for score entry (click-to-expand). DOM is the
// source of truth for typed-but-unsubmitted scores while the panel is open.
const _expanded = new Set();

// Last submission attempt that failed validation, keyed by matchUuid. Consumed
// once on the next _refreshEntry to restore all typed games for retry.
const _failedAttempt = new Map();

// Host-provided hooks; set by renderMatch() for the duration of an entry's
// lifecycle. We keep them at module scope because _setDigit / _submitOK /
// _refreshEntry all need them and threading the object through every helper
// would bloat the signatures considerably.
let _hooks = { onBeforeSubmit: () => {}, rerender: () => {} };

export function hasExpandedRows() {
  return _expanded.size > 0;
}

export function renderMatch(m, tournamentId, myPlayerId, myNickname, stageRules, hooks) {
  if (hooks) _hooks = { onBeforeSubmit: () => {}, rerender: () => {}, ...hooks };
  return _renderMatch(m, tournamentId, myPlayerId, myNickname, stageRules);
}

function _renderMatch(m, tournamentId, myPlayerId, myNickname, stageRules = {}) {
  const dash = t('common.em_dash');
  const labelA = m.team_a_name || m.player_a_nickname || m.player_a_id?.substring(0, 8) || dash;
  const labelB = m.team_b_name || m.player_b_nickname || m.player_b_id?.substring(0, 8) || dash;
  const table = (m.table_number && m.status !== 'finished') ? t('match.table', { n: m.table_number }) : '';
  const bestOf = m.best_of || stageRules.best_of || 1;
  const games = m.games || [];

  // Series wins count
  let winsA = 0, winsB = 0;
  for (const g of games) {
    if (g.score_a > g.score_b) winsA++;
    else if (g.score_b > g.score_a) winsB++;
  }

  // Score display
  let scoreText;
  if (bestOf <= 1) {
    // Single game: show game score or "vs"
    scoreText = m.status === 'finished' ? `${m.score_a ?? 0} : ${m.score_b ?? 0}` : t('match.vs');
  } else {
    // Multi-game: show series score (wins)
    scoreText = m.status === 'finished'
      ? `${winsA} : ${winsB}`
      : (games.length > 0 ? `${winsA} : ${winsB}` : t('match.vs'));
  }

  const isMyMatch = myPlayerId && (
    m.player_a_id === myPlayerId || m.player_b_id === myPlayerId
  ) || myNickname && (
    labelA.includes(myNickname) || labelB.includes(myNickname)
  );
  const highlightStyle = isMyMatch ? 'background: #e3f2fd; border-radius: 4px; padding: 6px 4px;' : 'padding: 6px 0;';

  // Score span — clickable to toggle the entry block when match isn't finished
  const scoreSpan = UI.html('span', {
    id: `score-center-${m.uuid}`,
    style: `padding: 2px 10px; border-radius: 4px; font-weight: bold; ${
      m.status === 'finished' ? 'background: #e8f5e9' : 'background: #f5f5f5; cursor: pointer'
    }`,
    ...(m.status !== 'finished' ? {
      title: t('match.click_score'),
      onclick: () => {
        const opening = !_expanded.has(m.uuid);
        if (opening) _expanded.add(m.uuid);
        else _expanded.delete(m.uuid);
        _refreshEntry(m.uuid, tournamentId, stageRules, m, null, opening);
      },
    } : {}),
  }, [scoreText]);

  const row = UI.html('div', {
    style: `display: flex; align-items: center; gap: 8px; border-bottom: 1px solid #eee; flex-wrap: wrap; ${highlightStyle}`,
  }, [
    ...(table ? [UI.html('span', { className: 'meta', style: 'min-width: 50px' }, [table])] : []),
    UI.html('strong', { style: 'flex: 1; text-align: right; min-width: 80px' }, [labelA]),
    scoreSpan,
    UI.html('strong', { style: 'flex: 1; min-width: 80px' }, [labelB]),
  ]);

  // Show individual committed game scores for multi-game matches
  if (bestOf > 1 && games.length > 0) {
    const gamesLine = UI.html('div', {
      style: 'width: 100%; padding-left: 60px; font-size: 0.8rem; color: #666; margin-top: -4px; margin-bottom: 4px',
    });
    const parts = games.map((g, i) => {
      const bold = (i === games.length - 1 && m.status !== 'finished') ? 'font-weight:bold' : '';
      return `<span style="${bold}">G${i + 1}: ${g.score_a}–${g.score_b}</span>`;
    });
    gamesLine.innerHTML = parts.join(' &nbsp; ');
    row.appendChild(gamesLine);
  }

  // Per-match entry block (collapsed by default, expands when score is clicked)
  if (m.status !== 'finished') {
    const entry = UI.html('div', { id: `entry-${m.uuid}`, style: 'width: 100%' });
    row.appendChild(entry);
    _refreshEntry(m.uuid, tournamentId, stageRules, m, entry);
  }
  return row;
}

/**
 * Client-side score validation — mirrors backend scoring.validate_game_score.
 * Returns error message string or null if valid.
 */
function _validateScore(a, b, ppg, drawAllowed, marginRequired, scoreCap) {
  if (a < 0 || b < 0) return t('match.score_negative');
  if (a === b) {
    if (!drawAllowed) return t('match.draw_not_allowed', { a, b });
    if (a !== ppg - 1) return t('match.draw_must_be', { n: ppg - 1 });
    return null;
  }
  const winner = Math.max(a, b);
  const loser = Math.min(a, b);
  if (marginRequired > 0 && scoreCap > 0) {
    // Deuce rules: win by margin, up to cap
    if (winner === scoreCap && loser === scoreCap - marginRequired) return null;
    if (winner >= ppg && (winner - loser) >= marginRequired && winner <= scoreCap) return null;
    if (winner === ppg && loser < ppg) return null;
    return t('match.invalid_deuce', { a, b, ppg, margin: marginRequired, cap: scoreCap });
  }
  // Simple mode: winner must have exactly ppg points.
  // If draws are allowed at (ppg-1):(ppg-1), loser can have at most ppg-2.
  // If draws are NOT allowed, loser can have at most ppg-1.
  if (winner !== ppg) return t('match.winner_must_reach', { ppg, a, b });
  const maxLoser = drawAllowed ? ppg - 2 : ppg - 1;
  if (loser > maxLoser) {
    return drawAllowed
      ? t('match.invalid_with_draw', { a, b, n: ppg - 1, ppg, max: maxLoser })
      : t('match.loser_max', { max: maxLoser, ppg });
  }
  return null;
}

// Count series wins from a list of game scores
function _countWins(games) {
  let a = 0, b = 0;
  for (const g of games) {
    if (g.score_a > g.score_b) a++;
    else if (g.score_b > g.score_a) b++;
  }
  return { a, b };
}

// Is the series decided given committed + pending games and best-of?
function _seriesDecided(committed, pending, bestOf) {
  const all = [...committed, ...pending];
  const { a, b } = _countWins(all);
  const need = Math.floor(bestOf / 2) + 1;
  // Series is decided only when one side has the required wins. Reaching the
  // bestOf game count without a winner (e.g. all draws) does NOT decide it —
  // extra legs are needed.
  return a >= need || b >= need;
}

// Read existing input values from the panel (used to preserve typed values
// across grow/shrink re-renders). Returns array indexed by row, with null
// entries for unfilled inputs.
function _scrapeRows(matchUuid) {
  const out = [];
  let i = 0;
  while (true) {
    const va = document.getElementById(`pe-a-${matchUuid}-${i}`);
    const vb = document.getElementById(`pe-b-${matchUuid}-${i}`);
    if (!va && !vb) break;
    out.push({
      score_a: va && va.value !== '' ? parseInt(va.value) : null,
      score_b: vb && vb.value !== '' ? parseInt(vb.value) : null,
    });
    i++;
  }
  return out;
}

// Re-render the entry block for a single match (no full page render).
// Scrapes any currently-typed values before clearing the DOM so they survive
// the grow/shrink that happens after each fill action.
// `focusActive` — when true, focus jumps to the first blank input after render.
function _refreshEntry(matchUuid, tournamentId, stageRules, m, wrapEl = null, focusActive = false) {
  const wrap = wrapEl || document.getElementById(`entry-${matchUuid}`);
  if (!wrap) return;
  let prefill = _scrapeRows(matchUuid);
  // After a failed submit the spinner has already wiped the DOM, so scraping
  // returns nothing — fall back to the last attempt so the user sees all the
  // games they tried to submit, not just an empty panel.
  if (prefill.length === 0 && _failedAttempt.has(matchUuid)) {
    prefill = _failedAttempt.get(matchUuid).map(s => ({ score_a: s.score_a, score_b: s.score_b }));
    _failedAttempt.delete(matchUuid);
  }
  wrap.innerHTML = '';

  if (!_expanded.has(matchUuid)) return;
  const committed = (m.games || []).filter(g => g.is_finished !== false);
  // If server reports match is done, drop expansion and stop — no more legs.
  if (m.status === 'finished') {
    _expanded.delete(matchUuid);
    return;
  }
  const bestOf = m.best_of || stageRules.best_of || 1;
  const ppg = stageRules.points_per_game || 6;
  const scoreCap = stageRules.score_cap || ppg + 4;
  const drawAllowed = stageRules.draw_allowed !== undefined ? stageRules.draw_allowed : true;
  const marginRequired = stageRules.margin_required || 0;
  const marginInDecider = stageRules.margin_in_decider || 0;

  const labelA = m.team_a_name || m.player_a_nickname || t('common.em_dash');
  const labelB = m.team_b_name || m.player_b_nickname || t('common.em_dash');

  // Big prominent panel — visually dominant so it's the focus of the screen
  const panel = UI.html('div', {
    className: 'score-entry-panel',
    style: 'width:100%;background:#fff;border:2px solid #1976d2;border-radius:8px;'
      + 'padding:16px;margin:8px 0;box-shadow:0 2px 12px rgba(25,118,210,0.15);'
      + 'box-sizing:border-box',
  });
  wrap.appendChild(panel);

  // Compute target row count dynamically:
  //   baseRows        = minimum legs that could still decide the series given committed wins
  //   filledFromStart = consecutive prefilled rows from the top (used for decision check)
  //   lastFilledIdx   = index of the last non-blank row (preserves typed values past gaps)
  //   if filledFromStart doesn't decide the series, add one blank row for the next leg
  const need = Math.floor(bestOf / 2) + 1;
  const cWins = _countWins(committed);
  const baseRows = Math.max(1, need - Math.max(cWins.a, cWins.b));
  const filledFromStart = [];
  let stopped = false;
  let lastFilledIdx = -1;
  for (let i = 0; i < prefill.length; i++) {
    const p = prefill[i];
    const blank = p.score_a == null && p.score_b == null;
    if (!blank) lastFilledIdx = i;
    if (!stopped && blank) stopped = true;
    if (!stopped) filledFromStart.push({ score_a: p.score_a ?? 0, score_b: p.score_b ?? 0 });
  }
  const decided = _seriesDecided(committed, filledFromStart, bestOf);
  const numRows = Math.max(baseRows, lastFilledIdx + 1 + (decided ? 0 : 1));

  // Per-row effective margin: if margin_required is set it applies to every game;
  // otherwise margin_in_decider kicks in only on the row that would decide the
  // series (both sides at need-1 wins entering this row).
  const effMargins = [];
  let aw0 = cWins.a, bw0 = cWins.b;
  for (let i = 0; i < numRows; i++) {
    let eff = marginRequired;
    if (eff === 0 && marginInDecider > 0 && aw0 === need - 1 && bw0 === need - 1) eff = marginInDecider;
    effMargins.push(eff);
    const p = prefill[i];
    if (p && (p.score_a != null || p.score_b != null)) {
      const a = p.score_a ?? 0, b = p.score_b ?? 0;
      if (a > b) aw0++; else if (b > a) bw0++;
    }
  }

  const ctx = { matchUuid, tournamentId, stageRules, m, ppg, scoreCap, drawAllowed, marginRequired, marginInDecider, bestOf, numRows, effMargins };
  for (let i = 0; i < numRows; i++) {
    panel.appendChild(_renderRow(ctx, i, labelA, labelB, committed.length, prefill[i] || null));
  }

  // OK / Cancel row
  const okBtn = UI.html('button', {
    className: 'btn btn-primary',
    style: 'flex:1;font-size:1.1rem;padding:12px;min-height:48px',
    onclick: () => _submitOK(ctx),
  }, [t('common.ok')]);
  const cancelBtn = UI.html('button', {
    className: 'btn btn-secondary',
    style: 'min-height:48px;padding:12px 18px',
    onclick: () => {
      _expanded.delete(matchUuid);
      _failedAttempt.delete(matchUuid);
      _refreshEntry(matchUuid, tournamentId, stageRules, m);
    },
  }, [t('common.cancel')]);
  panel.appendChild(UI.html('div', {
    style: 'display:flex;gap:8px;margin-top:14px',
  }, [okBtn, cancelBtn]));

  if (focusActive) {
    setTimeout(() => _focusFirstBlank(matchUuid, numRows), 0);
  }
}

// One editable game row inside the panel. All visible rows are independent
// inputs; the panel renders enough rows to potentially decide the series at
// once. DOM holds typed values until OK. Names are clickable when bestOf > 1
// to fill the row's score (winner = ppg, loser = 0). `prefill` carries values
// scraped from the previous render so they survive grow/shrink re-renders.
function _renderRow(ctx, rowIdx, labelA, labelB, committedBase, prefill) {
  const { matchUuid, tournamentId, stageRules, m, ppg, scoreCap, bestOf } = ctx;
  const aId = `pe-a-${matchUuid}-${rowIdx}`;
  const bId = `pe-b-${matchUuid}-${rowIdx}`;

  const fillFromName = (winnerSide) => {
    const va = document.getElementById(aId);
    const vb = document.getElementById(bId);
    let a = (va.value === '' || va.value == null) ? null : parseInt(va.value);
    let b = (vb.value === '' || vb.value == null) ? null : parseInt(vb.value);
    if (a == null) a = winnerSide === 'a' ? ppg : 0;
    if (b == null) b = winnerSide === 'b' ? ppg : 0;
    va.value = String(a);
    vb.value = String(b);
    _refreshEntry(matchUuid, tournamentId, stageRules, m, null, true);
  };

  const onInputKeydown = (e) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    _maybeAutoSubmit(ctx);
  };

  const aClickable = bestOf > 1;
  const bClickable = bestOf > 1;
  const nameClickStyle = 'cursor:pointer;color:#1976d2;text-decoration:underline;user-select:none';
  const aStyle = `font-size:1.15rem;padding:8px 4px;text-align:right;`
    + (aClickable ? nameClickStyle : 'color:#333');
  const bStyle = `font-size:1.15rem;padding:8px 4px;text-align:left;`
    + (bClickable ? nameClickStyle : 'color:#333');

  // Digit picker buttons for one side (0..ppg). Clicking fills this row's
  // input; see _setDigit for the auto-fill rules of the other side.
  const digitsFor = (side, alignEnd) => {
    const btns = [];
    for (let v = 0; v <= ppg; v++) {
      btns.push(UI.html('button', {
        className: 'btn', type: 'button',
        style: 'min-width:48px;min-height:48px;padding:8px 10px;font-size:1.2rem;font-weight:bold',
        onclick: () => _setDigit(ctx, rowIdx, side, v),
      }, [String(v)]));
    }
    return UI.html('div', {
      style: `display:flex;gap:6px;flex-wrap:wrap;justify-content:${alignEnd ? 'flex-end' : 'flex-start'}`,
    }, btns);
  };

  // Side column: name on top, digit buttons below, aligned to the side.
  const sideColumn = (side, label, nameStyle, clickable) => {
    const nameAttrs = { style: nameStyle };
    if (clickable) {
      nameAttrs.onclick = () => fillFromName(side);
      nameAttrs.title = t('match.click_team_won', { name: label });
    }
    return UI.html('div', {
      style: `flex:1;display:flex;flex-direction:column;align-items:${side === 'a' ? 'flex-end' : 'flex-start'};gap:4px;min-width:0`,
    }, [
      UI.html('span', nameAttrs, [label]),
      digitsFor(side, side === 'a'),
    ]);
  };

  const inputAttrs = (id, value) => {
    const a = {
      type: 'number', id, min: '0', max: String(scoreCap),
      style: 'width:56px;font-size:1.2rem;text-align:center;padding:6px',
      placeholder: '0', onkeydown: onInputKeydown,
    };
    if (value != null) a.value = String(value);
    return a;
  };
  const aPre = prefill?.score_a;
  const bPre = prefill?.score_b;

  return UI.html('div', {
    style: 'display:flex;gap:12px;align-items:center;padding:10px 0;border-bottom:1px dashed #eee',
  }, [
    UI.html('span', { style: 'min-width:32px;color:#999;font-size:0.85rem;align-self:flex-start;padding-top:14px' },
      [t('match.game_label', { n: committedBase + rowIdx + 1 })]),
    sideColumn('a', labelA, aStyle, aClickable),
    UI.html('div', { style: 'display:flex;gap:6px;align-items:center;min-width:140px;justify-content:center' }, [
      UI.html('input', inputAttrs(aId, aPre)),
      UI.html('span', { style: 'font-size:1.3rem' }, [':']),
      UI.html('input', inputAttrs(bId, bPre)),
    ]),
    sideColumn('b', labelB, bStyle, bClickable),
  ]);
}

// Set a digit value into one row's input and auto-fill the other side when
// the outcome is unambiguous (only fills if the other input is blank):
//   - draw value (ppg-1) with drawAllowed → other = ppg-1 (mirror draw)
//   - any losing score (< ppg, and not the draw case above) → other = max(value+margin, ppg)
//     (margin = effective margin for this row; uses margin_in_decider on the deciding leg)
//   - winning score (>= ppg) → leave other blank (user picks loser score)
// Submission only happens via Enter or the OK button.
function _setDigit(ctx, rowIdx, side, value) {
  const { matchUuid, tournamentId, stageRules, m, ppg, drawAllowed, effMargins } = ctx;
  const margin = effMargins[rowIdx] || 0;
  const aId = `pe-a-${matchUuid}-${rowIdx}`;
  const bId = `pe-b-${matchUuid}-${rowIdx}`;
  const va = document.getElementById(aId);
  const vb = document.getElementById(bId);
  if (!va || !vb) return;
  const target = side === 'a' ? va : vb;
  const other = side === 'a' ? vb : va;
  target.value = String(value);
  const otherBlank = (other.value === '' || other.value == null);
  if (otherBlank) {
    if (margin === 0 && drawAllowed && value === ppg - 1) {
      other.value = String(ppg - 1);
    } else if (value < ppg) {
      other.value = String(Math.max(value + (margin || 1), ppg));
    }
  }
  _refreshEntry(matchUuid, tournamentId, stageRules, m, null, true);
}

// Read all visible row inputs into a {filled, error} pair. `filled` is the
// list of validated games up to the first blank row; gaps trigger an error.
function _readRows(ctx) {
  const { matchUuid, numRows, ppg, scoreCap, drawAllowed, effMargins } = ctx;
  const filled = [];
  let seenBlank = false;
  for (let i = 0; i < numRows; i++) {
    const va = document.getElementById(`pe-a-${matchUuid}-${i}`);
    const vb = document.getElementById(`pe-b-${matchUuid}-${i}`);
    const rawA = va?.value;
    const rawB = vb?.value;
    const isBlank = (rawA === '' || rawA == null) && (rawB === '' || rawB == null);
    if (isBlank) { seenBlank = true; continue; }
    if (seenBlank) {
      return { filled: [], error: t('match.no_gaps') };
    }
    const a = (rawA === '' || rawA == null) ? 0 : parseInt(rawA);
    const b = (rawB === '' || rawB == null) ? 0 : parseInt(rawB);
    const err = _validateScore(a, b, ppg, drawAllowed, effMargins[i] || 0, scoreCap);
    if (err) {
      return { filled: [], error: `${t('match.game_label', { n: i + 1 })}: ${err}` };
    }
    filled.push({ score_a: a, score_b: b });
  }
  return { filled, error: null };
}

// Enter handler: if filled rows decide the series, submit; otherwise focus
// the next blank input. Validation errors are silent here — the OK button
// surfaces them when the user explicitly tries to submit.
function _maybeAutoSubmit(ctx) {
  const { m, bestOf, matchUuid, numRows } = ctx;
  const committed = (m.games || []).filter(g => g.is_finished !== false);
  const { filled, error } = _readRows(ctx);
  if (error) return;
  if (filled.length && _seriesDecided(committed, filled, bestOf)) {
    _submitOK(ctx);
  } else {
    _focusFirstBlank(matchUuid, numRows);
  }
}

// Focus the first input that is still blank across all visible rows.
function _focusFirstBlank(matchUuid, numRows) {
  for (let i = 0; i < numRows; i++) {
    const a = document.getElementById(`pe-a-${matchUuid}-${i}`);
    if (a && (a.value === '' || a.value == null)) { a.focus(); return; }
    const b = document.getElementById(`pe-b-${matchUuid}-${i}`);
    if (b && (b.value === '' || b.value == null)) { b.focus(); return; }
  }
}

// OK handler: read all visible rows, validate consecutively, submit in order.
async function _submitOK(ctx) {
  const { matchUuid, tournamentId } = ctx;
  const { filled, error } = _readRows(ctx);
  if (error) { UI.toast(error, 'error'); return; }
  if (!filled.length) return;
  await _submitPending(matchUuid, tournamentId, filled);
}

// Replace the entry panel content with a spinner + "submitting" label.
function _showSubmitting(matchUuid) {
  const wrap = document.getElementById(`entry-${matchUuid}`);
  if (!wrap) return;
  wrap.innerHTML = '';
  wrap.appendChild(UI.html('div', {
    className: 'score-entry-panel',
    style: 'width:100%;background:#fff;border:2px solid #1976d2;border-radius:8px;'
      + 'padding:24px;margin:8px 0;box-shadow:0 2px 12px rgba(25,118,210,0.15);'
      + 'box-sizing:border-box;display:flex;align-items:center;justify-content:center;gap:12px',
  }, [
    UI.html('span', { className: 'spinner' }),
    UI.html('span', { style: 'font-size:1.1rem;color:#1976d2' }, [t('match.submitting')]),
  ]));
}

// Send the given games to the server in a single batched request. Shows a
// spinner immediately. On success the page re-renders; on error the attempted
// scores are stashed in _failedAttempt so the next render restores the full
// dialog (all games, including the ones that were correct) for retry.
async function _submitPending(matchUuid, tournamentId, scores) {
  if (!scores || !scores.length) return;
  _hooks.onBeforeSubmit();
  _showSubmitting(matchUuid);
  try {
    await API.submitScores(matchUuid, scores);
    _failedAttempt.delete(matchUuid);
    UI.toast(t('match.score_submitted'), 'success');
  } catch (e) {
    _failedAttempt.set(matchUuid, scores);
    UI.toast(e.message, 'error');
  }
  // render() either collapses the panel (match finished) or re-draws the
  // remaining rows. _expanded is preserved so the panel stays open if needed.
  _hooks.rerender();
}
