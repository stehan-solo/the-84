# the-84

Personal 12-week accountability tracker — daily habits, training, and body metrics.

A standalone PWA: installs to the iOS home screen and works fully offline.
No build step, no dependencies, no network calls at runtime.

## Deploying to Netlify

Drag this folder onto Netlify, or connect the repo — `netlify.toml` sets
`publish = "."` with no build command. HTTPS comes free, which service workers
require.

To install on iPhone: open the site in **Safari** (Chrome on iOS cannot install
PWAs), then Share → Add to Home Screen. It launches without browser chrome and
runs with no connection.

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
| `the-84-v4.html` | The original embedded fragment this was built from. Archived, not used at runtime. |

## What changed from `the-84-v4.html`

The source was a fragment — it opened with `<style>` and had no `<html>`, `<head>`,
or `<body>` — designed to be embedded in a host page that provided `window.storage`.
Four changes made it standalone. The layout CSS and all app logic are otherwise
byte-for-byte identical:

1. **Wrapped in a real HTML document**, with the manifest link, the iOS
   home-screen meta tags, and the service worker registration.
2. **`window.storage` → `localStorage`**, same key (`the84:state:v1`), same value
   (the state object as a JSON string). The two calls were `await`ed; `localStorage`
   is synchronous, so `load()` is no longer `async` and boots as `load();render()`
   instead of `load().then(render)`.
3. **Google Fonts `@import` → self-hosted `fonts.css`.** An `@import` from
   `fonts.googleapis.com` fails with no network, which would have dropped the app to
   system fonts offline — the one thing that would have visibly broken the design.
4. **A small standalone stylesheet** in a second `<style>` block: page background,
   and safe-area insets so content clears the notch and home indicator. The app's own
   stylesheet is untouched.

There is one behavioural addition. Saves are debounced by 400ms, and iOS can suspend
a home-screen app before that timer fires, silently dropping the last change. The
pending write is now flushed on `visibilitychange` and `pagehide`. Same key, same
data — it only guarantees the write lands. If you would rather not have it, delete
`flush()` and its two listeners in `index.html`.

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
