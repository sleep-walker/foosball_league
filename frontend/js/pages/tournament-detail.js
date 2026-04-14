/**
 * Tournament detail page — shows stages, standings, matches, controls.
 */
const TournamentDetailPage = (() => {
  let _tournamentId = null;
  let _roundsNewestFirst = true;  // default: newest round on top
  let _wsConnected = false;       // only connect WS once
  let _suppressUntil = 0;         // suppress WS toasts+renders after own action

  let _rendered = false;

  async function render(id) {
    _tournamentId = id;
    // Show loading only on very first load
    if (!_rendered) UI.loading();

    try {
      const t = API.isLoggedIn() ? await API.tournament(id) : await API.publicTournament(id);
      UI.title(t.name || 'Tournament');
      _rendered = true;

      // Highlight: only in player view, not organizer control view
      // Organizer can switch to player view via "👤 My view" button
      let myPlayerId = null;
      let myNickname = null;
      let isOrganizer = false;
      if (API.isLoggedIn()) {
        try {
          const user = await API.me();
          isOrganizer = (user?.id === t.owner_id);
          // Don't highlight organizer's own rows on the control page
          if (!isOrganizer) {
            const me = await API.myPlayer();
            myPlayerId = me?.player_id;
            myNickname = me?.nickname;
          }
        } catch (_) {}
      }

      // Connect WebSocket for live updates (only once)
      if (!_wsConnected || _tournamentId !== id) {
        WS.connect(id);
        WS.onEvent(onLiveEvent);
        _wsConnected = true;
      }

      const container = UI.html('div', {});

      // Info card
      container.appendChild(UI.html('div', { className: 'card' }, [
        UI.html('h3', {}, [t.name || 'Tournament']),
        UI.html('div', { className: 'meta' }, [
          `📅 ${t.date}  📍 ${t.location || '—'}  🎮 ${t.player_mode}`,
        ]),
        UI.html('div', { style: 'margin-top: 8px' }, [
          UI.statusBadge(t.status || 'preparing'),
          UI.html('span', { className: 'meta', style: 'margin-left: 8px' }, [
            `${(t.registrations || []).length} players`,
          ]),
        ]),
      ]));

      // Controls (if logged in)
      if (API.isLoggedIn()) {
        const controls = UI.html('div', { className: 'card' }, [
          UI.html('h3', {}, ['Controls']),
        ]);
        if (t.status === 'registration') {
          controls.appendChild(UI.html('button', {
            className: 'btn btn-primary', style: 'margin-right: 8px',
            onclick: () => doAction(() => API.startTournament(id), 'Tournament started!'),
          }, ['▶ Start Tournament']));
        }
        if (t.status === 'running') {
          controls.appendChild(UI.html('button', {
            className: 'btn btn-danger', style: 'margin-right: 8px',
            onclick: () => doAction(() => API.finishTournament(id), 'Tournament finished!'),
          }, ['⏹ Finish Tournament']));
        }
        // Live View link — opens in new tab so organizer keeps tournament controls
        controls.appendChild(UI.html('a', {
          className: 'btn btn-secondary',
          style: 'margin-right: 8px; text-decoration: none; display: inline-block',
          href: `${window.location.origin}${window.location.pathname}#live/${id}`,
          target: '_blank', rel: 'noopener',
        }, ['📺 Live View']));

        // Delete — always available, with confirmation
        controls.appendChild(UI.html('button', {
          className: 'btn btn-danger btn-sm', style: 'margin-top: 8px',
          onclick: () => doDelete(id, t.name),
        }, ['🗑 Delete Tournament']));
        container.appendChild(controls);
      }

      // Stages
      for (const stage of (t.stages || [])) {
        container.appendChild(await renderStage(id, stage, t.status, myPlayerId, myNickname));
      }

      // Players section
      container.appendChild(await renderPlayers(id, t, myNickname));

      // Export links
      container.appendChild(UI.html('div', { className: 'card' }, [
        UI.html('h3', {}, ['Export']),
        UI.html('a', { href: `/v1/public/tournaments/${id}/export?format=json`, className: 'btn btn-secondary btn-sm', style: 'margin-right: 8px' }, ['📄 JSON']),
        UI.html('a', { href: `/v1/public/tournaments/${id}/export?format=csv_standings`, className: 'btn btn-secondary btn-sm', style: 'margin-right: 8px' }, ['📊 CSV Standings']),
        UI.html('a', { href: `/v1/public/tournaments/${id}/export?format=html`, className: 'btn btn-secondary btn-sm' }, ['🖨 Print']),
      ]));

      UI.render(container);
    } catch (e) {
      UI.error(e.message);
    }
  }

  async function renderStage(tournamentId, stage, tStatus, myPlayerId, myNickname) {
    const card = UI.html('div', { className: 'card' }, [
      UI.html('h3', {}, [`${stage.name} (${stage.stage_type})`]),
    ]);

    // Elimination bracket button (always available)
    if (API.isLoggedIn() && tStatus === 'running' && stage.stage_type === 'elimination') {
      card.appendChild(UI.html('button', {
        className: 'btn btn-primary btn-sm', style: 'margin-bottom: 8px',
        onclick: () => doAction(() => API.generateBracket(tournamentId, stage.uuid), 'Bracket generated!'),
      }, ['🏆 Generate Bracket']));
    }

    // Matches grouped by round (newest first by default)
    try {
      const matches = await API.matches(tournamentId);
      const stageMatches = matches.filter(m => m.stage_id === stage.uuid);
      if (stageMatches.length) {
        const byRound = {};
        for (const m of stageMatches) {
          const r = m.round_number || 1;
          (byRound[r] = byRound[r] || []).push(m);
        }
        const maxRound = Math.max(...Object.keys(byRound).map(Number));
        const latestAll = byRound[maxRound] || [];
        const allDone = latestAll.length > 0 && latestAll.every(m => m.status === 'finished');

        // Draw button: only when latest round is complete
        if (API.isLoggedIn() && tStatus === 'running' && allDone && stage.stage_type === 'group') {
          card.appendChild(UI.html('button', {
            className: 'btn btn-primary', style: 'margin-bottom: 12px',
            onclick: () => doAction(() => API.drawRound(tournamentId, stage.uuid), 'Round drawn!'),
          }, ['🎲 Draw New Round']));
        }

        // Sort toggle
        const sortBtn = UI.html('button', {
          className: 'btn btn-secondary btn-sm', style: 'margin-bottom: 8px; float: right',
          onclick: () => { _roundsNewestFirst = !_roundsNewestFirst; render(_tournamentId); },
        }, [_roundsNewestFirst ? '↑ Oldest first' : '↓ Newest first']);
        card.appendChild(sortBtn);

        const roundKeys = Object.keys(byRound).map(Number)
          .sort(_roundsNewestFirst ? (a, b) => b - a : (a, b) => a - b);
        for (const round of roundKeys) {
          const rm = byRound[round];
          const roundDone = rm.every(m => m.status === 'finished');
          const label = round === maxRound && !roundDone ? `Round ${round} — in progress` : `Round ${round}`;
          card.appendChild(UI.html('h4', { style: 'margin-top: 12px; clear: both' }, [label]));
          for (const m of rm) {
            card.appendChild(_renderMatch(m, tournamentId, myPlayerId, myNickname));
          }
        }
      } else if (API.isLoggedIn() && tStatus === 'running' && stage.stage_type === 'group') {
        // No matches yet — show initial draw button
        card.appendChild(UI.html('button', {
          className: 'btn btn-primary', style: 'margin-top: 12px',
          onclick: () => doAction(() => API.drawRound(tournamentId, stage.uuid), 'Round drawn!'),
        }, ['🎲 Draw New Round']));
      }
    } catch (_) { /* no matches yet */ }

    return card;
  }

  function _renderMatch(m, tournamentId, myPlayerId, myNickname) {
    const labelA = m.team_a_name || m.player_a_nickname || m.player_a_id?.substring(0, 8) || '—';
    const labelB = m.team_b_name || m.player_b_nickname || m.player_b_id?.substring(0, 8) || '—';
    const table = m.table_number ? `Table ${m.table_number}` : 'Queued';
    const scoreText = m.status === 'finished'
      ? `${m.score_a ?? 0} : ${m.score_b ?? 0}`
      : 'vs';

    // Check if current user is in this match (for highlighting)
    const isMyMatch = myPlayerId && (
      m.player_a_id === myPlayerId || m.player_b_id === myPlayerId
    ) || myNickname && (
      labelA.includes(myNickname) || labelB.includes(myNickname)
    );
    const highlightStyle = isMyMatch ? 'background: #e3f2fd; border-radius: 4px; padding: 6px 4px;' : 'padding: 6px 0;';

    const row = UI.html('div', {
      style: `display: flex; align-items: center; gap: 8px; border-bottom: 1px solid #eee; flex-wrap: wrap; ${highlightStyle}`,
    }, [
      UI.html('span', { className: 'meta', style: 'min-width: 60px' }, [table]),
      UI.html('strong', { style: 'flex: 1; text-align: right; min-width: 80px' }, [labelA]),
      UI.html('span', {
        style: `padding: 2px 10px; border-radius: 4px; font-weight: bold; ${
          m.status === 'finished' ? 'background: #e8f5e9' : 'background: #f5f5f5'
        }`,
      }, [scoreText]),
      UI.html('strong', { style: 'flex: 1; min-width: 80px' }, [labelB]),
    ]);

    // Inline score entry for pending matches
    if (m.status !== 'finished') {
      const onEnter = (e) => {
        if (e.key === 'Enter') {
          const va = document.getElementById(`score-a-${m.uuid}`)?.value;
          const vb = document.getElementById(`score-b-${m.uuid}`)?.value;
          if (va !== '' && vb !== '') submitScore(tournamentId, m.uuid);
        }
      };
      row.appendChild(UI.html('input', {
        type: 'number', id: `score-a-${m.uuid}`, min: '0', max: '20',
        style: 'width: 40px', placeholder: '0', onkeydown: onEnter,
      }));
      row.appendChild(UI.html('span', {}, [':']));
      row.appendChild(UI.html('input', {
        type: 'number', id: `score-b-${m.uuid}`, min: '0', max: '20',
        style: 'width: 40px', placeholder: '0', onkeydown: onEnter,
      }));
      row.appendChild(UI.html('button', {
        id: `score-btn-${m.uuid}`,
        className: 'btn btn-primary btn-sm',
        onclick: () => submitScore(tournamentId, m.uuid),
      }, ['✓']));
    }
    return row;
  }

  async function submitScore(tournamentId, matchId) {
    const inputA = document.getElementById(`score-a-${matchId}`);
    const inputB = document.getElementById(`score-b-${matchId}`);
    const btn = document.getElementById(`score-btn-${matchId}`);
    const a = parseInt(inputA?.value) || 0;
    const b = parseInt(inputB?.value) || 0;

    // Show spinner
    if (inputA) inputA.disabled = true;
    if (inputB) inputB.disabled = true;
    if (btn) { btn.disabled = true; btn.textContent = '⏳'; }

    try {
      await API.submitScore(matchId, a, b);

      // Replace inputs with final score inline — no page reload
      if (inputA) inputA.remove();
      if (inputB) inputB.remove();
      // Remove the ":" separator
      const row = btn?.parentElement;
      if (row) {
        const sep = row.querySelector(`#score-btn-${matchId}`)?.previousElementSibling;
        if (sep && sep.textContent === ':') sep.remove();
      }
      if (btn) {
        btn.className = '';
        btn.style.cssText = 'background:#e8f5e9;border:none;border-radius:4px;font-weight:bold;font-size:1rem;padding:2px 12px;cursor:default';
        btn.textContent = `${a} : ${b} ✅`;
      }

      // Suppress WS-triggered re-renders for this score action
      _suppressUntil = Date.now() + 5000;

      // Check if all matches in this round are done → show "Draw Next Round" without full reload
      _refreshStandingsQuietly(tournamentId);
    } catch (e) {
      if (inputA) inputA.disabled = false;
      if (inputB) inputB.disabled = false;
      if (btn) { btn.disabled = false; btn.textContent = '✓'; }
      UI.toast(e.message, 'error');
    }
  }

  async function _refreshStandingsQuietly(tournamentId) {
    // Refresh just the standings table without full page reload
    try {
      const t = API.isLoggedIn() ? await API.tournament(tournamentId) : await API.publicTournament(tournamentId);
      const stage = (t.stages || []).find(s => s.stage_type === 'group');
      if (!stage) return;

      const standings = await API.publicStandings(tournamentId, stage.uuid);
      const existing = document.querySelector('.data-table');
      if (existing && standings.length) {
        const rows = standings.map((r, i) => [
          String(i + 1),
          r.nickname || r.participant_id?.substring(0, 8) || '—',
          String(r.matches_played || 0),
          String(r.sets_won || 0),
          String((r.goal_difference > 0 ? '+' : '') + (r.goal_difference || 0)),
          String(r.points),
        ]);
        const tbl = UI.table(['#', 'Player', 'GP', 'S+', 'G±', 'Pts'], rows);
        existing.replaceWith(tbl);
      }

      // No need to inject Draw button — renderStage already handles it
    } catch (_) { /* non-critical */ }
  }

  async function renderPlayers(tournamentId, t, myNickname) {
    const card = UI.html('div', { className: 'card' }, [
      UI.html('h3', {}, [`Players (${(t.registrations || []).length})`]),
    ]);

    // Helper: get player name from registration
    const _regName = (r) => {
      const p = r.player;
      if (p) return p.nickname || `${p.first_name || ''} ${p.last_name || ''}`.trim() || '—';
      return r.player_id?.substring(0, 8) || '—';
    };

    // List current registrations
    if (t.registrations && t.registrations.length) {
      if (t.status === 'running' || t.status === 'finished') {
        // Running/finished: show standings with stats from first group stage
        const stage = (t.stages || []).find(s => s.stage_type === 'group');
        let standings = [];
        if (stage) {
          try { standings = await API.publicStandings(tournamentId, stage.uuid); } catch(_) {}
        }
        if (standings.length) {
          const rows = standings.map((r, i) => [
            String(i + 1),
            r.nickname || r.participant_id?.substring(0, 8) || '—',
            String(r.matches_played || 0),
            String(r.sets_won || 0),
            String((r.goal_difference > 0 ? '+' : '') + (r.goal_difference || 0)),
            String(r.points),
          ]);
          const tbl = UI.table(['#', 'Player', 'GP', 'S+', 'G±', 'Pts'], rows);
          if (myNickname) {
            const trs = tbl.querySelectorAll('tbody tr');
            standings.forEach((r, i) => {
              if (r.nickname === myNickname && trs[i]) {
                trs[i].style.background = '#e3f2fd';
                trs[i].style.fontWeight = 'bold';
              }
            });
          }
          card.appendChild(tbl);
        } else {
          const rows = t.registrations.map((r, i) => [String(i + 1), _regName(r)]);
          card.appendChild(UI.table(['#', 'Player'], rows));
        }
      } else {
        // Registration phase: simple numbered list
        const rows = t.registrations.map((r, i) => [String(i + 1), _regName(r)]);
        card.appendChild(UI.table(['#', 'Player'], rows));
      }
    }

    // Add player controls (only if tournament is still accepting players)
    if (t.status === 'registration' || t.is_registration_open) {
      card.appendChild(UI.html('h4', { style: 'margin-top: 16px' }, ['Add Player']));

      const registeredIds = new Set((t.registrations || []).map((r) => r.player_id));
      const applicantIds = new Set((t.applicants || []).map((a) => a.uuid));
      let allPlayers = [];
      try { allPlayers = await API.players(); } catch (_) {}
      const available = allPlayers.filter((p) => !registeredIds.has(p.uuid) && !applicantIds.has(p.uuid));

      // Tab buttons
      const tabs = UI.html('div', { style: 'display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 8px' });

      // Tab: Accept pre-registered (applicants) — always visible
      const applicants = t.applicants || [];
      tabs.appendChild(_tabBtn('applicants', `✋ Accept (${applicants.length})`));

      // Tab: Add from league
      if (t.league_id) {
        tabs.appendChild(_tabBtn('league', '🏅 From league'));
      }

      // Tab: Existing player
      tabs.appendChild(_tabBtn('existing', '👤 All players'));

      // Tab: New player
      tabs.appendChild(_tabBtn('new', '➕ New player'));

      card.appendChild(tabs);

      // Panel: applicants — always present, shows message when empty
      const appDiv = UI.html('div', { id: 'add-applicants-panel', className: 'striped-list', style: 'display: none' });
      if (applicants.length) {
        for (const a of applicants) {
          appDiv.appendChild(UI.html('div', { style: 'display: flex; align-items: center; justify-content: space-between; padding: 6px 8px' }, [
            UI.html('span', {}, [a.nickname || '—']),
            UI.html('button', {
              className: 'btn btn-primary btn-sm',
              onclick: () => acceptApplicant(tournamentId, a.uuid, a.nickname),
            }, ['✓ Accept']),
          ]));
        }
        if (applicants.length > 1) {
          appDiv.appendChild(UI.html('button', {
            className: 'btn btn-primary btn-sm', style: 'margin-top: 8px',
            onclick: () => acceptAllApplicants(tournamentId, applicants),
          }, [`✓ Accept all (${applicants.length})`]));
        }
      } else {
        appDiv.appendChild(UI.html('p', { className: 'meta' }, [
          'No one pre-registered yet. Players can scan the QR code to sign up.',
        ]));
      }
      card.appendChild(appDiv);

      // Panel: league players
      if (t.league_id) {
        const leagueDiv = UI.html('div', { id: 'add-league-panel', className: 'striped-list', style: 'display: none' });
        let leaguePlayers = [];
        try { leaguePlayers = await API.leaguePlayers(t.league_id); } catch (_) {}
        const leagueAvail = leaguePlayers.filter((p) => !registeredIds.has(p.uuid));
        if (leagueAvail.length) {
          for (const p of leagueAvail) {
            leagueDiv.appendChild(UI.html('div', { style: 'display: flex; align-items: center; justify-content: space-between; padding: 6px 8px' }, [
              UI.html('span', {}, [p.nickname || p.uuid.substring(0, 8)]),
              UI.html('button', {
                className: 'btn btn-primary btn-sm',
                onclick: () => doAction(() => API.addPlayer(tournamentId, p.uuid), `${p.nickname} added!`),
              }, ['+ Add']),
            ]));
          }
          // Add all from league
          if (leagueAvail.length > 1) {
            leagueDiv.appendChild(UI.html('button', {
              className: 'btn btn-primary btn-sm', style: 'margin-top: 8px',
              onclick: () => addAllFromList(tournamentId, leagueAvail),
            }, [`+ Add all (${leagueAvail.length})`]));
          }
        } else {
          leagueDiv.appendChild(UI.html('p', { className: 'meta' }, ['All league players already registered.']));
        }
        card.appendChild(leagueDiv);
      }

      // Panel: existing player (dropdown)
      const existingDiv = UI.html('div', { id: 'add-existing-panel', style: 'display: none' });
      if (available.length) {
        const select = UI.html('select', { id: 'add-existing-select' },
          [UI.html('option', { value: '' }, ['— select player —'])].concat(
            available.map((p) => UI.html('option', { value: p.uuid }, [p.nickname || p.uuid.substring(0, 8)]))
          )
        );
        existingDiv.appendChild(select);
        existingDiv.appendChild(UI.html('button', {
          className: 'btn btn-primary btn-sm', style: 'margin-left: 8px',
          onclick: () => addExisting(tournamentId),
        }, ['Add']));
      } else {
        existingDiv.appendChild(UI.html('p', { className: 'meta' }, ['All known players already registered.']));
      }
      card.appendChild(existingDiv);

      // Panel: new player
      const keyHandler = (e) => { if (e.key === 'Enter') { e.preventDefault(); addNew(tournamentId); } };
      const newDiv = UI.html('div', { id: 'add-new-panel', style: 'display: none' }, [
        UI.html('div', { style: 'display: flex; gap: 8px; flex-wrap: wrap; align-items: end' }, [
          UI.html('div', { className: 'form-group', style: 'flex: 1; min-width: 120px' }, [
            UI.html('label', {}, ['Nickname *']),
            UI.html('input', { id: 'new-p-nickname', type: 'text', placeholder: 'Nickname', onkeydown: keyHandler }),
          ]),
          UI.html('div', { className: 'form-group', style: 'flex: 1; min-width: 120px' }, [
            UI.html('label', {}, ['First name']),
            UI.html('input', { id: 'new-p-first', type: 'text', onkeydown: keyHandler }),
          ]),
          UI.html('div', { className: 'form-group', style: 'flex: 1; min-width: 120px' }, [
            UI.html('label', {}, ['Last name']),
            UI.html('input', { id: 'new-p-last', type: 'text', onkeydown: keyHandler }),
          ]),
          UI.html('button', {
            className: 'btn btn-primary btn-sm', style: 'margin-bottom: 12px',
            onclick: () => addNew(tournamentId),
          }, ['Create & Add']),
        ]),
      ]);
      card.appendChild(newDiv);

      // Auto-show: applicants if any, else league if linked, else all players
      if (applicants.length) showTab('applicants');
      else if (t.league_id) showTab('league');
      else showTab('applicants');
    }

    return card;
  }

  function _tabBtn(name, label) {
    return UI.html('button', {
      className: 'btn btn-secondary btn-sm',
      id: `tab-${name}`,
      onclick: () => showTab(name),
    }, [label]);
  }

  function showTab(which) {
    for (const id of ['applicants', 'league', 'existing', 'new']) {
      const el = document.getElementById(`add-${id}-panel`);
      if (el) el.style.display = id === which ? '' : 'none';
      const btn = document.getElementById(`tab-${id}`);
      if (btn) btn.style.fontWeight = id === which ? 'bold' : 'normal';
    }
  }

  async function addExisting(tournamentId) {
    const sel = document.getElementById('add-existing-select');
    const pid = sel?.value;
    if (!pid) { UI.toast('Select a player', 'error'); return; }
    await doAction(() => API.addPlayer(tournamentId, pid), 'Player added!');
  }

  async function addNew(tournamentId) {
    const nickname = document.getElementById('new-p-nickname')?.value?.trim();
    if (!nickname) { UI.toast('Nickname is required', 'error'); return; }
    try {
      const player = await API.createPlayer({
        nickname,
        first_name: document.getElementById('new-p-first')?.value?.trim() || undefined,
        last_name: document.getElementById('new-p-last')?.value?.trim() || undefined,
      });
      await API.addPlayer(tournamentId, player.uuid);
      UI.toast(`${nickname} created & added!`, 'success');
      render(_tournamentId);
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  }

  async function acceptApplicant(tournamentId, playerId, nickname) {
    try {
      await API.addPlayer(tournamentId, playerId);
      UI.toast(`${nickname || 'Player'} accepted!`, 'success');
      render(_tournamentId);
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  }

  async function acceptAllApplicants(tournamentId, applicants) {
    let count = 0;
    for (const a of applicants) {
      try { await API.addPlayer(tournamentId, a.uuid); count++; }
      catch (_) { /* skip failed */ }
    }
    UI.toast(`${count} players accepted!`, 'success');
    render(_tournamentId);
  }

  async function addAllFromList(tournamentId, players) {
    let count = 0;
    for (const p of players) {
      try { await API.addPlayer(tournamentId, p.uuid); count++; }
      catch (_) { /* skip failed */ }
    }
    UI.toast(`${count} players added!`, 'success');
    render(_tournamentId);
  }

  async function doDelete(id, name) {
    if (!confirm(`Delete tournament "${name || id}"? This cannot be undone.`)) return;
    try {
      await API.deleteTournament(id);
      UI.toast('Tournament deleted', 'success');
      App.navigate('tournaments');
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  }

  async function doAction(fn, successMsg) {
    try {
      await fn();
      UI.toast(successMsg, 'success');
      // Suppress WS events — we already showed feedback + will render ourselves
      _suppressUntil = Date.now() + 2000;
      render(_tournamentId);
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  let _renderTimeout = null;
  function _debouncedRender() {
    if (_renderTimeout) clearTimeout(_renderTimeout);
    _renderTimeout = setTimeout(() => render(_tournamentId), 500);
  }

  function onLiveEvent(event) {
    if (Date.now() < _suppressUntil) return; // ignore events from own actions

    const notifyEvents = {
      applicant_registered: (e) => `✋ ${e.data?.nickname || 'Someone'} wants to play!`,
    };
    const fmt = notifyEvents[event.type];
    if (fmt) UI.toast(fmt(event), 'info');

    if (['round_drawn', 'bracket_generated', 'match_finished', 'score_updated', 'applicant_registered'].includes(event.type)) {
      _debouncedRender();
    }
  }

  function cleanup() { WS.disconnect(); WS.offEvent(onLiveEvent); }

  return { render, cleanup };
})();
