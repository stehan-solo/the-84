#!/usr/bin/env python3
"""Publish approved social posts from social/queue/ to each platform.

A post file is markdown: a `---` frontmatter block of `key: value` lines,
then one `## <platform>` section per platform holding that platform's text.
Anything on main is approved (drafts arrive by PR, and merging approves them).

After each successful platform the file gets a `posted.<platform>: <url>`
line, so a re-run only retries what is left. A file with every section
posted moves to social/posted/.

  python3 social/publish.py            publish everything due
  python3 social/publish.py --dry-run  show what would be published
  python3 social/publish.py --check    validate queue files, publish nothing

Standard library only, so the GitHub Action needs no install step.
"""

import argparse
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QUEUE = ROOT / "queue"
POSTED = ROOT / "posted"
FAILED = ROOT / "failed"
REPO = ROOT.parent
MAX_ATTEMPTS = 3

META_VERSION = os.environ.get("META_GRAPH_VERSION") or "v24.0"
LINKEDIN_VERSION = os.environ.get("LINKEDIN_VERSION") or "202608"
FRONT_RE = re.compile(r"\A---[ \t]*\n(.*?)^---[ \t]*$\n?(.*)\Z", re.S | re.M)
URL_RE = re.compile(r"https?://[^\s<>()\"']+[^\s<>()\"'.,;:!?]")


class PublishError(Exception):
    pass


# ---------- post files ----------

class Post:
    def __init__(self, path, meta, sections, order):
        self.path = path
        self.meta = meta          # frontmatter, insertion-ordered
        self.sections = sections  # platform -> text
        self.order = order

    @classmethod
    def load(cls, path):
        raw = Path(path).read_text(encoding="utf-8")
        m = FRONT_RE.match(raw)
        if not m:
            raise PublishError(f"{path}: missing --- frontmatter block")
        meta = {}
        for line in m.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, val = line.partition(":")
            if not sep:
                raise PublishError(f"{path}: bad frontmatter line {line!r}")
            meta[key.strip()] = val.split(" #", 1)[0].strip()
        sections, order, current = {}, [], None
        for line in m.group(2).splitlines():
            h = re.match(r"^##\s+(\S+)\s*$", line)
            if h:
                current = h.group(1).lower()
                sections[current] = []
                order.append(current)
            elif current:
                sections[current].append(line)
        sections = {k: "\n".join(v).strip() for k, v in sections.items()}
        return cls(Path(path), meta, sections, order)

    def get(self, key, default=""):
        return self.meta.get(key, default)

    def record(self, key, value):
        """Write one frontmatter key back to disk immediately."""
        self.meta[key] = str(value).replace("\n", " ")
        m = FRONT_RE.match(self.path.read_text(encoding="utf-8"))
        lines = [l for l in m.group(1).splitlines() if not l.startswith(key + ":")]
        lines.append(f"{key}: {self.meta[key]}")
        self.path.write_text("---\n" + "\n".join(lines) + "\n---\n" + m.group(2), encoding="utf-8")

    def due(self, now):
        when = self.get("schedule")
        if not when:
            return True
        dt = datetime.fromisoformat(when.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt <= now

    def unposted(self):
        return [p for p in self.order
                if p in PLATFORMS and self.sections.get(p) and f"posted.{p}" not in self.meta]

    def pending(self):
        return [p for p in self.unposted()
                if int(self.get(f"attempts.{p}", "0") or 0) < MAX_ATTEMPTS]

    def media_path(self, key):
        rel = self.get(key)
        if not rel:
            return None
        p = (REPO / rel).resolve()
        if not p.is_file():
            raise PublishError(f"{key} file not found: {rel}")
        return p


# ---------- http ----------

def http(method, url, *, headers=None, data=None, json_body=None, form=None, timeout=120):
    headers = dict(headers or {})
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers.setdefault("Content-Type", "application/json")
    elif form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    headers.setdefault("User-Agent", "the-84-social-agent/1.0")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        raise PublishError(f"{method} {url.split('?')[0]} -> HTTP {e.code}: {body}") from None


def jload(body):
    return json.loads(body.decode() or "{}")


def env(*names):
    out = []
    for n in names:
        v = os.environ.get(n, "").strip()
        if not v:
            raise PublishError(f"missing secret {n}")
        out.append(v)
    return out if len(out) > 1 else out[0]


def multipart(fields, files):
    boundary = "----the84" + secrets.token_hex(12)
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for k, path in files.items():
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; '
                      f'filename="{path.name}"\r\nContent-Type: {ctype}\r\n\r\n').encode()
                     + path.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def google_access_token(refresh_var):
    client_id, client_secret = env("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET")
    refresh = os.environ.get(refresh_var) or os.environ.get("GOOGLE_REFRESH_TOKEN")
    if not refresh:
        raise PublishError(f"missing secret {refresh_var} (or GOOGLE_REFRESH_TOKEN)")
    _, _, body = http("POST", "https://oauth2.googleapis.com/token", form={
        "client_id": client_id, "client_secret": client_secret,
        "refresh_token": refresh, "grant_type": "refresh_token"})
    return jload(body)["access_token"]


def meta_wait(host, container_id, token, field):
    """Poll a Meta media container until it is ready to publish."""
    for _ in range(20):
        _, _, body = http("GET", f"{host}/{container_id}?fields={field}&access_token={token}")
        status = jload(body).get(field, "")
        if status in ("FINISHED", "PUBLISHED"):
            return
        if status in ("ERROR", "EXPIRED"):
            raise PublishError(f"media container {container_id} status {status}")
        time.sleep(3)
    raise PublishError(f"media container {container_id} not ready after 60s")


# ---------- platforms ----------

def bluesky(post, text):
    handle, password = env("BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD")
    svc = os.environ.get("BLUESKY_SERVICE", "https://bsky.social").rstrip("/")
    _, _, body = http("POST", f"{svc}/xrpc/com.atproto.server.createSession",
                      json_body={"identifier": handle, "password": password})
    sess = jload(body)
    auth = {"Authorization": f"Bearer {sess['accessJwt']}"}
    record = {"$type": "app.bsky.feed.post", "text": text,
              "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    facets = []
    for m in URL_RE.finditer(text):
        start = len(text[:m.start()].encode())
        facets.append({"index": {"byteStart": start, "byteEnd": start + len(m.group().encode())},
                       "features": [{"$type": "app.bsky.richtext.facet#link", "uri": m.group()}]})
    if facets:
        record["facets"] = facets
    img = post.media_path("image")
    if img:
        if img.stat().st_size > 1_000_000:
            raise PublishError("Bluesky images must be under 1 MB")
        _, _, body = http("POST", f"{svc}/xrpc/com.atproto.repo.uploadBlob", data=img.read_bytes(),
                          headers={**auth, "Content-Type": mimetypes.guess_type(img.name)[0] or "image/jpeg"})
        record["embed"] = {"$type": "app.bsky.embed.images", "images": [
            {"alt": post.get("image_alt"), "image": jload(body)["blob"]}]}
    _, _, body = http("POST", f"{svc}/xrpc/com.atproto.repo.createRecord", headers=auth,
                      json_body={"repo": sess["did"], "collection": "app.bsky.feed.post", "record": record})
    rkey = jload(body)["uri"].rsplit("/", 1)[-1]
    return f"https://bsky.app/profile/{sess.get('handle', handle)}/post/{rkey}"


def mastodon(post, text):
    instance, token = env("MASTODON_INSTANCE", "MASTODON_TOKEN")
    base = instance.rstrip("/")
    if not base.startswith("http"):
        base = "https://" + base
    auth = {"Authorization": f"Bearer {token}"}
    status = {"status": text, "visibility": os.environ.get("MASTODON_VISIBILITY", "public")}
    img = post.media_path("image")
    if img:
        data, ctype = multipart({"description": post.get("image_alt")}, {"file": img})
        _, _, body = http("POST", f"{base}/api/v2/media", data=data, headers={**auth, "Content-Type": ctype})
        status["media_ids"] = [jload(body)["id"]]
    key = hashlib.sha256(f"{post.path.name}:mastodon".encode()).hexdigest()
    _, _, body = http("POST", f"{base}/api/v1/statuses", json_body=status,
                      headers={**auth, "Idempotency-Key": key})
    return jload(body)["url"]


def _oauth1_header(method, url, ck, cs, tk, ts):
    q = lambda s: urllib.parse.quote(str(s), safe="~")
    oauth = {"oauth_consumer_key": ck, "oauth_nonce": secrets.token_hex(16),
             "oauth_signature_method": "HMAC-SHA1", "oauth_timestamp": str(int(time.time())),
             "oauth_token": tk, "oauth_version": "1.0"}
    params = "&".join(f"{q(k)}={q(v)}" for k, v in sorted(oauth.items()))
    base = "&".join([method, q(url), q(params)])
    sig = hmac.new(f"{q(cs)}&{q(ts)}".encode(), base.encode(), hashlib.sha1).digest()
    oauth["oauth_signature"] = base64.b64encode(sig).decode()
    return "OAuth " + ", ".join(f'{q(k)}="{q(v)}"' for k, v in sorted(oauth.items()))


def x(post, text):
    ck, cs, tk, ts = env("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")
    url = "https://api.x.com/2/tweets"
    _, _, body = http("POST", url, json_body={"text": text},
                      headers={"Authorization": _oauth1_header("POST", url, ck, cs, tk, ts)})
    return f"https://x.com/i/web/status/{jload(body)['data']['id']}"


def _linkedin_text(text):
    """LinkedIn 'little text': escape reserved chars, keep #hashtags live."""
    out, last = [], 0
    esc = lambda s: re.sub(r"([\\|{}@\[\]()<>#*_~])", r"\\\1", s)
    for m in re.finditer(r"(?<![\w#])#(\w+)", text):
        out.append(esc(text[last:m.start()]))
        out.append("{hashtag|\\#|" + m.group(1) + "}")
        last = m.end()
    out.append(esc(text[last:]))
    return "".join(out)


def linkedin(post, text):
    token, author = env("LINKEDIN_TOKEN", "LINKEDIN_AUTHOR_URN")
    _, headers, _ = http("POST", "https://api.linkedin.com/rest/posts", headers={
        "Authorization": f"Bearer {token}", "LinkedIn-Version": LINKEDIN_VERSION,
        "X-Restli-Protocol-Version": "2.0.0"}, json_body={
        "author": author, "commentary": _linkedin_text(text), "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [],
                         "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False})
    urn = {k.lower(): v for k, v in headers.items()}.get("x-restli-id", "")
    return f"https://www.linkedin.com/feed/update/{urn}" if urn else "posted (no id returned)"


def threads(post, text):
    uid, token = env("THREADS_USER_ID", "THREADS_TOKEN")
    host = "https://graph.threads.net/v1.0"
    form = {"text": text, "access_token": token, "media_type": "TEXT"}
    if post.get("image_url"):
        form.update(media_type="IMAGE", image_url=post.get("image_url"))
    _, _, body = http("POST", f"{host}/{uid}/threads", form=form)
    cid = jload(body)["id"]
    meta_wait(host, cid, token, "status")
    _, _, body = http("POST", f"{host}/{uid}/threads_publish",
                      form={"creation_id": cid, "access_token": token})
    pid = jload(body)["id"]
    _, _, body = http("GET", f"{host}/{pid}?fields=permalink&access_token={token}")
    return jload(body).get("permalink", pid)


def instagram(post, text):
    uid, token = env("INSTAGRAM_USER_ID", "INSTAGRAM_TOKEN")
    image_url = post.get("image_url")
    if not image_url:
        raise PublishError("Instagram needs image_url (a public https link to the image)")
    host = f"https://{os.environ.get('INSTAGRAM_GRAPH_HOST', 'graph.facebook.com')}/{META_VERSION}"
    _, _, body = http("POST", f"{host}/{uid}/media",
                      form={"image_url": image_url, "caption": text, "access_token": token})
    cid = jload(body)["id"]
    meta_wait(host, cid, token, "status_code")
    _, _, body = http("POST", f"{host}/{uid}/media_publish",
                      form={"creation_id": cid, "access_token": token})
    mid = jload(body)["id"]
    _, _, body = http("GET", f"{host}/{mid}?fields=permalink&access_token={token}")
    return jload(body).get("permalink", mid)


def facebook(post, text):
    page, token = env("FACEBOOK_PAGE_ID", "FACEBOOK_PAGE_TOKEN")
    host = f"https://graph.facebook.com/{META_VERSION}"
    if post.get("image_url"):
        _, _, body = http("POST", f"{host}/{page}/photos",
                          form={"url": post.get("image_url"), "message": text, "access_token": token})
        pid = jload(body).get("post_id") or jload(body)["id"]
    else:
        form = {"message": text, "access_token": token}
        if post.get("link"):
            form["link"] = post.get("link")
        _, _, body = http("POST", f"{host}/{page}/feed", form=form)
        pid = jload(body)["id"]
    return f"https://www.facebook.com/{pid}"


def _youtube_parts(text):
    m = re.match(r"\s*title:\s*(.+?)\n(.*)\Z", text + "\n", re.S | re.I)
    if not m:
        raise PublishError("youtube section must start with a 'title: ...' line")
    return m.group(1).strip(), m.group(2).strip()


def youtube(post, text):
    video = post.media_path("video")
    if not video:
        raise PublishError("YouTube needs a video file (video: social/media/clip.mp4)")
    title, description = _youtube_parts(text)
    token = google_access_token("YOUTUBE_REFRESH_TOKEN")
    tags = [t.strip() for t in post.get("youtube_tags").split(",") if t.strip()]
    ctype = mimetypes.guess_type(video.name)[0] or "video/*"
    size = video.stat().st_size
    _, headers, _ = http(
        "POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={"Authorization": f"Bearer {token}", "X-Upload-Content-Type": ctype,
                 "X-Upload-Content-Length": str(size)},
        json_body={"snippet": {"title": title, "description": description, "tags": tags},
                   "status": {"privacyStatus": post.get("youtube_privacy", "public"),
                              "selfDeclaredMadeForKids": False}})
    location = {k.lower(): v for k, v in headers.items()}["location"]
    with video.open("rb") as f:
        _, _, body = http("PUT", location, data=f, timeout=1800, headers={
            "Authorization": f"Bearer {token}", "Content-Type": ctype, "Content-Length": str(size)})
    return f"https://youtu.be/{jload(body)['id']}"


def google_business(post, text):
    account, location = env("GBP_ACCOUNT_ID", "GBP_LOCATION_ID")
    token = google_access_token("GBP_REFRESH_TOKEN")
    body = {"languageCode": os.environ.get("GBP_LANGUAGE", "en"), "summary": text, "topicType": "STANDARD"}
    if post.get("link"):
        body["callToAction"] = {"actionType": post.get("gbp_action", "LEARN_MORE"), "url": post.get("link")}
    if post.get("image_url"):
        body["media"] = [{"mediaFormat": "PHOTO", "sourceUrl": post.get("image_url")}]
    _, _, resp = http("POST", f"https://mybusiness.googleapis.com/v4/accounts/{account}"
                      f"/locations/{location}/localPosts",
                      headers={"Authorization": f"Bearer {token}"}, json_body=body)
    data = jload(resp)
    return data.get("searchUrl") or data.get("name", "posted")


# name -> (publish fn, max length, counts URLs as this many chars or None)
PLATFORMS = {
    "bluesky": (bluesky, 300, None),
    "mastodon": (mastodon, 500, 23),
    "x": (x, 280, 23),
    "linkedin": (linkedin, 3000, None),
    "threads": (threads, 500, None),
    "instagram": (instagram, 2200, None),
    "facebook": (facebook, 60000, None),
    "youtube": (youtube, 5000, None),
    "google_business": (google_business, 1500, None),
}


def text_length(text, url_len):
    if url_len:
        text = URL_RE.sub("x" * url_len, text)
    return len(text)


def problems(post):
    """Return a list of reasons this post would fail before calling any API."""
    out = []
    unknown = [p for p in post.sections if p not in PLATFORMS and p != "notes"]
    if unknown:
        out.append(f"unknown platform section(s): {', '.join(unknown)} "
                   f"(use: {', '.join(PLATFORMS)})")
    if not any(post.sections.get(p) for p in PLATFORMS):
        out.append("no platform sections with text")
    try:
        post.due(datetime.now(timezone.utc))
    except ValueError:
        out.append(f"bad schedule {post.get('schedule')!r} (use 2026-10-09T09:00+02:00)")
    for p, text in post.sections.items():
        if p not in PLATFORMS or not text:
            continue
        if p == "youtube":
            try:
                title, text = _youtube_parts(text)
                if len(title) > 100:
                    out.append(f"youtube: title is {len(title)} chars, limit 100")
            except PublishError as e:
                out.append(f"youtube: {e}")
        limit, url_len = PLATFORMS[p][1], PLATFORMS[p][2]
        n = text_length(text, url_len)
        if n > limit:
            out.append(f"{p}: {n} chars, limit {limit}")
    if post.sections.get("instagram") and not post.get("image_url"):
        out.append("instagram: needs image_url")
    if post.sections.get("youtube") and not post.get("video"):
        out.append("youtube: needs video")
    for key in ("image", "video"):
        if post.get(key) and not (REPO / post.get(key)).is_file():
            out.append(f"{key} file not found: {post.get(key)}")
    return out


# ---------- main ----------

def publish_file(path, dry_run=False, now=None):
    """Publish the due, pending sections of one file. Returns (posted, failed)."""
    post = Post.load(path)
    now = now or datetime.now(timezone.utc)
    if post.get("hold").lower() in ("yes", "true", "1"):
        print(f"  {path.name}: on hold")
        return 0, 0
    if not post.due(now):
        print(f"  {path.name}: scheduled for {post.get('schedule')}")
        return 0, 0
    bad = problems(post)
    if bad:
        for b in bad:
            print(f"  {path.name}: INVALID {b}")
        return 0, 1
    posted = failed = 0
    for platform in post.pending():
        if dry_run:
            print(f"  {path.name}: would post to {platform}")
            continue
        try:
            url = PLATFORMS[platform][0](post, post.sections[platform])
        except Exception as e:  # keep going so one platform can't block the rest
            n = int(post.get(f"attempts.{platform}", "0") or 0) + 1
            post.record(f"attempts.{platform}", n)
            post.record(f"error.{platform}", str(e)[:300])
            print(f"  {path.name}: {platform} FAILED (attempt {n}/{MAX_ATTEMPTS}): {e}")
            failed += 1
            continue
        post.record(f"posted.{platform}", url)
        print(f"  {path.name}: {platform} -> {url}")
        posted += 1
    if not dry_run and not post.pending():
        dest = POSTED if not post.unposted() else FAILED
        dest.mkdir(exist_ok=True)
        post.path.rename(dest / post.path.name)
        if dest is FAILED:
            print(f"  {path.name}: gave up on {', '.join(post.unposted())}; moved to social/failed/")
    return posted, failed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true", help="validate queue files and exit")
    ap.add_argument("files", nargs="*", type=Path, help="default: every file in social/queue")
    args = ap.parse_args(argv)
    files = args.files or sorted(QUEUE.glob("*.md"))
    if not files:
        print("queue is empty")
        return 0
    if args.check:
        errors = 0
        for f in files:
            try:
                post = Post.load(f)
                bad = problems(post)
            except PublishError as e:
                bad = [str(e)]
            for b in bad:
                print(f"{f}: {b}")
            errors += len(bad)
            if not bad:
                print(f"{f}: ok ({', '.join(post.unposted())})")
        return 1 if errors else 0
    total_failed = 0
    for f in files:
        try:
            _, failed = publish_file(f, dry_run=args.dry_run)
        except PublishError as e:
            print(f"  {f.name}: {e}")
            failed = 1
        total_failed += failed
    return 1 if total_failed else 0


if __name__ == "__main__":
    sys.exit(main())
