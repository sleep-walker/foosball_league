/**
 * Public self-registration page — linked from QR code.
 * URL: #register/{tournament_id}
 * No login required.
 */
const RegisterPage = (() => {
  let _tournamentId = null;
  let _token = null;

  async function render(id) {
    _tournamentId = id;
    // Extract token from hash: #register/{id}?token=xxx
    const hashParts = window.location.hash.split('?');
    const params = new URLSearchParams(hashParts[1] || '');
    _token = params.get('token') || '';
    UI.title('Tournament Registration');
    UI.loading();

    try {
      const t = await API.publicTournament(id);

      const keyHandler = (e) => { if (e.key === 'Enter') { e.preventDefault(); doRegister(); } };

      const container = UI.html('div', {}, [
        UI.html('div', { className: 'card', style: 'text-align: center' }, [
          UI.html('h2', {}, [t.name || 'Tournament']),
          UI.html('div', { className: 'meta' }, [
            `📅 ${t.date}  📍 ${t.location || ''}`,
          ]),
          UI.html('div', { style: 'margin-top: 8px' }, [
            UI.statusBadge(t.status),
            UI.html('span', { className: 'meta', style: 'margin-left: 8px' }, [
              `${t.player_count} players`,
            ]),
          ]),
        ]),
      ]);

      if (!t.is_registration_open && t.status !== 'registration') {
        container.appendChild(UI.html('div', { className: 'card' }, [
          UI.html('p', { style: 'color: #c0392b' }, ['Registration is closed.']),
        ]));
        UI.render(container);
        return;
      }

      if (!_token) {
        container.appendChild(UI.html('div', { className: 'card' }, [
          UI.html('p', { style: 'color: #c0392b' }, [
            '⚠ Please scan the QR code at the venue to register.',
          ]),
        ]));
        UI.render(container);
        return;
      }

      container.appendChild(UI.html('div', { className: 'card' }, [
        UI.html('h3', {}, ['Sign up to play']),
        UI.html('div', { className: 'form-group' }, [
          UI.html('label', {}, ['Nickname *']),
          UI.html('input', { id: 'reg-nickname', type: 'text', placeholder: 'Your nickname', onkeydown: keyHandler }),
        ]),
        UI.html('div', { className: 'form-group' }, [
          UI.html('label', {}, ['First name']),
          UI.html('input', { id: 'reg-first', type: 'text', onkeydown: keyHandler }),
        ]),
        UI.html('div', { className: 'form-group' }, [
          UI.html('label', {}, ['Last name']),
          UI.html('input', { id: 'reg-last', type: 'text', onkeydown: keyHandler }),
        ]),
        UI.html('button', { className: 'btn btn-primary', onclick: () => doRegister() }, ['✋ I want to play!']),
      ]));

      // Show current player list
      if (t.players && t.players.length) {
        const rows = t.players.map((p, i) => [String(i + 1), p.nickname || '—']);
        container.appendChild(UI.html('div', { className: 'card' }, [
          UI.html('h3', {}, ['Already registered']),
          UI.table(['#', 'Player'], rows),
        ]));
      }

      UI.render(container);
      // Auto-focus nickname field
      document.getElementById('reg-nickname')?.focus();
    } catch (e) {
      UI.error(e.message);
    }
  }

  async function doRegister() {
    const nickname = document.getElementById('reg-nickname')?.value?.trim();
    if (!nickname) { UI.toast('Nickname is required', 'error'); return; }

    try {
      const res = await fetch(`/v1/public/tournaments/${_tournamentId}/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nickname,
          first_name: document.getElementById('reg-first')?.value?.trim() || null,
          last_name: document.getElementById('reg-last')?.value?.trim() || null,
          token: _token,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        UI.toast(data.detail || 'Registration failed', 'error');
        return;
      }
      UI.toast(data.message, 'success');
      // Re-render to show updated player list
      render(_tournamentId);
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  }

  return { render };
})();
