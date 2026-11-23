# Social posting agent

You give it topics. Every morning Claude drafts posts in your voice. **Nothing is posted until you approve it.**

| Platforms | Where the draft goes | How you approve |
|---|---|---|
| Facebook, Instagram, YouTube, TikTok | A **draft in Metricool** | Open it in the Metricool app, check it, tap Schedule or Publish |
| LinkedIn | A **"Social drafts" PR** on GitHub | Tap **Merge pull request**. The *Social publish* Action posts it within minutes |

The PR opens every morning there's a new topic, even with no LinkedIn post, because merging it is also what marks the topics as done.
Its description links to each Metricool draft.

## Day to day

1. **Add a topic.** Edit `social/topics.md` on GitHub (the phone app works) and add a bullet under `## Inbox` with your notes.
   Instagram, TikTok and YouTube need a public image or video link: add `[image_url: …]` or `[video_url: …]`.
2. **Next morning, review.** Open the *Social drafts* PR. Use its Metricool links to publish those drafts, then merge the PR for LinkedIn.
3. **To skip a post,** delete the draft in Metricool, or delete the LinkedIn file in the PR before merging.

If LinkedIn posting fails, the failure is recorded as `error.linkedin` in the post's file and retried on the next hourly run, up to 3 attempts. After that the file moves to `social/failed/`.
A red *Social publish* run is how you find out, so turn on GitHub's failed-workflow notifications.

## LinkedIn setup (once, about 15 minutes)

1. Go to **linkedin.com/developers** → **Create app**. LinkedIn requires a company page for every app; your own page is fine.
2. On the app's **Products** tab, add **Share on LinkedIn** and **Sign In with LinkedIn using OpenID Connect**. Both are free and approved instantly.
3. Open **Docs and tools → OAuth Token Tools → Create token**. Tick `openid`, `profile` and `w_member_social`, then copy the access token.
4. Find your member ID. Ask Claude in any session to look it up with that token, or call `https://api.linkedin.com/v2/userinfo` with it; the `sub` value is your ID.
5. In this GitHub repo, go to **Settings → Secrets and variables → Actions → New repository secret** and add:
   - `LINKEDIN_TOKEN`: the access token
   - `LINKEDIN_AUTHOR_URN`: `urn:li:person:` followed by your ID
6. **The token expires after 60 days.** Set a reminder, repeat step 3, and update `LINKEDIN_TOKEN`.

This posts as you personally. Posting as a company page needs LinkedIn's Community Management API, which needs approval.

## Setup

1. Fill in `social/profile.md`: who you are, your voice, a few example posts, and which platforms to use.
2. For platforms that post directly, add their secrets, under **Settings → Secrets and variables → Actions** on this repo.
3. **Settings → Actions → General → Workflow permissions** must allow *Read and write*, so the Action can record what it posted.
4. Recommended: protect `main` so changes need a PR. This keeps the drafting routine from ever reaching main without you.

Run `python3 social/publish.py --dry-run` locally to see what would post. Run `python3 -m unittest social/test_publish.py` for the tests.

### Secrets for other direct platforms (optional)

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
