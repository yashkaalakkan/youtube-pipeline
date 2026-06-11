# YouTube Pipeline — GitHub Actions

Automatically downloads YouTube videos from a list and re-uploads them to your channel.
Runs twice daily at **5:00 AM** and **5:00 PM UTC** — entirely in the cloud, no local machine needed.

---

## Repo Structure

```
youtube-pipeline/
│
├── uploader.py                      ← Main pipeline script
├── links.txt                        ← Your YouTube links (one per line)
├── README.md                        ← This file
└── .github/
    └── workflows/
        └── pipeline.yml             ← GitHub Actions workflow
```

---

## Setup Steps

### 1. Create a GitHub Repo

- Go to https://github.com/new
- Create a **private** repo (recommended, since links.txt lives in it)
- Upload all files maintaining the folder structure above

### 2. Add GitHub Secrets

Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these 3 secrets:

| Secret Name        | Value                       |
|--------------------|-----------------------------|
| `YT_CLIENT_ID`     | Your Google OAuth client ID |
| `YT_CLIENT_SECRET` | Your Google OAuth secret    |
| `YT_REFRESH_TOKEN` | Your OAuth refresh token    |

> ✅ These are encrypted and never exposed in logs.

#### How to get your OAuth credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable **YouTube Data API v3**
3. Go to **APIs & Services** → **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
4. Application type: **Desktop app**
5. Download the JSON — `client_id` and `client_secret` are inside
6. To get your `refresh_token`, use [OAuth Playground](https://developers.google.com/oauthplayground/):
   - Gear icon → check "Use your own OAuth credentials" → enter your client ID & secret
   - Authorize `https://www.googleapis.com/auth/youtube.upload`
   - Exchange auth code for tokens → copy the **Refresh token**

### 3. Add Your Links

Edit `links.txt` — one YouTube URL per line:

```
https://www.youtube.com/watch?v=XXXXXXXXX
https://www.youtube.com/watch?v=YYYYYYYYY
https://www.youtube.com/watch?v=ZZZZZZZZZ
```

The script always picks the **bottom link**, uploads it, then removes it and commits the file back automatically.

### 4. That's It!

The workflow triggers automatically at **5 AM and 5 PM UTC** every day.

---

## Manual Run

You can trigger it anytime:

1. Go to your repo → **Actions** tab
2. Click **YouTube Pipeline**
3. Click **Run workflow** → **Run workflow**

---

## How It Works

```
links.txt (bottom URL)
       ↓
  yt-dlp download
  (video + thumbnail + metadata)
       ↓
  Upload to YouTube
  (same title, description, tags, thumbnail)
       ↓
  Scheduled public in 2 hours
       ↓
  Link removed → links.txt committed back
```

1. Reads the **last link** from `links.txt`
2. Downloads the video + metadata via `yt-dlp`
3. Uploads to your YouTube channel with original title, description, tags & thumbnail
4. Schedules the video to go **public 2 hours after upload**
5. Removes the processed link and commits `links.txt` back to the repo

---

## Configuration

Edit these constants at the top of `uploader.py`:

| Variable         | Default      | Description                          |
|------------------|--------------|--------------------------------------|
| `LINKS_FILE`     | `links.txt`  | Path to your links file              |
| `DOWNLOAD_DIR`   | `downloads`  | Temp folder for downloaded files     |
| `METADATA_DIR`   | `metadata`   | Folder for saved metadata JSON files |
| `SCHEDULE_DELAY` | `2`          | Hours until uploaded video goes public |

To change upload times, edit the cron lines in `.github/workflows/pipeline.yml`:

```yaml
- cron: "0 5 * * *"   # 5:00 AM UTC
- cron: "0 17 * * *"  # 5:00 PM UTC
```

Use [crontab.guru](https://crontab.guru) to build custom schedules.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Workflow not triggering | GitHub may delay cron by ~15 min; check Actions are enabled in repo Settings |
| `403` on YouTube upload | Re-check your OAuth credentials in Secrets; token may need refresh |
| `No more links` exit | Add more URLs to `links.txt` and commit |
| Video not found after download | The source URL may be private, age-restricted, or deleted |
| Thumbnail upload failed | Non-fatal warning — video still uploads successfully |
