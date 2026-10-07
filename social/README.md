# Social posting agent

You give it topics. It drafts posts for each platform in your voice and opens a PR. **Nothing is posted until you merge the PR.**

```
social/topics.md  ──(daily routine: Claude drafts)──▶  PR with social/queue/*.md
                                                              │  you review, edit, merge
                                                              ▼
              social/posted/*.md  ◀──(GitHub Action publishes)──  main
```

## Day to day

1. **Add a topic.** Edit `social/topics.md` on GitHub (works on the phone app) and add a bullet under `## Inbox` with your notes.
   Or open a Claude Code session on this repo and say "/social-draft <topic>".
2. **Review.** The daily routine opens a PR named *Social drafts: …*. Its description shows every post.
   Edit text on the PR's Files tab, delete a `## platform` section to skip that platform, or delete the file to skip the post.
3. **Merge to approve.** The *Social publish* Action posts everything due within a few minutes.
   Posts with a `schedule:` wait for that time; the Action checks hourly.
   Each post file gets `posted.<platform>: <url>` lines and moves to `social/posted/`.

If a platform fails, the others still post. The failure is recorded as `error.<platform>` in the file and retried on the next hourly run, up to 3 attempts. After that the file moves to `social/failed/`.
A red *Social publish* run is how you find out, so turn on GitHub's failed-workflow notifications.

To fix a post that's already merged but not yet out, edit it in `social/queue/` on main. Add `hold: yes` to pause it.

## Setup

1. Fill in `social/profile.md`: who you are, your voice, a few example posts, and which platforms to use.
2. Add secrets for each platform you keep, under **Settings → Secrets and variables → Actions** on this repo.
3. **Settings → Actions → General → Workflow permissions** must allow *Read and write*, so the Action can record what it posted.
4. Recommended: protect `main` so changes need a PR. This keeps the drafting routine from ever reaching main without you.

Run `python3 social/publish.py --dry-run` locally to see what would post. Run `python3 -m unittest social/test_publish.py` for the tests.

### Secrets by platform

| platform | secrets | where to get them |
|---|---|---|
| Bluesky | `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` | Settings → Privacy and security → App passwords |
| Mastodon | `MASTODON_INSTANCE` (e.g. `mastodon.social`), `MASTODON_TOKEN` | Preferences → Development → New application with `write:statuses` and `write:media` → copy the access token |
| X | `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET` | console.x.com: create an app with *Read and write* user permissions, then generate the consumer keys and your access token and secret. X API posting is pay-per-use: buy credits first. Reported prices are about $0.015 per post, or $0.20 if it has a link. |
| LinkedIn | `LINKEDIN_TOKEN`, `LINKEDIN_AUTHOR_URN` | developer.linkedin.com: create an app and add the *Share on LinkedIn* product (scope `w_member_social`). Get a token with the OAuth token generator. Author is `urn:li:person:<id>`; for a company page, use `urn:li:organization:<id>` with `w_organization_social`. **Tokens expire after 60 days.** |
| Threads | `THREADS_USER_ID`, `THREADS_TOKEN` | developers.facebook.com: create an app with the Threads use case and `threads_content_publish`, then get a long-lived token (valid 60 days, refreshable) |
| Instagram | `INSTAGRAM_USER_ID`, `INSTAGRAM_TOKEN` | Needs a Business or Creator account linked to a Facebook Page, plus a Meta app with `instagram_content_publish`. A system-user token doesn't expire. Every post needs a public `image_url`. |
| Facebook Page | `FACEBOOK_PAGE_ID`, `FACEBOOK_PAGE_TOKEN` | A Page access token with `pages_manage_posts`; the same Meta app works. |
| YouTube | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN` (or a shared `GOOGLE_REFRESH_TOKEN`) | console.cloud.google.com: enable *YouTube Data API v3*, create an OAuth client, and get a refresh token with scope `youtube.upload` (OAuth Playground works). Until Google audits your project, uploads are forced to private. Each post needs a `video:` file; keep it under 100 MB, GitHub's file limit. |
| Google Business Profile | `GBP_ACCOUNT_ID`, `GBP_LOCATION_ID`, `GBP_REFRESH_TOKEN` (or `GOOGLE_REFRESH_TOKEN`), plus the Google client ID and secret | Request Business Profile API access from Google first; approval takes days. The scope is `business.manage`. |

Optional **variables** (not secrets): `LINKEDIN_VERSION` (default `202608`, in `YYYYMM` form) and `META_GRAPH_VERSION` (default `v24.0`). Bump them when LinkedIn or Meta retire a version. Expired versions return HTTP 426 on LinkedIn and an error naming the version on Meta.

**Tokens that expire** (LinkedIn, and Threads/Instagram/Facebook unless you use a system-user token) cause `401` errors after about 60 days. Replace the secret when that happens.

## Post file format

```markdown
---
topic: New opening hours
schedule: 2026-10-09T09:00+02:00   # optional; no timezone means UTC
link: https://example.com           # Facebook preview, Google Business button
image: social/media/hours.jpg       # Bluesky (<1 MB), Mastodon
image_url: https://…/hours.jpg      # Instagram (required), Threads, Facebook, Google Business
image_alt: Shopfront at dusk
video: social/media/clip.mp4        # YouTube (required)
youtube_privacy: unlisted           # optional, default public
hold: yes                           # optional, keeps it from posting
---

## notes
For the reviewer; never posted.

## bluesky
…
## youtube
title: The video title
The description…
```

Sections: `bluesky`, `mastodon`, `x`, `linkedin`, `threads`, `instagram`, `facebook`, `youtube`, `google_business`.

**Limitations.** X and LinkedIn posts are text only, and links in them still show previews. YouTube community posts and Shorts-specific settings aren't in the API.
