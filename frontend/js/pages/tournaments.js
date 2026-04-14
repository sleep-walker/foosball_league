/**
 * Tournaments list page (authenticated only).
 */
const TournamentsPage = (() => {
  async function render() {
    UI.title('Tournaments');
    UI.loading();
    try {
      const items = await API.tournaments();
      const container = UI.html('div', {});

      container.appendChild(UI.html('button', {
        className: 'btn btn-primary',
        onclick: () => showCreateForm(container),
      }, ['+ New Tournament']));

      if (!items.length) {
        container.appendChild(UI.html('p', { className: 'loading' }, ['No tournaments yet. Create one!']));
      }

      for (const t of items) {
        const card = UI.html('div', { className: 'card', onclick: () => App.navigate('tournament-detail', t.uuid) }, [
          UI.html('h3', {}, [t.name || 'Unnamed Tournament']),
          UI.html('div', { className: 'meta' }, [
            `📅 ${t.date}  📍 ${t.location || '—'}  `,
          ]),
          UI.html('div', { style: 'margin-top: 6px' }, [
            UI.statusBadge(t.status || 'preparing'),
            UI.html('span', { className: 'meta', style: 'margin-left: 8px' }, [
              `${(t.registrations || []).length} players`,
            ]),
          ]),
        ]);
        container.appendChild(card);
      }

      UI.render(container);
    } catch (e) {
      UI.error(e.message);
    }
  }

  const PLAYER_MODES = [
    ['singles', 'Singles (1v1)'],
    ['doubles', 'Doubles (2v2)'],
  ];

  async function showCreateForm(container) {
    const today = new Date().toISOString().slice(0, 10);
    const keyHandler = (e) => { if (e.key === 'Enter') { e.preventDefault(); doCreate(); } };

    const modeSelect = UI.html('select', { id: 'new-t-mode' },
      PLAYER_MODES.map(([val, label]) => UI.html('option', { value: val }, [label]))
    );

    // Load leagues for selection
    let allLeagues = [];
    try { allLeagues = await API.leagues(); } catch (_) {}
    const leagueSelect = UI.html('select', { id: 'new-t-league' },
      [UI.html('option', { value: '' }, ['— no league —'])].concat(
        allLeagues.map((l) => UI.html('option', { value: l.uuid }, [l.name]))
      )
    );

    const form = UI.html('div', { className: 'card' }, [
      UI.html('h3', {}, ['New Tournament']),
      _field('Name', 'new-t-name', 'text', 'Tuesday Foosball', keyHandler),
      _dateField('Date', 'new-t-date', today, keyHandler),
      _field('Location', 'new-t-location', 'text', 'Pub U Fleků', keyHandler),
      UI.html('div', { className: 'form-group' }, [
        UI.html('label', { for: 'new-t-mode' }, ['Player Mode']),
        modeSelect,
      ]),
      UI.html('div', { className: 'form-group' }, [
        UI.html('label', { for: 'new-t-league' }, ['League (optional)']),
        leagueSelect,
      ]),
      UI.html('div', { style: 'margin-top: 12px' }, [
        UI.html('button', { className: 'btn btn-primary', onclick: () => doCreate() }, ['Create']),
      ]),
    ]);
    container.insertBefore(form, container.children[1]);
  }

  function _field(label, id, type, placeholder = '', keyHandler = null) {
    const attrs = { id, type, placeholder };
    if (keyHandler) attrs.onkeydown = keyHandler;
    return UI.html('div', { className: 'form-group' }, [
      UI.html('label', { for: id }, [label]),
      UI.html('input', attrs),
    ]);
  }

  function _dateField(label, id, defaultValue, keyHandler = null) {
    const attrs = { id, type: 'date', value: defaultValue };
    if (keyHandler) attrs.onkeydown = keyHandler;
    return UI.html('div', { className: 'form-group' }, [
      UI.html('label', { for: id }, [label]),
      UI.html('input', attrs),
    ]);
  }

  async function doCreate() {
    try {
      const leagueId = document.getElementById('new-t-league')?.value || undefined;
      const data = {
        name: document.getElementById('new-t-name').value,
        date: document.getElementById('new-t-date').value || new Date().toISOString().slice(0, 10),
        location: document.getElementById('new-t-location').value,
        player_mode: document.getElementById('new-t-mode').value,
        league_id: leagueId || undefined,
      };
      const t = await API.createTournament(data);
      UI.toast('Tournament created!', 'success');
      App.navigate('tournament-detail', t.uuid);
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  }

  return { render };
})();
