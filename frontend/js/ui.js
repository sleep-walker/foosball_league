/**
 * UI utilities — toast notifications, DOM helpers, navigation.
 */
const UI = (() => {
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

  function html(tag, attrs = {}, children = []) {
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
    return html('span', { className: `badge badge-${status}` }, [status]);
  }

  function table(headers, rows) {
    const thead = html('thead', {}, [
      html('tr', {}, headers.map((h) => html('th', {}, [h]))),
    ]);
    const tbody = html('tbody', {}, rows.map((row) =>
      html('tr', {}, row.map((cell) =>
        html('td', {}, [typeof cell === 'string' ? cell : cell])
      ))
    ));
    return html('table', { className: 'data-table' }, [thead, tbody]);
  }

  function render(el) {
    const c = content();
    c.innerHTML = '';
    if (typeof el === 'string') c.innerHTML = el;
    else c.appendChild(el);
  }

  function loading() { render(html('div', { className: 'loading' }, ['Loading...'])); }
  function error(msg) { render(html('div', { className: 'loading' }, [`Error: ${msg}`])); }

  return { content, title, toast, html, statusBadge, table, render, loading, error };
})();
