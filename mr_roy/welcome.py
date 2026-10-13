"""What `roy` on its own prints: who he is, what he does, what is running.

The portrait is pixel art drawn with half blocks: each character cell is two
pixels, the top one in the foreground colour and the bottom in the background,
so a 24x28 grid prints as 24x14 characters.
"""

from __future__ import annotations

import os
import sys

ART = [
    "........OOOOOOOO........",
    "......OOHHHHHHHHOO......",
    ".....OHHHHhHHHhHHHO.....",
    "....OHHHHhHHHhHHHHHO....",
    "....OHHHhHHHhHHHHHHO....",
    "...OXHHHSSSSSSSSHHHXO...",
    "...OXHSSSSSSSSSSSSHXO...",
    "...OXSSOOOSSSSOOOSSXO...",
    "..OsSSSSSSSSSSSSSSSSsO..",
    "..OsSSSOSSSSSSSSOSSSsO..",
    "..OsSSOSOSSSSSSOSOSSsO..",
    "...OSSllSSSSsSSSllSSO...",
    "...OSSSSSSSssSSSSSSSO...",
    "...OSSSOSSSSSSSSOSSSO...",
    "...OSSSSOTTTTTTOSSSSO...",
    "....OSSSSOOOOOOSSSSO....",
    ".....OSSSSSSSSSSSSO.....",
    "......OOSSSSSSSSOO......",
    ".........OsSSsO.........",
    ".....OOKKKOssOKKKOO.....",
    "..OkKKKKKKKkkKKKKKKKkO..",
    ".OkKKKKKKKKPkKKKKKKKKkO.",
    "OkKKkKKKKKKkkKKKKKKkKKkO",
    "OkKKkKKKKKKkkKKKKKKkKKkO",
    "OkKKkKKKKKKPkKKKKKKkKKkO",
    "OkKKkKKKKKKkkKKKKKKkKKkO",
    "OkKKkKKKKKKkkKKKKKKkKKkO",
    "OkKKkKKKKKKPkKKKKKKkKKkO",
]
# The approved portrait (report.PORTRAIT): swept-back hair going silver at the
# temples, heavy brows, smiling eyes, a broad smile, a light purple kurta.
PALETTE = {
    "O": (31, 26, 23), "H": (42, 36, 32), "h": (84, 76, 70), "X": (189, 182, 174),
    "S": (176, 116, 80), "s": (142, 90, 58), "l": (201, 140, 100), "T": (244, 238, 226),
    "K": (201, 182, 228), "k": (169, 148, 204), "P": (91, 69, 128),
}


def portrait_png(size: int, scale: int) -> bytes:
    """The portrait as a square PNG on cream, shoulders on the bottom edge.
    The app icon (1024, 32) and the report's tab icon (64, 2). Stdlib only:
    nearest-neighbour blocks need no imaging library."""
    import struct
    import zlib

    background = (240, 233, 220)
    left, top = (size - len(ART[0]) * scale) // 2, size - len(ART) * scale
    rows = []
    for y in range(size):
        art = ART[(y - top) // scale] if y >= top else ""
        row = bytearray(b"\0")
        for x in range(size):
            cell = art[(x - left) // scale] if art and 0 <= x - left < len(art) * scale else "."
            row += bytes(PALETTE.get(cell, background))
        rows.append(bytes(row))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def _colour() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def portrait() -> list[str]:
    lines = []
    for top, bottom in zip(ART[0::2], ART[1::2]):
        line = ""
        for a, b in zip(top, bottom):
            if a == "." and b == ".":
                line += " "
            elif b == ".":
                line += "\033[38;2;{};{};{}m▀\033[0m".format(*PALETTE[a])
            elif a == ".":
                line += "\033[38;2;{};{};{}m▄\033[0m".format(*PALETTE[b])
            else:
                line += "\033[38;2;{};{};{};48;2;{};{};{}m▀\033[0m".format(*PALETTE[a], *PALETTE[b])
        lines.append(line)
    return lines


def _status() -> list[tuple[bool, str, str]]:
    """(ok, what, detail). Each check is a local lookup; no network, no mic."""
    from . import config, grammar, schedule, wispr

    rows = []
    try:
        running = schedule.service_state("com.mrroy.listen").get("state") == "running"
    except Exception:  # noqa: BLE001
        running = False
    rows.append((bool(running), "background", "running" if running else "not set up: run roy setup"))
    try:
        latest = wispr.health().get("latest") if wispr.available() else None
    except Exception:  # noqa: BLE001
        latest = None
    rows.append((bool(latest), "Wispr Flow", f"last dictation {latest[:10]}" if latest else "not found"))
    rows.append((grammar.llm_available(), "grammar",
                 f"checked by {grammar.llm_name()}" if grammar.llm_available() else "off (MR_ROY_NO_LLM)" if os.environ.get("MR_ROY_NO_LLM")
                 else "no Claude Code or Codex CLI"))
    pages = sorted(config.REPORTS_DIR.glob("????-??-??.html"))
    rows.append((bool(pages), "lessons", f"latest {pages[-1].stem}" if pages else "first one tomorrow 08:30"))
    return rows


def show() -> int:
    colour = _colour()
    bold, dim, green, red, reset = ("\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[0m") if colour \
        else ("",) * 5
    beside = [
        "",
        f"{bold}Mr Roy{reset}",
        "Your English teacher, in the terminal.",
        "",
        "He reads what you type and what you",
        "dictate, then every morning hands you one",
        "page: what you said, what to say, and why.",
    ]
    art = portrait() if colour else [" " * 24] * (len(ART) // 2)
    print()
    for i, line in enumerate(art):
        print(f"  {line}   {beside[i] if i < len(beside) else ''}")

    print(f"\n  {bold}What he does{reset}")
    for what, how in (
        ("reads your typing", "Claude Code, Codex, Gmail, Notes, Slack, ChatGPT"),
        ("reads your speech", "from Wispr Flow dictations; never the mic"),
        ("23:30 every night", "checks the day's grammar"),
        ("08:30 every morning", "opens the lesson: what you said, what to say, why"),
    ):
        print(f"    {what:<21}{dim}{how}{reset}")

    print(f"\n  {bold}Right now{reset}")
    for ok, what, detail in _status():
        mark = f"{green}●{reset}" if ok else f"{red}○{reset}"
        print(f"    {mark} {what:<12}{dim}{detail}{reset}")

    print(f"\n  {bold}Commands{reset}")
    for command, what in (
        ("roy setup", "first time? start here"),
        ("roy morning", "open the latest lesson"),
        ("roy analyse-day", "run tonight's check now"),
        ("roy logs", "what the background jobs did"),
        ("roy install --remove", "stop everything"),
        ("roy --help", "every command"),
    ):
        print(f"    {command:<27}{dim}{what}{reset}")

    print(f"\n  {dim}Private by design: no audio is touched. Password fields and private chats are"
          f"\n  never read. Only the day's sentences go to the grammar checker. Everything is forgotten"
          f"\n  two nights later.{reset}\n")
    return 0
