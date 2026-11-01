#!/usr/bin/env python3
"""Download YouTube playlists or video URL lists as MP3 without duplicates."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

try:
    import yt_dlp
except ImportError:
    print(
        "Не встановлено yt-dlp. Виконай: python -m pip install -r requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(2)


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = BASE_DIR / "mp3"
DEFAULT_BOOKS_FILE = BASE_DIR / "downloaded_books.txt"
DEFAULT_ARCHIVE_FILE = BASE_DIR / "youtube_archive.txt"
DEFAULT_SIMILARITY_THRESHOLD = 0.94
DOWNLOAD_ATTEMPTS = 3
RETRY_DELAYS_SECONDS = (10, 20)
YOUTUBE_ID_RE = re.compile(r"\[([A-Za-z0-9_-]{11})\]\s*$")


@dataclass
class Stats:
    found: int = 0
    downloaded: int = 0
    title_skips: int = 0
    archive_skips: int = 0
    unavailable: int = 0
    failed: int = 0


def path_from_arg(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else BASE_DIR / path


def default_playlist_file() -> Path:
    plural = BASE_DIR / "playlists.txt"
    singular = BASE_DIR / "playlist.txt"
    if plural.exists():
        return plural
    if singular.exists():
        return singular
    return plural


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Завантажує YouTube-плейлісти/відео як MP3 і пропускає повтори."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--playlist", metavar="URL", help="Один playlist/video URL")
    source.add_argument(
        "--playlist-file",
        type=path_from_arg,
        metavar="FILE",
        help="TXT-файл: один playlist/video URL у рядку",
    )
    parser.add_argument(
        "--output",
        type=path_from_arg,
        default=DEFAULT_OUTPUT_DIR,
        help="Папка для MP3 (типово: mp3)",
    )
    parser.add_argument(
        "--books-file",
        type=path_from_arg,
        default=DEFAULT_BOOKS_FILE,
        help="Локальна база успішно завантажених назв",
    )
    parser.add_argument(
        "--archive",
        type=path_from_arg,
        default=DEFAULT_ARCHIVE_FILE,
        help="Архів video ID для yt-dlp",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=DEFAULT_SIMILARITY_THRESHOLD,
        metavar="0..1",
        help="Поріг обережної нечіткої перевірки назв (типово: 0.94)",
    )
    parser.add_argument(
        "--no-fuzzy",
        action="store_true",
        help="Вимкнути нечітке порівняння назв; залишити лише точне",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Перевірити списки й повтори без завантаження та запису",
    )
    parser.add_argument(
        "--cookies-from-browser",
        choices=("safari", "chrome", "firefox"),
        help="Використати вхід у YouTube з указаного браузера, якщо це потрібно",
    )
    args = parser.parse_args()
    if not 0.0 <= args.similarity_threshold <= 1.0:
        parser.error("--similarity-threshold має бути від 0 до 1")
    if args.playlist_file is None:
        args.playlist_file = default_playlist_file()
    return args


def normalize_title(title: str) -> str:
    """Return a conservative comparison form while retaining part numbers."""
    title = unicodedata.normalize("NFKC", title).casefold()
    title = re.sub(r"\.(mp3|mp4|m4a|webm|wav|opus)$", "", title)
    title = YOUTUBE_ID_RE.sub(" ", title)
    title = re.sub(r"^\s*\d{1,4}\s*[.)\-–—:]\s*", "", title)
    title = re.sub(r"\[(shevchenko|ukr_klasyka|roman|detektyv|rizne)\]", " ", title)
    title = re.sub(r"#\S+", " ", title)
    junk_phrases = (
        "аудіокнига українською мовою",
        "аудіокнига українською",
        "аудіокниги українською",
        "аудіо книга українською",
        "повна аудіокнига",
        "аудіокнига повністю",
        "слухати українською",
        "слухати онлайн",
        "українською мовою",
        "повна версія",
        "повний твір",
    )
    for phrase in junk_phrases:
        title = title.replace(phrase, " ")
    title = re.sub(r"[^\w\sіїєґ']", " ", title, flags=re.UNICODE)
    return re.sub(r"\s+", " ", title).strip()


def title_from_mp3(path: Path) -> str:
    title = path.stem
    title = YOUTUBE_ID_RE.sub("", title).strip()
    return re.sub(r"^\d{1,4}\s*[.)\-–—:]\s*", "", title).strip()


def read_nonempty_lines(path: Path, *, create: bool = False) -> list[str]:
    if not path.exists():
        if create:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            return []
        raise FileNotFoundError(path)
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def unique_in_order(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def load_known_titles(books_file: Path, output_dir: Path, *, create: bool = True) -> list[str]:
    if books_file.exists():
        titles = read_nonempty_lines(books_file)
    elif create:
        titles = read_nonempty_lines(books_file, create=True)
    else:
        titles = []
    scan_dirs = unique_in_order([str(output_dir.resolve()), str(BASE_DIR.resolve())])
    for directory_name in scan_dirs:
        directory = Path(directory_name)
        if directory.exists():
            titles.extend(title_from_mp3(path) for path in directory.glob("*.mp3"))
    return unique_in_order(title for title in titles if normalize_title(title))


def append_downloaded_title(path: Path, title: str) -> None:
    """Durably append exactly one successful title."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(title.strip().replace("\n", " ") + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def numbers_in(title: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\d+", title))


def find_duplicate(
    new_title: str,
    known_titles: list[str],
    exact_titles: set[str],
    threshold: float,
    fuzzy: bool,
) -> tuple[str | None, float]:
    normalized_new = normalize_title(new_title)
    if not normalized_new:
        return None, 0.0
    if normalized_new in exact_titles:
        for old_title in known_titles:
            if normalize_title(old_title) == normalized_new:
                return old_title, 1.0
    if not fuzzy or len(normalized_new) < 12:
        return None, 0.0

    best_match: str | None = None
    best_score = 0.0
    new_numbers = numbers_in(normalized_new)
    for old_title in known_titles:
        normalized_old = normalize_title(old_title)
        if len(normalized_old) < 12 or numbers_in(normalized_old) != new_numbers:
            continue
        score = SequenceMatcher(None, normalized_new, normalized_old).ratio()
        if score > best_score:
            best_match, best_score = old_title, score
    return (best_match, best_score) if best_score >= threshold else (None, best_score)


def load_archive_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        parts = line.strip().split()
        if parts:
            ids.add(parts[-1])
    return ids


def get_urls(args: argparse.Namespace) -> list[str]:
    if args.playlist:
        return [args.playlist.strip()]
    try:
        urls = read_nonempty_lines(args.playlist_file)
    except FileNotFoundError as exc:
        raise SystemExit(
            f"Не знайдено {exc.filename}. Створи playlists.txt і встав URL по одному в рядок."
        ) from exc
    urls = unique_in_order(urls)
    if not urls:
        raise SystemExit(f"Файл {args.playlist_file.name} порожній. Додай хоча б один URL.")
    return urls


def common_ydl_options(args: argparse.Namespace) -> dict[str, object]:
    options: dict[str, object] = {
        "retries": 10,
        "fragment_retries": 10,
        "ignoreerrors": False,
        "force_ipv4": True,
        "sleep_interval": 3,
        "max_sleep_interval": 6,
        "extractor_args": {
            # visionOS avoids the current intermittent 403 experiment that
            # affects android_vr and PO-token-backed web clients.
            "youtube": {"player_client": ["visionos"]},
        },
    }
    if args.cookies_from_browser:
        options["cookiesfrombrowser"] = (args.cookies_from_browser,)
    return options


def entry_url(entry: dict[str, object]) -> str | None:
    webpage_url = entry.get("webpage_url")
    if isinstance(webpage_url, str) and webpage_url.startswith(("http://", "https://")):
        return webpage_url
    video_id = entry.get("id")
    if isinstance(video_id, str) and video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    raw_url = entry.get("url")
    if isinstance(raw_url, str) and raw_url.startswith(("http://", "https://")):
        return raw_url
    return None


def inspect_url(url: str, args: argparse.Namespace) -> list[dict[str, object] | None]:
    options = common_ydl_options(args)
    options.update({"quiet": True, "extract_flat": "in_playlist", "ignoreerrors": True})
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        return []
    entries = info.get("entries") if isinstance(info, dict) else None
    return list(entries) if entries is not None else [info]


def download_video(url: str, args: argparse.Namespace) -> dict[str, object] | None:
    args.output.mkdir(parents=True, exist_ok=True)
    options = common_ydl_options(args)
    options.update(
        {
            "format": "bestaudio/best",
            "outtmpl": str(args.output / "%(title)s [%(id)s].%(ext)s"),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "download_archive": str(args.archive),
            "noplaylist": True,
            "continuedl": True,
            "quiet": False,
        }
    )
    with yt_dlp.YoutubeDL(options) as ydl:
        return ydl.extract_info(url, download=True)


def download_video_with_retries(
    url: str, args: argparse.Namespace
) -> dict[str, object] | None:
    """Retry the whole extraction so YouTube issues a fresh media URL/token."""
    last_error: Exception | None = None
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            return download_video(url, args)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            last_error = exc
            if attempt == DOWNLOAD_ATTEMPTS:
                break
            delay = RETRY_DELAYS_SECONDS[attempt - 1]
            print(
                f"⚠️  YouTube відхилив спробу {attempt}/{DOWNLOAD_ATTEMPTS}. "
                f"Повторюю через {delay} секунд…"
            )
            time.sleep(delay)
    assert last_error is not None
    raise last_error


def main() -> int:
    args = parse_args()
    if not args.dry_run and shutil.which("ffmpeg") is None:
        print("Не знайдено FFmpeg. Встанови його командою: brew install ffmpeg", file=sys.stderr)
        return 2
    urls = get_urls(args)
    known_titles = load_known_titles(args.books_file, args.output, create=not args.dry_run)
    exact_titles = {normalize_title(title) for title in known_titles}
    archive_ids = load_archive_ids(args.archive)
    stats = Stats()

    print(f"URL у черзі: {len(urls)}")
    print(f"Відомих назв (база + наявні MP3): {len(known_titles)}")
    print(f"Video ID в архіві yt-dlp: {len(archive_ids)}")
    if args.dry_run:
        print("Режим перевірки: файли та списки не змінюються.")

    for source_number, source_url in enumerate(urls, start=1):
        print(f"\n{'=' * 64}\nURL {source_number}/{len(urls)}: {source_url}\n{'=' * 64}")
        try:
            entries = inspect_url(source_url, args)
        except Exception as exc:
            stats.failed += 1
            print(f"❌ Не вдалося прочитати URL: {exc}")
            continue
        if not entries:
            stats.failed += 1
            print("❌ За цим URL не знайдено доступних відео.")
            continue
        print(f"Знайдено позицій: {len(entries)}")

        for index, entry in enumerate(entries, start=1):
            stats.found += 1
            if not entry:
                stats.unavailable += 1
                print(f"⚠️  {index}: недоступне або видалене відео")
                continue
            title = str(entry.get("title") or "Без назви")
            video_id = str(entry.get("id") or "")
            if video_id and video_id in archive_ids:
                stats.archive_skips += 1
                print(f"⏭️  Архів yt-dlp: {title}")
                continue
            duplicate, score = find_duplicate(
                title,
                known_titles,
                exact_titles,
                args.similarity_threshold,
                not args.no_fuzzy,
            )
            if duplicate:
                stats.title_skips += 1
                print(f"⏭️  Назва вже є: {title}")
                if normalize_title(title) != normalize_title(duplicate):
                    print(f"    Схожа на: {duplicate} ({score:.0%})")
                continue
            video_url = entry_url(entry)
            if not video_url:
                stats.unavailable += 1
                print(f"⚠️  Немає адреси відео: {title}")
                continue
            if args.dry_run:
                print(f"⬇️  Нове: {title}")
                continue

            print(f"\n⬇️  Завантажую: {title}")
            try:
                result = download_video_with_retries(video_url, args)
                refreshed_archive = load_archive_ids(args.archive)
                if not result or (video_id and video_id not in refreshed_archive):
                    raise RuntimeError("yt-dlp не підтвердив успішне завантаження в архіві")
                final_title = str(result.get("title") or title).strip()
                append_downloaded_title(args.books_file, final_title)
                known_titles.append(final_title)
                exact_titles.add(normalize_title(final_title))
                archive_ids = refreshed_archive
                stats.downloaded += 1
                print(f"✅ Готово: {final_title}")
            except KeyboardInterrupt:
                print("\nСкасовано користувачем. Незавершена назва не додана до бази.")
                return 130
            except Exception as exc:
                stats.failed += 1
                print(f"❌ Помилка: {title}\n   {exc}\n   Назва не додана до бази.")

    print("\n" + "=" * 64)
    print(
        "Підсумок: "
        f"знайдено {stats.found}; "
        f"завантажено {stats.downloaded}; "
        f"пропущено за назвою {stats.title_skips}; "
        f"за архівом {stats.archive_skips}; "
        f"недоступні {stats.unavailable}; "
        f"помилки {stats.failed}."
    )
    return 1 if stats.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
