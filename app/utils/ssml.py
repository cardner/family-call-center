"""Parse and sanitize a small SSML subset for Twilio neural TTS.

Admin-editable prompts may include ``<break>``, ``<emphasis>``, and
``<prosody>`` tags. Unknown tags are stripped on save. At render time the
parsed structure is applied via the Twilio SDK so SSML is not XML-escaped.
"""

import re

_ATTR_RE = re.compile(r'(\w[\w-]*)=["\']([^"\']*)["\']')
_BREAK_TAG_RE = re.compile(r"<break(\s+[^>]*?)\s*/>", re.IGNORECASE)
_OPEN_TAG_RE = re.compile(r"<(emphasis|prosody)(\s+[^>]*?)>", re.IGNORECASE)
_ANY_TAG_RE = re.compile(r"</?[^>]+>")

_BREAK_TIME_RE = re.compile(r"^\d+(\.\d+)?(ms|s)$", re.IGNORECASE)
_BREAK_STRENGTHS = frozenset(
    {"x-weak", "weak", "medium", "strong", "x-strong"}
)
_EMPHASIS_LEVELS = frozenset({"strong", "moderate", "reduced"})
_PROSODY_RATES = frozenset(
    {"x-slow", "slow", "medium", "fast", "x-fast"}
)
_PROSODY_PITCHES = frozenset(
    {"default", "x-low", "low", "medium", "high", "x-high"}
)
_PROSODY_VOLUMES = frozenset(
    {"default", "silent", "x-soft", "soft", "medium", "loud", "x-loud"}
)
_PERCENT_RE = re.compile(r"^[+-]?\d+%$")
_DB_RE = re.compile(r"^[+-]?\d+(\.\d+)?dB$", re.IGNORECASE)


def _parse_attrs(attr_string):
    return dict(_ATTR_RE.findall(attr_string or ""))


def _validated_break_attrs(attrs):
    clean = {}
    time = attrs.get("time", "").strip()
    if _BREAK_TIME_RE.match(time):
        clean["time"] = time
    strength = attrs.get("strength", "").strip().lower()
    if strength in _BREAK_STRENGTHS:
        clean["strength"] = strength
    return clean


def _validated_emphasis_attrs(attrs):
    clean = {}
    level = attrs.get("level", "").strip().lower()
    if level in _EMPHASIS_LEVELS:
        clean["level"] = level
    return clean


def _validated_prosody_attrs(attrs):
    clean = {}
    rate = attrs.get("rate", "").strip().lower()
    if rate in _PROSODY_RATES or _PERCENT_RE.match(rate):
        clean["rate"] = rate
    pitch = attrs.get("pitch", "").strip().lower()
    if pitch in _PROSODY_PITCHES or _PERCENT_RE.match(pitch):
        clean["pitch"] = pitch
    volume = attrs.get("volume", "").strip().lower()
    if volume in _PROSODY_VOLUMES or _DB_RE.match(volume):
        clean["volume"] = volume
    return clean


def _parse_nodes(text):
    """Return a list of (kind, ...) nodes from SSML-ish prompt text."""
    nodes = []
    pos = 0
    while pos < len(text):
        if text[pos] != "<":
            end = text.find("<", pos)
            if end == -1:
                chunk = text[pos:]
                if chunk:
                    nodes.append(("text", chunk))
                break
            chunk = text[pos:end]
            if chunk:
                nodes.append(("text", chunk))
            pos = end
            continue

        match = _BREAK_TAG_RE.match(text, pos)
        if match:
            nodes.append(("break", _validated_break_attrs(_parse_attrs(match.group(1)))))
            pos = match.end()
            continue

        match = _OPEN_TAG_RE.match(text, pos)
        if match:
            tag = match.group(1).lower()
            attrs = _parse_attrs(match.group(2))
            close = f"</{tag}>"
            close_idx = text.lower().find(close, match.end())
            if close_idx == -1:
                nodes.append(("text", text[pos : pos + 1]))
                pos += 1
                continue
            inner = _parse_nodes(text[match.end() : close_idx])
            if tag == "emphasis":
                nodes.append(("emphasis", _validated_emphasis_attrs(attrs), inner))
            else:
                nodes.append(("prosody", _validated_prosody_attrs(attrs), inner))
            pos = close_idx + len(close)
            continue

        match = _ANY_TAG_RE.match(text, pos)
        if match:
            pos = match.end()
            continue

        nodes.append(("text", text[pos]))
        pos += 1
    return nodes


def _serialize_nodes(nodes):
    parts = []
    for node in nodes:
        kind = node[0]
        if kind == "text":
            parts.append(node[1])
        elif kind == "break":
            attrs = node[1]
            attr_bits = []
            if "time" in attrs:
                attr_bits.append(f'time="{attrs["time"]}"')
            if "strength" in attrs:
                attr_bits.append(f'strength="{attrs["strength"]}"')
            if attr_bits:
                parts.append(f"<break {' '.join(attr_bits)}/>")
        elif kind == "emphasis":
            attrs, inner = node[1], node[2]
            level = attrs.get("level")
            if level:
                parts.append(
                    f'<emphasis level="{level}">{_serialize_nodes(inner)}</emphasis>'
                )
            else:
                parts.append(_serialize_nodes(inner))
        elif kind == "prosody":
            attrs, inner = node[1], node[2]
            attr_bits = []
            for key in ("rate", "pitch", "volume"):
                if key in attrs:
                    attr_bits.append(f'{key}="{attrs[key]}"')
            if attr_bits:
                parts.append(
                    f'<prosody {" ".join(attr_bits)}>{_serialize_nodes(inner)}</prosody>'
                )
            else:
                parts.append(_serialize_nodes(inner))
    return "".join(parts)


def normalize_ivr_ssml(text):
    """Parse prompt text and return canonical SSML with only allowed tags."""
    if not text:
        return ""
    return _serialize_nodes(_parse_nodes(str(text)))


def apply_ssml_to_say(say, text):
    """Apply parsed SSML/plain text to a Twilio ``Say`` element."""

    def _apply_nodes(nodes):
        for node in nodes:
            kind = node[0]
            if kind == "text":
                say.append(node[1])
            elif kind == "break":
                attrs = node[1]
                if attrs:
                    say.break_(**attrs)
            elif kind == "emphasis":
                attrs, inner = node[1], node[2]
                if attrs.get("level"):
                    emphasis = say.emphasis(level=attrs["level"])
                    _apply_nodes_to(emphasis, inner)
                else:
                    _apply_nodes(inner)
            elif kind == "prosody":
                attrs, inner = node[1], node[2]
                if any(key in attrs for key in ("rate", "pitch", "volume")):
                    prosody = say.prosody(**attrs)
                    _apply_nodes_to(prosody, inner)
                else:
                    _apply_nodes(inner)

    def _apply_nodes_to(target, nodes):
        for node in nodes:
            kind = node[0]
            if kind == "text":
                target.append(node[1])
            elif kind == "break":
                attrs = node[1]
                if attrs:
                    target.break_(**attrs)
            elif kind == "emphasis":
                attrs, inner = node[1], node[2]
                if attrs.get("level"):
                    emphasis = target.emphasis(level=attrs["level"])
                    _apply_nodes_to(emphasis, inner)
                else:
                    _apply_nodes_to(target, inner)
            elif kind == "prosody":
                attrs, inner = node[1], node[2]
                if any(key in attrs for key in ("rate", "pitch", "volume")):
                    prosody = target.prosody(**attrs)
                    _apply_nodes_to(prosody, inner)
                else:
                    _apply_nodes_to(target, inner)

    _apply_nodes(_parse_nodes(text or ""))
