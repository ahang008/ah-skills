#!/usr/bin/env python3
"""Download an authorized Douyin playback stream without platform watermark."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from typing import Optional
from urllib.parse import parse_qs, urlparse


USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 Mobile/15E148"
)
APP_USER_AGENT = "Aweme 350101 rv:350101 (iPhone; iOS 17.0; zh_CN) Cronet"
METADATA_URL = "https://aweme.snssdk.com/aweme/v1/feed/?aweme_id={video_id}&aid=1128"
DOUYIN_HOSTS = ("douyin.com", "iesdouyin.com")
DEFAULT_LIBRARY_NAME = "抖音无水印视频"
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


class DownloadError(RuntimeError):
    """Expected failure that can be reported safely to the user."""


def host_allowed(host: str, suffixes: tuple[str, ...]) -> bool:
    host = host.lower().rstrip(".")
    return any(host == suffix or host.endswith("." + suffix) for suffix in suffixes)


def extract_share_url(text: str) -> str:
    urls = re.findall(r"https?://[^\s<>\"']+", text)
    for candidate in urls:
        candidate = candidate.rstrip("),.;!?]}，。；！？】）")
        parsed = urlparse(candidate)
        if parsed.scheme == "https" and parsed.hostname and host_allowed(parsed.hostname, DOUYIN_HOSTS):
            return candidate
    raise DownloadError("没有识别到抖音官方 HTTPS 分享链接")


def extract_video_id(url: str, html: str = "") -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if query.get("modal_id") and query["modal_id"][0].isdigit():
        return query["modal_id"][0]
    match = re.search(r"/(?:video|note)/(\d{16,22})(?:/|$|\?)", url)
    if match:
        return match.group(1)
    if html:
        match = re.search(r"/(?:video|note)/(\d{16,22})", html)
        if match:
            return match.group(1)
    raise DownloadError("抖音链接已打开，但没有解析到作品 ID")


def proxy_candidates(explicit: Optional[str]) -> list[Optional[str]]:
    configured = explicit or os.environ.get("AH_DOUYIN_PROXY")
    return [configured, None] if configured else [None]


class CurlClient:
    def __init__(self, proxies: list[Optional[str]], timeout: int = 60):
        if not shutil.which("curl"):
            raise DownloadError("系统缺少 curl，无法访问抖音资源")
        self.proxies = proxies
        self.timeout = timeout
        self.selected_proxy: Optional[str] = None
        self.has_selected_proxy = False

    def _ordered_proxies(self) -> list[Optional[str]]:
        if not self.has_selected_proxy:
            return self.proxies
        return [self.selected_proxy] + [item for item in self.proxies if item != self.selected_proxy]

    def fetch(self, url: str, destination: Path, user_agent: str, timeout: Optional[int] = None) -> str:
        errors: list[str] = []
        for proxy in self._ordered_proxies():
            destination.unlink(missing_ok=True)
            command = [
                "curl",
                "--location",
                "--silent",
                "--show-error",
                "--fail-with-body",
                "--compressed",
                "--proto",
                "=https",
                "--proto-redir",
                "=https",
                "--connect-timeout",
                "8",
                "--max-time",
                str(timeout or self.timeout),
                "--retry",
                "2",
                "--retry-all-errors",
                "--user-agent",
                user_agent,
                "--output",
                str(destination),
                "--write-out",
                "%{url_effective}",
            ]
            if proxy:
                command.extend(["--proxy", proxy])
            command.append(url)
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            if result.returncode == 0 and destination.exists() and destination.stat().st_size > 0:
                self.selected_proxy = proxy
                self.has_selected_proxy = True
                return result.stdout.strip() or url
            label = proxy or "direct"
            errors.append(f"{label}: {result.stderr.strip()[-180:]}")
        raise DownloadError("网络请求失败；" + " | ".join(errors))


def parse_metadata(payload: dict, video_id: str) -> dict:
    aweme_list = payload.get("aweme_list") or []
    item = next((row for row in aweme_list if str(row.get("aweme_id")) == video_id), None)
    if not item:
        raise DownloadError("抖音接口没有返回对应作品，作品可能已删除、设为私密或触发风控")
    if item.get("images") and not item.get("video"):
        raise DownloadError("当前版本只下载视频作品，不处理图集")
    return item


def valid_media_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(host)
        return not (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
        )
    except ValueError:
        return True


def media_sources(item: dict) -> list[dict]:
    video = item.get("video") or {}
    sources: list[dict] = []

    def add_source(name: str, node: dict, score: int) -> None:
        if not isinstance(node, dict):
            return
        for url in node.get("url_list") or []:
            if isinstance(url, str) and valid_media_url(url):
                sources.append(
                    {
                        "name": name,
                        "url": url,
                        "score": score,
                        "data_size": int(node.get("data_size") or 0),
                        "width": int(node.get("width") or 0),
                        "height": int(node.get("height") or 0),
                    }
                )

    h264 = video.get("play_addr_h264") or {}
    add_source("play_addr_h264", h264, 3_000_000_000 + int(h264.get("data_size") or 0))

    play = video.get("play_addr") or {}
    add_source("play_addr", play, 2_000_000_000 + int(play.get("data_size") or 0))

    for index, rate in enumerate(video.get("bit_rate") or []):
        node = rate.get("play_addr") or {}
        url_key = str(node.get("url_key") or "").lower()
        if "h264" in url_key:
            score = 1_000_000_000 + int(rate.get("bit_rate") or 0) - index
            add_source("bit_rate_h264", node, score)

    unique: list[dict] = []
    seen: set[str] = set()
    for source in sorted(sources, key=lambda row: row["score"], reverse=True):
        if source["url"] not in seen:
            seen.add(source["url"])
            unique.append(source)
    if not unique:
        raise DownloadError("作品存在，但没有找到可用的 H.264 播放源")
    return unique


def safe_component(value: str, fallback: str, limit: int = 72) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = re.sub(r"版本过低.*$", "", value).strip()
    kept: list[str] = []
    for char in value:
        category = unicodedata.category(char)
        if char in "/\\:*?\"<>|" or category.startswith("C") or category == "So":
            continue
        kept.append(char)
    value = re.sub(r"\s+", " ", "".join(kept)).strip(" .-_#")
    value = value[:limit].rstrip(" .")
    if not value or value.upper() in WINDOWS_RESERVED_NAMES:
        return fallback
    return value


def safe_title(value: str, limit: int = 72) -> str:
    return safe_component(value, "未命名视频", limit)


def ensure_author_directory(library_dir: Path, author: str) -> Path:
    library_dir = library_dir.expanduser().resolve()
    library_dir.mkdir(parents=True, exist_ok=True)
    author_name = safe_component(author, "未知博主", limit=64)
    author_dir = library_dir / author_name
    if author_dir.is_symlink():
        raise DownloadError("博主目录是符号链接，为防止路径越界已停止下载")
    author_dir.mkdir(exist_ok=True)
    if not author_dir.is_dir() or author_dir.resolve().parent != library_dir:
        raise DownloadError("无法创建安全的博主分类目录")
    return author_dir


def unique_output_path(output_dir: Path, title: str, video_id: str) -> Path:
    base = f"抖音-{safe_title(title)}-{video_id}"
    candidate = output_dir / f"{base}.mp4"
    number = 2
    while candidate.exists():
        candidate = output_dir / f"{base}-{number}.mp4"
        number += 1
    return candidate


def verify_media(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        with path.open("rb") as handle:
            header = handle.read(32)
        if b"ftyp" not in header:
            raise DownloadError("文件已下载，但无法确认它是有效 MP4")
        return {
            "duration_seconds": None,
            "video_streams": None,
            "audio_streams": None,
            "verification": "mp4_header_only",
        }

    command = [
        ffprobe,
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise DownloadError("视频已下载，但 ffprobe 校验失败：" + result.stderr.strip()[-240:])
    data = json.loads(result.stdout)
    streams = data.get("streams") or []
    video_streams = [row for row in streams if row.get("codec_type") == "video"]
    audio_streams = [row for row in streams if row.get("codec_type") == "audio"]
    if not video_streams:
        raise DownloadError("下载结果不包含视频流")
    duration = data.get("format", {}).get("duration")
    return {
        "duration_seconds": round(float(duration), 3) if duration else None,
        "video_streams": len(video_streams),
        "audio_streams": len(audio_streams),
        "video_codec": video_streams[0].get("codec_name"),
        "audio_codec": audio_streams[0].get("codec_name") if audio_streams else None,
        "width": video_streams[0].get("width"),
        "height": video_streams[0].get("height"),
        "verification": "ffprobe",
    }


def default_output_dir() -> str:
    return os.environ.get(
        "AH_DOUYIN_OUTPUT_DIR",
        str(Path.home() / "Desktop" / DEFAULT_LIBRARY_NAME),
    )


def download(args: argparse.Namespace) -> dict:
    share_url = extract_share_url(" ".join(args.share_text))
    parsed = urlparse(share_url)
    if not parsed.hostname or not host_allowed(parsed.hostname, DOUYIN_HOSTS):
        raise DownloadError("仅支持抖音官方链接")

    library_dir = Path(args.output_dir).expanduser().resolve()
    client = CurlClient(proxy_candidates(args.proxy), timeout=args.timeout)

    with tempfile.TemporaryDirectory(prefix="ah-douyin-") as temp_name:
        temp_dir = Path(temp_name)
        share_page = temp_dir / "share.html"
        final_url = client.fetch(share_url, share_page, USER_AGENT)
        final_host = urlparse(final_url).hostname
        if not final_host or not host_allowed(final_host, DOUYIN_HOSTS):
            raise DownloadError("抖音分享链接跳转到了非官方域名，已停止处理")
        html = share_page.read_text(encoding="utf-8", errors="replace")
        video_id = extract_video_id(final_url, html)

        metadata_path = temp_dir / "metadata.json"
        client.fetch(METADATA_URL.format(video_id=video_id), metadata_path, APP_USER_AGENT)
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DownloadError("抖音元数据响应不是有效 JSON") from exc

        item = parse_metadata(payload, video_id)
        sources = media_sources(item)
        title = item.get("desc") or "未命名视频"
        author = (item.get("author") or {}).get("nickname") or ""

        if args.metadata_only:
            return {
                "status": "metadata_ok",
                "video_id": video_id,
                "title": title,
                "author": author,
                "source_kind": sources[0]["name"],
                "paid_api_used": False,
            }

        author_dir = ensure_author_directory(library_dir, author)
        destination = unique_output_path(author_dir, title, video_id)
        partial = destination.with_suffix(destination.suffix + ".part")
        errors: list[str] = []
        selected: Optional[dict] = None
        for source in sources:
            try:
                client.fetch(source["url"], partial, USER_AGENT, timeout=args.download_timeout)
                selected = source
                break
            except DownloadError as exc:
                partial.unlink(missing_ok=True)
                errors.append(str(exc))
        if not selected:
            raise DownloadError("所有无水印播放源均下载失败；" + " | ".join(errors[-2:]))

        if partial.stat().st_size < 1024:
            partial.unlink(missing_ok=True)
            raise DownloadError("下载文件异常小，已停止保存")
        os.replace(partial, destination)
        try:
            verification = verify_media(destination)
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    return {
        "status": "ok",
        "library_path": str(library_dir),
        "author_folder": str(author_dir),
        "path": str(destination),
        "filename": destination.name,
        "bytes": destination.stat().st_size,
        "video_id": video_id,
        "title": title,
        "author": author,
        "source_kind": selected["name"],
        "transcoded": False,
        "paid_api_used": False,
        **verification,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="解析抖音分享口令，将无抖音平台水印的播放源保存为 MP4。"
    )
    parser.add_argument("share_text", nargs="+", help="完整抖音口令或官方分享链接")
    parser.add_argument(
        "--output-dir",
        default=default_output_dir(),
        help="媒体库根目录；默认为桌面/抖音无水印视频",
    )
    parser.add_argument("--proxy", help="可选代理，例如 http://127.0.0.1:7890")
    parser.add_argument("--timeout", type=int, default=60, help="页面和接口超时秒数")
    parser.add_argument("--download-timeout", type=int, default=1800, help="视频下载超时秒数")
    parser.add_argument("--metadata-only", action="store_true", help="只验证解析，不下载视频")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = download(args)
    except DownloadError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"status": "error", "message": "用户中止下载"}, ensure_ascii=False), file=sys.stderr)
        return 130
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
