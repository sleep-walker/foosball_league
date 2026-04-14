/**
 * Players list page.
 */
const PlayersPage = (() => {
  async function render() {
    UI.title('Players');
    UI.loading();
    try {
      const items = await API.players();
      const rows = items.map((p) => [
        p.nickname || '—',
        p.first_name || '', p.last_name || '',
        p.email || '—',
      ]);
      const container = UI.html('div', {}, [
        UI.table(['Nickname', 'First', 'Last', 'Email'], rows),
      ]);
      UI.render(container);
    } catch (e) {
      UI.error(e.message);
    }
  }
  return { render };
})();
