/**
 * Live View page — public spectator view for TV/projector.
 * Shows standings and match scores for a selected tournament.
 */
const LivePage = (() => {
  let _interval = null;
  let _showQR = false;
  let _currentTid = null;

  async function render(tid) {
    UI.title('Live View');
    _showQR = false;

    // Enter live mode — hide sidebar, go full-screen
    document.body.classList.add('live-mode');

    const container = UI.html('div', {});

    // Close button (top-left)
    container.appendChild(UI.html('button', {
      style: 'position: fixed; top: 8px; left: 8px; z-index: 1000; background: rgba(0,0,0,0.5); color: #fff; border: none; border-radius: 50%; width: 36px; height: 36px; font-size: 1.2rem; cursor: pointer;',
      onclick: () => { document.body.classList.remove('live-mode'); window.close(); },
      title: 'Close Live View',
    }, ['✕']));

    if (!tid) {
      // No tournament ID — show input
      container.appendChild(UI.html('div', { className: 'form-group', style: 'margin-top: 48px' }, [
        UI.html('label', { for: 'live-tid' }, ['Tournament ID']),
        UI.html('input', { id: 'live-tid', type: 'text', placeholder: 'Paste tournament UUID',
          value: '', onkeydown: (e) => { if (e.key === 'Enter') startLive(); },
        }),
      ]));
      container.appendChild(UI.html('button', {
        className: 'btn btn-primary', onclick: () => startLive(),
      }, ['📺 Start Live View']));
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
    if (!tid) { UI.toast('Enter a tournament ID', 'error'); return; }
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
      }, ['📱 Show QR for registration']));
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
      const t = await API.publicTournament(tid);
      let html = `<div class="card"><h3>${_esc(t.name || 'Tournament')}</h3>`;
      html += `<div class="meta">${_esc(t.status)} — ${t.player_count || 0} players</div></div>`;

      if (t.status === 'running' || t.status === 'finished') {
        // Two-column layout: matches (left) + standings (right)
        html += '<div style="display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start">';

        // --- LEFT: Matches (current round + previous) ---
        html += '<div style="flex:2;min-width:320px">';
        try {
          let matches = [];
          for (const stage of (t.stages || [])) {
            try {
              const sm = await API.publicMatches(tid, stage.uuid);
              matches = matches.concat(sm);
            } catch (_) {}
          }
          if (matches.length) {
            const byRound = {};
            for (const m of matches) (byRound[m.round_number || 1] = byRound[m.round_number || 1] || []).push(m);
            const rounds = Object.keys(byRound).map(Number).sort((a, b) => b - a);
            for (const rn of rounds.slice(0, 2)) {
              const rm = byRound[rn];
              const allDone = rm.every(m => m.status === 'finished');
              const label = rn === rounds[0] ? (allDone ? `Round ${rn} ✓` : `Round ${rn} — in progress`) : `Round ${rn} ✓`;
              html += `<div class="card"><h3>${label}</h3>`;
              for (const m of rm) {
                const a = m.team_a_name || m.player_a_name || '—';
                const b = m.team_b_name || m.player_b_name || '—';
                const tbl = m.table_number ? `Table ${m.table_number}` : 'Queued';
                const score = m.status === 'finished' ? `${m.score_a ?? 0} : ${m.score_b ?? 0}` : 'vs';
                const bg = m.status === 'finished' ? '#e8f5e9' : '#fff3e0';
                html += `<div style="display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid #eee;flex-wrap:wrap">`;
                html += `<span class="meta" style="min-width:60px">${_esc(tbl)}</span>`;
                html += `<strong style="flex:1;text-align:right;min-width:80px">${_esc(a)}</strong>`;
                html += `<span style="padding:2px 12px;border-radius:4px;font-weight:bold;font-size:1.1rem;background:${bg}">${score}</span>`;
                html += `<strong style="flex:1;min-width:80px">${_esc(b)}</strong>`;
                html += `</div>`;
              }
              html += '</div>';
            }
          }
        } catch (_) {}
        html += '</div>';

        // --- RIGHT: Standings ---
        html += '<div style="flex:1;min-width:280px">';
        if (t.stages && t.stages.length) {
          const groupStage = t.stages.find(s => s.stage_type === 'group') || t.stages[0];
          try {
            const standings = await API.publicStandings(tid, groupStage.uuid);
            if (standings.length) {
              html += '<div class="card"><h3>Standings</h3>';
              html += '<table class="data-table"><thead><tr><th>#</th><th>Player</th><th>GP</th><th>S+</th><th>G±</th><th>Pts</th></tr></thead><tbody>';
              standings.forEach((r, i) => {
                const name = _esc(r.nickname || r.participant_id?.substring(0, 8) || '—');
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
        if (t.players && t.players.length) {
          html += '<div class="card"><h3>✅ Registered Players</h3>';
          html += '<table class="data-table"><thead><tr><th>#</th><th>Player</th></tr></thead><tbody>';
          t.players.forEach((p, i) => {
            html += `<tr><td>${i + 1}</td><td>${_esc(p.nickname || p.uuid?.substring(0, 8) || '—')}</td></tr>`;
          });
          html += '</tbody></table></div>';
        }
        if (t.applicants && t.applicants.length) {
          html += '<div class="card"><h3>✋ Want to play</h3>';
          html += '<table class="data-table"><thead><tr><th>#</th><th>Player</th></tr></thead><tbody>';
          t.applicants.forEach((p, i) => {
            html += `<tr><td>${i + 1}</td><td>${_esc(p.nickname || p.uuid?.substring(0, 8) || '—')}</td></tr>`;
          });
          html += '</tbody></table></div>';
        }
      }

      el.innerHTML = html;
    } catch (e) {
      el.innerHTML = `<div class="loading">Error: ${e.message}</div>`;
    }
  }

  function _esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

  async function toggleQR() {
    _showQR = !_showQR;
    const qrEl = document.getElementById('live-qr');
    const btn = document.getElementById('qr-toggle-btn');
    if (!qrEl) return;

    if (!_showQR || !_currentTid) {
      btn.textContent = '📱 Show QR for registration';
      qrEl.innerHTML = '';
      return;
    }

    btn.textContent = '📱 Hide QR';

    try {
      // Get registration URL (with secret token) via JSON endpoint
      const res = await fetch(`/v1/public/tournaments/${_currentTid}/qr?format=json`);
      if (!res.ok) throw new Error('QR endpoint failed');
      const data = await res.json();
      const regUrl = data.registration_url;

      // Try to load SVG QR image from server
      const svgUrl = `/v1/public/tournaments/${_currentTid}/qr?format=svg`;
      const card = document.createElement('div');
      card.className = 'card';
      card.style.cssText = 'display: inline-block; padding: 24px; text-align: center';
      card.innerHTML = `<h3>📱 Scan to register</h3>`;

      const img = document.createElement('img');
      img.src = svgUrl;
      img.alt = 'QR Code';
      img.style.cssText = 'max-width: 300px; display: block; margin: 12px auto';
      img.onerror = () => {
        // Fallback: show URL as text if qrcode library not installed
        img.remove();
        const fallback = document.createElement('div');
        fallback.style.cssText = 'margin: 12px 0; padding: 16px; background: #f5f5f5; border-radius: 8px; word-break: break-all; font-size: 1.1rem';
        fallback.innerHTML = `<p style="margin-bottom:8px; color:#666">QR image unavailable.<br>Share this link instead:</p>
          <a href="${regUrl}" style="color: #0f3460; font-weight: bold">${regUrl}</a>`;
        card.appendChild(fallback);
      };
      card.appendChild(img);

      const meta = document.createElement('p');
      meta.className = 'meta';
      meta.style.marginTop = '8px';
      meta.textContent = 'Players: scan with phone camera to sign up';
      card.appendChild(meta);

      qrEl.innerHTML = '';
      qrEl.appendChild(card);
    } catch (e) {
      qrEl.innerHTML = `<p class="meta">Could not load QR: ${e.message}</p>`;
    }
  }

  function onEvent(event) {
    UI.toast(`🔴 ${event.type}`, 'info');
    const tid = event.tournament_id;
    if (tid) refreshLive(tid);
  }

  function cleanup() {
    if (_interval) { clearInterval(_interval); _interval = null; }
    WS.disconnect();
    WS.offEvent(onEvent);
  }

  return { render, cleanup };
})();
