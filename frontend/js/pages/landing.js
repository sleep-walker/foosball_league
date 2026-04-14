/**
 * Landing page — shown to unauthenticated visitors.
 */
const LandingPage = (() => {
  function render() {
    UI.title('Foosball League');

    const container = UI.html('div', {}, [
      UI.html('div', { className: 'card', style: 'text-align: center; padding: 32px' }, [
        UI.html('h2', { style: 'margin-bottom: 12px' }, ['⚽ Welcome to Foosball League']),
        UI.html('p', { style: 'color: #666; margin-bottom: 20px' }, [
          'Manage tournaments, track standings, and compete with friends.',
        ]),
        UI.html('div', { style: 'display: flex; gap: 12px; justify-content: center; flex-wrap: wrap' }, [
          UI.html('button', {
            className: 'btn btn-primary',
            onclick: () => App.navigate('login'),
          }, ['🔑 Sign In / Register']),
          UI.html('button', {
            className: 'btn btn-secondary',
            onclick: () => App.navigate('live'),
          }, ['📺 Live View']),
        ]),
      ]),
      UI.html('div', { className: 'card' }, [
        UI.html('h3', {}, ['What is Foosball League?']),
        UI.html('ul', { style: 'margin: 8px 0 0 20px; line-height: 1.8' }, [
          UI.html('li', {}, ['🏆 Organize Swiss, DYP, and elimination tournaments']),
          UI.html('li', {}, ['📊 Live standings and bracket updates via WebSocket']),
          UI.html('li', {}, ['📱 Works on phone — install as an app (PWA)']),
          UI.html('li', {}, ['📺 Public view for TV screens and projectors']),
          UI.html('li', {}, ['📤 Export results as JSON, CSV, or PDF']),
          UI.html('li', {}, ['🎲 Swiss pairing, DYP, Monster DYP, single & double elimination']),
          UI.html('li', {}, ['🏅 Long-running leagues with Elo, placement points, or W/L scoring']),
        ]),
      ]),
    ]);

    UI.render(container);
  }

  return { render };
})();
