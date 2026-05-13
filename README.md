# YT → MP3  ·  Self-Hosted on Unraid

A locally-hosted YouTube to MP3 converter. Paste a URL, pick a folder, download.
Supports single videos and full playlists. Embeds 320kbps audio, album art, and ID3 tags.

---

## Quick Start (Unraid — Docker Compose)

### 1. Copy files to your Unraid server

```bash
# On your Unraid terminal (or SSH in):
mkdir -p /mnt/user/appdata/yt2mp3
# Copy the contents of this folder to /mnt/user/appdata/yt2mp3
```

### 2. Edit docker-compose.yml

Open `docker-compose.yml` and change the volume mount to point to your music share:

```yaml
volumes:
  - /mnt/user/media/Music:/downloads   # ← your path here
```

Change the port `7474` if it conflicts with another container.

### 3. Build and start

```bash
cd /mnt/user/appdata/yt2mp3
docker compose up -d --build
```

### 4. Open in your browser

```
http://YOUR_UNRAID_IP:7474
```

---

## Adding via Unraid's Docker UI (no Compose)

If you prefer Unraid's built-in Docker template UI instead of Compose:

1. Go to **Docker** tab → **Add Container**
2. Fill in:
   - **Repository**: build from local path (or push to Docker Hub first)
   - **Port**: `7474` → `5000`
   - **Volume Path (Container)**: `/downloads`
   - **Volume Path (Host)**: your share, e.g. `/mnt/user/media/Music`
   - **Variable**: `DOWNLOAD_DIR` = `/downloads`
3. Click **Apply**

---

## Keeping yt-dlp updated

YouTube changes frequently. Update yt-dlp inside the container:

```bash
docker exec yt2mp3 pip install -U yt-dlp
```

Or rebuild the image periodically:

```bash
docker compose build --no-cache && docker compose up -d
```

---

## Permissions

If downloaded files are owned by root, uncomment the `user` line in `docker-compose.yml`:

```yaml
user: "99:100"   # nobody:users — Unraid's default unprivileged user
```

---

## Features

- ✅ Single videos and full playlists
- ✅ 320kbps MP3
- ✅ Embedded album art (video thumbnail)
- ✅ ID3 tags: title, artist (channel name), year
- ✅ Real-time progress bar with speed + ETA
- ✅ Server-side folder browser — pick any subfolder in your share
- ✅ No data leaves your server
