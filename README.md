# Hormuz Watch

A small dashboard comparing daily Strait of Hormuz vessel transits against Brent
crude oil price. It refreshes itself once a day with no server, no database and
no API key — a scheduled GitHub Action re-pulls both public data sources,
rebuilds `index.html`, and commits it back to the repo.

**Live page:** enable GitHub Pages (see below) and it'll be at
`https://<your-username>.github.io/<repo-name>/`

## How the auto-refresh works

- `scripts/refresh_data.py` pulls:
  - **Vessel transits** from [IMF PortWatch](https://portwatch.imf.org/pages/chokepoint6) (chokepoint6 = Strait of Hormuz), a free ArcGIS-hosted dataset, no key needed.
  - **Brent crude price** from [FRED series DCOILBRENTEU](https://fred.stlouisfed.org/series/DCOILBRENTEU) (sourced from the US EIA), a free CSV endpoint, no key needed.
- It merges the two by date, keeps the most recent 120 days, and writes `data/combined.json` + a rebuilt `index.html`.
- `.github/workflows/refresh.yml` runs that script every day at 06:00 UTC and pushes the result if anything changed. You can also trigger it on demand from the repo's **Actions** tab → "Refresh Hormuz Watch" → **Run workflow**.

No secrets or API keys are required — the workflow's built-in `GITHUB_TOKEN` is enough to commit.

## Setting it up

1. **Create a repo** on GitHub (public or private both work for the Action; Pages needs it either public, or private on a paid plan).
2. **Push these files** to it:
   ```
   git init
   git add .
   git commit -m "Hormuz Watch: initial commit"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git push -u origin main
   ```
3. **Turn on GitHub Pages**: repo → Settings → Pages → Source → "Deploy from a branch" → Branch `main`, folder `/ (root)`. Save.
4. **Turn on Actions** if it isn't already (Settings → Actions → General → allow workflows to run).
5. Wait for the first scheduled run, or trigger it manually (Actions tab → Refresh Hormuz Watch → Run workflow) to confirm it works end to end.

## Putting it on your GitHub profile

If `<repo-name>` matches your GitHub username exactly, its `README.md` renders
directly on your profile page — that's the "special" profile-README repo
GitHub supports. Otherwise, link to this repo or its Pages URL from your
profile README, e.g.:

```markdown
### 🛢️ [Hormuz Watch](https://<your-username>.github.io/<repo-name>/)
Daily Strait of Hormuz vessel transits vs. Brent crude, refreshed automatically.
```

## Files

- `index.html` — the page (rebuilt automatically; safe to regenerate, don't hand-edit the `DATA` array).
- `scripts/template.html` — the actual template with layout/CSS/JS; edit this if you want to change how the page looks.
- `scripts/refresh_data.py` — the fetch/merge/build script.
- `data/combined.json` — the current dataset (also rebuilt automatically).
- `.github/workflows/refresh.yml` — the daily schedule.

## Notes on the data

- Transit counts are AIS-based estimates from PortWatch across all cargo types (tanker, dry bulk, container, general cargo, ro-ro); "tankers" is the tanker-type subset. PortWatch itself warns that AIS spoofing and vessels "going dark" during the current conflict make these a floor, not a ceiling.
- Every price point is a real reported FRED quote — weekends/holidays with no quote are simply skipped rather than estimated.
- The five timeline entries in the page (strikes, price peaks, etc.) are hand-curated from news reporting at build time and will silently drop off the timeline once they roll outside the 120-day window — that's expected, not a bug.
