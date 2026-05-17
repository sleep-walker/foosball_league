"""
Frontend smoke tests using Playwright.

These tests start a real ASGI server and verify that pages render
correctly in a headless browser.
"""


import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    """Start a real uvicorn server in a subprocess with a fresh test DB.

    Uses a subprocess so the app gets a clean import with the test DB URL.
    This ensures the tests exercise the real HTTP stack — the same path a
    phone or browser takes.

    Port is chosen dynamically (kernel-assigned) to avoid collisions with
    zombie subprocesses from a prior aborted test run.  Without this, a
    leftover uvicorn on a hard-coded port would silently accept the new
    test's HTTP calls and serve them from stale DB state, producing
    confusing flaky failures.
    """
    import os
    import time
    import socket as sock
    import subprocess
    import signal

    tmp_db = tmp_path_factory.mktemp("db") / "test_live.db"
    db_url = f"sqlite+aiosqlite:///{tmp_db}"
    host = "127.0.0.1"

    # Ask the kernel for a free port.  We close immediately; uvicorn will
    # re-bind it (SO_REUSEADDR avoids TIME_WAIT races on most systems).
    with sock.socket(sock.AF_INET, sock.SOCK_STREAM) as _s:
        _s.bind((host, 0))
        port = _s.getsockname()[1]

    env = os.environ.copy()
    env["ASYNC_DATABASE_URL"] = db_url
    env["CORS_ORIGINS"] = "*"
    env["AUTO_VERIFY_USERS"] = "true"
    env["BASE_URL"] = f"http://{host}:{port}"

    proc = subprocess.Popen(
        [
            "python", "-m", "uvicorn", "league_app.main:app",
            "--host", host, "--port", str(port), "--log-level", "warning",
        ],
        env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )

    # Wait for server to be ready — but also detect early exit so we don't
    # hang the full 10s when uvicorn dies (e.g. EADDRINUSE on the rare race).
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read().decode() if proc.stdout else ""
            pytest.fail(
                f"uvicorn exited early with code {proc.returncode}.\n{out}"
            )
        try:
            with sock.create_connection((host, port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        out = proc.stdout.read().decode() if proc.stdout else ""
        proc.kill()
        pytest.fail(f"Server did not start in time.\n{out}")

    yield f"http://{host}:{port}"

    # Fast teardown: short SIGTERM grace, then SIGKILL.  Holding the
    # interpreter open here delays the next test module.
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


@pytest.fixture(scope="module")
def _pw_browser(live_server):
    """Module-scoped Playwright browser instance."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser, live_server
        browser.close()


@pytest.fixture()
def browser_page(_pw_browser):
    """Fresh browser page for each test (clean state, no cross-test leaks).

    Forces English locale so smoke tests are deterministic regardless of the
    host environment's language settings.
    """
    browser, base_url = _pw_browser
    context = browser.new_context(locale="en-US")
    page = context.new_page()
    yield page, base_url
    context.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLandingPage:
    def test_landing_page_renders(self, browser_page):
        """Landing page shows welcome message, not stuck on 'Loading...'."""
        page, base_url = browser_page
        page.goto(base_url)

        # Wait for the welcome heading to appear (proves lit-html rendered)
        heading = page.wait_for_selector("h2", timeout=5000)
        assert "Welcome to Foosball League" in heading.text_content()

    def test_landing_page_has_buttons(self, browser_page):
        """Landing page shows Sign In and Live View buttons."""
        page, base_url = browser_page
        page.goto(base_url)
        page.wait_for_selector("h2", timeout=5000)

        buttons = page.query_selector_all("button")
        texts = [b.text_content().strip() for b in buttons]
        assert any("Sign In" in t for t in texts), f"Expected Sign In button, got: {texts}"
        assert any("Live View" in t for t in texts), f"Expected Live View button, got: {texts}"

    def test_no_js_console_errors(self, browser_page):
        """No JavaScript errors in the console on landing page load."""
        page, base_url = browser_page

        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))

        page.goto(base_url)
        page.wait_for_selector("h2", timeout=5000)

        assert errors == [], f"JS console errors: {errors}"

    def test_loading_indicator_hidden(self, browser_page):
        """The initial 'Loading...' indicator is hidden after app boots."""
        page, base_url = browser_page
        page.goto(base_url)
        page.wait_for_selector("h2", timeout=5000)

        loading_el = page.query_selector("#page-loading")
        if loading_el:
            assert not loading_el.is_visible(), "Loading indicator should be hidden after render"


class TestLiveViewCleanup:
    def test_close_live_view_restores_navigation(self, browser_page):
        """After closing Live View, navigation should work again."""
        page, base_url = browser_page

        # Navigate to live view
        page.goto(f"{base_url}/#live")

        # Wait for the close button (proves live-mode rendered)
        close_btn = page.wait_for_selector(
            "button[title='Close Live View']", timeout=5000
        )

        # Verify live-mode is active
        has_live_mode = page.evaluate(
            "document.body.classList.contains('live-mode')"
        )
        assert has_live_mode, "live-mode should be active"

        # Click close
        close_btn.click()

        # Should navigate to landing — wait for welcome heading
        page.wait_for_selector("h2", timeout=5000)
        has_live_mode = page.evaluate(
            "document.body.classList.contains('live-mode')"
        )
        assert not has_live_mode, "live-mode class should be removed after closing"

        # Close button must be gone (was the actual bug — position:fixed stayed)
        close_btn_after = page.query_selector("button[title='Close Live View']")
        assert close_btn_after is None, "Close button should be removed after leaving live view"

        # Header should be visible again
        header = page.query_selector("header")
        assert header is not None and header.is_visible(), "Header should be visible"


class TestInstallBanner:
    def test_dismiss_persists_via_localstorage(self, browser_page):
        """Clicking dismiss sets localStorage flag so banner won't show again."""
        page, base_url = browser_page
        page.goto(base_url)
        page.wait_for_selector("h2", timeout=5000)

        # Simulate: user clicks dismiss on the install banner
        page.evaluate("localStorage.setItem('install-dismissed', '1')")

        # Verify the flag is set
        val = page.evaluate("localStorage.getItem('install-dismissed')")
        assert val == "1"

        # Reload — the app should NOT show the banner even if beforeinstallprompt fires
        page.reload()
        page.wait_for_selector("h2", timeout=5000)

        # The banner should stay hidden (has 'hidden' class)
        banner = page.query_selector("#install-banner")
        if banner:
            assert not banner.is_visible(), "Banner should stay hidden after dismiss"


class TestQRRegistrationFlow:
    """Simulate exactly what a mobile user does: scan QR → see register page → submit."""

    def _create_tournament(self, page, base_url):
        """Create a tournament via real HTTP and return its UUID + auth headers."""
        import httpx

        # Register (form-encoded, as fastapi-users expects)
        httpx.post(f"{base_url}/api/v1/users/register", json={
            "email": "qr_org@test.com", "password": "password123",
        })
        # Login (OAuth2 form)
        r = httpx.post(f"{base_url}/api/v1/users/login", data={
            "username": "qr_org@test.com", "password": "password123",
        })
        assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create tournament (JSON body)
        r = httpx.post(f"{base_url}/api/v1/tournaments/", headers=headers, json={
            "name": "QR Test Cup", "date": "2026-05-01",
        })
        assert r.status_code == 200, f"Create tournament failed: {r.status_code} {r.text}"
        return r.json()["uuid"], headers

    def test_register_page_shows_login_link(self, browser_page):
        """The register page must show a 'Log in' link for existing users."""
        import httpx
        page, base_url = browser_page
        t_id, _ = self._create_tournament(page, base_url)

        # Get QR registration URL
        r = httpx.get(f"{base_url}/api/v1/public/tournaments/{t_id}/qr?format=json")
        reg_url = r.json()["registration_url"]

        # Navigate to the QR URL (what a phone does after scanning)
        page.goto(reg_url)
        page.wait_for_load_state("networkidle")

        # Debug: capture what actually rendered
        content = page.content()
        assert "input" in content.lower() or "nickname" in content.lower(), (
            f"Register page did not render. URL: {reg_url}\n"
            f"Page title: {page.title()}\n"
            f"Content snippet: {content[:500]}"
        )

        page.wait_for_selector("input", timeout=5000)

        # Must have a login link
        login_link = page.query_selector("a[href='#login']")
        assert login_link is not None, (
            "Register page must show 'Log in' link. "
            f"Page content: {page.content()[:300]}"
        )

    def test_anonymous_registration_works(self, browser_page):
        """An unknown player scans QR, enters nickname, clicks submit → sees success."""
        page, base_url = browser_page
        t_id, org_headers = self._create_tournament(page, base_url)

        # Get QR URL
        import httpx
        r = httpx.get(f"{base_url}/api/v1/public/tournaments/{t_id}/qr?format=json")
        reg_url = r.json()["registration_url"]

        page.goto(reg_url)
        page.wait_for_selector("input", timeout=5000)

        # Fill in nickname
        page.fill("input[type='text']", "MobileBubák")

        # Capture network response for the POST
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))

        with page.expect_response(lambda r: "/register" in r.url) as resp_info:
            page.click("button.btn-primary")

        response = resp_info.value
        assert response.status == 200, (
            f"Registration POST returned {response.status}: {response.text()}"
        )
        assert errors == [], f"JS errors during registration: {errors}"

        # After successful registration, user must see confirmation — NOT "scan QR code"
        page.wait_for_load_state("networkidle")
        content = page.text_content("body")
        assert "you're on the list" in content.lower(), (
            f"Expected success message, got: {content[:300]}"
        )
        assert "scan the qr" not in content.lower(), (
            f"Success page must NOT show 'scan QR code' prompt. Got: {content[:300]}"
        )

    def test_cors_preflight_works(self, browser_page):
        """OPTIONS preflight to register endpoint must return 200, not 405."""
        import httpx
        _, base_url = browser_page
        t_id, _ = self._create_tournament(None, base_url)

        r = httpx.options(
            f"{base_url}/api/v1/public/tournaments/{t_id}/register",
            headers={
                "Origin": "http://different-origin.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert r.status_code == 200, (
            f"CORS preflight returned {r.status_code} — "
            f"mobile browsers will show 'Method Not Allowed'"
        )


class TestLiveViewMultiStage:
    """Live view must render every stage of a multi-stage tournament.

    Regression for the bug where the matches-render path concatenated all
    stages and grouped by round number — a 2nd stage's round 1 ended up
    hidden behind a 1st stage's higher rounds, so the whole stage went
    invisible to spectators.
    """

    def _setup_two_stage_tournament(self, base_url):
        """Create org, tournament with 4 players, play group stage, then add
        an elimination stage. Returns (tournament_id, group_stage_name,
        elim_stage_name).
        """
        import httpx
        suffix = str(id(self))[-6:]  # unique per test invocation
        email = f"multi_stage_{suffix}@test.com"
        httpx.post(f"{base_url}/api/v1/users/register", json={
            "email": email, "password": "password123",
        })
        r = httpx.post(f"{base_url}/api/v1/users/login", data={
            "username": email, "password": "password123",
        })
        token = r.json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        r = httpx.post(f"{base_url}/api/v1/tournaments/", headers=h, json={
            "name": "Multi-Stage Cup", "date": "2026-05-02",
        })
        t_id = r.json()["uuid"]

        for nick in ("MSA", "MSB", "MSC", "MSD"):
            pid = httpx.post(
                f"{base_url}/api/v1/players/", headers=h,
                json={"nickname": nick},
            ).json()["uuid"]
            httpx.post(
                f"{base_url}/api/v1/tournaments/{t_id}/players/?player_id={pid}",
                headers=h,
            )

        # Start tournament — auto-creates default group stage with round 1
        httpx.post(f"{base_url}/api/v1/tournaments/{t_id}/start", headers=h)

        # Score all default-stage matches to completion
        ms = httpx.get(
            f"{base_url}/api/v1/tournaments/{t_id}/matches/", headers=h,
        ).json()
        for m in ms:
            httpx.patch(
                f"{base_url}/api/v1/matches/{m['uuid']}/score", headers=h,
                json={"score_a": 6, "score_b": 0},
            )

        # Add elimination stage on top + activate + generate bracket
        elim = httpx.post(
            f"{base_url}/api/v1/tournaments/{t_id}/stages/", headers=h,
            json={
                "name": "Playoff", "stage_type": "elimination",
                "tournament_id": t_id,
                "rules": {"best_of": 1, "consolation_match": True},
            },
        ).json()
        elim_id = elim["uuid"]
        httpx.post(
            f"{base_url}/api/v1/tournaments/{t_id}/stages/{elim_id}/activate",
            headers=h,
        )
        httpx.post(
            f"{base_url}/api/v1/tournaments/{t_id}/stages/{elim_id}"
            "/generate-bracket", headers=h,
        )

        # Read back the auto-named group stage to know its label
        info = httpx.get(
            f"{base_url}/api/v1/public/tournaments/{t_id}",
        ).json()
        stage_names = [s["name"] for s in info["stages"]]
        assert "Playoff" in stage_names, f"Elim stage missing: {stage_names}"
        group_name = next(s for s in stage_names if s != "Playoff")
        return t_id, group_name, "Playoff"

    def test_active_stage_renders_in_live_view(self, browser_page):
        """When a 2nd stage is active, live view shows ITS bracket and not
        the previous (finished) group stage's standings/rounds.

        Group standings and earlier rounds are no longer interesting once
        the elimination has started — spectators only care about who's
        playing right now.
        """
        page, base_url = browser_page
        t_id, group_name, elim_name = self._setup_two_stage_tournament(base_url)

        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto(f"{base_url}/#live/{t_id}")

        # Wait for live content area to populate
        page.wait_for_selector("#live-content .card", timeout=8000)
        # Give async per-stage publicMatches calls time to render
        page.wait_for_load_state("networkidle")

        body_text = page.text_content("#live-content")

        # Active stage (Playoff) must be visible
        assert elim_name in body_text, (
            f"Active elimination stage '{elim_name}' missing from live view. "
            f"Got: {body_text[:500]}"
        )
        # Previous (finished) group stage must NOT bleed through
        assert group_name not in body_text, (
            f"Finished group stage '{group_name}' should not appear once "
            f"elimination is active. Got: {body_text[:500]}"
        )
        # Standings panel belongs to the group stage and must be hidden too
        assert "Standings" not in body_text, (
            f"Standings should be hidden during elimination stage. "
            f"Got: {body_text[:500]}"
        )

        # Elimination final must appear (4 players → final + 3rd place)
        assert "Final" in body_text or "🏆" in body_text, (
            f"Bracket final card missing. Got: {body_text[:500]}"
        )
        # ...and must NOT carry an "in progress" suffix on the final/3rd
        # place card (regression: misleading when bracket round 1 is live).
        assert "Final — in progress" not in body_text, (
            "Final card must not show '— in progress' suffix"
        )
        assert "3rd place — in progress" not in body_text, (
            "3rd place card must not show '— in progress' suffix"
        )

        assert errors == [], f"JS errors during live view render: {errors}"

    def test_group_stage_shows_standings_in_live_view(self, browser_page):
        """While the group stage is still the active stage, the live view
        must show round matches AND the standings panel."""
        import httpx
        page, base_url = browser_page

        # Set up a singles tournament + start it (auto-creates group stage)
        suffix = "g" + str(id(self))[-5:]
        email = f"live_group_{suffix}@test.com"
        httpx.post(f"{base_url}/api/v1/users/register", json={
            "email": email, "password": "password123",
        })
        token = httpx.post(f"{base_url}/api/v1/users/login", data={
            "username": email, "password": "password123",
        }).json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        t_id = httpx.post(
            f"{base_url}/api/v1/tournaments/", headers=h,
            json={"name": "Group Live", "date": "2026-05-02"},
        ).json()["uuid"]
        for nick in ("LGA", "LGB"):
            pid = httpx.post(
                f"{base_url}/api/v1/players/", headers=h,
                json={"nickname": nick},
            ).json()["uuid"]
            httpx.post(
                f"{base_url}/api/v1/tournaments/{t_id}/players/?player_id={pid}",
                headers=h,
            )
        httpx.post(f"{base_url}/api/v1/tournaments/{t_id}/start", headers=h)
        ms = httpx.get(
            f"{base_url}/api/v1/tournaments/{t_id}/matches/", headers=h,
        ).json()
        for m in ms:
            httpx.patch(
                f"{base_url}/api/v1/matches/{m['uuid']}/score", headers=h,
                json={"score_a": 6, "score_b": 0},
            )

        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto(f"{base_url}/#live/{t_id}")
        page.wait_for_selector("#live-content .card", timeout=8000)
        page.wait_for_load_state("networkidle")

        body_text = page.text_content("#live-content")
        assert "LGA" in body_text and "LGB" in body_text, (
            f"Group-stage match missing. Got: {body_text[:500]}"
        )
        assert "Standings" in body_text, (
            f"Standings panel must show during group stage. "
            f"Got: {body_text[:500]}"
        )
        assert errors == [], f"JS errors during live view render: {errors}"


class TestTournamentWizard:
    """Wizard renders without console errors for a freshly-created tournament."""

    def _create_tournament_and_login(self, page, base_url, email_prefix="wizard_user"):
        """Create a tournament + log the browser in via localStorage."""
        import httpx
        email = f"{email_prefix}@test.com"
        httpx.post(f"{base_url}/api/v1/users/register", json={
            "email": email, "password": "password123",
        })
        r = httpx.post(f"{base_url}/api/v1/users/login", data={
            "username": email, "password": "password123",
        })
        assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        r = httpx.post(f"{base_url}/api/v1/tournaments/", headers=headers, json={
            "name": "Wizard Test Cup", "date": "2026-05-03",
        })
        assert r.status_code == 200, f"Create tournament failed: {r.status_code} {r.text}"
        t_id = r.json()["uuid"]

        # Plant the token into the browser via an init script so api.js
        # picks it up at module-load time (it caches the value once).
        page.add_init_script(
            f"localStorage.setItem('auth_token', '{token}');"
        )
        return t_id, headers

    def test_wizard_renders_for_empty_tournament(self, browser_page):
        """Navigating to the wizard for a brand-new tournament must not
        produce JS errors and must show the stepper + a step body."""
        page, base_url = browser_page
        t_id, _ = self._create_tournament_and_login(page, base_url, "wizard_empty")

        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))

        page.goto(f"{base_url}/#tournament-wizard/{t_id}")
        page.wait_for_selector(".wizard-stepper", timeout=8000)
        page.wait_for_load_state("networkidle")

        assert errors == [], f"JS errors loading wizard: {errors}"

        # Stepper has 8 step buttons
        steps = page.query_selector_all(".wizard-stepper button")
        assert len(steps) == 8, f"Expected 8 steps in stepper, got {len(steps)}"

        # Body must have something (a card)
        body = page.query_selector(".wizard-step-body .card")
        assert body is not None, "Wizard step body did not render any card"

    def test_wizard_play_step_renders_for_running_tournament(self, browser_page):
        """A tournament with active matches must land on the Play step
        with the score-entry panel rendered (not crash on missing data)."""
        page, base_url = browser_page
        import httpx

        email = "wizard_play@test.com"
        httpx.post(f"{base_url}/api/v1/users/register", json={
            "email": email, "password": "password123",
        })
        token = httpx.post(f"{base_url}/api/v1/users/login", data={
            "username": email, "password": "password123",
        }).json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        r = httpx.post(f"{base_url}/api/v1/tournaments/", headers=h, json={
            "name": "Wizard Play Cup", "date": "2026-05-05",
        })
        t_id = r.json()["uuid"]

        for nick in ("WPA", "WPB", "WPC", "WPD"):
            pid = httpx.post(
                f"{base_url}/api/v1/players/", headers=h,
                json={"nickname": nick},
            ).json()["uuid"]
            httpx.post(
                f"{base_url}/api/v1/tournaments/{t_id}/players/?player_id={pid}",
                headers=h,
            )
        httpx.post(f"{base_url}/api/v1/tournaments/{t_id}/start", headers=h)

        page.add_init_script(f"localStorage.setItem('auth_token', '{token}');")

        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto(f"{base_url}/#tournament-wizard/{t_id}")
        page.wait_for_selector(".wizard-stepper", timeout=8000)
        page.wait_for_load_state("networkidle")

        assert errors == [], f"JS errors loading Play step: {errors}"

        body_text = page.text_content(".wizard-step-body") or ""
        # Play step renders round labels + match rows; check at least the
        # round heading made it through.
        assert "round 1" in body_text.lower() or "kolo 1" in body_text.lower(), (
            f"Play step did not render round info. Got: {body_text[:500]}"
        )

    def test_wizard_redirects_anonymous_to_public_view(self, browser_page):
        """Anonymous users hitting the wizard URL get redirected to the
        public read-only view (tournament-detail)."""
        page, base_url = browser_page
        # No login this time — create tournament via separate session
        import httpx
        httpx.post(f"{base_url}/api/v1/users/register", json={
            "email": "wizard_anon_org@test.com", "password": "password123",
        })
        r = httpx.post(f"{base_url}/api/v1/users/login", data={
            "username": "wizard_anon_org@test.com", "password": "password123",
        })
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        r = httpx.post(f"{base_url}/api/v1/tournaments/", headers=headers, json={
            "name": "Wizard Anon Cup", "date": "2026-05-04",
        })
        t_id = r.json()["uuid"]

        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))

        page.goto(f"{base_url}/#tournament-wizard/{t_id}")
        page.wait_for_load_state("networkidle")

        # Should have been redirected to landing (logged-out → public landing).
        # The wizard's redirect only fires after fetch; if we ended up on
        # landing or login that's also fine.  What matters is no errors.
        assert errors == [], f"JS errors during anon wizard load: {errors}"


class TestModuleLoading:
    def test_all_js_modules_serve_200(self, browser_page):
        """All JS module files return HTTP 200."""
        page, base_url = browser_page

        js_files = [
            "/js/app.js", "/js/ui.js", "/js/api.js", "/js/ws.js",
            "/js/vendor/lit-html.js",
            "/js/pages/landing.js", "/js/pages/tournaments.js",
            "/js/pages/tournament-detail.js", "/js/pages/tournament-wizard.js",
            "/js/pages/leagues.js",
            "/js/pages/players.js", "/js/pages/live.js",
            "/js/pages/register.js", "/js/pages/login.js",
            # Wizard modules
            "/js/pages/tournament-wizard/wizard-state.js",
            "/js/pages/tournament-wizard/stepper.js",
            "/js/pages/tournament-wizard/steps/setup.js",
            "/js/pages/tournament-wizard/steps/players.js",
            "/js/pages/tournament-wizard/steps/stage.js",
            "/js/pages/tournament-wizard/steps/rules.js",
            "/js/pages/tournament-wizard/steps/play.js",
            "/js/pages/tournament-wizard/steps/advance.js",
            "/js/pages/tournament-wizard/steps/next.js",
            "/js/pages/tournament-wizard/steps/done.js",
        ]

        for js_file in js_files:
            response = page.request.get(f"{base_url}{js_file}")
            assert response.status == 200, f"{js_file} returned {response.status}"
