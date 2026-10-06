#!/usr/bin/env python3
"""Independent, local talking-head edit planner and FFmpeg renderer.

Only user-selected source intervals are cut. No speech/silence classifier exists.
This file uses Python's standard library and subprocess argument arrays.
"""

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path


FORMAT = "ah-talking-head-project"
REVISION = 1
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
EPSILON = 1e-7


class EditError(Exception):
    """An actionable invalid input or failed verification."""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EditError(f"{name} must be a finite number, not a boolean")
    try:
        parsed = float(value)
    except (OverflowError, ValueError) as exc:
        raise EditError(f"{name} must be finite") from exc
    if not math.isfinite(parsed):
        raise EditError(f"{name} must be finite")
    return parsed


def string(value, name, allow_empty=False):
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise EditError(f"{name} must be a nonempty string")
    return value


def object_value(value, name):
    if not isinstance(value, dict):
        raise EditError(f"{name} must be an object")
    return value


def keys(value, allowed, name):
    unknown = set(value) - set(allowed)
    if unknown:
        raise EditError(f"Unknown {name} fields: {', '.join(sorted(unknown))}")


def read_json(path):
    def invalid_constant(value):
        raise EditError(f"Nonfinite JSON number: {value}")

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise EditError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def check_tree(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise EditError("Nonfinite JSON number, including overflowing exponent")
        if isinstance(value, dict):
            for item in value.values():
                check_tree(item)
        elif isinstance(value, list):
            for item in value:
                check_tree(item)

    try:
        with Path(path).open("r", encoding="utf-8-sig") as handle:
            result = json.load(handle, parse_constant=invalid_constant,
                               object_pairs_hook=unique_pairs)
            check_tree(result)
            return result
    except (OSError, ValueError) as exc:
        raise EditError(f"Cannot read JSON {path}: {exc}") from exc


def write_json_new(path, data):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def digest(path):
    value = hashlib.sha256()
    try:
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                value.update(chunk)
    except OSError as exc:
        raise EditError(f"Cannot hash {path}: {exc}") from exc
    return value.hexdigest()


def input_file(path, name):
    result = Path(path).expanduser().resolve()
    if not result.is_file():
        raise EditError(f"{name} is not a local file: {result}")
    return result


def run(arguments, timeout=None):
    try:
        result = subprocess.run(arguments, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EditError(f"Cannot run {arguments[0]}: {exc}") from exc
    if result.returncode:
        raise EditError(f"{Path(arguments[0]).name} exited {result.returncode}: "
                        f"{result.stderr[-12000:]}")
    return result


def rate(value):
    try:
        result = float(Fraction(str(value)))
    except (ValueError, ZeroDivisionError):
        return 0.0
    return result if math.isfinite(result) else 0.0


def duration_value(value):
    try:
        parsed = float(value)
    except (ValueError, TypeError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def packet_video_duration(path, index, origin, fps, ffprobe):
    """Scan selected-video packet bounds when a container lacks stream duration.

    An audio tail or container duration must never authorize absent video.
    Packet rows are streamed rather than loading a long video's packet JSON.
    """
    arguments = [ffprobe, "-v", "error", "-select_streams", str(index), "-show_entries",
                 "packet=pts_time,duration_time", "-of", "csv=p=0", str(path)]
    try:
        process = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", errors="replace")
        last_end = None
        for row in process.stdout:
            fields = row.strip().split(",")
            try:
                pts = float(fields[0])
                span = float(fields[1]) if len(fields) > 1 and fields[1] != "N/A" else 1 / fps
            except (ValueError, IndexError):
                continue
            if math.isfinite(pts) and math.isfinite(span) and span >= 0:
                last_end = max(last_end or pts, pts + (span or 1 / fps))
        stderr = process.stderr.read()
        returncode = process.wait()
    except OSError as exc:
        raise EditError(f"Cannot inspect video packet duration: {exc}") from exc
    finally:
        if "process" in locals():
            process.stdout.close()
            process.stderr.close()
    if returncode or last_end is None or last_end <= origin:
        raise EditError(f"Cannot determine actual selected-video duration: {stderr[-12000:]}")
    return last_end - origin


def probe(path, ffprobe=FFPROBE, count_frames=False):
    arguments = [ffprobe, "-v", "error"]
    if count_frames:
        arguments.append("-count_frames")
    arguments += ["-show_streams", "-show_format", "-of", "json", str(path)]
    raw = json.loads(run(arguments).stdout)
    videos = [s for s in raw.get("streams", []) if s.get("codec_type") == "video"
              and not s.get("disposition", {}).get("attached_pic", 0)]
    audios = [s for s in raw.get("streams", []) if s.get("codec_type") == "audio"]
    if not videos or not audios:
        raise EditError("Input must contain a playable video stream and an audio stream")
    video, audio = videos[0], audios[0]
    fps = rate(video.get("avg_frame_rate")) or rate(video.get("r_frame_rate"))
    if not 1 <= fps <= 120:
        raise EditError("A video frame rate between 1 and 120 fps is required")
    origin = float(video.get("start_time") or 0)
    if not math.isfinite(origin):
        raise EditError("Video stream start time is nonfinite")
    video_duration = duration_value(video.get("duration"))
    container_duration = duration_value(raw.get("format", {}).get("duration"))
    if video_duration is None:
        video_duration = packet_video_duration(path, video["index"], origin, fps, ffprobe)
    width, height = int(video.get("width", 0)), int(video.get("height", 0))
    if width < 1 or height < 1:
        raise EditError("Cannot determine video dimensions")
    rotation = 0
    for side_data in video.get("side_data_list", []):
        if "rotation" in side_data:
            rotation = int(side_data["rotation"]) % 360
    if rotation in (90, 270):
        width, height = height, width
    return {
        "video_duration_seconds": video_duration,
        "container_duration_seconds": container_duration,
        "video_origin_seconds": origin,
        "frame_rate": fps,
        "display_width": width,
        "display_height": height,
        "video_stream_index": video["index"],
        "audio_stream_index": audio["index"],
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
        "audio_sample_rate": int(audio.get("sample_rate") or 0),
        "audio_channels": audio.get("channels"),
        "audio_duration_seconds": duration_value(audio.get("duration")),
        "video_frames_read": video.get("nb_read_frames"),
        "stream_count": len(raw.get("streams", [])),
    }


TIMESTAMP = re.compile(r"^(\d{2,}):([0-5]\d):([0-5]\d),(\d{3})$")


def parse_time(value):
    match = TIMESTAMP.fullmatch(value.strip())
    if not match:
        raise EditError(f"Invalid SRT timestamp: {value}")
    hours, minutes, seconds, millis = map(int, match.groups())
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def parse_srt(path, duration):
    try:
        content = Path(path).read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    except (OSError, UnicodeError) as exc:
        raise EditError(f"Cannot read UTF-8 SRT: {exc}") from exc
    cues = []
    previous_end = 0.0
    for position, block in enumerate(re.split(r"\n[ \t]*\n", content.strip()), 1):
        lines = block.splitlines()
        if len(lines) < 3 or lines[0].strip() != str(position):
            raise EditError("SRT requires consecutive cue numbers starting at 1 and cue text")
        times = lines[1].split(" --> ")
        if len(times) != 2:
            raise EditError(f"Cue {position} requires an SRT timestamp pair")
        start, end = map(parse_time, times)
        text = "\n".join(lines[2:]).strip()
        if not text or start < previous_end - EPSILON or end <= start or end > duration + EPSILON:
            raise EditError(f"Cue {position} has empty text, overlap, invalid duration or exceeds source")
        cues.append({"cue": position, "source_start": start, "source_end": end, "text": text})
        previous_end = end
    if not cues:
        raise EditError("SRT has no cues")
    return cues


def milliseconds(value):
    return int(math.floor(value * 1000 + 0.5))


def time_text(value):
    amount = milliseconds(value)
    hours, amount = divmod(amount, 3600000)
    minutes, amount = divmod(amount, 60000)
    seconds, millis = divmod(amount, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def srt_text(cues):
    return "".join(f"{index}\n{time_text(c['timeline_start'])} --> "
                   f"{time_text(c['timeline_end'])}\n{c['text']}\n\n"
                   for index, c in enumerate(cues, 1))


def compile_plan(clips, cues, media):
    if not isinstance(clips, list) or not clips:
        raise EditError("clips must be a nonempty array of explicit source selections")
    mapped, captions, previous_end, cursor = [], [], 0.0, 0.0
    normalized = []
    by_cue = {cue["cue"]: cue for cue in cues}
    for index, supplied in enumerate(clips, 1):
        supplied = object_value(supplied, f"clip {index}")
        keys(supplied, ["source_start", "source_end", "speed", "decision",
                        "protected_speech", "caption_edits"], f"clip {index}")
        start = number(supplied.get("source_start"), f"clip {index} source_start")
        end = number(supplied.get("source_end"), f"clip {index} source_end")
        speed = number(supplied.get("speed", 1), f"clip {index} speed")
        decision = string(supplied.get("decision"), f"clip {index} decision")
        if start < 0 or end <= start or start < previous_end - EPSILON:
            raise EditError(f"Clip {index} is negative, unordered, empty or overlaps its predecessor")
        if end > media["video_duration_seconds"] + EPSILON:
            raise EditError(f"Clip {index} exceeds actual video duration")
        if not 0.5 <= speed <= 2:
            raise EditError(f"Clip {index} speed must be between 0.5 and 2")
        target_duration = (end - start) / speed
        if end - start + EPSILON < 1 / media["frame_rate"] or target_duration + EPSILON < 1 / media["frame_rate"]:
            raise EditError(f"Clip {index} must retain at least one source and output video frame")
        protected = supplied.get("protected_speech", [])
        if not isinstance(protected, list):
            raise EditError(f"Clip {index} protected_speech must be an array")
        for item in protected:
            object_value(item, "protected speech")
            keys(item, ["start", "end", "note"], "protected speech")
            speech_start = number(item.get("start"), "protected speech start")
            speech_end = number(item.get("end"), "protected speech end")
            if speech_start < 0 or speech_end <= speech_start or speech_end > media["video_duration_seconds"] + EPSILON:
                raise EditError(f"Clip {index} protected speech bounds are invalid")
            if speech_start < start - EPSILON or speech_end > end + EPSILON:
                raise EditError(f"Clip {index} cuts protected speech or protected speech crosses a clip boundary")
            if "note" in item:
                string(item["note"], "protected speech note", allow_empty=True)
        edits = supplied.get("caption_edits", [])
        if not isinstance(edits, list):
            raise EditError(f"Clip {index} caption_edits must be an array")
        edit_by_cue = {}
        for item in edits:
            object_value(item, "caption edit")
            keys(item, ["cue", "source_start", "source_end", "text"], "caption edit")
            cue_id = item.get("cue")
            if isinstance(cue_id, bool) or not isinstance(cue_id, int) or cue_id not in by_cue or cue_id in edit_by_cue:
                raise EditError(f"Clip {index} caption edit cue must name one unique original cue")
            edit_start = number(item.get("source_start"), "caption edit source_start")
            edit_end = number(item.get("source_end"), "caption edit source_end")
            edit_text = string(item.get("text"), "caption edit text")
            if not edit_text.strip() or "\n\n" in edit_text or "\r" in edit_text:
                raise EditError("Caption replacement text cannot contain blank cue separators or carriage returns")
            original = by_cue[cue_id]
            if (edit_start < max(start, original["source_start"]) - EPSILON or
                    edit_end > min(end, original["source_end"]) + EPSILON or edit_end <= edit_start):
                raise EditError(f"Clip {index} caption edit bounds must fit the retained original cue fragment")
            edit_by_cue[cue_id] = {"source_start": edit_start, "source_end": edit_end, "text": edit_text}
        for cue in cues:
            retained_start = max(start, cue["source_start"])
            retained_end = min(end, cue["source_end"])
            if retained_end <= retained_start + EPSILON:
                continue
            edit = edit_by_cue.get(cue["cue"])
            partial = retained_start > cue["source_start"] + EPSILON or retained_end < cue["source_end"] - EPSILON
            if partial and edit is None:
                raise EditError(f"Clip {index} retains only part of cue {cue['cue']}; explicit replacement text and source bounds are required")
            selected = edit or cue
            captions.append({
                "original_cue": cue["cue"], "clip": index,
                "source_start": selected["source_start"], "source_end": selected["source_end"],
                "timeline_start": cursor + (selected["source_start"] - start) / speed,
                "timeline_end": cursor + (selected["source_end"] - start) / speed,
                "text": selected["text"], "explicit_replacement": edit is not None,
            })
        mapped.append({"clip": index, "source_start": start, "source_end": end,
                       "speed": speed, "timeline_start": cursor,
                       "timeline_end": cursor + target_duration})
        normalized.append({"source_start": start, "source_end": end, "speed": speed,
                           "decision": decision, "protected_speech": protected, "caption_edits": edits})
        cursor += target_duration
        previous_end = end
    previous_ms = 0
    for cue in captions:
        start_ms, end_ms = milliseconds(cue["timeline_start"]), milliseconds(cue["timeline_end"])
        if start_ms < previous_ms or end_ms <= start_ms or end_ms > milliseconds(cursor):
            raise EditError("Mapped SRT has overlap, zero length or out-of-timeline timestamps after millisecond rounding")
        previous_ms = end_ms
    return normalized, {"duration_seconds": cursor, "clips": mapped, "captions": captions}


def honest_limits():
    return {
        "human_listening": "unverified",
        "caption_wording_and_audio_alignment": "unverified",
        "native_jianying_project": "unsupported_and_unverified",
        "semantic_cut_quality": "requires_human_review",
        "protected_speech_scope": "only_explicitly_marked_intervals_are_checked",
    }


def check_hash_entry(entry, name):
    object_value(entry, name)
    file = input_file(string(entry.get("file"), f"{name} file"), name)
    sha = string(entry.get("sha256"), f"{name} sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", sha) or digest(file) != sha:
        raise EditError(f"{name} changed: SHA-256 does not match the editable project")
    return file


def load_project(path, ffprobe=FFPROBE):
    project_path = input_file(path, "project")
    loaded_project_hash = digest(project_path)
    project = object_value(read_json(project_path), "project")
    keys(project, ["format", "format_revision", "created_utc", "source", "caption_source",
                   "clips", "creation_mapping", "verification_limits"], "project")
    if project.get("format") != FORMAT or isinstance(project.get("format_revision"), bool) or project.get("format_revision") != REVISION:
        raise EditError("Unsupported editable project format or revision")
    source = check_hash_entry(project.get("source"), "source")
    if source == project_path:
        raise EditError("Project and source paths alias each other")
    media = probe(source, ffprobe)
    caption_source = project.get("caption_source")
    cues = []
    if caption_source is not None:
        srt = check_hash_entry(caption_source, "caption source")
        if srt in (source, project_path):
            raise EditError("Caption input, source and project must be different files")
        cues = parse_srt(srt, media["video_duration_seconds"])
        supplied_cues = caption_source.get("cues")
        if not isinstance(supplied_cues, list):
            raise EditError("Original caption cues must be an array")
        for item in supplied_cues:
            object_value(item, "original caption cue")
            if isinstance(item.get("cue"), bool) or not isinstance(item.get("cue"), int):
                raise EditError("Original caption cue number must be an integer, not a boolean")
            number(item.get("source_start"), "original caption source_start")
            number(item.get("source_end"), "original caption source_end")
        if caption_source.get("cues") != cues:
            raise EditError("Original caption cues in project differ from the hashed SRT; use caption_edits for text changes")
    clips, mapping = compile_plan(project.get("clips"), cues, media)
    if digest(source) != project["source"]["sha256"]:
        raise EditError("Source changed during validation")
    if digest(project_path) != loaded_project_hash:
        raise EditError("Editable project changed during validation")
    if caption_source is not None:
        check_hash_entry(caption_source, "caption source")
    return project_path, project, source, media, clips, mapping, loaded_project_hash


def create(args):
    source = input_file(args.source, "source")
    plan_path = input_file(args.plan, "plan")
    target = Path(args.project).expanduser().resolve()
    srt = input_file(args.srt, "caption source") if args.srt else None
    if target.exists() or target in (source, plan_path, srt):
        raise EditError("Project must be a new path and cannot alias an input")
    if srt in (source, plan_path):
        raise EditError("SRT, plan and source must be different files")
    source_hash = digest(source)
    media = probe(source, args.ffprobe)
    cues = parse_srt(srt, media["video_duration_seconds"]) if srt else []
    caption_hash = digest(srt) if srt else None
    plan = object_value(read_json(plan_path), "plan")
    keys(plan, ["clips"], "plan")
    clips, mapping = compile_plan(plan.get("clips"), cues, media)
    if digest(source) != source_hash or (srt and digest(srt) != caption_hash):
        raise EditError("An input changed during project creation")
    project = {
        "format": FORMAT, "format_revision": REVISION, "created_utc": utc_now(),
        "source": {"file": str(source), "sha256": source_hash, "media_at_creation": media},
        "caption_source": {"file": str(srt), "sha256": caption_hash, "cues": cues} if srt else None,
        "clips": clips, "creation_mapping": mapping, "verification_limits": honest_limits(),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    write_json_new(target, project)
    return {"status": "created", "project": str(target), "mapping": mapping,
            "verification_limits": honest_limits()}


def inspect(args):
    path, project, source, media, clips, mapping, project_hash = load_project(args.project, args.ffprobe)
    duration = mapping["duration_seconds"]
    covered = sum(c["timeline_end"] - c["timeline_start"] for c in mapping["captions"])
    return {"status": "valid", "project": str(path), "source": str(source), "source_media": media,
            "source_hash_matches": True, "mapping": mapping,
            "creation_mapping_matches_current_clips": project.get("creation_mapping") == mapping,
            "caption_timeline_fraction": covered / duration if mapping["captions"] else None,
            "verification_limits": honest_limits()}


def output_checks(video, expected, source_media, clip_count, ffmpeg=FFMPEG, ffprobe=FFPROBE):
    media = probe(video, ffprobe, count_frames=True)
    frame_seconds = 1 / source_media["frame_rate"]
    aac_seconds = 1024 / 48000
    # Video quantization happens once on the final timeline. Audio sample
    # rounding can add at most one sample per selected clip, plus AAC packets.
    tolerance = 2 * frame_seconds + 2 * aac_seconds + clip_count / 48000
    audio_tolerance = 2 * aac_seconds + clip_count / 48000
    expected_width = (source_media["display_width"] + 1) // 2 * 2
    expected_height = (source_media["display_height"] + 1) // 2 * 2
    checks = {
        "exactly_one_video_and_audio": media["stream_count"] == 2,
        "expected_dimensions": media["display_width"] == expected_width and media["display_height"] == expected_height,
        "h264_and_aac": media["video_codec"] == "h264" and media["audio_codec"] == "aac",
        "audio_48000_hz": media["audio_sample_rate"] == 48000,
        "frame_rate_matches": abs(media["frame_rate"] - source_media["frame_rate"]) < 0.02,
        "video_duration_within_tolerance": abs(media["video_duration_seconds"] - expected) <= tolerance,
        "container_duration_within_tolerance": media["container_duration_seconds"] is not None and abs(media["container_duration_seconds"] - expected) <= tolerance,
        "audio_duration_within_tolerance": media["audio_duration_seconds"] is not None and abs(media["audio_duration_seconds"] - expected) <= audio_tolerance,
        "frames_present": str(media["video_frames_read"]).isdigit() and int(media["video_frames_read"]) > 0,
    }
    decode_error = None
    try:
        run([ffmpeg, "-hide_banner", "-v", "error", "-xerror", "-i", str(video),
             "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"])
        checks["full_decode"] = True
    except EditError as exc:
        checks["full_decode"] = False
        decode_error = str(exc)
    return {"passed": all(checks.values()), "checks": checks, "actual_media": media,
            "expected_duration_seconds": expected,
            "video_and_container_tolerance_seconds": tolerance,
            "audio_tolerance_seconds": audio_tolerance,
            "frame_tolerance_basis_seconds": frame_seconds,
            "aac_packet_basis_seconds": aac_seconds, "decode_error": decode_error}


def filter_graph(clips, media):
    video_index, audio_index = media["video_stream_index"], media["audio_stream_index"]
    fps, origin = media["frame_rate"], media["video_origin_seconds"]
    filters = []
    # One split establishes a common normalized source clock before every clip.
    video_labels = "".join(f"[sv{i}]" for i in range(len(clips)))
    audio_labels = "".join(f"[sa{i}]" for i in range(len(clips)))
    filters.append(f"[0:{video_index}]setpts=PTS-({origin:.12g})/TB,split={len(clips)}{video_labels}")
    filters.append(f"[0:{audio_index}]asetpts=PTS-({origin:.12g})/TB,aresample=48000:async=1:first_pts=0,asplit={len(clips)}{audio_labels}")
    for index, clip in enumerate(clips):
        start, end, speed = clip["source_start"], clip["source_end"], clip["speed"]
        target = (end - start) / speed
        full_frames = max(1, int(math.floor(target * fps + EPSILON)))
        filters.append(f"[sv{index}]trim=start={start:.12g}:end={end:.12g},"
                       f"setpts=(PTS-STARTPTS)/{speed:.12g},fps={fps:.12g},"
                       f"tpad=stop_mode=clone:stop_duration={target:.12g},trim=end_frame={full_frames},"
                       f"pad=ceil(iw/2)*2:ceil(ih/2)*2,format=yuv420p[v{index}]")
        filters.append(f"[sa{index}]apad,atrim=start={start:.12g}:end={end:.12g},asetpts=PTS-STARTPTS,"
                       f"atempo={speed:.12g},apad,atrim=duration={target:.12g}[a{index}]")
    pairs = "".join(f"[v{i}][a{i}]" for i in range(len(clips)))
    total = sum((c["source_end"] - c["source_start"]) / c["speed"] for c in clips)
    # Never let a ceil-rounded video segment lengthen concat's exact audio
    # clock. One final fps fills the subframe gaps without cumulative drift.
    filters.append(f"{pairs}concat=n={len(clips)}:v=1:a=1[joinedv][outa]")
    filters.append(f"[joinedv]tpad=stop_mode=clone:stop_duration={2 / fps:.12g},"
                   f"fps={fps:.12g},trim=duration={total:.12g}[outv]")
    return ";".join(filters)


def render(args):
    path, project, source, media, clips, mapping, project_hash = load_project(args.project, args.ffprobe)
    output_dir = Path(args.output_dir).expanduser().resolve()
    inputs = [path, source]
    if project.get("caption_source"):
        inputs.append(Path(project["caption_source"]["file"]).resolve())
    if output_dir.exists() or any(output_dir == value or output_dir in value.parents for value in inputs):
        raise EditError("Render directory must be new and cannot contain or alias an input")
    # Build/check the command and all plans before creating any render directory.
    video = output_dir / "edited.mp4"
    subtitles = output_dir / "captions.srt"
    graph = filter_graph(clips, media)
    arguments = [args.ffmpeg, "-hide_banner", "-v", "warning", "-xerror", "-n", "-i", str(source),
                 "-filter_complex", graph, "-map", "[outv]", "-map", "[outa]",
                 "-map_metadata", "-1", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                 "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(video)]
    report = {"report_format": "ah-talking-head-render-report", "report_revision": 1,
              "status": "running", "started_utc": utc_now(), "project_file": str(path),
              "project_sha256": project_hash, "source_file": str(source),
              "source_sha256": project["source"]["sha256"], "source_media": media,
              "mapping": mapping, "verification_limits": honest_limits(),
              "timeline_quantization": {"video_boundary_seconds": 1 / media["frame_rate"],
                                        "audio_sample_seconds": 1 / 48000,
                                        "audio_max_sample_rounding_seconds": len(clips) / 48000},
              "caption_timeline_fraction": sum(c["timeline_end"] - c["timeline_start"] for c in mapping["captions"]) / mapping["duration_seconds"] if mapping["captions"] else None,
              "dependencies": {"python": sys.version.split()[0], "ffmpeg": args.ffmpeg, "ffprobe": args.ffprobe,
                               "video_encoder": "libx264", "audio_encoder": "aac"},
              "render_arguments": arguments, "artifacts": {}}
    if digest(source) != project["source"]["sha256"] or digest(path) != project_hash:
        raise EditError("Source or editable project changed before rendering")
    if project.get("caption_source"):
        check_hash_entry(project["caption_source"], "caption source")
    output_dir.mkdir(parents=True, exist_ok=False)
    try:
        report["dependencies"]["ffmpeg_version"] = run([args.ffmpeg, "-version"]).stdout.splitlines()[0]
        report["dependencies"]["ffprobe_version"] = run([args.ffprobe, "-version"]).stdout.splitlines()[0]
        result = run(arguments)
        report["render_log_tail"] = result.stderr[-12000:]
        if digest(source) != project["source"]["sha256"] or digest(path) != project_hash:
            raise EditError("Source or editable project changed during rendering")
        if project.get("caption_source"):
            check_hash_entry(project["caption_source"], "caption source")
        with subtitles.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(srt_text(mapping["captions"]))
        report["output_verification"] = output_checks(video, mapping["duration_seconds"], media,
                                                      len(clips), args.ffmpeg, args.ffprobe)
        report["artifacts"] = {"video": {"file": "edited.mp4", "sha256": digest(video)},
                               "captions": {"file": "captions.srt", "sha256": digest(subtitles)}}
        if not report["output_verification"]["passed"]:
            raise EditError("Rendered output failed stream, duration or full decode verification")
        report["status"] = "completed"
    except (EditError, OSError, ValueError, KeyboardInterrupt) as exc:
        report["status"] = "failed"
        report["error"] = str(exc) or "Render interrupted"
    finally:
        report["finished_utc"] = utc_now()
        write_json_new(output_dir / "validation-report.json", report)
    if report["status"] != "completed":
        raise EditError(f"Render failed; preserved validation-report.json in {output_dir}: {report.get('error')}")
    return {"status": "completed", "output_dir": str(output_dir), "report": report}


def audit(args):
    output_dir = Path(args.output_dir).expanduser().resolve()
    report = object_value(read_json(output_dir / "validation-report.json"), "render report")
    if report.get("report_format") != "ah-talking-head-render-report" or report.get("status") != "completed":
        raise EditError("Audit requires a completed independent render report")
    mapping = object_value(report.get("mapping"), "render mapping")
    expected = number(mapping.get("duration_seconds"), "expected duration")
    if expected <= 0 or not isinstance(mapping.get("clips"), list) or not mapping["clips"]:
        raise EditError("Invalid render timeline")
    artifacts = report.get("artifacts", {})
    for kind, fixed_name in (("video", "edited.mp4"), ("captions", "captions.srt")):
        entry = artifacts.get(kind, {})
        if entry.get("file") != fixed_name:
            raise EditError("Report artifact paths must use the fixed local filenames")
        file = input_file(output_dir / fixed_name, kind)
        if file.parent != output_dir or digest(file) != entry.get("sha256"):
            raise EditError(f"Rendered {kind} changed or path leaves output directory")
    captions_file = output_dir / "captions.srt"
    content = captions_file.read_text(encoding="utf-8")
    if content != srt_text(mapping.get("captions", [])):
        raise EditError("Rendered captions differ from the report's timeline mapping")
    if content.strip():
        parse_srt(captions_file, expected + 0.0005)
    verification = output_checks(output_dir / "edited.mp4", expected, report["source_media"],
                                 len(mapping["clips"]), args.ffmpeg, args.ffprobe)
    return {"status": "passed" if verification["passed"] else "failed",
            "artifact_hashes_match": True, "output_verification": verification,
            "verification_limits": honest_limits()}


def doctor(args):
    versions = {}
    for name, executable in (("ffmpeg", args.ffmpeg), ("ffprobe", args.ffprobe)):
        versions[name] = run([executable, "-version"]).stdout.splitlines()[0]
    encoders = run([args.ffmpeg, "-hide_banner", "-encoders"]).stdout
    filters = run([args.ffmpeg, "-hide_banner", "-filters"]).stdout
    needed_filters = ["trim", "atrim", "setpts", "asetpts", "split", "asplit", "concat",
                      "atempo", "aresample", "apad", "fps", "tpad", "pad", "format"]
    checks = {"libx264": bool(re.search(r"\blibx264\b", encoders)),
              "aac": bool(re.search(r"\baac\b", encoders))}
    checks.update({name: bool(re.search(rf"\b{re.escape(name)}\b", filters)) for name in needed_filters})
    return {"status": "ready" if all(checks.values()) else "unavailable", "versions": versions,
            "python": sys.version.split()[0], "checks": checks,
            "verification_limits": honest_limits()}


def parser():
    result = argparse.ArgumentParser(description="Independent local interval-based talking-head editor. No automatic speech deletion.")
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("doctor", "create", "inspect", "validate", "render", "audit"):
        command = commands.add_parser(name)
        command.add_argument("--ffmpeg", default=FFMPEG, help="FFmpeg executable (default: PATH discovery, then Homebrew fallback)")
        command.add_argument("--ffprobe", default=FFPROBE, help="ffprobe executable")
        if name == "create":
            command.add_argument("--source", required=True, help="Authorized local audiovisual source")
            command.add_argument("--plan", required=True, help="JSON with explicit source selections and speech protections")
            command.add_argument("--project", required=True, help="New editable project JSON path")
            command.add_argument("--srt", help="Optional UTF-8 source SRT")
        elif name in ("inspect", "validate", "render"):
            command.add_argument("--project", required=True, help="Editable project JSON")
        if name in ("render", "audit"):
            command.add_argument("--output-dir", required=True, help="New directory for render; existing render directory for audit")
        command.set_defaults(handler={"doctor": doctor, "create": create, "inspect": inspect,
                                      "validate": inspect, "render": render, "audit": audit}[name])
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = args.handler(args)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if result["status"] not in ("failed", "unavailable") else 1
    except (EditError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
