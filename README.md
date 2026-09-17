# Hormuz Watch

I built this to answer a question I kept seeing argued about without any chart to back it up: does oil traffic through the Strait of Hormuz actually move with the price of oil, day by day, during the current crisis? So I put the two series next to each other and let them speak for themselves.

It's a small dashboard that compares daily vessel transits through the Strait of Hormuz against the price of Brent crude. The part I'm most pleased with is that it needs nothing from me once it's running. No server, no database, no API key I have to guard. A scheduled GitHub Action wakes up once a day, pulls both data sources fresh, rebuilds the page, and commits the result back to this repo. I just check in on it occasionally.

**Live page:** once you turn on GitHub Pages (steps below), it'll sit at [Hormuz Watch](https://eshaaalali.github.io/hormuz-watch/)

## How it actually works

Every day, `scripts/refresh_data.py` goes out and gets two things:

* Vessel transit counts from [IMF PortWatch](https://portwatch.imf.org/pages/chokepoint6), which tracks the Strait of Hormuz (their chokepoint6) using AIS ship transponder data. It's free and needs no key.
* Brent crude prices from [FRED series DCOILBRENTEU](https://fred.stlouisfed.org/series/DCOILBRENTEU), which is the US EIA's own data, made available through the Federal Reserve. Also free, also no key.

The script lines the two up by date, keeps the most recent 120 days, and writes out `data/combined.json` along with a freshly rebuilt `index.html`. Then `.github/workflows/refresh.yml`, the GitHub Action, runs that script every day at 06:00 UTC and pushes whatever changed. If you ever want to see it happen on demand rather than waiting for the schedule, you can trigger it yourself from the repo's Actions tab under "Refresh Hormuz Watch," then "Run workflow."

Nothing here needs a secret or an API key. The workflow's own built in `GITHUB_TOKEN` is enough for it to commit on my behalf.

## Setting it up yourself

If you want to run your own copy, here's what I did:

1. Create a new repo on GitHub. Public or private both work for the Action itself; Pages needs the repo to be public, unless you're on a paid GitHub plan.
2. Push the project files into it:
   ```
   git init
   git add .
   git commit -m "Hormuz Watch: initial commit"
   git branch -M main
   git remote add origin https://github.com/<your username>/<repo name>.git
   git push -u origin main
   ```

3. Turn on GitHub Pages: go to the repo's Settings, then Pages, set Source to "Deploy from a branch," pick branch `main` and folder `/ (root)`, and save.
4. Make sure Actions are allowed to run for the repo (Settings, then Actions, then General).
5. Either wait for the first scheduled run, or trigger it yourself from the Actions tab to confirm everything works end to end.

## Putting it on your GitHub profile

If you name the repo exactly the same as your GitHub username, its README renders straight onto your profile page automatically, which is a neat trick GitHub supports. Otherwise, I'd just link to the repo or its Pages URL from wherever your profile README already lives, something like:

```markdown
### 🛢️ [Hormuz Watch](https://<your username>.github.io/<repo name>/)
Daily Strait of Hormuz vessel transits versus Brent crude, refreshed automatically.
```

## What's in here

* `index.html`, the page itself. It gets rebuilt automatically, so it's safe to regenerate; I'd avoid hand editing the `DATA` array inside it.
* `scripts/template.html`, the actual template with the layout, styling, and behavior. This is the file to edit if you want the page to look or work differently.
* `scripts/refresh_data.py`, the script that fetches, merges, and rebuilds everything.
* `data/combined.json`, the current dataset, also rebuilt automatically.
* `.github/workflows/refresh.yml`, the daily schedule that ties it all together.

## Being honest about the data

A few things I think are worth knowing before you trust any single number on this page:

Transit counts are AIS based estimates from PortWatch, covering every kind of cargo vessel (tanker, dry bulk, container, general cargo, and ro-ro). "Tankers" refers specifically to the tanker subset of that count. PortWatch itself is upfront that AIS spoofing and vessels going dark during the current conflict mean these numbers are a floor, not a ceiling, on real traffic.

Every price point on this page is a real, reported FRED quote. I didn't estimate or interpolate anything. Weekends and holidays simply don't have a quote, so those dates are skipped rather than guessed at.

The five timeline entries on the page (the strikes, the price peaks, and so on) are events I hand curated from news reporting when I built this. As the rolling 120 day window moves forward, they'll quietly drop off once they age out of range. That's expected behavior, not a bug.
