/**
 * API client — handles all communication with the backend.
 */
const BASE = '/api/v1';
const PUBLIC = '/api/v1/public';
let _token = localStorage.getItem('auth_token') || null;

function setToken(token) {
  _token = token;
  if (token) localStorage.setItem('auth_token', token);
  else localStorage.removeItem('auth_token');
}

function getToken() { return _token; }
function isLoggedIn() { return !!_token; }

async function _fetch(url, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (_token) headers['Authorization'] = `Bearer ${_token}`;
  const res = await fetch(url, { ...opts, headers });
  if (res.status === 401) { setToken(null); throw new Error('Unauthorized'); }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    let msg = `HTTP ${res.status}`;
    if (typeof body.detail === 'string') msg = body.detail;
    else if (Array.isArray(body.detail)) msg = body.detail.map((e) => e.msg || JSON.stringify(e)).join('; ');
    else if (body.detail) msg = JSON.stringify(body.detail);
    throw new Error(msg);
  }
  if (res.status === 204) return null;
  return res.json();
}

const get = (path) => _fetch(path);
const post = (path, data) => _fetch(path, { method: 'POST', body: JSON.stringify(data) });
const patch = (path, data) => _fetch(path, { method: 'PATCH', body: JSON.stringify(data) });
const del = (path) => _fetch(path, { method: 'DELETE' });

// --- Auth ---
async function register(email, password) {
  const res = await fetch(`${BASE}/users/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || 'Registration failed');
  }
  return res.json();
}

async function login(email, password) {
  const form = new URLSearchParams({ username: email, password });
  const res = await fetch(`${BASE}/users/login`, {
    method: 'POST', body: form,
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  if (!res.ok) throw new Error('Login failed');
  const data = await res.json();
  setToken(data.access_token);
  return data;
}

function logout() { setToken(null); }

// --- Public (no auth) ---
const publicTournament = (id) => get(`${PUBLIC}/tournaments/${id}`);
const publicStandings = (tid, sid) => get(`${PUBLIC}/tournaments/${tid}/stages/${sid}/standings`);
const publicMatches = (tid, sid, round) => {
  let url = `${PUBLIC}/tournaments/${tid}/stages/${sid}/matches`;
  if (round != null) url += `?round_number=${round}`;
  return get(url);
};
const publicLeague = (id) => get(`${PUBLIC}/leagues/${id}`);
const publicLeagueStandings = (id) => get(`${PUBLIC}/leagues/${id}/standings`);

// --- Authenticated ---
const me = () => get(`${BASE}/users/me`);
const tournaments = () => get(`${BASE}/tournaments/`);
const tournament = (id) => get(`${BASE}/tournaments/${id}`);
const createTournament = (data) => post(`${BASE}/tournaments/`, data);
const startTournament = (id) => post(`${BASE}/tournaments/${id}/start`);
const finishTournament = (id) => post(`${BASE}/tournaments/${id}/finish`);
const deleteTournament = (id) => del(`${BASE}/tournaments/${id}`);
const myPlayer = () => get(`${BASE}/users/me/player`);
const matches = (tid) => get(`${BASE}/tournaments/${tid}/matches/`);
const submitScore = (matchId, scoreA, scoreB) =>
  patch(`${BASE}/matches/${matchId}/score`, { score_a: scoreA, score_b: scoreB });
const submitScores = (matchId, scores) =>
  patch(`${BASE}/matches/${matchId}/scores`, { scores });
const drawRound = (tid, sid) => post(`${BASE}/tournaments/${tid}/stages/${sid}/draw-round`);
const generateBracket = (tid, sid, src) => {
  let url = `${BASE}/tournaments/${tid}/stages/${sid}/generate-bracket`;
  if (src) url += `?source_stage_id=${src}`;
  return post(url);
};
const addPlayer = (tid, pid) => post(`${BASE}/tournaments/${tid}/players/?player_id=${pid}`);
const pausePlayer = (tid, pid) => post(`${BASE}/tournaments/${tid}/players/${pid}/pause`);
const unpausePlayer = (tid, pid) => post(`${BASE}/tournaments/${tid}/players/${pid}/unpause`);
const createPlayer = (data) => post(`${BASE}/players/`, data);
const leagues = () => get(`${BASE}/leagues/`);
const league = (id) => get(`${BASE}/leagues/${id}`);
const createLeague = (data) => post(`${BASE}/leagues/`, data);
const leaguePlayers = (id) => get(`${BASE}/leagues/${id}/players`);
const leagueStandings = (id) => get(`${BASE}/leagues/${id}/standings`);
const leagueRulePresets = (id) => get(`${BASE}/leagues/${id}/rule-presets`);
const createLeagueRulePreset = (id, data) => post(`${BASE}/leagues/${id}/rule-presets`, data);
const updateLeagueRulePreset = (leagueId, presetId, data) => patch(`${BASE}/leagues/${leagueId}/rule-presets/${presetId}`, data);
const deleteLeagueRulePreset = (leagueId, presetId) => del(`${BASE}/leagues/${leagueId}/rule-presets/${presetId}`);
const players = () => get(`${BASE}/players/`);
const standings = (tid, sid) => get(`${BASE}/tournaments/${tid}/stages/${sid}/standings`);

const API = {
  setToken, getToken, isLoggedIn, register, login, logout, me,
  tournaments, tournament, createTournament, startTournament, finishTournament, deleteTournament,
  myPlayer, matches, submitScore, submitScores, drawRound, generateBracket, addPlayer, pausePlayer, unpausePlayer,
  createPlayer, leagues, league, createLeague, leaguePlayers, leagueStandings,
  leagueRulePresets, createLeagueRulePreset, updateLeagueRulePreset, deleteLeagueRulePreset,
  players, standings,
  publicTournament, publicStandings, publicMatches, publicLeague, publicLeagueStandings,
  get, post, patch, del,
};
export default API;
