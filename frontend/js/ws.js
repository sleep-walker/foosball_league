/**
 * WebSocket client for live tournament updates.
 */
let _socket = null;
let _tournamentId = null;
const _listeners = [];

function connect(tournamentId) {
  disconnect();
  _tournamentId = tournamentId;
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${proto}//${location.host}/ws/tournaments/${tournamentId}`;
  _socket = new WebSocket(url);

  _socket.onmessage = (evt) => {
    try {
      const event = JSON.parse(evt.data);
      _listeners.forEach((fn) => fn(event));
    } catch (e) { console.warn('WS parse error', e); }
  };

  _socket.onclose = () => {
    // Auto-reconnect after 3s
    setTimeout(() => {
      if (_tournamentId === tournamentId) connect(tournamentId);
    }, 3000);
  };
}

function disconnect() {
  if (_socket) { _socket.close(); _socket = null; }
  _tournamentId = null;
}

function onEvent(fn) { _listeners.push(fn); }
function offEvent(fn) { const i = _listeners.indexOf(fn); if (i >= 0) _listeners.splice(i, 1); }

const WS = { connect, disconnect, onEvent, offEvent };
export default WS;
