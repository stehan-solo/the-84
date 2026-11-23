"""Tests for publish.py. Run: python3 -m unittest social/test_publish.py"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish  # noqa: E402

SAMPLE = """---
topic: Opening hours change
link: https://example.com/hours
image_url: https://example.com/a.jpg
---

## notes
For the reviewer only.

## bluesky
New hours from Monday: https://example.com/hours

## x
New hours from Monday #news

## linkedin
We're open later (from Monday) #smallbusiness

## threads
New hours from Monday.

## instagram
New hours from Monday.

## facebook
New hours from Monday.

## google_business
New hours from Monday.

## mastodon
New hours from Monday.
"""

ENV = {
    "BLUESKY_HANDLE": "me.bsky.social", "BLUESKY_APP_PASSWORD": "pw",
    "MASTODON_INSTANCE": "mastodon.social", "MASTODON_TOKEN": "t",
    "X_API_KEY": "k", "X_API_SECRET": "s", "X_ACCESS_TOKEN": "t", "X_ACCESS_SECRET": "ts",
    "LINKEDIN_TOKEN": "t", "LINKEDIN_AUTHOR_URN": "urn:li:person:abc",
    "THREADS_USER_ID": "1", "THREADS_TOKEN": "t",
    "INSTAGRAM_USER_ID": "2", "INSTAGRAM_TOKEN": "t",
    "FACEBOOK_PAGE_ID": "3", "FACEBOOK_PAGE_TOKEN": "t",
    "GOOGLE_CLIENT_ID": "c", "GOOGLE_CLIENT_SECRET": "s", "GOOGLE_REFRESH_TOKEN": "r",
    "GBP_ACCOUNT_ID": "acc", "GBP_LOCATION_ID": "loc",
}


class FakeHTTP:
    """Answers each request from the first matching URL fragment."""

    ROUTES = [
        ("createSession", {"accessJwt": "jwt", "did": "did:plc:me", "handle": "me.bsky.social"}),
        ("createRecord", {"uri": "at://did:plc:me/app.bsky.feed.post/rkey1"}),
        ("/api/v1/statuses", {"url": "https://mastodon.social/@me/1"}),
        ("api.x.com/2/tweets", {"data": {"id": "99"}}),
        ("api.linkedin.com", {}),
        ("threads_publish", {"id": "t-post"}),
        ("graph.threads.net/v1.0/1/threads", {"id": "t-container"}),
        ("fields=status_code", {"status_code": "FINISHED"}),
        ("fields=status", {"status": "FINISHED"}),
        ("fields=permalink", {"permalink": "https://perma/link"}),
        ("/media_publish", {"id": "ig-post"}),
        ("/2/media", {"id": "ig-container"}),
        ("/3/photos", {"id": "photo", "post_id": "3_44"}),
        ("/3/feed", {"id": "3_55"}),
        ("oauth2.googleapis.com/token", {"access_token": "gtoken"}),
        ("localPosts", {"name": "accounts/acc/locations/loc/localPosts/1", "searchUrl": "https://g/p"}),
        ("upload/youtube", {}),
        ("upload-session", {"id": "vid1"}),
    ]

    def __init__(self, fail=()):
        self.calls = []
        self.fail = fail

    def __call__(self, method, url, **kw):
        self.calls.append((method, url, kw))
        if any(f in url for f in self.fail):
            raise publish.PublishError(f"{method} {url} -> HTTP 500: boom")
        for frag, body in self.ROUTES:
            if frag in url:
                headers = {}
                if "linkedin" in url:
                    headers["x-restli-id"] = "urn:li:share:7"
                if "upload/youtube" in url:
                    headers["Location"] = "https://upload/upload-session"
                return 201, headers, json.dumps(body).encode()
        raise AssertionError(f"unexpected request {method} {url}")

    def find(self, frag):
        return [c for c in self.calls if frag in c[1]]


class PublishTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.queue, self.posted, self.failed = self.tmp / "queue", self.tmp / "posted", self.tmp / "failed"
        self.queue.mkdir()
        for name, val in [("QUEUE", self.queue), ("POSTED", self.posted),
                          ("FAILED", self.failed), ("REPO", self.tmp)]:
            p = mock.patch.object(publish, name, val)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(os.environ, ENV)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(publish.time, "sleep")
        p.start()
        self.addCleanup(p.stop)

    def write(self, text, name="2026-10-07-hours.md"):
        f = self.queue / name
        f.write_text(text)
        return f

    def test_parses_frontmatter_and_sections(self):
        post = publish.Post.load(self.write(SAMPLE))
        self.assertEqual(post.get("topic"), "Opening hours change")
        self.assertEqual(post.sections["x"], "New hours from Monday #news")
        self.assertNotIn("notes", post.unposted())
        self.assertEqual(publish.problems(post), [])

    def test_publishes_everything_and_archives(self):
        f = self.write(SAMPLE)
        fake = FakeHTTP()
        with mock.patch.object(publish, "http", fake):
            posted, failed = publish.publish_file(f)
        self.assertEqual((posted, failed), (8, 0))
        self.assertFalse(f.exists())
        done = publish.Post.load(self.posted / f.name)
        self.assertEqual(done.get("posted.x"), "https://x.com/i/web/status/99")
        self.assertEqual(done.get("posted.bluesky"), "https://bsky.app/profile/me.bsky.social/post/rkey1")
        self.assertEqual(done.get("posted.linkedin"), "https://www.linkedin.com/feed/update/urn:li:share:7")
        self.assertEqual(done.get("posted.facebook"), "https://www.facebook.com/3_44")
        self.assertEqual(done.get("posted.google_business"), "https://g/p")
        self.assertEqual(done.sections["bluesky"], "New hours from Monday: https://example.com/hours")

    def test_bluesky_link_facet_uses_byte_offsets(self):
        f = self.write("---\n---\n## bluesky\nCafé → https://example.com/x.\n")
        fake = FakeHTTP()
        with mock.patch.object(publish, "http", fake):
            publish.publish_file(f)
        record = fake.find("createRecord")[0][2]["json_body"]["record"]
        idx = record["facets"][0]["index"]
        self.assertEqual(record["text"].encode()[idx["byteStart"]:idx["byteEnd"]], b"https://example.com/x")

    def test_linkedin_escapes_and_keeps_hashtags(self):
        self.assertEqual(publish._linkedin_text("Open (late) #smallbusiness_1 a_b"),
                         "Open \\(late\\) {hashtag|\\#|smallbusiness_1} a\\_b")

    def test_x_signs_with_oauth1(self):
        f = self.write("---\n---\n## x\nhello\n")
        fake = FakeHTTP()
        with mock.patch.object(publish, "http", fake):
            publish.publish_file(f)
        auth = fake.find("api.x.com")[0][2]["headers"]["Authorization"]
        self.assertTrue(auth.startswith("OAuth "))
        self.assertIn('oauth_signature="', auth)
        self.assertIn('oauth_consumer_key="k"', auth)

    def test_partial_failure_retries_only_what_failed(self):
        f = self.write(SAMPLE)
        with mock.patch.object(publish, "http", FakeHTTP(fail=["api.x.com"])):
            posted, failed = publish.publish_file(f)
        self.assertEqual((posted, failed), (7, 1))
        post = publish.Post.load(f)
        self.assertEqual(post.pending(), ["x"])
        self.assertEqual(post.get("attempts.x"), "1")
        fake = FakeHTTP()
        with mock.patch.object(publish, "http", fake):
            self.assertEqual(publish.publish_file(f), (1, 0))
        self.assertEqual(len(fake.find("createRecord")), 0)  # bluesky not re-posted
        self.assertTrue((self.posted / f.name).exists())

    def test_gives_up_after_max_attempts(self):
        f = self.write("---\n---\n## x\nhello\n")
        for _ in range(publish.MAX_ATTEMPTS):
            with mock.patch.object(publish, "http", FakeHTTP(fail=["api.x.com"])):
                publish.publish_file(f if f.exists() else self.failed / f.name)
        self.assertTrue((self.failed / f.name).exists())

    def test_schedule_and_hold(self):
        f = self.write("---\nschedule: 2026-10-09T09:00+02:00\n---\n## x\nhello\n")
        before = datetime(2026, 10, 9, 6, 59, tzinfo=timezone.utc)
        after = datetime(2026, 10, 9, 7, 0, tzinfo=timezone.utc)
        fake = FakeHTTP()
        with mock.patch.object(publish, "http", fake):
            self.assertEqual(publish.publish_file(f, now=before), (0, 0))
            self.assertEqual(fake.calls, [])
            self.assertEqual(publish.publish_file(f, now=after), (1, 0))
        g = self.write("---\nhold: yes\n---\n## x\nhello\n", "held.md")
        with mock.patch.object(publish, "http", FakeHTTP()):
            self.assertEqual(publish.publish_file(g), (0, 0))
        self.assertTrue(g.exists())

    def test_validation(self):
        post = publish.Post.load(self.write(
            "---\nschedule: tomorrow\n---\n## x\n" + "a" * 281 + "\n## instagram\nhi\n## tiktok\nhi\n"
            "## youtube\nno title line\n"))
        bad = "\n".join(publish.problems(post))
        for expected in ("tiktok", "bad schedule", "x: 281 chars", "instagram: needs image_url",
                         "youtube: youtube section must start", "youtube: needs video"):
            self.assertIn(expected, bad)

    def test_x_counts_urls_as_23(self):
        url = "https://example.com/" + "a" * 200
        post = publish.Post.load(self.write(f"---\n---\n## x\n{url}\n"))
        self.assertEqual(publish.problems(post), [])

    def test_invalid_file_is_not_published(self):
        f = self.write("---\n---\n## x\n" + "a" * 300 + "\n## bluesky\nfine\n")
        fake = FakeHTTP()
        with mock.patch.object(publish, "http", fake):
            self.assertEqual(publish.publish_file(f), (0, 1))
        self.assertEqual(fake.calls, [])

    def test_missing_secret_is_reported(self):
        f = self.write("---\n---\n## x\nhello\n")
        with mock.patch.dict(os.environ, {"X_API_KEY": ""}), \
             mock.patch.object(publish, "http", FakeHTTP()):
            publish.publish_file(f)
        self.assertIn("missing secret X_API_KEY", publish.Post.load(f).get("error.x"))

    def test_youtube_upload(self):
        (self.tmp / "clip.mp4").write_bytes(b"\0" * 10)
        f = self.write("---\nvideo: clip.mp4\nyoutube_tags: a, b\n---\n## youtube\n"
                       "title: My clip\nThe description.\n")
        fake = FakeHTTP()
        with mock.patch.object(publish, "http", fake):
            self.assertEqual(publish.publish_file(f), (1, 0))
        meta = fake.find("upload/youtube")[0][2]["json_body"]
        self.assertEqual(meta["snippet"], {"title": "My clip", "description": "The description.",
                                           "tags": ["a", "b"]})
        self.assertEqual(publish.Post.load(self.posted / f.name).get("posted.youtube"),
                         "https://youtu.be/vid1")

    def test_dry_run_changes_nothing(self):
        f = self.write(SAMPLE)
        before = f.read_text()
        with mock.patch.object(publish, "http", FakeHTTP(fail=[""])):
            publish.publish_file(f, dry_run=True)
        self.assertEqual(f.read_text(), before)


if __name__ == "__main__":
    unittest.main()
