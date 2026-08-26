# the-84

Personal 12-week accountability tracker — daily habits, training, and body metrics.

A standalone PWA: installs to the iOS home screen and works fully offline.
No build step, no dependencies, no network calls at runtime.

## Deploying

No build step. Everything is served as-is from the repo root, and every path in the
app is relative, so it works both at a domain root and under a repository subpath.

**GitHub Pages** — Settings → Pages → deploy from the branch, folder `/ (root)`. The
app lands at `https://<user>.github.io/the-84/`. `.nojekyll` keeps Jekyll out of it.

**Netlify** — drag the folder onto Netlify, or connect the repo. `netlify.toml` sets
`publish = "."` with no build command, plus the cache headers.

HTTPS comes free on both, which service workers require.

To install on iPhone: open the site in **Safari** (Chrome on iOS cannot install
PWAs), then Share → Add to Home Screen. It launches without browser chrome and
runs with no connection.

> GitHub Pages does not let you set response headers, so `sw.js` is served with its
> default 10-minute cache and a new deploy can take that long to reach a device.
> Netlify applies the no-cache header in `netlify.toml` and updates on next launch.

The manifest deliberately has **no `id` member**. `id` resolves against the origin, so
a value like `"/"` would claim `https://<user>.github.io/` — an identity shared with
every other GitHub Pages site on that domain. Omitting it defaults the identity to
`start_url`, which is relative and so unique per repository.

## The week

| Day | Session | Time |
| --- | --- | --- |
| Monday | Run — social 5K | 17:00–18:00 |
| Tuesday | Lift — legs priority | 05:45–06:45 |
| Wednesday | Run — 4×4 intervals | 05:45–06:50 |
| Thursday | Lift — legs priority | 05:45–06:45 |
| Friday | Lift — upper body | 05:45–06:45 |
| Saturday | Parkrun — hard | 08:00 |
| Sunday | Mobility + walk | post-church |

Quiet-time, shutdown times and per-day notes are unchanged — they stay attached to the
weekday, not to the session.

Monday's evening block runs **18:00–20:00** rather than 17:00–20:00, since the social
5K takes 17:00–18:00 and Janie covers homework. Every other day is 17:00–20:00. The
check's storage key is unchanged, so Mondays already logged still count.

## Changing one day's session

Tap the training banner. A small editor opens with the session name and time. **Save**
applies it to that day only, **Reset to pattern** clears it, **Cancel** discards.
An overridden day shows a `CHANGED` marker, and both the banner and the training
checklist item read the override.

Overrides live at `S.days[<date>].session` as `{t, w}`. Either field can be left blank
to fall back to the pattern, so changing only the name keeps the usual time. Saving
values identical to the pattern stores nothing rather than a redundant copy. Overrides
ride along in the JSON backup, and they never affect scoring — a day has the same
number of checks either way.

## Files

| File | Purpose |
| --- | --- |
| `index.html` | The whole app — markup, styles, and logic in one file. |
| `manifest.json` | Web app manifest: name, icons, standalone display, theme colors. |
| `sw.js` | Service worker: precaches the app, serves it offline. |
| `fonts.css` + `fonts/` | Self-hosted Inter, Sora, and IBM Plex Mono (latin subsets). |
| `icons/` | App icons: 32, 180 (apple-touch), 192, 512, and a 512 maskable. |
| `netlify.toml` | Deploy config and cache headers. |
| `tools/` | Scripts that regenerate the icons and re-fetch the fonts. |
| `.nojekyll` | Keeps GitHub Pages from running the folder through Jekyll. |
| `the-84-v5.html` | The original embedded fragment this was built from. Archived, not used at runtime. |
| `the-84-v4.html` | The previous version, as committed to `main`. Archived. |

## What changed from `the-84-v5.html`

Beyond the weekly pattern, the Monday evening block and the session override described
above, four edits make the fragment a standalone page. The source opened with
`<style>` and had no `<html>`, `<head>` or `<body>` — it was built to be embedded in a
host page that provided `window.storage`. Layout CSS and colours are untouched:

1. **Wrapped in a real HTML document**, with the manifest link, the iOS
   home-screen meta tags, and the service worker registration.
2. **`window.storage` → `localStorage`**, same key (`the84:state:v1`), same value
   (the state object as a JSON string). The two calls were `await`ed; `localStorage`
   is synchronous, so `load()` is no longer `async` and boots as `load();render()`
   instead of `load().then(render)`. `setItem` returns nothing and throws on failure,
   so the old `if(!r)` branch folds into the `catch`; both `stamp()` paths and the
   footer's SAVED / NOT SAVED readout behave as before.
3. **Google Fonts `@import` → self-hosted `fonts.css`.** An `@import` from
   `fonts.googleapis.com` fails with no network, which would have dropped the app to
   system fonts offline — the one thing that would have visibly broken the design.
4. **A small standalone stylesheet** in a second `<style>` block: page background,
   and safe-area insets so content clears the notch and home indicator. The app's own
   stylesheet is untouched.

There is one behavioural addition. Saves are debounced by 400ms, and iOS can suspend
a home-screen app before that timer fires, silently dropping the last change — a
checkbox ticked on the way out of the app. The pending write is now flushed on
`visibilitychange` and `pagehide`. Same key, same data; it only guarantees the write
lands. The flush writes quietly (no toast on a page that is going away), but still
stamps the footer. If you would rather not have it, delete `flush()` and its two
listeners in `index.html`.

## Backup and restore

Both buttons work unchanged. **Download backup** writes `the84-backup-YYYY-MM-DD.json`
containing the same state object that lives in `localStorage`; **Restore backup**
reads one back. Backups made before this conversion restore fine — the shape did not
change.

Worth doing periodically: iOS can evict `localStorage` for web apps left unused for
an extended period, and the JSON file is the only copy that survives that.

## Offline behaviour

`sw.js` precaches every file on install, then serves them cache-first and refreshes
in the background, so home-screen launches are instant and work with no network. A
new deploy is picked up on the next launch.

**Bump `CACHE_VERSION` in `sw.js` whenever you change `index.html`, the fonts, the
manifest, or an icon** — that string is what invalidates the old cache. Forget it and
users keep the old version.

Clearing the cache only discards the app files. Habit, training, and metric data lives
in `localStorage` and is never touched by the service worker.

## Local development

Service workers need an HTTP origin — opening `index.html` over `file://` will not
register one, and the app will not go offline. Any static server works:

```sh
python3 -m http.server 8000
```

Then open `http://localhost:8000` (`localhost` counts as a secure origin).

## Regenerating assets

```sh
node tools/generate-icons.js icons   # redraw all five PNGs
node tools/fetch-fonts.js            # re-download the woff2 subsets
```

Icon colors are the three constants at the top of `tools/generate-icons.js`, currently
the app's `--bg`, `--amber`, and `--sky`.
