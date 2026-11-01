# Audiobook Playlist Downloader

A Python command-line tool for preparing an offline MP3 audiobook collection. Created to help a blind listener access audiobooks without navigating video playlists, it automates audio downloads, conversion and duplicate checks for the person preparing the collection.

## Features

- Accept individual YouTube URLs or playlists from a text file.
- Convert audio to MP3 at 192 kbps using yt-dlp and FFmpeg.
- Skip previously downloaded video IDs using a persistent archive.
- Normalize titles and conservatively compare similar titles, retaining chapter and part numbers.
- Check existing MP3 files alongside the local title history.
- Retry failed downloads and resume partial transfers.
- Record titles only after a successful download and conversion is confirmed.
- Preview the queue with `--dry-run`, without downloading or modifying local files.
- Print counts of downloaded, skipped, unavailable and failed items.

The tool prepares audio files; it is not an audiobook player or a screen-reader interface. Console messages are in Ukrainian.

## Requirements

- Python 3.10 or newer
- FFmpeg available on PATH
- Dependencies listed in `requirements.txt`
- Internet access for metadata lookup and downloads

## Setup

```bash
git clone https://github.com/irenezvirkovska-hue/audiobook-playlist-downloader.git
cd audiobook-playlist-downloader
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --pre -r requirements.txt
```

On Windows, activate the environment with `.venv\Scripts\activate`.
Install FFmpeg separately for your operating system.

Create your local input file:

```bash
cp playlists.example.txt playlists.txt
```

Replace the example URLs with URLs for content you are permitted to download. Use one URL per line; blank lines and lines beginning with `#` are ignored. Optionally copy `downloaded_books.example.txt` to `downloaded_books.txt` and replace the examples with your existing title history.

## Usage

```bash
# Inspect the queue and duplicates without downloading
python youtube_to_mp3.py --dry-run

# Download from playlists.txt
python youtube_to_mp3.py

# Process a single URL
python youtube_to_mp3.py --playlist "YOUTUBE_URL"

# Use a different input file or destination
python youtube_to_mp3.py --playlist-file my_urls.txt --output mp3

# See all options
python youtube_to_mp3.py --help
```

Additional options include `--books-file`, `--archive`, `--no-fuzzy` and `--similarity-threshold`. The default similarity threshold is 0.94. Optional `--cookies-from-browser` accepts `safari`, `chrome` or `firefox` when an authenticated session is needed.

## Duplicate handling

The script first checks the video ID archive, then compares normalized titles against the title history and existing MP3 filenames. Fuzzy comparisons require matching numeric components so different numbered parts are not treated as the same title. This is a heuristic, not audio-content matching.

The title history is appended after yt-dlp confirms success in its archive. Network failures are retried; a failed item does not add a title to the history.

## Tests

```bash
python -m unittest discover -s tests -v
```

The included tests cover title normalization, duplicate and part-number handling, input parsing, extractor configuration and retry behavior. They do not contact YouTube or validate live downloads. YouTube compatibility depends on the current yt-dlp version and upstream changes.

## Repository contents

- `youtube_to_mp3.py` - downloader and command-line interface
- `requirements.txt` - Python dependency
- `tests/test_youtube_to_mp3.py` - unit tests
- `playlists.example.txt` and `downloaded_books.example.txt` - sample inputs
- `.gitignore` - excludes local history, playlists, audio, environments and credentials

Personal playlists, download history, browser sessions and audio files are not included.

Use only content you have permission to download and follow the applicable platform terms and copyright requirements.
