/**
 * Leagues list page with create form.
 */
const LeaguesPage = (() => {
  const SCORING_TYPES = [
    ['placement_points', 'Placement Points'],
    ['elo', 'Elo Rating'],
    ['win_loss', 'Win/Loss Points'],
  ];

  async function render() {
    UI.title('Leagues');
    UI.loading();
    try {
      const items = await API.leagues();
      const container = UI.html('div', {});

      container.appendChild(UI.html('button', {
        className: 'btn btn-primary', style: 'margin-bottom: 12px',
        onclick: () => showCreateForm(container),
      }, ['+ New League']));

      if (!items.length) {
        container.appendChild(UI.html('p', { className: 'loading' }, ['No leagues yet. Create one!']));
      }
      for (const l of items) {
        const card = UI.html('div', { className: 'card' }, [
          UI.html('h3', {}, [l.name || 'Unnamed League']),
          UI.html('div', { className: 'meta' }, [
            `Scoring: ${l.scoring_type || '—'}  |  ${l.description || ''}`,
          ]),
          UI.html('button', {
            className: 'btn btn-secondary btn-sm', style: 'margin-top: 8px',
            onclick: () => showLeagueDetail(l.uuid, container),
          }, ['Manage players']),
        ]);
        card.id = `league-${l.uuid}`;
        container.appendChild(card);
      }
      UI.render(container);
    } catch (e) {
      UI.error(e.message);
    }
  }

  function showCreateForm(container) {
    const keyHandler = (e) => { if (e.key === 'Enter') { e.preventDefault(); doCreate(); } };
    const scoringSelect = UI.html('select', { id: 'new-l-scoring' },
      SCORING_TYPES.map(([val, label]) => UI.html('option', { value: val }, [label]))
    );
    const form = UI.html('div', { className: 'card' }, [
      UI.html('h3', {}, ['New League']),
      UI.html('div', { className: 'form-group' }, [
        UI.html('label', {}, ['Name']),
        UI.html('input', { id: 'new-l-name', type: 'text', placeholder: 'Tuesday League', onkeydown: keyHandler }),
      ]),
      UI.html('div', { className: 'form-group' }, [
        UI.html('label', {}, ['Description']),
        UI.html('input', { id: 'new-l-desc', type: 'text', placeholder: 'Weekly foosball league', onkeydown: keyHandler }),
      ]),
      UI.html('div', { className: 'form-group' }, [
        UI.html('label', {}, ['Scoring']),
        scoringSelect,
      ]),
      UI.html('button', { className: 'btn btn-primary', onclick: () => doCreate() }, ['Create']),
    ]);
    container.insertBefore(form, container.children[1]);
  }

  async function doCreate() {
    try {
      await API.createLeague({
        name: document.getElementById('new-l-name').value,
        description: document.getElementById('new-l-desc').value,
        scoring_type: document.getElementById('new-l-scoring').value,
      });
      UI.toast('League created!', 'success');
      render();
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  }

  async function showLeagueDetail(leagueId, container) {
    const detailId = `league-detail-${leagueId}`;
    let existing = document.getElementById(detailId);
    if (existing) { existing.remove(); return; } // toggle

    const card = document.getElementById(`league-${leagueId}`);
    if (!card) return;

    const detail = UI.html('div', { id: detailId, className: 'card', style: 'margin-top: 4px' });

    // Load current members
    let members = [];
    try { members = await API.leaguePlayers(leagueId); } catch (_) {}

    detail.appendChild(UI.html('h4', {}, [`Members (${members.length})`]));
    if (members.length) {
      const rows = members.map((p, i) => [
        String(i + 1), p.nickname || '—',
        `${p.first_name || ''} ${p.last_name || ''}`.trim() || '—',
      ]);
      detail.appendChild(UI.table(['#', 'Nickname', 'Name'], rows));
    }

    // --- Add player: existing ---
    detail.appendChild(UI.html('h4', { style: 'margin-top: 12px' }, ['Add player']));

    let allPlayers = [];
    try { allPlayers = await API.players(); } catch (_) {}
    const memberIds = new Set(members.map((m) => m.uuid));
    const available = allPlayers.filter((p) => !memberIds.has(p.uuid));

    if (available.length) {
      const select = UI.html('select', { id: `add-lp-${leagueId}` },
        [UI.html('option', { value: '' }, ['— existing player —'])].concat(
          available.map((p) => UI.html('option', { value: p.uuid }, [p.nickname || p.uuid.substring(0, 8)]))
        )
      );
      detail.appendChild(UI.html('div', { style: 'display: flex; gap: 8px; align-items: center; margin-bottom: 8px' }, [
        select,
        UI.html('button', {
          className: 'btn btn-primary btn-sm',
          onclick: () => _addExistingToLeague(leagueId, detailId, container),
        }, ['+ Add']),
      ]));
    }

    // --- Add player: create new ---
    const kh = (e) => { if (e.key === 'Enter') { e.preventDefault(); _createAndAddToLeague(leagueId, detailId, container); } };
    detail.appendChild(UI.html('div', { style: 'display: flex; gap: 8px; flex-wrap: wrap; align-items: end' }, [
      UI.html('div', { className: 'form-group', style: 'flex: 1; min-width: 100px' }, [
        UI.html('label', {}, ['Nickname *']),
        UI.html('input', { id: `new-lp-nick-${leagueId}`, type: 'text', placeholder: 'Nickname', onkeydown: kh }),
      ]),
      UI.html('div', { className: 'form-group', style: 'flex: 1; min-width: 100px' }, [
        UI.html('label', {}, ['First name']),
        UI.html('input', { id: `new-lp-first-${leagueId}`, type: 'text', onkeydown: kh }),
      ]),
      UI.html('div', { className: 'form-group', style: 'flex: 1; min-width: 100px' }, [
        UI.html('label', {}, ['Last name']),
        UI.html('input', { id: `new-lp-last-${leagueId}`, type: 'text', onkeydown: kh }),
      ]),
      UI.html('button', {
        className: 'btn btn-primary btn-sm', style: 'margin-bottom: 12px',
        onclick: () => _createAndAddToLeague(leagueId, detailId, container),
      }, ['Create & Add']),
    ]));

    card.after(detail);
  }

  async function _addExistingToLeague(leagueId, detailId, container) {
    const pid = document.getElementById(`add-lp-${leagueId}`)?.value;
    if (!pid) { UI.toast('Select a player', 'error'); return; }
    try {
      await API.post(`/api/v1/leagues/${leagueId}/players/?player_id=${pid}`);
      UI.toast('Player added!', 'success');
      document.getElementById(detailId)?.remove();
      showLeagueDetail(leagueId, container);
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  async function _createAndAddToLeague(leagueId, detailId, container) {
    const nickname = document.getElementById(`new-lp-nick-${leagueId}`)?.value?.trim();
    if (!nickname) { UI.toast('Nickname is required', 'error'); return; }
    try {
      const player = await API.createPlayer({
        nickname,
        first_name: document.getElementById(`new-lp-first-${leagueId}`)?.value?.trim() || undefined,
        last_name: document.getElementById(`new-lp-last-${leagueId}`)?.value?.trim() || undefined,
      });
      await API.post(`/api/v1/leagues/${leagueId}/players/?player_id=${player.uuid}`);
      UI.toast(`${nickname} created & added!`, 'success');
      document.getElementById(detailId)?.remove();
      showLeagueDetail(leagueId, container);
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  return { render };
})();
