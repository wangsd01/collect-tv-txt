"""Stream quality checking via ffmpeg subprocesses.

Replaces hand-rolled HTTP-segment-timing heuristics (separate code paths for
HLS vs. UDP/RTP-over-HTTP) with a short real decode of the stream: ffmpeg
either decodes cleanly -- actual proof the stream is playable -- or fails
with a classifiable error. This is the same approach used by iptv-checker
(the checker behind the iptv-org project), and it works identically across
HLS, UDP, RTP, and RTSP without protocol-specific parsing.
"""
import re
import subprocess
import time
from urllib.parse import urlparse

OK = "OK"
TIMEOUT = "TIMEOUT"
UNREACHABLE = "UNREACHABLE"
DNS_ERROR = "DNS_ERROR"
FORBIDDEN = "FORBIDDEN"
NOT_FOUND = "NOT_FOUND"
CLIENT_ERROR = "CLIENT_ERROR"
SERVER_ERROR = "SERVER_ERROR"
DECODE_ERROR = "DECODE_ERROR"
UNKNOWN_ERROR = "UNKNOWN_ERROR"
BLACK_SCREEN = "BLACK_SCREEN"
FROZEN_VIDEO = "FROZEN_VIDEO"
NO_VIDEO_TRACK = "NO_VIDEO_TRACK"

# Errors worth a single retry -- likely a transient network blip rather than
# a permanently dead or blocked source.
_RETRYABLE_ERRORS = {TIMEOUT, UNREACHABLE, SERVER_ERROR, DECODE_ERROR, UNKNOWN_ERROR}

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)


def _classify_ffmpeg_error(stderr_text):
    text = stderr_text or ""
    match = re.search(r"Server returned (\d{3})", text)
    if match:
        code = int(match.group(1))
        if code == 403:
            return FORBIDDEN
        if code == 404:
            return NOT_FOUND
        if 500 <= code < 600:
            return SERVER_ERROR
        if 400 <= code < 500:
            return CLIENT_ERROR
    if "Connection timed out" in text or "Operation timed out" in text:
        return TIMEOUT
    if "Connection refused" in text:
        return UNREACHABLE
    if "Name or service not known" in text or "nodename nor servname" in text:
        return DNS_ERROR
    if "Invalid data found" in text:
        return DECODE_ERROR
    return UNKNOWN_ERROR


def _decode_attempt(url, decode_seconds, hard_timeout, user_agent):
    cmd = [
        "ffmpeg", "-v", "error", "-xerror", "-nostdin",
        "-user_agent", user_agent,
        "-t", str(decode_seconds),
        "-i", url,
        "-f", "null", "-",
    ]
    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=hard_timeout,
        )
    except subprocess.TimeoutExpired:
        return False, TIMEOUT, time.monotonic() - start
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found on PATH -- install ffmpeg to run stream checks")

    elapsed = time.monotonic() - start
    if result.returncode != 0:
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        return False, _classify_ffmpeg_error(stderr_text), elapsed
    return True, OK, elapsed


def check_stream_tracks(url, connect_grace=5, user_agent=_DEFAULT_USER_AGENT):
    """Inspect stream types and require a video track; audio is optional."""
    cmd = ["ffprobe", "-v", "error"]
    if urlparse(url).scheme in {"http", "https"}:
        cmd.extend(("-user_agent", user_agent))
    cmd.extend((
        "-show_entries", "stream=codec_type", "-of", "csv=p=0", url,
    ))
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=connect_grace + 5,
        )
    except subprocess.TimeoutExpired:
        return False, False, TIMEOUT
    except FileNotFoundError:
        raise RuntimeError("ffprobe not found on PATH -- install ffmpeg to inspect stream tracks")

    if result.returncode != 0:
        error = _classify_ffmpeg_error(result.stderr.decode("utf-8", errors="replace"))
        return False, False, error
    track_types = set(result.stdout.decode("utf-8", errors="replace").splitlines())
    has_video, has_audio = "video" in track_types, "audio" in track_types
    return has_video, has_audio, OK if has_video else NO_VIDEO_TRACK


def check_stream_quality(url, decode_seconds=5, connect_grace=5, retries=1,
                          retry_delay=1.0, max_overrun_ratio=1.6,
                          user_agent=_DEFAULT_USER_AGENT):
    """Decode `decode_seconds` of `url` with ffmpeg to verify it's actually playable.

    A stream that stalls waiting for network data takes noticeably longer than
    `decode_seconds` of wall-clock time to decode `decode_seconds` of content --
    that overrun is the real signature of a choppy/congested source, as opposed
    to guessing from segment download byte counts.

    Returns (is_choppy: bool, speed_score: float, error_code: str).
    speed_score is decode_seconds / elapsed_time: >1 means faster than
    real-time (fine), <1 means ffmpeg had to wait on the network.
    """
    hard_timeout = decode_seconds + connect_grace
    attempts = retries + 1
    last_error = UNKNOWN_ERROR
    for attempt in range(attempts):
        ok, error_code, elapsed = _decode_attempt(url, decode_seconds, hard_timeout, user_agent)
        if ok:
            overrun_ratio = elapsed / decode_seconds if decode_seconds else 1.0
            is_choppy = overrun_ratio > max_overrun_ratio
            speed_score = decode_seconds / elapsed if elapsed > 0 else float("inf")
            return is_choppy, speed_score, OK
        last_error = error_code
        if error_code not in _RETRYABLE_ERRORS or attempt == attempts - 1:
            break
        time.sleep(retry_delay)
    return True, 0.0, last_error


def check_stream_content(url, sample_seconds=8, connect_grace=4,
                         black_ratio=0.75, freeze_seconds=6,
                         user_agent=_DEFAULT_USER_AGENT):
    """Reject streams whose sampled content is mostly black or frozen.

    This catches decodable error slates and dead video tracks, which the
    connectivity check intentionally considers playable.  It does not try to
    classify normal broadcast advertisements or identify the channel logo.

    Returns ``(acceptable, reason)``.  A checker/network failure is returned as
    an ordinary stream error so callers can quarantine the candidate.
    """
    if sample_seconds <= 0:
        return True, OK

    minimum_black = max(1.0, sample_seconds * black_ratio)
    effective_freeze = min(max(1.0, freeze_seconds), sample_seconds * 0.75)
    filters = (
        f"blackdetect=d={minimum_black:.3f}:pix_th=0.10,"
        f"freezedetect=n=-50dB:d={effective_freeze:.3f}"
    )
    cmd = ["ffmpeg", "-hide_banner", "-v", "info", "-nostdin"]
    if urlparse(url).scheme in {"http", "https"}:
        cmd.extend(("-user_agent", user_agent))
    cmd.extend((
        "-t", str(sample_seconds), "-i", url,
        "-an", "-vf", filters, "-f", "null", "-",
    ))
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=sample_seconds + connect_grace,
        )
    except subprocess.TimeoutExpired:
        return False, TIMEOUT
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found on PATH -- install ffmpeg to run stream checks")

    stderr_text = result.stderr.decode("utf-8", errors="replace")
    if result.returncode != 0:
        return False, _classify_ffmpeg_error(stderr_text)

    black_durations = [
        float(value)
        for value in re.findall(r"black_duration:([0-9]+(?:\.[0-9]+)?)", stderr_text)
    ]
    if any(duration >= minimum_black for duration in black_durations):
        return False, BLACK_SCREEN

    # freezedetect only emits freeze_start after the configured duration has
    # already elapsed, so one marker is sufficient to reject the sample.
    freeze_starts = [
        float(value)
        for value in re.findall(r"freeze_start:\s*([0-9]+(?:\.[0-9]+)?)", stderr_text)
    ]
    if freeze_starts:
        return False, FROZEN_VIDEO
    return True, OK


def check_stream_frame(url, connect_grace=5, user_agent=_DEFAULT_USER_AGENT):
    """Return whether at least one video frame can be decoded from a stream."""
    cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-nostdin"]
    if urlparse(url).scheme in {"http", "https"}:
        cmd.extend(("-user_agent", user_agent))
    cmd.extend(("-i", url, "-frames:v", "1", "-f", "null", "-"))
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=connect_grace + 5,
        )
    except subprocess.TimeoutExpired:
        return False, TIMEOUT
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found on PATH -- install ffmpeg to run stream checks")
    if result.returncode == 0:
        return True, OK
    return False, _classify_ffmpeg_error(result.stderr.decode("utf-8", errors="replace"))
