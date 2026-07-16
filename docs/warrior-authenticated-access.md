# Warrior Trading — Authenticated Access Runbook

Repeatable local browser access for agents and humans mapping Warrior member
content. **Credentials, cookies, and auth state never live in this repository.**

## Quick start

From the Nova repo root:

```powershell
.\scripts\open_warrior_site.ps1
```

Optional landing URL:

```powershell
.\scripts\open_warrior_site.ps1 -Url "https://lms.warriortrading.ai/learner-dashboard/"
.\scripts\open_warrior_site.ps1 -Url "https://www.warriortrading.com/chat-room-access/"
```

## What this uses

| Item | Location |
|------|----------|
| Persistent Chrome profile | `%LOCALAPPDATA%\Nova\browser-profiles\warrior-site` |
| Portable auth export (optional) | `%LOCALAPPDATA%\Nova\browser-profiles\warrior-site-auth.json` |
| Scratch screenshots / dumps | `.tmp/warrior-site-map/` (gitignored) |
| agent-browser session name | `warrior-site` |

The launcher opens a **headed** Chromium window so CAPTCHA / 2FA / consent UI
are visible when needed.

## First login (human once)

1. Run `.\scripts\open_warrior_site.ps1`.
2. If redirected to Access Denied / Sign in, enter member email + password in
   the visible window.
3. Accept cookies if prompted.
4. Complete CAPTCHA / 2FA / legal acceptance if Warrior shows them.
5. Confirm `https://www.warriortrading.com/dashboard/` loads as
   **Member's Dashboard**.
6. Optionally save state (agent does this after a successful login):

```powershell
npx --yes agent-browser@latest --session warrior-site state save "$env:LOCALAPPDATA\Nova\browser-profiles\warrior-site-auth.json"
```

Later runs reuse the profile — no password in chat or scripts.

## Day Trade Dash entry path

1. Members Dashboard → **Click Here to Enter**  
   (`/chat-room-access/…`)
2. **Click here to Enter the Platform** → SSO into  
   `https://chatroom.warriortrading.com/dashboard?…`
3. Accept the in-app **Disclaimer** modal (`ACCEPT`).
4. Layout widgets load (HOD Momo, Running Up, Gappers, Gainers, Chart, Quote).

Do not commit SSO query tokens, JWT payloads, or cookie dumps.

## Agent automation notes (PowerShell)

- Quote element refs: `click '@e12'` — bare `@e12` is eaten by PowerShell.
- Prefer `--session warrior-site --headed --profile <profileDir>`.
- Screenshots: use forward-slash paths, e.g.  
  `screenshot --full "./.tmp/warrior-site-map/page.png"`.
- Stop and ask the user for: CAPTCHA, 2FA, payment/billing changes,
  enrollment/purchase, posting chat, or any trading action.

## Safe boundaries

| Allowed | Not allowed |
|---------|-------------|
| Read-only navigation of member pages | Scraping/redistributing paid course video/text bodies |
| Index course titles / chapter lists | Committing passwords, cookies, SSO JWTs |
| Map Day Trade Dash widgets / columns | Placing trades or posting in chat |
| Screenshot to `.tmp/` for mapping | Storing secrets under the git tree |

## Durable map

Site hierarchy and widget inventory (for future questions):

- Obsidian: `knowledge/obsidian/01-Courses/Warrior-Trading/Authenticated-Site-Map.md`
- Canvas: `warrior-site-map.canvas.tsx` (Cursor canvases folder)

## Recovery

| Symptom | Fix |
|---------|-----|
| Access Denied after profile wipe | Re-login once in the headed window |
| Chatroom disclaimer every visit | Accept once; profile should remember |
| SSO link expired | Re-enter from `/chat-room-access/` (do not reuse old SSO URLs) |
| Stale session | Clear only the local profile dir above, then first-login again |
