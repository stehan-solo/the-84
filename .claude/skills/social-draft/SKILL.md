---
name: social-draft
description: Draft social media posts from the topic inbox (social/topics.md) or from a topic passed as an argument, write them to social/queue/, validate them, and open a PR for approval. Use when asked to draft social posts, when the scheduled drafting routine runs, or when the user gives a topic to post about.
---

# Draft social posts for approval

You write drafts. You never publish. Publishing happens only when the user merges your PR,
which triggers `.github/workflows/social-publish.yml`. Never push to `main` and never merge your own PR.

## 1. Gather

1. Read `social/profile.md` for the enabled platforms, voice, rules and example posts.
2. Collect topics:
   - If you were given a topic as an argument, use that.
   - Otherwise take every bullet under `## Inbox` in `social/topics.md` on `main`.
   - If there are none, stop: say "No topics in the inbox" and open no PR.
3. List open PRs whose head branch starts with `social-drafts/`. Skip any topic one of them already covers.
   If nothing is left after that, stop.

## 2. Write one file per topic

Path: `social/queue/YYYY-MM-DD-<short-slug>.md` (today's date). Format:

```markdown
---
topic: <the topic, one line>
schedule: 2026-10-09T09:00+02:00    # only if the topic gave [when: …]; omit otherwise
link: https://…                     # only if the notes give one
image: social/media/x.jpg           # only if given
image_url: https://…                # only if given
image_alt: <describe the image>     # whenever there's an image
video: social/media/clip.mp4        # only if given
---

## notes
Why you made the choices you did, any source links, anything the reviewer should check.
The publisher ignores this section.

## bluesky
…post text…

## x
…
```

Only include a `## <platform>` section for platforms enabled in profile.md, narrowed by any `[only: …]` tag.
Leave out a platform when it can't take the post:
- `instagram` needs `image_url`. Leave it out if there's none, and say so in notes.
- `youtube` needs `video`. Leave it out if there's none.
- `google_business` is for business updates only. Leave it out for personal posts.

Write each platform natively. Don't paste the same text everywhere:

| platform | hard limit | how to write it |
|---|---|---|
| bluesky | 300 chars | conversational, link inline, no hashtags |
| x | 280 (each URL counts as 23) | punchy, one idea, at most one hashtag. A link makes the post cost about 13× more on X's API, so include one only when it's the point of the post |
| mastodon | 500 (each URL counts as 23) | like Bluesky; CamelCase hashtags help discovery |
| threads | 500 | casual, a question works well |
| linkedin | 3000 | first line hooks; short paragraphs; up to two hashtags at the end |
| instagram | 2200 | caption to the image; link won't be clickable, so say "link in bio" |
| facebook | long | friendly, two or three short paragraphs; the `link` becomes a preview |
| youtube | first line `title: …` (≤100 chars), then description ≤5000 | |
| google_business | 1500 | what's new and why it matters to a customer; `link` becomes a "Learn more" button |

Follow the voice and rules in profile.md exactly. Don't invent facts, numbers, dates, quotes or offers.
If a topic needs facts you don't have, write what you can and list the open questions in `notes`.

## 3. Validate

Run `python3 social/publish.py --check <your new files>`. Fix every problem it reports and run it again until it says `ok`.

## 4. Open the PR

1. In `social/topics.md`, move each drafted bullet from `## Inbox` to `## Drafted`, prefixed with today's date.
2. Create branch `social-drafts/YYYY-MM-DD` (append `-2`, `-3` if it exists), commit, and push.
3. Open a PR into `main` titled `Social drafts: <topic>[, <topic>…]`. For the body, start with this checklist:

   > **Merging publishes these posts** (at their `schedule`, or within minutes if none).
   > - To edit: change the text in the file (✏️ on the Files tab).
   > - To skip a platform: delete its `## section`.
   > - To skip a post: delete its file.
   > - To park it unposted: add `hold: yes` to its frontmatter.
   > - To reject everything: close the PR and remove the topic from the Inbox.

   Then, for each file, give the topic and each platform's text in a quote block so the user can review it on a phone without opening files.
   End with anything from `notes` the user should check.
