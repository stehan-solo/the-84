---
name: social-draft
description: Draft social media posts from the topic inbox (social/topics.md) or from a topic passed as an argument. Saves Facebook, Instagram, YouTube and TikTok posts as Metricool drafts, writes LinkedIn (and any other direct platform) posts to social/queue/, and opens a PR for approval. Use when asked to draft social posts, when the scheduled drafting routine runs, or when the user gives a topic to post about.
---

# Draft social posts for approval

You write drafts. You never publish. There are two routes, and `social/profile.md` says which platform takes which:

- **Through Metricool** (Facebook, Instagram, YouTube, TikTok): save each post as a Metricool **draft**
  (`draft: true`). The user reviews and publishes it in the Metricool app.
  Never create a scheduled or auto-publishing Metricool post, and never edit one you didn't create in this run.
- **Directly** (LinkedIn, plus anything else listed under "Directly"): write the post to a file in `social/queue/` and open a PR.
  Merging the PR publishes it through `.github/workflows/social-publish.yml`. Never push to `main` and never merge your own PR.

## 1. Gather

1. Read `social/profile.md`. It gives the platforms and their routes, the Metricool blogId and timezone, the voice, the rules, and example posts.
2. Collect topics:
   - If you were given a topic as an argument, use that.
   - Otherwise take every bullet under `## Inbox` in `social/topics.md` on `main`.
   - If there are none, stop: say "No new topics." and open no PR.
3. List open PRs whose head branch starts with `social-drafts/`. Skip any topic one of them already covers.
   If nothing is left after that, stop.

## 2. Decide platforms per topic

Start from the platforms in profile.md, narrowed by any `[only: …]` tag. Then leave out a platform when it can't take the post, and say why in your summary:
- `instagram` and `tiktok` need an `image_url` or a `video_url`.
- `youtube` needs a `video_url` and a title (from `[youtube_title: …]`, or write one of at most 100 characters).
- `facebook` and `linkedin` can be text only.

Write each platform natively. Don't paste the same text everywhere:

| platform | limit | how to write it |
|---|---|---|
| linkedin | 3000 | first line hooks; short paragraphs; up to two hashtags at the end |
| facebook | long | friendly, two or three short paragraphs; a link becomes a preview |
| instagram | 2200 | caption to the image; links aren't clickable, so say "link in bio"; up to five hashtags |
| tiktok | 2200 | one punchy line, then two or three hashtags |
| youtube | title ≤100, description ≤5000 | say what the video shows; put links in the description |
| bluesky | 300 | conversational, link inline, no hashtags |
| x | 280 (each URL counts as 23) | one idea, at most one hashtag |
| mastodon / threads | 500 | casual; CamelCase hashtags on Mastodon |

Follow the voice and rules in profile.md exactly. Don't invent facts, numbers, dates, quotes or offers.
If a topic needs facts you don't have, write what you can and list the open questions.

## 3. Metricool platforms: save drafts

For each topic that has Metricool platforms, make **one** `createScheduledPost` call with:
- `blogId` from profile.md
- `date`: the topic's `[when: …]` time if given, otherwise tomorrow at 09:00 in the brand's timezone. The date can't be in the past.
- `info`: `draft: true` and `autoPublish: true`. Set `providers` to the topic's Metricool platforms and `text` to the Facebook text
  (or the Instagram caption if there's no Facebook post). Set `media` to the image/video URL if one was given, and `mediaAltText` when there's an image.
  Include a `<network>Data` object for every provider. Set `youtubeData.title`, `youtubeData.madeForKids: false` and `youtubeData.type` ("short" for vertical clips under 60 seconds, otherwise "video").
  Set `tiktokData.title` too.
  Metricool sends one text to every network in the call. When the platforms need different wording, make one call per platform instead.

Keep each `plannerUrl` from the responses. If the Metricool tools aren't available, or a call fails, don't retry.
Put that platform's text in the PR body under "Not saved to Metricool", with the error, so the user can paste it in by hand.

## 4. Direct platforms: write one file per topic

Only for topics with a direct platform (normally LinkedIn). Path: `social/queue/YYYY-MM-DD-<short-slug>.md` (today's date):

```markdown
---
topic: <the topic, one line>
schedule: 2026-10-09T09:00+02:00    # only if the topic gave [when: …]; omit otherwise
link: https://…                     # only if the notes give one
---

## notes
Why you made the choices you did, any source links, anything the reviewer should check.
The publisher ignores this section.

## linkedin
…post text…
```

Run `python3 social/publish.py --check <your new files>`. Fix every problem it reports, and run it again until it says `ok`.

## 5. Open the PR

Always open one, even when every post went to Metricool, because the PR is also what moves topics out of the Inbox.

1. In `social/topics.md`, move each drafted bullet from `## Inbox` to `## Drafted`, prefixed with today's date.
2. Create branch `social-drafts/YYYY-MM-DD` (append `-2`, `-3` if it exists), commit, and push.
3. Open a PR into `main` titled `Social drafts: <topic>[, <topic>…]`. Write the body in plain words for someone on a phone:

   > **In Metricool (not posted yet):** <platforms>. Open each link below, check the post, and tap Schedule or Publish there. Delete it in Metricool to skip it.
   >
   > **Merging this PR posts to:** <direct platforms>, at their scheduled time or within minutes if none.
   > - To edit: change the text in the file (✏️ on the Files tab).
   > - To skip one: delete its file. To skip everything: close the PR and remove the topic from the Inbox.

   Then, for each topic, give the Metricool planner links and each platform's text in a quote block.
   End with any open questions, and any platforms you left out and why.
   If no topic has a direct platform, say "Merging this PR only updates the topic list. It posts nothing."
