# User Stories

## Roles

- **Organizer** — owns a league or tournament, manages registration, draws, and results.
- **Player** — a participant who joins leagues and tournaments but does not organize them.
- **Admin** — system-wide superuser (manages users, can intervene in any league/tournament).

---

## Story 1: Weekly Pub Tournament

A pub hosts a weekly foosball tournament. The format rotates between **DYP**
(Draw Your Partner), **Monster DYP**, and **fixed pairs**.

### Registration

- The organizer creates a tournament for the evening and sets the format and entry fee.
- A QR code is displayed at the venue.
- A registered player scans the QR code on their phone, confirms their name, and
  joins the tournament.
- The organizer sees the player appear in the participant list, collects the entry
  fee, and marks the player as paid.
- An unregistered walk-in can be added manually by the organizer.

### Phase 1 — Group Stage (Swiss / Round-Robin)

- The system generates random matchups for each round.
- It avoids repeating the same opponent pairing when possible.
- Typically 5–7 rounds are played, depending on time.
- Each match is **one game to 6 points**; a 5:5 score counts as a draw.
  (Sometimes games are played to 5 when time is short.)
- After each game, either player or the organizer enters the score.
- The system updates standings automatically (wins, draws, points, goal
  difference).

### Phase 2 — Elimination (Knockout)

- Top players from the group stage advance to a single-elimination bracket.
- Matches are **best of 3** (first to 2 wins), each game to 6 points.
  The deciding game requires a margin of 2 or more.
- **Semi-final losers play a 3rd-place match** before the final.
- Finals and the 3rd-place match may optionally be **best of 5** (first to 3 wins).
- The system generates the bracket and advances winners automatically.

### Notifications

- When a new round is drawn, each player receives a push/web notification:
  which table to go to and who their opponent is.
- The organizer can send a broadcast message to all participants (e.g., "Final
  round starting in 5 minutes").

### Live Standings

- Players can view **live standings on their phone** at any time during the
  tournament — current round results, group table, elimination bracket.
- A public standings screen (TV/projector) can optionally be displayed at the
  venue using the same live data.

### Results & History

- Final standings (1st, 2nd, 3rd, …) are published at the end of the evening.
- Players can view their tournament history, win/loss record, and statistics.

---

## Story 2: Ongoing Office League

A group of colleagues want a long-running, casual foosball league at work.

### Setup

- An organizer creates a league and invites colleagues (or sets it to open
  registration).
- Players join the league; there is no fixed schedule.

### League Scoring Rules

Each league defines its own **scoring rules**. Two typical examples:

- **Pub tournament league** — players earn points based on tournament placement
  (e.g., 1st = 10 pts, 2nd = 7, 3rd = 5, 4th = 4, …, participation = 1 pt).
  The league leaderboard is the sum of points across all tournaments in the
  season.
- **Office league** — individual game results are tracked using an Elo-style
  rating or simple win/loss points. No tournaments required.

The organizer configures the scoring model when creating the league.

### Casual Play (Office-style League)

- Two (or four) players meet at the foosball table whenever they like.
- They record the result in the app.
- The system maintains a **running leaderboard** according to the league's
  scoring rules.
- Over time, inactive scores may decay (configurable score erosion) so the
  standings stay fresh.

### Occasional League Tournament

- The organizer decides to hold a tournament within the league.
- League members must explicitly sign up for the tournament.
- The tournament follows the same structure as Story 1 (group stage +
  elimination), but is linked to the league.
- Tournament results feed into league standings according to the league's
  scoring rules (e.g., placement points for pub leagues, individual game
  results for office leagues).

### Live League Standings

- Players can check the current league leaderboard on their phone at any time.

### Resetting / Seasons

- The organizer can start a new season: archive current standings and begin
  fresh, or simply let the erosion mechanism keep things dynamic.

---

## Story 3: Player Experience

As a player I want a smooth mobile experience so I can focus on playing, not
on paperwork.

- I open the app, scan a QR code, and I am in the tournament.
- I see my upcoming match: opponent name, table number.
- After the game I tap the score and submit — done.
- I get notified when the next round is ready.
- I can check standings and my personal stats at any time.
- Between tournaments I can browse my history: tournaments played, win rate,
  rating progression.

---

## Story 4: Organizer Experience

As an organizer I want to run a tournament evening with minimal friction.

- I create tonight's tournament in 30 seconds: pick format, set entry fee, go.
- Players self-register via QR code; I just confirm and collect the fee.
- I tap "Draw next round" and the system assigns fair matchups.
- Scores flow in from players' phones; I only intervene on disputes.
- When the group stage is done I tap "Generate bracket" and the elimination
  phase is ready.
- At the end I publish results with one tap.

---

## Match Formats (Reference)

| Phase | Games | Points per game | Draw rule | Win condition |
|-------|-------|-----------------|-----------|---------------|
| Group stage (normal) | 1 | to 6 | 5:5 is a draw | Single game |
| Group stage (short) | 1 | to 5 | 4:4 is a draw | Single game |
| Elimination (standard) | Best of 3 | to 6 | N/A | First to 2 wins; deciding game needs margin ≥ 2 |
| Elimination (finals/3rd) | Best of 5 | to 6 | N/A | First to 3 wins; deciding game needs margin ≥ 2 |

---

## Glossary

- **DYP (Draw Your Partner)** — partners are assigned randomly each round.
- **Monster DYP** — a DYP variant where partnerships rotate more aggressively.
- **Fixed pairs** — teams are set for the entire tournament.
- **Swiss system** — a pairing method that matches players with similar records
  while avoiding repeat matchups.
- **Score erosion** — a mechanism that gradually reduces older results' weight
  in standings, keeping the leaderboard dynamic over long periods.
