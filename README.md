# Media Downloader  ·  Self-Hosted on Unraid

A locally-hosted media downloader. Paste any supported link, choose MP3 or MP4, pick a quality, and download. Supports single videos and full playlists. Works with 1000+ sites via yt-dlp.

---

## Quick Start (Unraid — Docker Compose)

### 1. Copy files to your Unraid server

```bash
mkdir -p /mnt/user/appdata/media-dl
# Copy the contents of this folder to /mnt/user/appdata/media-dl
```

### 2. Edit docker-compose.yml

Open `docker-compose.yml` and change the volume mount to point to your share:

```yaml
volumes:
  - /mnt/user/media/Music:/downloads   # ← your path here
```

Change the port `7474` if it conflicts with another container.

### 3. Build and start

```bash
cd /mnt/user/appdata/media-dl
docker compose up -d --build
```

### 4. Open in your browser

```
http://YOUR_UNRAID_IP:7474
```

---

## Manual Docker Commands

```bash
docker build -t media-dl /mnt/user/appdata/media-dl

docker run -d \
  --name media-dl \
  --restart unless-stopped \
  -p 7474:5000 \
  -v /mnt/user/media/Music:/downloads \
  -e DOWNLOAD_DIR=/downloads \
  media-dl
```

### Rebuild after updating files

```bash
docker rm -f media-dl
docker build --no-cache -t media-dl /mnt/user/appdata/media-dl
docker run -d \
  --name media-dl \
  --restart unless-stopped \
  -p 7474:5000 \
  -v /mnt/user/media/Music:/downloads \
  -e DOWNLOAD_DIR=/downloads \
  media-dl
```

---

## Adding via Unraid's Docker UI (no Compose)

1. Go to **Docker** tab → **Add Container**
2. Fill in:
   - **Name**: `media-dl`
   - **Port**: `7474` → `5000`
   - **Volume Path (Container)**: `/downloads`
   - **Volume Path (Host)**: your share, e.g. `/mnt/user/media/Music`
   - **Variable**: `DOWNLOAD_DIR` = `/downloads`
3. Click **Apply**

---

## Keeping yt-dlp updated

Sites change frequently. Update yt-dlp inside the running container:

```bash
docker exec media-dl pip install -U yt-dlp
```

Or do a full rebuild:

```bash
docker rm -f media-dl
docker build --no-cache -t media-dl /mnt/user/appdata/media-dl
```

---

## Permissions

If downloaded files are owned by root, uncomment the `user` line in `docker-compose.yml`:

```yaml
user: "99:100"   # nobody:users — Unraid's default unprivileged user
```

---

## Features

- ✅ 1000+ supported sites via yt-dlp
- ✅ MP3 (audio) and MP4 (video) output
- ✅ Selectable quality — MP3: 64–320 kbps · MP4: 240p–4K
- ✅ Single videos and full playlists (zipped for download)
- ✅ Embedded album art and ID3 tags (MP3)
- ✅ Real-time progress bar with speed + ETA
- ✅ Save to device (browser download) or directly to a server folder
- ✅ Server-side folder browser — pick any subfolder in your share
- ✅ No data leaves your server
