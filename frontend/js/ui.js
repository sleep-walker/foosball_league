/**
 * UI utilities — toast notifications, DOM helpers, navigation.
 */
import { html as litHtml, render as litRender } from 'lit-html';
import { t } from './i18n.js';
const content = () => document.getElementById('app-content');
const title = (text) => { document.getElementById('page-title').textContent = text; };

function toast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function htmlEl(tag, attrs = {}, children = []) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith('on') && typeof v === 'function') {
      el.addEventListener(k.slice(2).toLowerCase(), v);
    } else if (k === 'className') el.className = v;
    else el.setAttribute(k, v);
  }
  for (const child of children) {
    if (typeof child === 'string') el.appendChild(document.createTextNode(child));
    else if (child) el.appendChild(child);
  }
  return el;
}

function statusBadge(status) {
  return htmlEl('span', { className: `badge badge-${status}` }, [status]);
}

function table(headers, rows) {
  const thead = htmlEl('thead', {}, [
    htmlEl('tr', {}, headers.map((h) => htmlEl('th', {}, [h]))),
  ]);
  const tbody = htmlEl('tbody', {}, rows.map((row) =>
    htmlEl('tr', {}, row.map((cell) =>
      htmlEl('td', {}, [typeof cell === 'string' ? cell : cell])
    ))
  ));
  return htmlEl('table', { className: 'data-table' }, [thead, tbody]);
}

function render(el) {
  const c = content();
  // Clear everything — including lit-html tracked state
  c.innerHTML = '';
  delete c['_$litPart$'];
  if (typeof el === 'string') c.innerHTML = el;
  else c.appendChild(el);
}

function loading() { render(htmlEl('div', { className: 'loading' }, [t('common.loading')])); }
function error(msg) { render(htmlEl('div', { className: 'loading' }, [t('common.error', { msg })])); }

/**
 * Render a lit-html template into the main content area.
 * Replaces the old imperative render() for pages that use lit-html templates.
 */
function renderPage(template) {
  const c = content();
  // Clear any imperative content before lit-html render
  c.innerHTML = '';
  delete c['_$litPart$'];
  litRender(template, c);
}

const UI = { content, title, toast, html: htmlEl, statusBadge, table, render, loading, error, renderPage };
export { litHtml as html, litRender };
export default UI;
