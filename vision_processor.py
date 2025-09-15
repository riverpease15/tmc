"""
Vision-to-MakeCode pipeline for micro:bit

High-level flow:
- OCR an input image of physical MakeCode-style blocks (Google Vision API)
- Parse the raw OCR lines into a structured command model
- Generate MakeCode JavaScript, using a centralized mapper (static/blocks_map.json)

Design goals:
- Centralize mappings (icons, sounds, pins, radio, events, grid, conditionals)
- Be tolerant to OCR noise (1/0, I/|, O/o, punctuation) and spacing
- Keep parsing logic small and uniform: event bodies are parsed via parse_actions_from
"""

import io
import os
import sys
import json

import pandas as pd
from google.cloud import vision
from google.cloud.vision_v1 import AnnotateImageResponse, types

# Configuration
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"dolphin-393123-2ac6bf25dfab.json"
OUTPUT_FILE = "static/code_file.js"

# Initialize Google Vision client
client = vision.ImageAnnotatorClient()

# Load centralized blocks mapping
# This file is the single source of truth for block pseudonames, templates,
# and assets. It is consumed by both parsing (validation/normalization) and
# codegen (template rendering).
try:
    with open(os.path.join("static", "blocks_map.json"), "r") as _bm_file:
        _BLOCKS_MAP = json.load(_bm_file)
except Exception:
    _BLOCKS_MAP = {"icons": {}, "sounds": {}, "pins": {}, "radio": {}, "synonyms": {}}

ICONS = {k.upper(): v.get("value") for k, v in _BLOCKS_MAP.get("icons", {}).items()}
SOUNDS = {k.upper(): v.get("value") for k, v in _BLOCKS_MAP.get("sounds", {}).items()}
PINS = {k.upper(): v.get("value") for k, v in _BLOCKS_MAP.get("pins", {}).items() if isinstance(v, dict) and "value" in v}
PIN_WRITE_TEMPLATE = _BLOCKS_MAP.get("pins", {}).get("templateDigitalWrite")
RADIO_SETGROUP_TEMPLATE = _BLOCKS_MAP.get("radio", {}).get("setGroup", {}).get("template")
RADIO_SENDSTRING_TEMPLATE = _BLOCKS_MAP.get("radio", {}).get("sendString", {}).get("template")
SYNONYMS = {k.upper(): v for k, v in _BLOCKS_MAP.get("synonyms", {}).items()}
EVENT_TEMPLATES = _BLOCKS_MAP.get("events", {})
TEMPLATES = _BLOCKS_MAP.get("templates", {})

# Constants
GRID_NOISE_TOKENS = {"+", "*", "·", "•", ","}

def get_icon_code(icon_name: str) -> str:
    """Resolve an icon pseudoname to MakeCode IconNames.*, defaulting safely.

    Tolerates case differences and unknown values by falling back to Heart.
    The actual mapping comes from static/blocks_map.json.
    """
    if not isinstance(icon_name, str):
        return 'IconNames.Heart'
    lookup_key = icon_name.strip().upper()
    return ICONS.get(lookup_key, 'IconNames.Heart')

def get_sound_code(sound_name: str) -> str:
    """Resolve a sound pseudoname to MakeCode soundExpression.*, defaulting safely.

    Tolerates case differences and unknown values by falling back to happy.
    The actual mapping comes from static/blocks_map.json.
    """
    if not isinstance(sound_name, str):
        return 'soundExpression.happy'
    lookup_key = sound_name.strip().upper()
    return SOUNDS.get(lookup_key, 'soundExpression.happy')

def render_template(template_str: str, params: dict) -> str:
    """Render {{placeholders}} in a tiny mustache-like fashion.

    This is intentionally simple (no escaping, no conditionals) because our
    templates are small, trusted strings defined in the mapper.
    """
    if not isinstance(template_str, str):
        return ""
    result = template_str
    for key, value in params.items():
        result = result.replace(f"{{{{{key}}}}}", str(value))
    return result

def get_event_template(handler: dict) -> str | None:
    """Return an event template from the mapper for a parsed handler type.

    If a template is missing, codegen falls back to a hardcoded equivalent.
    """
    if not isinstance(EVENT_TEMPLATES, dict):
        return None
    htype = handler.get('type')
    if htype == 'shake':
        entry = EVENT_TEMPLATES.get('ON SHAKE')
        return entry.get('template') if isinstance(entry, dict) else None
    if htype == 'sound_loud':
        # Match blocks_map label
        entry = EVENT_TEMPLATES.get('HEAR LOUD SOUND')
        return entry.get('template') if isinstance(entry, dict) else None
    if htype == 'sound_quiet':
        entry = EVENT_TEMPLATES.get('HEAR QUIET SOUND')
        return entry.get('template') if isinstance(entry, dict) else None
    if htype == 'button':
        btn = handler.get('button')
        # Match blocks_map labels
        key = f"ON BUTTON {btn}" if btn in ['A','B','AB'] else None
        if key and key in EVENT_TEMPLATES:
            entry = EVENT_TEMPLATES.get(key)
            return entry.get('template') if isinstance(entry, dict) else None
    if htype == 'radio_receives_message':
        entry = EVENT_TEMPLATES.get('GET A MESSAGE')
        return entry.get('template') if isinstance(entry, dict) else None
    return None

def normalize_pin_token(token):
    """Normalize OCR variants of pin tokens like 'PO' or Cyrillic 'РО' to 'P0'.

    Applies mapper synonyms and a small Cyrillic-to-Latin transform to be
    resilient to OCR misreads. Returns the normalized uppercase token.
    """
    if not isinstance(token, str):
        return token
    token_stripped = token.strip().upper()
    # First, apply mapping synonyms if defined
    if token_stripped in SYNONYMS:
        token_stripped = SYNONYMS[token_stripped].upper()
    cyr_to_lat = {
        '\u0420': 'P',  # Cyrillic capital Er
        '\u041e': 'O',  # Cyrillic capital O
    }
    normalized = ''.join(cyr_to_lat.get(ch, ch) for ch in token_stripped)
    if normalized == 'PO':
        return 'P0'
    return normalized

def parse_actions_from(df, base_index, start_offset):
    """Parse a sequence of actions at base_index+start_offset until a stopper token.

    Returns a tuple: (actions: list[str], consumed_relative_offset: int).
    The parser stops on control-flow keywords (ELSE/ON/IF) or end of input.
    Actions supported here mirror those commonly found inside events/IF bodies:
    - SHOW <ICON>
    - TURN ON/OFF <PIN>
    - SEND A MESSAGE <TEXT> (one- or two-line forms)
    - PLAY SOUND <SOUND> (one- or two-line forms with PLAY SOUND)
    """
    actions = []
    i = start_offset
    while base_index + i < len(df):
        next_cmd = df.loc[base_index + i, "command"]
        if next_cmd in ["ELSE", "ON", "IF"]:
            break

        if next_cmd == "SHOW" and base_index + i + 1 < len(df):
            kind, value, consumed_after_show = parse_show_common(df, base_index, i + 1)
            if kind == 'grid':
                rows = value.split("\n")
                spaced_rows = ["    " + " ".join(list(r)) for r in rows]
                grid_render = "\n".join(spaced_rows)
                grid_template = TEMPLATES.get('grid')
                if grid_template:
                    actions.append(render_template(grid_template, {"grid": grid_render}))
                else:
                    template = "`\n" + grid_render + "\n`"
                    actions.append(f"basic.showLeds({template});")
                i += 1 + consumed_after_show
                continue
            if kind == 'icon':
                actions.append(f"basic.showIcon({value})")
                i += 2
                continue

        if next_cmd == "TURN ON":
            # Look for bracketed pin in the next few tokens
            pin_cmd = None
            tokens_consumed = 1  # We consumed "TURN ON"
            
            # Check next few tokens for bracketed pin
            for j in range(1, min(6, len(df) - base_index - i)):  # Look ahead up to 5 tokens (for 5 pins)
                token = df.loc[base_index + i + j, "command"]
                if isinstance(token, str):
                    # Look for bracketed pin pattern like [PO] or [P1] within the token
                    import re
                    bracket_match = re.search(r'\[([^\]]+)\]', token)
                    if bracket_match:
                        # Extract pin from brackets and normalize
                        pin_name = bracket_match.group(1)
                        pin_cmd = normalize_pin_token(pin_name)
                        tokens_consumed += j
                        break
            
            if pin_cmd and pin_cmd in PINS:
                if PIN_WRITE_TEMPLATE:
                    actions.append(render_template(PIN_WRITE_TEMPLATE, {"pin": pin_cmd, "value": 1}))
                else:
                    actions.append(f"pins.digitalWritePin(DigitalPin.{pin_cmd}, 1)")
                i += tokens_consumed
                continue

        if next_cmd == "TURN OFF":
            # Look for bracketed pin in the next few tokens
            pin_cmd = None
            tokens_consumed = 1  # We consumed "TURN OFF"
            
            # Check next few tokens for bracketed pin
            for j in range(1, min(6, len(df) - base_index - i)):  # Look ahead up to 5 tokens (for 5 pins)
                token = df.loc[base_index + i + j, "command"]
                if isinstance(token, str):
                    # Look for bracketed pin pattern like [PO] or [P1] within the token
                    import re
                    bracket_match = re.search(r'\[([^\]]+)\]', token)
                    if bracket_match:
                        # Extract pin from brackets and normalize
                        pin_name = bracket_match.group(1)
                        pin_cmd = normalize_pin_token(pin_name)
                        tokens_consumed += j
                        break
            
            if pin_cmd and pin_cmd in PINS:
                if PIN_WRITE_TEMPLATE:
                    actions.append(render_template(PIN_WRITE_TEMPLATE, {"pin": pin_cmd, "value": 0}))
                else:
                    actions.append(f"pins.digitalWritePin(DigitalPin.{pin_cmd}, 0)")
                i += tokens_consumed
                continue

        # One-line SEND A MESSAGE
        if next_cmd == "SEND A MESSAGE" and base_index + i + 1 < len(df):
            msg = df.loc[base_index + i + 1, "command"]
            if isinstance(msg, str) and msg:
                actions.append(f"radio.sendString(\"{msg}\")")
                i += 2
                continue

        if next_cmd == "PLAY SOUND" and base_index + i + 1 < len(df):
            sound = df.loc[base_index + i + 1, "command"]
            sound_code = get_sound_code(sound)
            actions.append(f"music.play(music.builtinPlayableSoundEffect({sound_code}), music.PlaybackMode.UntilDone)")
            i += 2
            continue

        # Legacy split form removed (OCR provides PLAY SOUND)

        i += 1

    return actions, i - start_offset

def _normalize_grid_char(ch: str) -> str | None:
    """Map OCR glyphs to grid on/off: returns '#' (on) or '.' (off).

    Accepts common OCR variants so students can write 1/0 instead of #/.: 1/I/|
    become '#'; 0/O/o/-, punctuation or bullets become '.'. Unknown glyphs
    return None so upstream parsing can try alternate strategies.
    """
    if not isinstance(ch, str) or len(ch) == 0:
        return None
    c = ch.strip()
    if len(c) > 1:
        # If it is a 5-char row like "#..#." we'll handle elsewhere
        return None
    on_set = {"#", "1", "I", "|"}
    off_set = {".", "0", "O", "o", ",", "-", "·", "•"}
    if c in on_set:
        return "#"
    if c in off_set:
        return "."
    return None

def _normalize_grid_row(row_str: str) -> str | None:
    """Normalize a 5-character row to '#'/'.'.

    Handles spacing and noise removal, applies glyph mapping (1→#, 0→.), and
    validates exact row width of 5. Returns None if normalization fails.
    """
    if not isinstance(row_str, str):
        return None
    # Remove spaces and common noise characters
    s = (
        row_str.strip()
        .replace(" ", "")
        .replace("·", "")
        .replace("•", "")
        .replace(",", "")
    )
    # Map characters
    s = (
        s.replace("O", ".").replace("o", ".")
         .replace("I", "#").replace("|", "#")
         .replace("1", "#")
         .replace("0", ".")
         .replace("-", ".")
    )
    if len(s) != 5:
        return None
    for ch in s:
        if ch not in {"#", "."}:
            # Allow original glyphs and map
            if ch in {"I", "|"}:
                continue
            return None
    # Re-map allowed glyphs fully
    s = "".join("#" if ch in {"#"} else "." if ch in {"."} else ch for ch in s)
    return s

def parse_grid_from(df: pd.DataFrame, base_index: int, start_offset: int):
    """Parse a 5x5 LED grid starting at base_index+start_offset.

    Supports two shapes:
    1) Row-based: five lines, each 5 normalized glyphs (accepts '1'/'0', etc.)
    2) Glyph-based: 25 single-char tokens that normalize to on/off

    Returns (grid_str, consumed_after_show). If parsing fails, returns (None, 0).
    """
    # Attempt row-based parsing first
    rows: list[str] = []
    consumed = 0
    noise_tokens = GRID_NOISE_TOKENS
    for r in range(5):
        pos = base_index + start_offset + consumed
        if pos >= len(df):
            break
        candidate = df.loc[pos, "command"]
        # Skip standalone noise tokens
        if isinstance(candidate, str) and candidate.strip() in noise_tokens:
            consumed += 1
            r -= 1
            continue
        normalized = _normalize_grid_row(candidate)
        if normalized is None:
            # Try to merge up to the next 3 tokens to form a 5-char row
            merged = str(candidate)
            lookahead_used = 0
            while lookahead_used < 3 and base_index + start_offset + consumed + 1 + lookahead_used < len(df):
                nxt = df.loc[base_index + start_offset + consumed + 1 + lookahead_used, "command"]
                merged += str(nxt)
                trial = _normalize_grid_row(merged)
                if trial is not None:
                    normalized = trial
                    consumed += 1 + lookahead_used
                    break
                lookahead_used += 1
        if normalized is None:
            break
        rows.append(normalized)
        consumed += 1
    if len(rows) == 5:
        grid = "\n".join(rows)
        return grid, consumed

    # Fallback: collect 25 glyphs; allow multi-char tokens to expand
    rows = []
    glyphs: list[str] = []
    consumed = 0
    while base_index + start_offset + consumed < len(df) and len(glyphs) < 25:
        tok = df.loc[base_index + start_offset + consumed, "command"]
        # Skip noise tokens
        if isinstance(tok, str) and tok.strip() in noise_tokens:
            consumed += 1
            continue
        norm = _normalize_grid_char(tok)
        if norm is None:
            # If token contains multiple potential glyphs, try to expand
            if isinstance(tok, str):
                expanded_any = False
                for ch in tok:
                    n = _normalize_grid_char(ch)
                    if n is None:
                        expanded_any = False
                        break
                    glyphs.append(n)
                    expanded_any = True
                    if len(glyphs) >= 25:
                        break
                if expanded_any:
                    consumed += 1
                    continue
            break
        glyphs.append(norm)
        consumed += 1
    if glyphs:
        # Pad to 25 with '.' if short
        while len(glyphs) < 25:
            glyphs.append('.')
        for i in range(0, 25, 5):
            rows.append("".join(glyphs[i:i+5]))
        grid = "\n".join(rows[:5])
        return grid, consumed

    return None, 0

def parse_show_common(df: pd.DataFrame, base_index: int, show_offset: int):
    """Parse SHOW followed by either a 5x5 grid or an icon.

    Returns a tuple: (kind, value, consumed_after_show)
    - kind: 'grid' or 'icon' or None
    - value: grid string (5 lines) or icon code string
    - consumed_after_show: tokens consumed after the SHOW token
    """
    # Try grid first
    grid, consumed_after_show = parse_grid_from(df, base_index, show_offset)
    if grid:
        return 'grid', grid, consumed_after_show
    # Otherwise, treat as icon name on next token
    icon_name = df.loc[base_index + show_offset, "command"] if base_index + show_offset < len(df) else None
    if isinstance(icon_name, str) and icon_name:
        icon_code = get_icon_code(icon_name)
        return 'icon', icon_code, 1
    return None, None, 0

def process_image(image_file_name):
    """OCR the input image and return the full text annotation from Vision API.

    The proto-plus response is serialized+deserialized for stable access.
    """
    with io.open(image_file_name, "rb") as image_file:
        content = image_file.read()

    image = types.Image(content=content)
    response = client.text_detection(image=image)
    
    # Serialize and deserialize for compatibility
    serialized_proto_plus = AnnotateImageResponse.serialize(response)
    response = AnnotateImageResponse.deserialize(serialized_proto_plus)
    
    return response.full_text_annotation.text

def parse_commands(string_data):
    """Turn raw OCR text into a structured intermediate command model.

    The model contains top-level actions, event handlers, and an optional
    conditional block. Event bodies are parsed via parse_actions_from for
    consistency and low duplication.
    """
    # Split text into individual commands
    commands = string_data.split("\n")
    print(f"Extracted commands: {commands}")
    
    # Initialize command structure
    parsed_commands = {
        'channel': None,
        'actions': [],
        'event_handlers': []
    }
    
    # Create DataFrame for processing
    df = pd.DataFrame({"command": commands, "full_command": "", "code_command": ""})
    # Track token indices that are consumed as part of an ON ... {actions} body
    consumed_indices: set[int] = set()

    # Helper utilities to reduce repetition in ON-handling
    def token(pos: int) -> str | None:
        return df.loc[pos, "command"] if 0 <= pos < len(df) else None

    def mark_consumed(base_index: int, start_offset: int, consumed_rel: int) -> None:
        for k in range(base_index + start_offset, base_index + consumed_rel):
            consumed_indices.add(k)

    def handle_event(base_index: int, start_offset: int, handler: dict) -> None:
        actions, consumed_rel = parse_actions_from(df, base_index, start_offset)
        if actions:
            handler_with_actions = dict(handler)
            handler_with_actions['actions'] = actions
            parsed_commands['event_handlers'].append(handler_with_actions)
            mark_consumed(base_index, start_offset, consumed_rel)
    
    # Process each command
    for index, row in df.iterrows():
        value = row["command"]
        # Skip tokens that were already consumed as part of an earlier event's actions
        if index in consumed_indices:
            continue
        
        # Parse CHANNEL command
        if value == "CHANNEL":
            if index > 0:
                parsed_commands['channel'] = df.loc[index - 1, "command"]
        
        # Parse SEND A MESSAGE command
        elif value == "SEND A" and index + 1 < len(df) and df.loc[index + 1, "command"] == "MESSAGE":
            # Look for message content after MESSAGE
            message_content = None
            for i in range(2, 5):  # Look up to 3 positions ahead
                if index + i < len(df):
                    next_cmd = df.loc[index + i, "command"]
                    # Skip common keywords that aren't message content
                    if next_cmd not in ['ON', 'SHOW', 'TURN', 'PLAY', 'IF', 'GET', 'SEND']:
                        message_content = next_cmd
                        break
            
            if message_content:
                parsed_commands['actions'].append({
                    'type': 'send_message',
                    'message': message_content
                })

        # Parse SHOW LED grid immediately after SHOW token (5x5)
        elif value == "SHOW":
            kind, value_show, consumed_after_show = parse_show_common(df, index, 1)
            if kind == 'grid':
                parsed_commands.setdefault('actions', []).append({'type': 'show_grid', 'grid': value_show})
                continue
            if kind == 'icon':
                parsed_commands.setdefault('actions', []).append({'type': 'show_icon', 'icon': value_show})
                continue
        
        # Parse TURN ON/OFF commands
        elif value == "TURN ON":
            # Look for bracketed pin in the next few tokens
            pin_cmd = None
            for j in range(1, min(6, len(df) - index)):  # Look ahead up to 5 tokens (for 5 pins)
                token_val = df.loc[index + j, "command"] if index + j < len(df) else None
                if isinstance(token_val, str):
                    # Look for bracketed pin pattern like [PO] or [P1] within the token
                    import re
                    bracket_match = re.search(r'\[([^\]]+)\]', token_val)
                    if bracket_match:
                        # Extract pin from brackets and normalize
                        pin_name = bracket_match.group(1)
                        pin_cmd = normalize_pin_token(pin_name)
                        break
            
            if pin_cmd and pin_cmd in PINS:
                parsed_commands.setdefault('actions', []).append({'type': 'turn_on_pin', 'pin': pin_cmd})
        
        elif value == "TURN OFF":
            # Look for bracketed pin in the next few tokens
            pin_cmd = None
            for j in range(1, min(6, len(df) - index)):  # Look ahead up to 5 tokens (for 5 pins)
                token_val = df.loc[index + j, "command"] if index + j < len(df) else None
                if isinstance(token_val, str):
                    # Look for bracketed pin pattern like [PO] or [P1] within the token
                    import re
                    bracket_match = re.search(r'\[([^\]]+)\]', token_val)
                    if bracket_match:
                        # Extract pin from brackets and normalize
                        pin_name = bracket_match.group(1)
                        pin_cmd = normalize_pin_token(pin_name)
                        break
            
            if pin_cmd and pin_cmd in PINS:
                parsed_commands.setdefault('actions', []).append({'type': 'turn_off_pin', 'pin': pin_cmd})
        
        # Handle combined ON event tokens like "ON TILT RIGHT"
        elif value.startswith("ON "):
            event_part = value[3:]  # Remove "ON " prefix
            if event_part == "TILT LEFT":
                handle_event(index, 1, {'type': 'tilt_left'})
                continue
            elif event_part == "TILT RIGHT":
                handle_event(index, 1, {'type': 'tilt_right'})
                continue
            elif event_part == "TILT UP":
                handle_event(index, 1, {'type': 'tilt_up'})
                continue
            elif event_part == "TILT DOWN":
                handle_event(index, 1, {'type': 'tilt_down'})
                continue
            elif event_part == "SHAKE":
                handle_event(index, 1, {'type': 'shake'})
                continue
            elif event_part == "RADIO RECEIVES":
                handle_event(index, 1, {'type': 'radio_receives_message'})
                continue
            elif event_part == "HEAR LOUD SOUND":
                handle_event(index, 1, {'type': 'sound_loud'})
                continue
            elif event_part == "HEAR QUIET SOUND":
                handle_event(index, 1, {'type': 'sound_quiet'})
                continue
        
        # Consolidated ON ... event parsing using helpers
        elif value == "ON":
            # SHAKE
            if token(index + 1) == "SHAKE":
                handle_event(index, 2, {'type': 'shake'})
                continue

            # HEAR LOUD/QUIET SOUND
            if token(index + 1) == "HEAR" and token(index + 2) == "LOUD" and token(index + 3) == "SOUND":
                handle_event(index, 4, {'type': 'sound_loud'})
                continue
            if token(index + 1) == "HEAR" and token(index + 2) == "QUIET" and token(index + 3) == "SOUND":
                handle_event(index, 4, {'type': 'sound_quiet'})
                continue

            # RADIO RECEIVES (single, consistent form)
            if token(index + 1) == "RADIO" and token(index + 2) == "RECEIVES":
                handle_event(index, 3, {'type': 'radio_receives_message'})
                continue
            if token(index + 1) == "RADIO RECEIVES":
                # Combined token form
                handle_event(index, 2, {'type': 'radio_receives_message'})
                continue

            # HEAR LOUD/QUIET SOUND (combined single-token form)
            if token(index + 1) == "HEAR LOUD SOUND":
                handle_event(index, 2, {'type': 'sound_loud'})
                continue
            if token(index + 1) == "HEAR QUIET SOUND":
                handle_event(index, 2, {'type': 'sound_quiet'})
                continue

            # HEAR LOUD/QUIET SOUND (exact, mapper-aligned labels)
            if token(index + 1) == "HEAR" and token(index + 2) == "LOUD" and token(index + 3) == "SOUND":
                handle_event(index, 4, {'type': 'sound_loud'})
                continue
            if token(index + 1) == "HEAR" and token(index + 2) == "QUIET" and token(index + 3) == "SOUND":
                handle_event(index, 4, {'type': 'sound_quiet'})
                continue

            # PRESS BUTTON A/B/AB (supports single-token "PRESS BUTTON" or split)
            if (
                (token(index + 1) == "PRESS" and token(index + 2) == "BUTTON" and token(index + 3) in {"A", "B"})
                or
                (token(index + 1) == "PRESS BUTTON" and token(index + 2) in {"A", "B"})
            ):
                btn = token(index + 3) if token(index + 1) == "PRESS" else token(index + 2)
                start = 4 if token(index + 1) == "PRESS" else 3
                handle_event(index, start, {'type': 'button', 'button': btn})
                continue
            if (
                (token(index + 1) == "PRESS" and token(index + 2) == "BUTTON" and token(index + 3) == "A" and token(index + 4) == "B")
                or
                (token(index + 1) == "PRESS BUTTON" and token(index + 2) == "A" and token(index + 3) == "B")
            ):
                start = 5 if token(index + 1) == "PRESS" else 4
                handle_event(index, start, {'type': 'button', 'button': 'AB'})
                continue

            # TILT UP/DOWN/LEFT/RIGHT
            if token(index + 1) == "TILT" and token(index + 2) == "UP":
                handle_event(index, 3, {'type': 'tilt_up'})
                continue
            if token(index + 1) == "TILT" and token(index + 2) == "DOWN":
                handle_event(index, 3, {'type': 'tilt_down'})
                continue
            if token(index + 1) == "TILT" and token(index + 2) == "LEFT":
                handle_event(index, 3, {'type': 'tilt_left'})
                continue
            if token(index + 1) == "TILT" and token(index + 2) == "RIGHT":
                handle_event(index, 3, {'type': 'tilt_right'})
                continue

            # LOGO UP/DOWN
            if token(index + 1) == "LOGO" and token(index + 2) == "UP":
                handle_event(index, 3, {'type': 'logo_up'})
                continue
            if token(index + 1) == "LOGO" and token(index + 2) == "DOWN":
                handle_event(index, 3, {'type': 'logo_down'})
                continue
        
        # Parse IF combined conditions followed by actions and optional ELSE
        elif value == "IF":
            # General condition parsing supporting:
            # IF {COND} THEN
            # IF {COND} AND/OR {COND} THEN
            # Optional NOT before or after a condition ("NOT" on its own line)

            def parse_single_condition(start_idx: int) -> tuple[str | None, int]:
                """Parse a single condition starting at start_idx.

                Returns (js, consumed_count). Supports:
                - PRESS BUTTON <A|B|AB>
                - <number> EQUAL TO <P0|P1|P2>
                - <P0|P1|P2> EQUAL TO <number>
                - <number> SMALLER THAN <P*> and variants with GREATER THAN
                - <P*> SMALLER THAN <number> and GREATER THAN
                """
                tok0 = token(start_idx)
                tok1 = token(start_idx + 1)
                tok2 = token(start_idx + 2)

                # PRESS BUTTON X
                if tok0 == 'PRESS BUTTON' and tok1 in {'A', 'B', 'AB'}:
                    return f"input.buttonIsPressed(Button.{tok1})", 2
                # Combined PRESS BUTTON X
                if isinstance(tok0, str) and tok0 in {'PRESS BUTTON A', 'PRESS BUTTON B', 'PRESS BUTTON AB'}:
                    btn = tok0.split()[-1]
                    return f"input.buttonIsPressed(Button.{btn})", 1

                # Normalize pins and numbers
                left_norm = normalize_pin_token(tok0) if isinstance(tok0, str) else tok0
                right_norm = normalize_pin_token(tok2) if isinstance(tok2, str) else tok2

                # Comparators map
                comparator = tok1
                cmp_map = {
                    'EQUAL TO': '==',
                    'SMALLER THAN': '<',
                    'GREATER THAN': '>'
                }
                op = cmp_map.get(comparator)
                if op:
                    # Case: number OP Pn
                    if isinstance(tok0, str) and str(tok0).isdigit() and right_norm in {'P0', 'P1', 'P2'}:
                        return f"{tok0} {op} pins.digitalReadPin(DigitalPin.{right_norm})", 3
                    # Case: Pn OP number
                    if left_norm in {'P0', 'P1', 'P2'} and isinstance(tok2, str) and str(tok2).isdigit():
                        return f"pins.digitalReadPin(DigitalPin.{left_norm}) {op} {tok2}", 3

                return None, 0

            # Parse first condition (NOT comes after the condition)
            pos = index + 1
            invert_first = False
            cond1, c1 = parse_single_condition(pos)
            if cond1 is None:
                continue
            pos += c1
            # Allow trailing NOT after condition
            if token(pos) == 'NOT':
                invert_first = not invert_first
                pos += 1
            if invert_first:
                cond1 = f"!({cond1})"

            # Optional connector AND/OR and second condition (supports NOT placement)
            connector = token(pos)
            condition_js = cond1
            if connector in {'AND', 'OR'}:
                pos += 1
                invert_second = False
                cond2, c2 = parse_single_condition(pos)
                if cond2 is None:
                    continue
                pos += c2
                if token(pos) == 'NOT':
                    invert_second = not invert_second
                    pos += 1
                if invert_second:
                    cond2 = f"!({cond2})"
                op = '&&' if connector == 'AND' else '||'
                condition_js = f"{cond1} {op} {cond2}"

            # Expect THEN
            if token(pos) != 'THEN':
                continue

            # Parse THEN actions starting after THEN
            start_after_then = (pos - index) + 1
            then_actions, consumed = parse_actions_from(df, index, start_after_then)
            try:
                for k in range(index + start_after_then, index + start_after_then + consumed):
                    consumed_indices.add(k)
            except Exception:
                pass

            # ELSE branch (optional THEN after ELSE)
            else_actions: list[str] = []
            else_pos = index + start_after_then + consumed
            if else_pos < len(df) and token(else_pos) == 'ELSE':
                consumed_indices.add(else_pos)
                start_after_else = start_after_then + consumed + 1
                if token(else_pos + 1) == 'THEN':
                    consumed_indices.add(else_pos + 1)
                    start_after_else += 1
                else_actions, else_consumed = parse_actions_from(df, index, start_after_else)
                try:
                    for k in range(index + start_after_else, index + start_after_else + else_consumed):
                        consumed_indices.add(k)
                except Exception:
                    pass

            parsed_commands['conditional'] = {
                'condition_js': condition_js,
                'then_actions': then_actions,
                'else_actions': else_actions
            }
    
    return parsed_commands

def generate_code(parsed_commands):
    """Generate MakeCode JavaScript from the parsed command model.

    Prefers mapper-defined templates (radio, pins, events, grid, conditionals),
    and falls back to known-hardcoded snippets only if a template is missing.
    """
    code_parts = []
    
    # Generate channel setup
    if parsed_commands['channel']:
        try:
            channel_num = int(parsed_commands['channel'])
            if RADIO_SETGROUP_TEMPLATE:
                code_parts.append(render_template(RADIO_SETGROUP_TEMPLATE, {"group": channel_num}))
            else:
                code_parts.append(f"radio.setGroup({channel_num});")
        except ValueError:
            print(f"Warning: Invalid channel number '{parsed_commands['channel']}'")
    
    # Generate actions (for non-event-handler commands)
    if 'actions' in parsed_commands:
        for action in parsed_commands['actions']:
            if action['type'] == 'send_message':
                if RADIO_SENDSTRING_TEMPLATE:
                    code_parts.append(render_template(RADIO_SENDSTRING_TEMPLATE, {"message": action['message']}))
                else:
                    code_parts.append(f"radio.sendString(\"{action['message']}\");")
            elif action['type'] == 'show_grid':
                grid = action['grid']
                rows = grid.split("\n")
                spaced_rows = ["    " + " ".join(list(r)) for r in rows]
                grid_render = "\n".join(spaced_rows)
                grid_template = TEMPLATES.get('grid')
                if grid_template:
                    code_parts.append(render_template(grid_template, {"grid": grid_render}))
                else:
                    template = "`\n" + grid_render + "\n`"
                    code_parts.append(f"basic.showLeds({template});")
            elif action['type'] == 'show_icon':
                icon_code = get_icon_code(action['icon'])
                code_parts.append(f"basic.showIcon({icon_code})")
            elif action['type'] == 'turn_on_pin':
                pin = action['pin']
                if PIN_WRITE_TEMPLATE:
                    code_parts.append(render_template(PIN_WRITE_TEMPLATE, {"pin": pin, "value": 1}))
                else:
                    code_parts.append(f"pins.digitalWritePin(DigitalPin.{pin}, 1)")
            elif action['type'] == 'turn_off_pin':
                pin = action['pin']
                if PIN_WRITE_TEMPLATE:
                    code_parts.append(render_template(PIN_WRITE_TEMPLATE, {"pin": pin, "value": 0}))
                else:
                    code_parts.append(f"pins.digitalWritePin(DigitalPin.{pin}, 0)")
    
    # Generate top-level conditional block if present
    if 'conditional' in parsed_commands:
        cond = parsed_commands['conditional']
        then_code = "\n    ".join(cond.get('then_actions', []))
        else_code = "\n    ".join(cond.get('else_actions', []))
        if else_code:
            tpl = TEMPLATES.get('ifElse')
            if tpl:
                code_parts.append(render_template(tpl, {"condition": cond['condition_js'], "then": then_code, "else": else_code}))
            else:
                code_parts.append(f"if ({cond['condition_js']}) {{\n    {then_code}\n}} else {{\n    {else_code}\n}}")
        else:
            tpl = TEMPLATES.get('if')
            if tpl:
                code_parts.append(render_template(tpl, {"condition": cond['condition_js'], "then": then_code}))
            else:
                code_parts.append(f"if ({cond['condition_js']}) {{\n    {then_code}\n}}")

    # Generate event handlers
    for handler in parsed_commands['event_handlers']:
        actions_plain = "\n".join(handler.get('actions', []))
        template = get_event_template(handler)
        if template:
            # Ensure every action line is indented 4 spaces inside the template block
            if actions_plain:
                indented_actions = "\n".join(("    " + line) if line else "" for line in actions_plain.split("\n"))
            else:
                indented_actions = ""
            code_parts.append(render_template(template, {"actions": indented_actions}))
            continue
        # Fallback to hardcoded forms if template missing
        if handler['type'] == 'shake':
            indented = "\n".join(("    " + l) if l else "" for l in actions_plain.split("\n"))
            code_parts.append(f"input.onGesture(Gesture.Shake, function () {{\n{indented}\n}})")
        elif handler['type'] == 'button':
            button = handler.get('button')
            indented = "\n".join(("    " + l) if l else "" for l in actions_plain.split("\n"))
            if button == 'A':
                code_parts.append(f"input.onButtonPressed(Button.A, function () {{\n{indented}\n}})")
            elif button == 'B':
                code_parts.append(f"input.onButtonPressed(Button.B, function () {{\n{indented}\n}})")
            elif button == 'AB':
                code_parts.append(f"input.onButtonPressed(Button.AB, function () {{\n{indented}\n}})")
        elif handler['type'] == 'sound_loud':
            indented = "\n".join(("    " + l) if l else "" for l in actions_plain.split("\n"))
            code_parts.append(f"input.onSound(DetectedSound.Loud, function () {{\n{indented}\n}})")
        elif handler['type'] == 'sound_quiet':
            indented = "\n".join(("    " + l) if l else "" for l in actions_plain.split("\n"))
            code_parts.append(f"input.onSound(DetectedSound.Quiet, function () {{\n{indented}\n}})")
        elif handler['type'] == 'radio_receives_message':
            indented = "\n".join(("    " + l) if l else "" for l in actions_plain.split("\n"))
            code_parts.append(f"radio.onReceivedString(function (receivedString) {{\n{indented}\n}})")
        elif handler['type'] == 'tilt_up':
            indented = "\n".join(("    " + l) if l else "" for l in actions_plain.split("\n"))
            code_parts.append(f"input.onScreenUp(function () {{\n{indented}\n}})")
        elif handler['type'] == 'tilt_down':
            indented = "\n".join(("    " + l) if l else "" for l in actions_plain.split("\n"))
            code_parts.append(f"input.onScreenDown(function () {{\n{indented}\n}})")
        elif handler['type'] == 'tilt_left':
            indented = "\n".join(("    " + l) if l else "" for l in actions_plain.split("\n"))
            code_parts.append(f"input.onGesture(Gesture.TiltLeft, function () {{\n{indented}\n}})")
        elif handler['type'] == 'tilt_right':
            indented = "\n".join(("    " + l) if l else "" for l in actions_plain.split("\n"))
            code_parts.append(f"input.onGesture(Gesture.TiltRight, function () {{\n{indented}\n}})")
        elif handler['type'] == 'logo_up':
            indented = "\n".join(("    " + l) if l else "" for l in actions_plain.split("\n"))
            code_parts.append(f"input.onLogoUp(function () {{\n{indented}\n}})")
        elif handler['type'] == 'logo_down':
            indented = "\n".join(("    " + l) if l else "" for l in actions_plain.split("\n"))
            code_parts.append(f"input.onLogoDown(function () {{\n{indented}\n}})")
    
    return "\n\n".join(code_parts)


def save_code_to_file(code, filename):
    """
    Save generated code to a file.
    
    Args:
        code (str): Generated JavaScript code
        filename (str): Output filename
    """
    # Remove existing file if it exists
    if os.path.exists(filename):
        os.remove(filename)
    
    with open(filename, "w") as file:
        file.write(code)
    
    print(f"Generated code saved to: {filename}")

def main():
    """
    Main function to process image and generate code.
    """
    if len(sys.argv) != 2:
        print("Usage: python vision_processor.py <image_file>")
        sys.exit(1)
    
    image_file_name = sys.argv[1]
    
    try:
        # Process image and extract text
        print(f"Processing image: {image_file_name}")
        string_data = process_image(image_file_name)
        
        # Parse commands
        parsed_commands = parse_commands(string_data)
        
        # Generate code
        generated_code = generate_code(parsed_commands)
        
        # Save to file
        save_code_to_file(generated_code, OUTPUT_FILE)
        
        print(f"Generated code:\n{generated_code}")
        
    except Exception as e:
        print(f"Error processing image: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
