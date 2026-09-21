# Provenance

## Release scope

`ah-douyin-clean-downloader` was created for a local Codex workflow in which a
user supplies an authorized Douyin share command or official link and receives
the platform-provided playback file on their Desktop.

The first source-available release was prepared on 2026-09-20. The implementation
in `scripts/download_douyin.py`, the Skill instructions, tests, and release
documentation were written for this project. No upstream source files are
vendored in this repository.

## Public projects consulted

The following public repositories were consulted for product behavior,
terminology, and maintenance context. They are references, not bundled runtime
dependencies.

| Repository | Reference inspected on 2026-09-20 | License shown upstream | Use in this project |
|---|---|---|---|
| `Evil0ctal/Douyin_TikTok_Download_API` | `9fa3e5406694c80ec0a97399f410948f130d0f9e` | Apache-2.0 | Compared self-hosted parsing, clean-stream selection, testing, and maintenance boundaries |
| `ucmao/media-parser` | `0b751170a07d086cb1cf74d5b7720b29b56db419` | MIT | Compared local parsing and multi-platform service boundaries |
| `yangbuyiya/yby6-video-parser-skill` | `b3eb3d4525678390bde4d9a3fd7823b3bad3f5bb` | MIT | Compared Agent Skill packaging and attribution style |
| `yzfly/douyin-mcp-server` | `b0bb8b1fbe4f514bf28099b1471928ebb3716ad2` | Apache-2.0 | Compared MCP and command-line product forms; MCP was excluded from the first release |

## Independent implementation decisions

- Accept only official `douyin.com` and `iesdouyin.com` links.
- Follow the share redirect and extract an item identifier.
- Read a Douyin-family metadata response and select H.264 playback sources.
- Do not select `download_addr` or any source explicitly marked as a watermarked
  download address.
- Download without transcoding and verify the resulting file locally.
- Avoid paid parsing APIs, account login, cookies, signature services, and
  visual inpainting.

These statements describe repository evidence and engineering intent. They are
not an independent legal opinion about any platform interface or third-party
right.

## Excluded material

This repository does not contain:

- code or documentation copied from Yichen skills;
- source code from the four referenced repositories;
- real user videos, private share links, cookies, tokens, or account data;
- Douyin application binaries, signing implementations, or access-control
  bypasses;
- an AI model for removing hard-coded logos, subtitles, or overlays.
