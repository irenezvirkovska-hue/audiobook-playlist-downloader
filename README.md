# Audiobook Playlist Downloader

**A Python CLI that turns YouTube audiobook playlists into a clean offline MP3 library, without duplicates.**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![yt-dlp](https://img.shields.io/badge/Powered%20by-yt--dlp-red)
![FFmpeg](https://img.shields.io/badge/Audio-FFmpeg-007808)
[![Tests](https://github.com/irenezvirkovska-hue/audiobook-playlist-downloader/actions/workflows/tests.yml/badge.svg)](https://github.com/irenezvirkovska-hue/audiobook-playlist-downloader/actions/workflows/tests.yml)

## Why I built it

I made this tool for my friend's mother. She is blind and loves audiobooks, but YouTube playlists, ads and recommendations are hard to navigate without sight. A simple MP3 player with ready files works much better for her.

Preparing those files by hand was slow, and the same book often appeared in several playlists under slightly different names. So I wrote a tool that downloads whole playlists, converts them to MP3 and **skips everything that is already in the collection**.

## Features

- **Batch download.** Single URLs or a list of playlists from a text file.
- **MP3 conversion.** 192 kbps audio via yt-dlp and FFmpeg.
- **Three layers of duplicate protection:**
  1. a persistent archive of downloaded video IDs;
  2. exact matching of normalized titles against the download history and existing MP3 files;
  3. fuzzy title matching that never merges different parts of a book.
- **Reliable downloads.** Retries after network errors and YouTube 403 responses, resumes partial files; a title is saved to history only after a successful conversion.
- **Dry run.** `--dry-run` shows what would be downloaded and what would be skipped, without changing anything.
- **Summary report.** Counts of downloaded, skipped, unavailable and failed items.

## How duplicate detection works

Audiobook titles on YouTube are noisy: track numbers, channel tags, video IDs, phrases like "full audiobook in Ukrainian". The tool normalizes every title before comparing:

| Raw title | Normalized |
| --- | --- |
| `001. [Shevchenko] Аудіокнига «Іван Підкова». Тарас Шевченко.mp3` | `аудіокнига іван підкова тарас шевченко` |
| `Книга \| Аудіокнига українською [abcdefghijk].mp3` | `книга` |

Then it compares the new title with the collection:

| New title | Already in the collection | Result |
| --- | --- | --- |
| `КНИГА: частина 1` | `Книга — Частина 1` | ⏭ Skipped: exact match after normalization |
| `Книга — Частина 2` | `Книга — Частина 1` | ⬇️ Downloaded: different part number |

Fuzzy matching (`difflib.SequenceMatcher`, threshold 0.94) is applied only when titles contain **the same numbers**, so "Part 1" and "Part 2" are never treated as duplicates.

## Quick start

Requirements: Python 3.10+ and [FFmpeg](https://ffmpeg.org/download.html) on your PATH.

```bash
git clone https://github.com/irenezvirkovska-hue/audiobook-playlist-downloader.git
cd audiobook-playlist-downloader
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --pre -r requirements.txt
cp playlists.example.txt playlists.txt
```

Put one playlist or video URL per line in `playlists.txt` (lines starting with `#` are ignored), then:

```bash
python youtube_to_mp3.py --dry-run                 # preview, nothing is downloaded
python youtube_to_mp3.py                           # download everything from playlists.txt
python youtube_to_mp3.py --playlist "YOUTUBE_URL"  # a single playlist or video
python youtube_to_mp3.py --help                    # all options
```

Useful options: `--output` (destination folder), `--no-fuzzy`, `--similarity-threshold`, `--cookies-from-browser safari|chrome|firefox`.

`--pre` installs the latest yt-dlp build, which keeps up with frequent YouTube changes. Console messages are in Ukrainian.

## Tests

```bash
python -m unittest discover -s tests -v
```

Unit tests cover title normalization, duplicate and part-number handling, input parsing, yt-dlp configuration and retry logic. They run without network access and on every push via GitHub Actions.

## Project structure

```text
audiobook-playlist-downloader/
├── youtube_to_mp3.py              # CLI, duplicate detection, download and retry logic
├── tests/test_youtube_to_mp3.py   # unit tests
├── playlists.example.txt          # sample input
├── downloaded_books.example.txt   # sample title history
└── requirements.txt
```

Personal playlists, download history and audio files stay local and are excluded from Git.

---

Use it only for content you are allowed to download, and follow YouTube's terms of service.

Built by **Iryna Zvirkovska**: [GitHub](https://github.com/irenezvirkovska-hue) · [LinkedIn](https://www.linkedin.com/in/iryna-zvirkovska/)
