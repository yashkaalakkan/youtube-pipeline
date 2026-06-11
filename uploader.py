import os
import json
import datetime
import sys
import subprocess

# ─── CONFIGURATION (from environment variables / GitHub Secrets) ──────────────
CLIENT_ID      = os.environ["YT_CLIENT_ID"]
CLIENT_SECRET  = os.environ["YT_CLIENT_SECRET"]
REFRESH_TOKEN  = os.environ["YT_REFRESH_TOKEN"]

LINKS_FILE     = "links.txt"
DOWNLOAD_DIR   = "downloads"
METADATA_DIR   = "metadata"
COOKIES_FILE   = "/tmp/yt_cookies.txt"
SCHEDULE_DELAY = 2  # hours until video goes public

SHORTS_MAX_DURATION = 60
# ──────────────────────────────────────────────────────────────────────────────

def install_dependencies():
    subprocess.check_call([
        sys.executable, "-m", "pip", "install",
        "yt-dlp", "yt-dlp-ejs", "google-api-python-client",
        "google-auth", "google-auth-oauthlib", "-q"
    ])

def setup_cookies():
    cookies_content = os.environ.get("YT_COOKIES", "").strip()
    if cookies_content:
        with open(COOKIES_FILE, "w") as f:
            f.write(cookies_content)
        print("[INFO] Cookies written from secret.")
        return COOKIES_FILE
    print("[WARN] YT_COOKIES secret not set — will try without cookies.")
    return None

def get_bottom_link(filepath):
    if not os.path.exists(filepath):
        print("[ERROR] links.txt not found.")
        sys.exit(1)
    with open(filepath, "r") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    if not lines:
        print("[INFO] No more links. Exiting.")
        sys.exit(0)
    return lines[-1]

def remove_bottom_link(filepath):
    with open(filepath, "r") as f:
        lines = f.readlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if lines:
        lines.pop()
    with open(filepath, "w") as f:
        f.writelines(lines)
    print("[INFO] Link removed from links.txt.")

def is_shorts_url(url):
    return "/shorts/" in url

def download_video(url, cookies_file=None):
    import yt_dlp
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    base_opts = {
        "outtmpl":            os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "format":             "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "writethumbnail":     True,
        "writeinfojson":      True,
        "quiet":              False,
        "retries":            10,
        "fragment_retries":   10,
        "ignoreerrors":       False,
        "cookiefile":         None,
        "cookiesfrombrowser": None,
        # Tell yt-dlp to use node runtime and fetch EJS solver scripts
        "extractor_args": {
            "youtube": {
                "player_client": ["ios"],
            }
        },
    }

    # Attempt 1 & 2: cookieless ios/android
    cookieless_attempts = [
        ("ios",     ["ios"]),
        ("android", ["android"]),
    ]
    for label, clients in cookieless_attempts:
        print(f"[INFO] Attempt: {label} (no cookies)")
        opts = dict(base_opts)
        opts["extractor_args"] = {"youtube": {"player_client": clients}}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=True)
        except Exception as e:
            print(f"[WARN] {label} failed: {e}")

    # Attempt 3: web + cookies + EJS solver via node
    if cookies_file and os.path.exists(cookies_file):
        print("[INFO] Attempt: web client with cookies + EJS solver")
        opts = dict(base_opts)
        opts["cookiefile"] = cookies_file
        opts["extractor_args"] = {"youtube": {"player_client": ["web"]}}
        # Use node runtime and fetch EJS scripts from GitHub
        opts["js_runtimes"] = {"node": {}}
        opts["remote_components"] = ["ejs:github"]
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=True)
        except Exception as e:
            print(f"[WARN] web+cookies+EJS failed: {e}")
    else:
        print("[WARN] No cookies available for web client fallback.")

    print("[ERROR] All download attempts failed.")
    sys.exit(1)

def save_metadata(info):
    os.makedirs(METADATA_DIR, exist_ok=True)
    video_id  = info.get("id", "unknown")
    meta_path = os.path.join(METADATA_DIR, f"{video_id}_metadata.json")

    metadata = {
        "id":          video_id,
        "title":       info.get("title", ""),
        "description": info.get("description", ""),
        "tags":        info.get("tags", []),
        "categories":  info.get("categories", []),
        "duration":    info.get("duration"),
        "uploader":    info.get("uploader", ""),
        "upload_date": info.get("upload_date", ""),
        "thumbnail":   info.get("thumbnail", ""),
        "webpage_url": info.get("webpage_url", ""),
    }

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"[INFO] Metadata saved: {meta_path}")
    return metadata

def get_video_file(video_id):
    for f in os.listdir(DOWNLOAD_DIR):
        if f.startswith(video_id) and f.endswith((".mp4", ".mkv", ".webm")):
            return os.path.join(DOWNLOAD_DIR, f)
    return None

def get_thumbnail_file(video_id):
    for f in os.listdir(DOWNLOAD_DIR):
        if f.startswith(video_id) and f.endswith((".jpg", ".jpeg", ".png", ".webp")):
            return os.path.join(DOWNLOAD_DIR, f)
    return None

def detect_upload_type(url, duration):
    if is_shorts_url(url):
        return "short"
    if duration and duration <= SHORTS_MAX_DURATION:
        return "short"
    return "video"

def upload_to_youtube(video_path, metadata, upload_type="video"):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )

    youtube = build("youtube", "v3", credentials=creds)

    publish_at     = datetime.datetime.utcnow() + datetime.timedelta(hours=SCHEDULE_DELAY)
    publish_at_str = publish_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    title       = metadata["title"]
    description = metadata["description"] or ""
    tags = []  # skip tags to avoid YouTube API invalidTags errors

    if upload_type == "short":
        print("[INFO] Upload type: SHORT")
        if "#Shorts" not in title and "#shorts" not in title:
            title = title + " #Shorts"
        if "#Shorts" not in description:
            description = "#Shorts\n\n" + description
        if "Shorts" not in tags:
            tags = ["Shorts"] + tags
    else:
        print("[INFO] Upload type: VIDEO (regular)")

    body = {
        "snippet": {
            "title":       title,
            "description": description,
            "tags":        tags,
            "categoryId":  "22",
        },
        "status": {
            "privacyStatus":           "private",
            "publishAt":               publish_at_str,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 5
    )

    print(f"[INFO] Uploading: {title}")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  Progress: {int(status.progress() * 100)}%")

    uploaded_id = response.get("id")
    print(f"[SUCCESS] Uploaded! Video ID: {uploaded_id}")
    print(f"[INFO] Goes public at: {publish_at_str} UTC")

    video_id = os.path.splitext(os.path.basename(video_path))[0]
    thumb    = get_thumbnail_file(video_id)
    if thumb:
        try:
            youtube.thumbnails().set(
                videoId=uploaded_id,
                media_body=MediaFileUpload(thumb)
            ).execute()
            print("[INFO] Thumbnail uploaded.")
        except Exception as e:
            print(f"[WARN] Thumbnail upload failed: {e}")

    return uploaded_id

def main():
    print(f"\n{'='*55}")
    print(f" YouTube Pipeline — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{'='*55}\n")

    install_dependencies()
    cookies_file = setup_cookies()

    url = get_bottom_link(LINKS_FILE)
    print(f"[INFO] Processing: {url}")

    info     = download_video(url, cookies_file)
    video_id = info.get("id")
    metadata = save_metadata(info)

    video_path = get_video_file(video_id)
    if not video_path:
        print("[ERROR] Downloaded video file not found.")
        sys.exit(1)

    duration    = metadata.get("duration")
    upload_type = detect_upload_type(url, duration)
    print(f"[INFO] Duration: {duration}s — detected as: {upload_type.upper()}")

    upload_to_youtube(video_path, metadata, upload_type=upload_type)
    remove_bottom_link(LINKS_FILE)

    print("\n[DONE] Pipeline completed successfully!")

if __name__ == "__main__":
    main()