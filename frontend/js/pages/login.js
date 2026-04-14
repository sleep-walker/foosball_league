/**
 * Login & Registration page.
 */
const LoginPage = (() => {
  let _mode = 'login'; // 'login' | 'register'

  function render() {
    UI.title(_mode === 'login' ? 'Sign In' : 'Register');

    if (API.isLoggedIn()) {
      renderLoggedIn();
      return;
    }

    if (_mode === 'register') {
      renderRegister();
    } else {
      renderLogin();
    }
  }

  function _onEnter(submitFn) {
    return (e) => { if (e.key === 'Enter') { e.preventDefault(); submitFn(); } };
  }

  function renderLogin() {
    const keyHandler = _onEnter(doLogin);
    const container = UI.html('div', { className: 'card' }, [
      UI.html('h3', {}, ['Sign In']),
      UI.html('div', { className: 'form-group' }, [
        UI.html('label', { for: 'login-email' }, ['Email']),
        UI.html('input', { id: 'login-email', type: 'email', placeholder: 'you@example.com', onkeydown: keyHandler }),
      ]),
      UI.html('div', { className: 'form-group' }, [
        UI.html('label', { for: 'login-pass' }, ['Password']),
        UI.html('input', { id: 'login-pass', type: 'password', onkeydown: keyHandler }),
      ]),
      UI.html('button', { className: 'btn btn-primary', onclick: () => doLogin() }, ['Login']),
      UI.html('p', { style: 'margin-top: 16px; font-size: 0.9rem' }, [
        "Don't have an account? ",
        UI.html('a', {
          href: '#', style: 'color: #0f3460; font-weight: 600',
          onclick: (e) => { e.preventDefault(); _mode = 'register'; render(); },
        }, ['Register here']),
      ]),
    ]);
    UI.render(container);
  }

  function renderRegister() {
    const keyHandler = _onEnter(doRegister);
    const container = UI.html('div', { className: 'card' }, [
      UI.html('h3', {}, ['Create Account']),
      UI.html('div', { className: 'form-group' }, [
        UI.html('label', { for: 'reg-email' }, ['Email']),
        UI.html('input', { id: 'reg-email', type: 'email', placeholder: 'you@example.com', onkeydown: keyHandler }),
      ]),
      UI.html('div', { className: 'form-group' }, [
        UI.html('label', { for: 'reg-pass' }, ['Password (min 8 chars)']),
        UI.html('input', { id: 'reg-pass', type: 'password', onkeydown: keyHandler }),
      ]),
      UI.html('div', { className: 'form-group' }, [
        UI.html('label', { for: 'reg-pass2' }, ['Confirm password']),
        UI.html('input', { id: 'reg-pass2', type: 'password', onkeydown: keyHandler }),
      ]),
      UI.html('div', { className: 'form-group' }, [
        UI.html('label', { for: 'reg-nickname' }, ['Nickname (for player profile)']),
        UI.html('input', { id: 'reg-nickname', type: 'text', placeholder: 'Your nickname', onkeydown: keyHandler }),
      ]),
      UI.html('button', { className: 'btn btn-primary', onclick: () => doRegister() }, ['Register']),
      UI.html('p', { style: 'margin-top: 16px; font-size: 0.9rem' }, [
        'Already have an account? ',
        UI.html('a', {
          href: '#', style: 'color: #0f3460; font-weight: 600',
          onclick: (e) => { e.preventDefault(); _mode = 'login'; render(); },
        }, ['Sign in']),
      ]),
    ]);
    UI.render(container);
  }

  async function renderLoggedIn() {
    try {
      const user = await API.me();
      const container = UI.html('div', { className: 'card' }, [
        UI.html('h3', {}, [`Hello, ${user.email}`]),
        UI.html('p', { className: 'meta' }, [
          user.is_superuser ? '👑 Administrator' : '👤 User',
        ]),
        UI.html('button', {
          className: 'btn btn-secondary', style: 'margin-top: 12px',
          onclick: () => { API.logout(); _mode = 'login'; App.navigate('login'); },
        }, ['Logout']),
      ]);
      UI.render(container);
    } catch (e) {
      API.logout();
      _mode = 'login';
      render();
    }
  }

  async function doLogin() {
    const email = document.getElementById('login-email').value;
    const pass = document.getElementById('login-pass').value;
    if (!email || !pass) { UI.toast('Fill in all fields', 'error'); return; }
    try {
      await API.login(email, pass);
      UI.toast('Logged in!', 'success');
      App.navigate('tournaments');
    } catch (e) {
      UI.toast('Login failed: ' + e.message, 'error');
    }
  }

  async function doRegister() {
    const email = document.getElementById('reg-email').value;
    const pass = document.getElementById('reg-pass').value;
    const pass2 = document.getElementById('reg-pass2').value;
    const nickname = document.getElementById('reg-nickname').value;

    if (!email || !pass) { UI.toast('Fill in email and password', 'error'); return; }
    if (pass.length < 8) { UI.toast('Password must be at least 8 characters', 'error'); return; }
    if (pass !== pass2) { UI.toast('Passwords do not match', 'error'); return; }

    try {
      await API.register(email, pass);
      UI.toast('Account created! You can now sign in.', 'success');

      // Auto-login after registration
      try {
        await API.login(email, pass);
        // Create player profile if nickname provided
        if (nickname) {
          try { await API.post('/api/v1/players/', { nickname }); }
          catch (_) { /* may fail if not verified yet */ }
        }
        App.navigate('tournaments');
      } catch (_) {
        UI.toast('Registered, but your account may need verification. Try logging in.', 'info');
        _mode = 'login';
        render();
      }
    } catch (e) {
      UI.toast('Registration failed: ' + e.message, 'error');
    }
  }

  return { render };
})();
