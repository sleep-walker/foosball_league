/**
 * Players list page.
 */
import UI from '../ui.js';
import API from '../api.js';
import { html } from 'lit-html';
import { t } from '../i18n.js';

function playersTemplate(players) {
  return html`
    <table class="data-table">
      <thead>
        <tr><th>${t('player.nickname')}</th><th>${t('player.first')}</th><th>${t('player.last')}</th><th>${t('player.email')}</th></tr>
      </thead>
      <tbody>
        ${players.map((p) => html`
          <tr>
            <td>${p.nickname || t('common.em_dash')}</td>
            <td>${p.first_name || ''}</td>
            <td>${p.last_name || ''}</td>
            <td>${p.email || t('common.em_dash')}</td>
          </tr>
        `)}
      </tbody>
    </table>
  `;
}

const PlayersPage = {
  async render() {
    UI.title(t('player.title'));
    UI.loading();
    try {
      const items = await API.players();
      UI.renderPage(playersTemplate(items));
    } catch (e) {
      UI.error(e.message);
    }
  },
};

export default PlayersPage;
