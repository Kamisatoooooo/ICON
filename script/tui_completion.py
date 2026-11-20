"""Filesystem completion without shell parsing (preserves Windows paths)."""
from __future__ import annotations

import os
import re
from pathlib import Path


def path_candidates(raw: str, *, directories_only: bool = False) -> list[str]:
    quote = raw[0] if raw[:1] in {'"', "'"} else ''
    value = raw[1:] if quote else raw
    if quote and value.endswith(quote):
        value = value[:-1]
    separators = {os.sep}
    if os.altsep:
        separators.add(os.altsep)
    position = max((value.rfind(separator) for separator in separators), default=-1)
    if position >= 0:
        parent, partial = value[:position + 1], value[position + 1:]
        separator = value[position]
    else:
        drive, partial = os.path.splitdrive(value)
        parent, separator = drive, os.sep
    # Expand ~ for lookup only; preserve the user's spelling in the completed text.
    if value == '~':
        return [f'{quote}~{separator}{quote}']
    folder = Path(parent or '.').expanduser()
    try:
        entries = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold(), p.name))
        matches = []
        for entry in entries:
            if not os.path.normcase(entry.name).startswith(os.path.normcase(partial)):
                continue
            if entry.name.startswith('.') and not partial.startswith('.'):
                continue
            is_dir = entry.is_dir()
            if directories_only and not is_dir:
                continue
            text = parent + entry.name + (separator if is_dir else '')
            # Spaces need no shell escaping: the TUI consumes the whole path.
            # Keep paired quotes if the user started quoting; quote new spaced paths.
            wrapper = quote or ('"' if any(char.isspace() for char in text) else '')
            matches.append(wrapper + text + wrapper)
        return matches
    except (OSError, ValueError):
        return []


def complete_prefix(text: str, commands: dict[str, str]) -> list[str]:
    """Return replacements for text BEFORE the cursor; never evaluate shell syntax."""
    leading = text[:len(text) - len(text.lstrip())]
    value = text.lstrip()
    argument = re.match(r'^(/\w+)(\s+)(.*)$', value, flags=re.DOTALL)
    if argument:
        command, spacing, raw = argument.groups()
        if command in {'/run', '/scan', '/output'}:
            prefix = leading + command + spacing
            return [prefix + match for match in path_candidates(raw, directories_only=command == '/output')]
        if command == '/set':
            setting = re.match(r'^(waifu2x|model-dir)(\s+)(.*)$', raw, flags=re.DOTALL)
            if setting:
                name, gap, path = setting.groups()
                prefix = leading + command + spacing + name + gap
                return [prefix + match for match in path_candidates(path, directories_only=name == 'model-dir')]
        return []
    if value.startswith('/'):
        matches = [leading + command + ' ' for command in commands if command.startswith(value)]
        if matches:
            return matches
    return [leading + match for match in path_candidates(value)]
