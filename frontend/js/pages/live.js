/**
 * Live View page — public spectator view for TV/projector.
 * Shows standings and match scores for a selected tournament.
 */
import UI from '../ui.js';
import API from '../api.js';
import WS from '../ws.js';
import { t } from '../i18n.js';

let _interval = null;
let _showQR = false;
let _currentTid = null;

async function render(tid) {
  UI.title(t('live.title'));
  _showQR = false;

  // Enter live mode — hide sidebar, go full-screen
  document.body.classList.add('live-mode');

  const container = UI.html('div', {});

  // Close button (top-left) — exit live mode and navigate home
  container.appendChild(UI.html('button', {
    style: 'position: fixed; top: 8px; left: 8px; z-index: 1000; background: rgba(0,0,0,0.5); color: #fff; border: none; border-radius: 50%; width: 36px; height: 36px; font-size: 1.2rem; cursor: pointer;',
    onclick: () => { cleanup(); App.navigate(API.isLoggedIn() ? 'tournaments' : 'landing'); },
    title: t('live.close'),
  }, ['✕']));

  if (!tid) {
    // No tournament ID — show input
    container.appendChild(UI.html('div', { className: 'form-group', style: 'margin-top: 48px' }, [
      UI.html('label', { for: 'live-tid' }, [t('live.tournament_id')]),
      UI.html('input', { id: 'live-tid', type: 'text', placeholder: t('live.tid_placeholder'),
        value: '', onkeydown: (e) => { if (e.key === 'Enter') startLive(); },
      }),
    ]));
    container.appendChild(UI.html('button', {
      className: 'btn btn-primary', onclick: () => startLive(),
    }, [t('live.start_btn')]));
  } else {
    // Auto-start with hidden input
    container.appendChild(UI.html('input', { id: 'live-tid', type: 'hidden', value: tid }));
  }

  // QR toggle + QR display area — rendered after startLive populates them
  container.appendChild(UI.html('div', { id: 'live-controls', style: 'margin-top: 8px' }));
  container.appendChild(UI.html('div', { id: 'live-qr', style: 'margin-top: 12px; text-align: center' }));
  container.appendChild(UI.html('div', { id: 'live-content', style: 'margin-top: 16px' }));

  UI.render(container);

  // Auto-start if tournament ID was passed (e.g. from tournament detail link)
  if (tid) startLive();
}

// Clean up live-mode when navigating away
const _origRender = render;
window.addEventListener('hashchange', () => {
  if (!window.location.hash.startsWith('#live')) {
    document.body.classList.remove('live-mode');
  }
});

async function startLive() {
  const tid = document.getElementById('live-tid').value.trim();
  if (!tid) { UI.toast(t('live.enter_tid'), 'error'); return; }
  _currentTid = tid;
  // Update URL so reload keeps the tournament
  if (!window.location.hash.includes(tid)) {
    history.replaceState(null, '', `#live/${tid}`);
  }

  WS.connect(tid);
  WS.onEvent(onEvent);

  // Show QR toggle for logged-in organizers
  const controlsEl = document.getElementById('live-controls');
  if (controlsEl && API.isLoggedIn()) {
    controlsEl.innerHTML = '';
    controlsEl.appendChild(UI.html('button', {
      className: 'btn btn-secondary btn-sm',
      id: 'qr-toggle-btn',
      onclick: () => toggleQR(),
    }, [t('live.show_qr')]));
  }

  await refreshLive(tid);
  // Auto-refresh every 30s
  if (_interval) clearInterval(_interval);
  _interval = setInterval(() => refreshLive(tid), 30000);
}

async function refreshLive(tid) {
  const el = document.getElementById('live-content');
  if (!el) return;

  try {
    const tour = await API.publicTournament(tid);
    let html = `<div class="card"><h3>${_esc(tour.name || t('tournament.title'))}</h3>`;
    html += `<div class="meta">${_esc(t(`status.${tour.status}`))} — ${_esc(t('tournament.players_count', { count: tour.player_count || 0 }))}</div></div>`;

    if (tour.status === 'running' || tour.status === 'finished') {
      // Two-column layout: matches (left) + standings (right)
      html += '<div style="display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start">';

      // Pick the single stage to display. Stages arrive ordered by
      // `ordering` ascending, so the LAST active one is the latest in
      // progression (handles the case where activate_stage doesn't
      // auto-finish prior stages — both group + elimination can read
      // as 'active' simultaneously, and we want the elimination).
      // Fallbacks: last finished stage, then last stage overall.
      const stages = tour.stages || [];
      const activeStage = [...stages].reverse().find(s => s.status === 'active')
        || [...stages].reverse().find(s => s.status === 'finished')
        || stages[stages.length - 1]
        || null;
      const showStageHeader = stages.length > 1 && activeStage;

      // --- LEFT: Matches for the current stage only ---
      html += '<div style="flex:2;min-width:320px">';
      if (activeStage) {
        try {
          let sm = [];
          try { sm = await API.publicMatches(tid, activeStage.uuid); } catch (_) {}
          if (sm.length) {
            if (showStageHeader) {
              html += `<h3 style="margin:16px 8px 8px 8px">${_esc(activeStage.name || '')}</h3>`;
            }
            const byRound = {};
            for (const m of sm) (byRound[m.round_number || 1] = byRound[m.round_number || 1] || []).push(m);
            const rounds = Object.keys(byRound).map(Number).sort((a, b) => b - a);
            const maxRn = rounds[0];
            for (const rn of rounds.slice(0, 2)) {
              const rm = byRound[rn];
              const allDone = rm.every(m => m.status === 'finished');
              // Final round of an elimination stage with 2+ matches → split into 🏆/🥉
              const isFinalElimRound = activeStage.stage_type === 'elimination'
                && rn === maxRn && rm.length >= 2;
              if (isFinalElimRound) {
                const sorted = [...rm].sort((a, b) =>
                  (a.bracket_position ?? 0) - (b.bracket_position ?? 0));
                const consolation = sorted[sorted.length - 1];
                const finals = sorted.slice(0, -1);
                // No in-progress / done suffix here — early bracket rounds would
                // otherwise label the (yet-unplayed) final as "in progress".
                for (const [hdr, group] of [[t('match.final'), finals], [t('match.third_place'), [consolation]]]) {
                  html += `<div class="card"><h3>${_esc(hdr)}</h3>`;
                  for (const m of group) {
                    html += _renderLiveMatch(m);
                  }
                  html += '</div>';
                }
                continue;
              }
              const label = rn === maxRn
                ? (allDone ? t('match.round_done', { n: rn }) : t('match.round_in_progress', { n: rn }))
                : t('match.round_done', { n: rn });
              html += `<div class="card"><h3>${_esc(label)}</h3>`;
              for (const m of rm) html += _renderLiveMatch(m);
              html += '</div>';
            }
          }
        } catch (_) {}
      }
      html += '</div>';

      // --- RIGHT: Standings (only for group stages — elimination has bracket) ---
      html += '<div style="flex:1;min-width:280px">';
      if (activeStage && activeStage.stage_type === 'group') {
        try {
          const standings = await API.publicStandings(tid, activeStage.uuid);
          if (standings.length) {
            html += `<div class="card"><h3>${_esc(t('live.standings_h'))}</h3>`;
            html += `<table class="data-table"><thead><tr><th>#</th><th>${_esc(t('live.standings_th_player'))}</th><th>${_esc(t('live.standings_th_gp'))}</th><th>${_esc(t('live.standings_th_sw'))}</th><th>${_esc(t('live.standings_th_gd'))}</th><th>${_esc(t('live.standings_th_pts'))}</th></tr></thead><tbody>`;
            standings.forEach((r, i) => {
              const name = _esc(r.nickname || r.participant_id?.substring(0, 8) || t('common.em_dash'));
              const gd = r.goal_difference > 0 ? `+${r.goal_difference}` : String(r.goal_difference || 0);
              html += `<tr><td>${i + 1}</td><td>${name}</td><td>${r.matches_played || 0}</td><td>${r.sets_won || 0}</td><td>${gd}</td><td><strong>${r.points}</strong></td></tr>`;
            });
            html += '</tbody></table></div>';
          }
        } catch (_) {}
      }
      html += '</div>';
      html += '</div>'; // close flex container
    } else {
      // Registration phase: show players + applicants
      const dash = t('common.em_dash');
      if (tour.players && tour.players.length) {
        const sorted = [...tour.players].sort((a, b) => (a.nickname || '').localeCompare(b.nickname || ''));
        html += `<div class="card"><h3>${_esc(t('live.registered'))}</h3>`;
        html += `<table class="data-table"><thead><tr><th>#</th><th>${_esc(t('live.standings_th_player'))}</th></tr></thead><tbody>`;
        sorted.forEach((p, i) => {
          html += `<tr><td>${i + 1}</td><td>${_esc(p.nickname || p.uuid?.substring(0, 8) || dash)}</td></tr>`;
        });
        html += '</tbody></table></div>';
      }
      if (tour.applicants && tour.applicants.length) {
        const sortedApp = [...tour.applicants].sort((a, b) => (a.nickname || '').localeCompare(b.nickname || ''));
        html += `<div class="card"><h3>${_esc(t('live.want_to_play'))}</h3>`;
        html += `<table class="data-table"><thead><tr><th>#</th><th>${_esc(t('live.standings_th_player'))}</th></tr></thead><tbody>`;
        sortedApp.forEach((p, i) => {
          html += `<tr><td>${i + 1}</td><td>${_esc(p.nickname || p.uuid?.substring(0, 8) || dash)}</td></tr>`;
        });
        html += '</tbody></table></div>';
      }
    }

    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="loading">${_esc(t('common.error', { msg: e.message }))}</div>`;
  }
}

function _esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

function _renderLiveMatch(m) {
  const dash = t('common.em_dash');
  const a = m.team_a_name || m.player_a_name || dash;
  const b = m.team_b_name || m.player_b_name || dash;
  const tbl = m.status === 'finished'
    ? ''
    : (m.table_number ? t('match.table', { n: m.table_number }) : t('match.queued'));
  const score = m.status === 'finished' ? `${m.score_a ?? 0} : ${m.score_b ?? 0}` : t('match.vs');
  const bg = m.status === 'finished' ? '#e8f5e9' : '#fff3e0';
  let h = '<div style="display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid #eee;flex-wrap:wrap">';
  h += `<span class="meta" style="min-width:60px">${_esc(tbl)}</span>`;
  h += `<strong style="flex:1;text-align:right;min-width:80px">${_esc(a)}</strong>`;
  h += `<span style="padding:2px 12px;border-radius:4px;font-weight:bold;font-size:1.1rem;background:${bg}">${score}</span>`;
  h += `<strong style="flex:1;min-width:80px">${_esc(b)}</strong>`;
  h += '</div>';
  return h;
}

async function toggleQR() {
  _showQR = !_showQR;
  const qrEl = document.getElementById('live-qr');
  const btn = document.getElementById('qr-toggle-btn');
  if (!qrEl) return;

  if (!_showQR || !_currentTid) {
    btn.textContent = t('live.show_qr');
    qrEl.innerHTML = '';
    return;
  }

  btn.textContent = t('live.hide_qr');

  try {
    // Get registration URL (with secret token) via JSON endpoint
    const res = await fetch(`/api/v1/public/tournaments/${_currentTid}/qr?format=json`);
    if (!res.ok) throw new Error(t('live.qr_endpoint_failed'));
    const data = await res.json();
    const regUrl = data.registration_url;

    // Try to load SVG QR image from server
    const svgUrl = `/api/v1/public/tournaments/${_currentTid}/qr?format=svg`;
    const card = document.createElement('div');
    card.className = 'card';
    card.style.cssText = 'display: inline-block; padding: 24px; text-align: center';
    card.innerHTML = `<h3>${t('live.scan_to_register')}</h3>`;

    const img = document.createElement('img');
    img.src = svgUrl;
    img.alt = 'QR Code';
    img.style.cssText = 'max-width: 300px; display: block; margin: 12px auto';
    img.onerror = () => {
      // Fallback: show URL as text if qrcode library not installed
      img.remove();
      const fallback = document.createElement('div');
      fallback.style.cssText = 'margin: 12px 0; padding: 16px; background: #f5f5f5; border-radius: 8px; word-break: break-all; font-size: 1.1rem';
      fallback.innerHTML = `<p style="margin-bottom:8px; color:#666">${t('live.qr_unavailable')}<br>${t('live.qr_share_link')}</p>
        <a href="${regUrl}" style="color: #0f3460; font-weight: bold">${regUrl}</a>`;
      card.appendChild(fallback);
    };
    card.appendChild(img);

    const meta = document.createElement('p');
    meta.className = 'meta';
    meta.style.marginTop = '8px';
    meta.textContent = t('live.scan_hint');
    card.appendChild(meta);

    qrEl.innerHTML = '';
    qrEl.appendChild(card);
  } catch (e) {
    qrEl.innerHTML = `<p class="meta">${_esc(t('live.qr_load_failed', { msg: e.message }))}</p>`;
  }
}

function onEvent(event) {
  UI.toast(t('ws.event_toast', { type: event.type }), 'info');
  const tid = event.tournament_id;
  if (tid) refreshLive(tid);
}

function cleanup() {
  if (_interval) { clearInterval(_interval); _interval = null; }
  document.body.classList.remove('live-mode');
  WS.disconnect();
  WS.offEvent(onEvent);
}

const LivePage = { render, cleanup };
export default LivePage;