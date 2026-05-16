# User Stories

## Roles

- **Organizer** — owns a league or tournament, manages registration, draws, and results.
- **Player** — a participant who joins tournaments.  No account needed — just scan the QR code.
- **Admin** — system-wide superuser (manages users, can intervene in any league/tournament).

---

## Story 1: Weekly Pub Tournament

A pub hosts a weekly foosball tournament.  The organizer chooses the **player
mode** (singles 1v1 or doubles 2v2) and the **team formation** method per stage
(DYP random, fixed pairs, or standings-based).

### Registration

- The organizer creates a tournament (name, date, location, player mode, entry fee).
- Optionally links the tournament to a **league** — league members are pre-suggested.
- The organizer opens **Live View** on a TV/projector and clicks **📱 Show QR**.
- Players scan the QR code on their phone.  The QR contains a **secret token** —
  only people physically at the venue can register (no remote cheating).
- The player enters a nickname → appears as **"✋ Want to play"** (applicant).
- The organizer clicks **✓ Accept** (or **Accept all**) to confirm registration
  and collect the entry fee.
- Walk-ins without a phone can be added manually by the organizer (existing
  player, from league, or brand-new unregistered player).

### Starting the tournament

- The organizer clicks **▶ Start Tournament**.
- Registration closes.
- For **doubles**: the system forms random teams (DYP) from all registered
  players.  Odd number of players → error (doubles needs even count).
- A default **group stage** is created automatically.
- The first Swiss round is drawn and table assignments are made.

### Phase 1 — Group Stage (Swiss, round by round)

Each round works as follows:

#### 1. Bye selection (if odd number of participants)

- **Singles, odd players**: 1 player sits out.
- **Doubles, odd teams**: this shouldn't happen (even players enforced), but if
  a player drops mid-tournament, 2 players (= 1 team) may sit out.
- **Who sits out?** The player/team who has played the **most games** so far.
  This ensures everyone plays approximately the same number of games.
- **Bye win**: configurable per tournament — the sitting-out player/team can
  optionally receive an automatic win (useful for elimination, less common
  in group stage).

#### 2. Team formation (doubles only)

Depends on the stage's `team_formation` setting:

| Setting         | Behaviour                                           |
|-----------------|-----------------------------------------------------|
| `random`        | New random teams every round (DYP style)            |
| `fixed`         | Teams set at tournament start, never change          |
| `from_results`  | After `random_rounds` rounds, pair strong+weak      |

Default: `random` with `random_rounds = 2` (same as Kickertool).

#### 3. Swiss pairing

- Teams (doubles) or players (singles) are the "participants".
- Swiss engine avoids repeating the same opponent pairing.
- After the initial `random_rounds`, pairing switches to standings-based
  (similar records play each other).

#### 4. Table assignment

- The tournament has N available tables (configured in `settings.table_count`).
- M matches are drawn for the round.
- If **M ≤ N**: each match is assigned a table (1, 2, 3, …).
- If **M > N**: first N matches play immediately; remaining matches are
  **queued** and start as tables free up.
- Goal: after each round, all participants have played approximately the
  same number of games.

#### 5. Notifications

- When a round is drawn, a **WebSocket event** `round_drawn` is sent.
- Players on their phone see: "Table 3: You + Pepa vs Karel + Jana".
- Players who sit out (bye) see: "You're sitting this one out."

#### 6. Score entry

- **By organizer**: in Tournament Detail, inline score entry per match.
- **By any participant**: on their phone (the self-registration page doubles
  as the player portal).  Any of the 4 players in a match can enter the score.
  The other players receive a notification with the entered score and who
  entered it.  Foosball players are honest.
- After a score is entered → WebSocket event `score_updated` → standings
  update live.

#### 7. Round completion → next round

- When all matches (including queued ones) in the current round are finished,
  the **🎲 Draw Next Round** button becomes active.
- The organizer draws the next round.  Repeat until enough rounds are played
  (typically 5–7).

### Phase 2 — Elimination (Knockout)

- Top players/teams from the group stage advance to a single-elimination bracket.
- Matches are **best of 3** (first to 2 wins), each game to 6 points.
  The deciding game requires a margin of 2 or more.
- **Semi-final losers play a 3rd-place match** before the final.
- Finals and the 3rd-place match may optionally be **best of 5**.
- The system generates the bracket and advances winners automatically.

### Live Standings

- Players can view **live standings on their phone** at any time — current round
  results, group table, elimination bracket.
- A **Live View** screen (TV/projector) at the venue shows the same data.
- The organizer can toggle **QR code display** on the Live View.

### Results & History

- Final standings (1st, 2nd, 3rd, …) are published at the end of the evening.
- Results can be **exported** as JSON, CSV, HTML, or PDF.
- Players can view their tournament history, win/loss record, and statistics.

---

## Story 2: Ongoing Office League

A group of colleagues want a long-running, casual foosball league at work.

### Setup

- An organizer creates a **league** (name, description, scoring type).
- Adds players to the league — existing players or creates new ones inline.
- When creating a tournament, links it to the league → league members are
  pre-suggested in the player dropdown.

### League Scoring Rules

Each league defines its own **scoring rules**:

| Scoring type       | Description                                          |
|--------------------|------------------------------------------------------|
| `placement_points` | Points based on tournament finishing position         |
| `elo`              | Elo rating (configurable K-factor, default 32)       |
| `win_loss`         | Simple W/L point accumulation                        |

### Casual Play (Office-style League)

- Two (or four) players meet at the foosball table whenever they like.
- They record the result in the app.
- The system maintains a **running leaderboard** according to the league's
  scoring rules.
- Over time, inactive scores may decay (configurable `erosion_factor`) so
  the standings stay fresh.

### Occasional League Tournament

- The organizer creates a tournament linked to the league.
- League members sign up via QR or are added by organizer.
- Tournament results feed into league standings.

### Public League Info

- Anyone with the league URL can see members and tournament count.
- League standings are accessible without authentication.

### Seasons

- The organizer can start a new season: archive current standings and begin
  fresh, or let the erosion mechanism keep things dynamic.

---

## Story 3: Player Experience

As a player I want a smooth mobile experience so I can focus on playing, not
on paperwork.

- I arrive at the venue, scan the QR code on the screen.
- I enter my nickname → I'm on the list (no account needed).
- The organizer accepts me → I'm registered.
- The tournament starts.  On my phone I see:
  - **My current match**: "Table 3: You + Pepa vs Karel + Jana"
  - If I'm sitting out: "You're sitting this one out."
- After the game I tap the score and submit — done.  My teammates/opponents
  get a notification with the score.
- I get notified when the next round is ready.
- I can check live standings at any time.
- Between tournaments I can browse my history: tournaments played, win rate.

---

## Story 4: Organizer Experience

As an organizer I want to run a tournament evening with minimal friction.

- I create tonight's tournament in 30 seconds: name, player mode, go.
- I open Live View on the projector and show the QR code.
- Players self-register; I click Accept All and collect fees.
- I tap **▶ Start** — teams are formed, first round is drawn, tables assigned.
- Scores flow in from players' phones; I only intervene on disputes.
- When all matches in the round are done, I tap **🎲 Draw Next Round**.
- After enough rounds, I tap **Generate bracket** for elimination playoffs.
- At the end I publish results with one tap.
- I can delete a tournament if something goes wrong.

---

## Match Formats (Reference)

| Phase                    | Games     | Points per game | Draw rule       | Win condition                                      |
|--------------------------|-----------|-----------------|-----------------|---------------------------------------------------|
| Group stage (normal)     | 1         | to 6            | 5:5 is a draw   | Single game                                       |
| Group stage (short)      | 1         | to 5            | 4:4 is a draw   | Single game                                       |
| Elimination (standard)   | Best of 3 | to 6            | N/A             | First to 2 wins; deciding game needs margin ≥ 2   |
| Elimination (finals/3rd) | Best of 5 | to 6            | N/A             | First to 3 wins; deciding game needs margin ≥ 2   |

---

## Technical Architecture (Summary)

| Level         | Configuration                                             |
|---------------|-----------------------------------------------------------|
| **Tournament** | `player_mode` (singles / doubles)                        |
| **Stage**      | `stage_type` (group / elimination / round_robin)         |
| **Stage**      | `pairing` (swiss / round_robin / random)                 |
| **Stage**      | `team_formation` (random / fixed / from_results)         |
| **Stage**      | `random_rounds` (default 2, then standings-based)        |

---

## Story 4b: All Players Visible in Standings

As a **player** or **organizer**, I want to see every registered player in the
standings table — even those who haven't played a match yet — so I know who
is in the tournament and can see the full leaderboard at a glance.

### Scenarios

- **Tournament just started:** Round 1 is drawn but not played yet.
  Standings show all 16 players with 0 points, 0 matches played.
- **Player joined late (late-join):** A player is added mid-tournament.
  They immediately appear in standings with 0 points.
- **Paused player:** A paused player does NOT appear in standings
  (they opted out temporarily).

---

## Story 5: QR Code Rotation (Anti-Remote-Registration)

As an **organizer**, I want the QR code on the Live View screen to change
periodically so that players who photograph it and share it remotely
cannot register from outside the venue.

### Scenarios

- **Happy path:** Player walks up, scans QR, opens registration form,
  signs up.  Works every time regardless of rotation.
- **QR rotates while scanning:** Player scanned a QR that's about to
  rotate.  The form still opens — a short grace period (seconds) ensures
  no one is blocked for being slow.
- **Photo shared via chat:** Someone photographs the QR and sends it to
  a friend 10 minutes later.  The friend's phone opens the URL but the
  nonce is too old — registration is refused.
- **5 players scan simultaneously:** Each successful scan triggers a
  visual confirmation on the Live View ("Pepa se připojuje…") and the
  QR animates to a new code.  All 5 register successfully.
- **No internet at venue:** QR rotation happens client-side, no server
  round-trip needed for generating new codes.

---

## Story 6: Offline-Resilient Tournament

As an **organizer**, I want to be able to finish a running tournament
even if the internet connection drops — managing everything from my
laptop, displaying results on the projector, and syncing back to the
server when connectivity returns.

### Scenarios

- **Internet drops mid-round:** Organizer continues entering scores,
  drawing rounds, and viewing standings — all from the laptop.
  A small badge indicates "offline" mode.
- **Projector/TV display:** Live View on the projector keeps working
  because it reads from local data on the organizer's laptop (HDMI/Cast).
- **Players' phones lose access:** Acceptable — the organizer announces
  pairings and results verbally, as in a traditional tournament.
- **Internet returns:** Pending changes sync automatically to the server.
  A toast confirms "Synced N changes".
- **Organizer closes laptop before reconnecting:** Data persists locally.
  Next time the app is opened with connectivity, a manual "Sync" action
  is available.
- **Player registered via QR while organizer was offline:** On reconnect,
  the new registration appears and the organizer can incorporate them.

---

## Glossary

- **DYP (Draw Your Partner)** — partners are assigned randomly each round.
  Implemented as `team_formation = random` on a doubles tournament stage.
- **Fixed pairs** — teams are set at tournament start and never change.
  Implemented as `team_formation = fixed`.
- **Swiss system** — a pairing method that matches participants with similar
  records while avoiding repeat matchups.
- **Bye** — when odd number of participants, the one who has played the most
  sits out.  Configurable: can optionally receive an automatic win.
- **Score erosion** — a mechanism that gradually reduces older results' weight
  in standings, keeping the leaderboard dynamic over long periods.
- **Registration token** — a secret in the QR code that proves physical
  presence at the venue.  Prevents remote self-registration.
