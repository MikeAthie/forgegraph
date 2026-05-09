# Legacy Tutorial Videos

Playwright tutorial clips for the Legacy ultimate test.

The capture suite writes stable `.webm` files here:

- `01-registration.webm`
- `02-company-objective.webm`
- `03-create-first-agent.webm`
- `04-create-first-judge.webm`
- `05-run-first-judge.webm`

Run from `frontend` with:

```powershell
$env:PLAYWRIGHT_RUNTIME_TARGET='docker'
$env:PLAYWRIGHT_REUSE_EXISTING_SERVER='true'
$env:PLAYWRIGHT_DEMO_CAPTURE='true'
$env:PLAYWRIGHT_DEMO_CAPTURE_DIR='logs/legacy-tutorial-playwright-output'
npx playwright test --config=playwright.demo.config.ts __tests__/demo-captures/legacy-tutorial-videos.spec.ts --project=demo-chromium
```

Set `PLAYWRIGHT_LEGACY_TUTORIAL_DIR` to override where the stable tutorial
clips are copied.
