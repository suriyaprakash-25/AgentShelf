# AgentShelf engineering context

Read `docs/ROADMAP_SOURCE.md` and `docs/IMPLEMENTATION_PLAN.md` before each phase.
The supplied source PDF is `docs/BUILD_GUIDE.pdf`; preserve it unchanged.
Follow the roadmap sprint order and review gates. Acceptance requires evidence;
never mark an integration working from a mock, configuration, or compilation alone.
Record progress and gaps in `docs/STATUS.md` without modifying the source document.
The user expanded scope to worldwide merchant access and a pre-submission live pilot.
Live eligibility and permissions are merchant-specific; never imply universal support.
Sandbox stays isolated and is the judge's payment environment. Live checkout is gated.
Use branches and reviewable commits, keep business rules outside route handlers,
store money as integer minor units, and redact secrets and personal data from logs.
Run meaningful tests with real Postgres for locking, constraints and migrations.
Do not publish credentials, contact people, purchase services, or submit the entry.
