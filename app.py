import os
import subprocess
import json
import re
import sys
from functools import lru_cache

from flask import Flask, jsonify, render_template, request, session, make_response
from werkzeug.utils import secure_filename
from openai import OpenAI

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
file_path = None

CODE_FILE_PATH = "static/code_file.js"
LM_STUDIO_BASE_URL = "http://localhost:1234/v1"
LM_STUDIO_API_KEY = "lm-studio"  # Dummy key for local LM Studio server

@lru_cache(maxsize=1)
def get_cached_block_mappings():
    """
    Load and cache block mappings from blocks_map.json.
    This runs once at startup and caches the results for all subsequent calls.

    Returns:
        tuple: (available_labels, trigger_labels, action_labels, blocks_info)
    """
    try:
        with open("static/blocks_map.json", "r") as f:
            blocks_map = json.load(f)

        # Build a list of human-visible block labels (exact strings students see)
        # Use the keys from categories that represent real blocks, and ignore value-only catalogs
        suggestable_categories = {
            "events", "basic", "input", "music", "led", "control", "variables", "logic", "loops", "math", "pins", "radio"
        }
        exclude_categories = {"synonyms", "templates", "icons", "sounds", "on"}

        available_labels = []
        trigger_labels = []  # event-style blocks that start behaviors
        for category, blocks in blocks_map.items():
            if category in exclude_categories:
                continue
            if category not in suggestable_categories:
                continue
            if not isinstance(blocks, dict):
                continue
            for block_name, block_info in blocks.items():
                if isinstance(block_info, dict) and "template" in block_info:
                    # Use the label as-shipped in blocks_map (e.g., "ON SHAKE", "SHOW ICON")
                    available_labels.append(block_name)
                    if category == "events":
                        trigger_labels.append(block_name)

        # De-duplicate while preserving order
        seen = set()
        available_labels = [x for x in available_labels if not (x in seen or seen.add(x))]

        # Compute actions = all available minus triggers (preserve order)
        seen = set()
        trigger_set = set(trigger_labels)
        action_labels = [x for x in available_labels if (x not in trigger_set) and not (x in seen or seen.add(x))]

        blocks_info = (
            "Available block labels (use EXACT strings; no namespaces, no parentheses): "
            + ", ".join(available_labels)
            + "\n"
            + "TRIGGER labels (pick exactly ONE): "
            + ", ".join(trigger_labels)
            + "\n"
            + "ACTION labels (pick 1–2): "
            + ", ".join(action_labels)
            + "\n\n"
        )

        print(f"DEBUG: Cached {len(available_labels)} suggestable labels")
        print(f"DEBUG: Cached {len(trigger_labels)} trigger labels, {len(action_labels)} action labels")

        return available_labels, trigger_labels, action_labels, blocks_info

    except Exception as e:
        print(f"Warning: Could not load block mapping: {e}")
        # Fallback minimal sets to keep the model and validators working
        trigger_labels = [
            "ON BUTTON A", "ON BUTTON B", "ON BUTTON AB", "ON SHAKE", "GET A MESSAGE", "HEAR LOUD SOUND", "HEAR QUIET SOUND", "ON PIN PRESSED"
        ]
        action_labels = [
            "SHOW ICON", "SHOW STRING", "SHOW LEDS", "PLAY SOUND", "PLAY MELODY", "PLAY TONE", "LIGHT LEVEL", "TEMPERATURE", "PLOT", "CLEAR SCREEN", "DIGITAL WRITE PIN", "SEND STRING"
        ]
        # De-duplicate and form available list
        seen = set()
        available_labels = [x for x in trigger_labels + action_labels if not (x in seen or seen.add(x))]
        # Informational text for the prompt
        blocks_info = (
            "Available block labels (use EXACT strings; no namespaces, no parentheses): "
            + ", ".join(available_labels)
            + "\n"
            + "TRIGGER labels (pick exactly ONE): "
            + ", ".join(trigger_labels)
            + "\n"
            + "ACTION labels (pick 1–2): "
            + ", ".join(action_labels)
            + "\n\n"
        )

        return available_labels, trigger_labels, action_labels, blocks_info

 

def _write_placeholder_code(message: str = "// code will appear here after processing an image"):
    try:
        with open(CODE_FILE_PATH, "w") as f:
            f.write(message)
    except Exception as e:
        print(f"Warning: could not write placeholder code: {e}")



def analyze_student_code(js_code):
    """
    Advanced analysis of student code to extract sophisticated patterns and capabilities.

    Args:
        js_code (str): The JavaScript code to analyze

    Returns:
        dict: Comprehensive analysis including advanced patterns
    """
    import re

    analysis = {
        'triggers': [],
        'actions': [],
        'sensors': [],
        'pins': [],
        'radio': False,
        'logic': [],
        'specific_details': {},
        'code_structure': 'simple',
        'advanced_patterns': [],
        'existing_implementations': [],
        'sophistication_level': 'beginner'
    }
    
    # Extract specific triggers
    if 'onButtonPressed' in js_code:
        buttons = re.findall(r'Button\.([AB]+)', js_code)
        analysis['triggers'].append(f"button_{buttons[0] if buttons else 'unknown'}")
        analysis['specific_details']['buttons_used'] = buttons

    # Also detect inline button checks like input.buttonIsPressed(Button.A)
    inline_buttons = re.findall(r'buttonIsPressed\(Button\.([AB])\)', js_code)
    if inline_buttons:
        existing = set(analysis['specific_details'].get('buttons_used', []))
        for b in inline_buttons:
            if b not in existing:
                existing.add(b)
        analysis['specific_details']['buttons_used'] = list(existing)
        # Treat as a button trigger context even if not an event
        for b in inline_buttons:
            analysis['triggers'].append(f"button_{b}")
    
    if 'onSound' in js_code:
        sound_types = re.findall(r'DetectedSound\.(\w+)', js_code)
        analysis['triggers'].append(f"sound_{sound_types[0] if sound_types else 'unknown'}")
        analysis['specific_details']['sound_types'] = sound_types
    
    if 'onGesture' in js_code:
        gestures = re.findall(r'Gesture\.(\w+)', js_code)
        analysis['triggers'].append(f"gesture_{gestures[0] if gestures else 'unknown'}")
        analysis['specific_details']['gestures'] = gestures
    
    # Extract specific actions
    if 'showIcon' in js_code:
        icons = re.findall(r'IconNames\.(\w+)', js_code)
        analysis['actions'].append(f"show_icon_{icons[0] if icons else 'unknown'}")
        analysis['specific_details']['icons_shown'] = icons
    
    if 'showString' in js_code:
        strings = re.findall(r'showString\("([^"]+)"', js_code)
        analysis['actions'].append("show_string")
        analysis['specific_details']['strings_shown'] = strings
    
    if 'showNumber' in js_code:
        analysis['actions'].append("show_number")
    
    if 'playTone' in js_code:
        analysis['actions'].append("play_tone")
    
    if 'radio.sendString' in js_code:
        messages = re.findall(r'sendString\("([^"]+)"', js_code)
        analysis['radio'] = True
        analysis['actions'].append("send_radio_message")
        analysis['specific_details']['radio_messages'] = messages
    
    # Extract specific sensors and pins
    if 'digitalReadPin' in js_code:
        pins = re.findall(r'DigitalPin\.(P[0-2])', js_code)
        analysis['pins'].extend(pins)
        analysis['actions'].append("read_digital_pin")
        analysis['specific_details']['digital_pins_read'] = pins
    
    if 'digitalWritePin' in js_code:
        pins = re.findall(r'DigitalPin\.(P[0-2])', js_code)
        analysis['pins'].extend(pins)
        analysis['actions'].append("write_digital_pin")
        analysis['specific_details']['digital_pins_written'] = pins
    
    if 'analogReadPin' in js_code:
        pins = re.findall(r'AnalogPin\.(P[0-2])', js_code)
        analysis['pins'].extend(pins)
        analysis['actions'].append("read_analog_pin")
        analysis['specific_details']['analog_pins_read'] = pins
    
    if 'lightLevel' in js_code:
        analysis['sensors'].append("light")
        analysis['actions'].append("read_light")
    
    if 'temperature' in js_code:
        analysis['sensors'].append("temperature")
        analysis['actions'].append("read_temperature")
    
    if 'acceleration' in js_code:
        dimensions = re.findall(r'Dimension\.(\w+)', js_code)
        analysis['sensors'].append("acceleration")
        analysis['actions'].append("read_acceleration")
        analysis['specific_details']['acceleration_dimensions'] = dimensions
    
    # Extract logic patterns
    if 'if (' in js_code:
        analysis['logic'].append("conditional")
        # Look for specific conditions
        if '&&' in js_code:
            analysis['logic'].append("and_condition")
        if '||' in js_code:
            analysis['logic'].append("or_condition")
        if '<' in js_code or '>' in js_code:
            analysis['logic'].append("comparison")
    
    if 'else' in js_code:
        analysis['logic'].append("else_branch")
    
    # Determine code structure complexity
    if_count = js_code.count('if (')
    if if_count > 1:
        analysis['code_structure'] = 'complex'
    elif if_count == 1:
        analysis['code_structure'] = 'conditional'
    
    # Remove duplicates
    analysis['pins'] = list(set(analysis['pins']))
    analysis['triggers'] = list(set(analysis['triggers']))
    analysis['actions'] = list(set(analysis['actions']))
    analysis['sensors'] = list(set(analysis['sensors']))
    analysis['logic'] = list(set(analysis['logic']))

    # COMPREHENSIVE CODE UNDERSTANDING - Based on complete blocks_map.json

    existing_capabilities = set()
    analysis['existing_implementations'] = []

    # Map every possible block from blocks_map.json to code patterns

    # === EVENTS (triggers) ===
    if 'onButtonPressed' in js_code:
        existing_capabilities.add('button_events')
        buttons = re.findall(r'onButtonPressed\(Button\.([AB]+)', js_code)
        analysis['existing_implementations'].append(f'Button event handlers: {", ".join(set(buttons)) or "multiple"}')

    if 'onGesture' in js_code:
        existing_capabilities.add('gesture_events')
        gestures = re.findall(r'onGesture\(Gesture\.(\w+)', js_code)
        analysis['existing_implementations'].append(f'Gesture detection: {", ".join(set(gestures)) or "shake/tilt"}')

    if 'onScreenUp' in js_code or 'onScreenDown' in js_code:
        existing_capabilities.add('screen_orientation')
        analysis['existing_implementations'].append('Screen orientation detection')

    if 'onLogoUp' in js_code or 'onLogoDown' in js_code:
        existing_capabilities.add('logo_touch')
        analysis['existing_implementations'].append('Logo touch detection')

    if 'onPinPressed' in js_code or 'onPinReleased' in js_code:
        existing_capabilities.add('pin_touch')
        analysis['existing_implementations'].append('Pin touch events')

    if 'onReceivedString' in js_code or 'onReceivedNumber' in js_code or 'onReceivedValue' in js_code:
        existing_capabilities.add('radio_receive_events')
        analysis['existing_implementations'].append('Radio receive event handlers')

    if 'onSound' in js_code:
        existing_capabilities.add('sound_events')
        analysis['existing_implementations'].append('Sound detection events')

    # === BASIC DISPLAY ===
    if 'showIcon' in js_code:
        existing_capabilities.add('icon_display')
        analysis['existing_implementations'].append('Icon display')

    if 'showString' in js_code:
        existing_capabilities.add('string_display')
        analysis['existing_implementations'].append('String display')

    if 'showNumber' in js_code:
        existing_capabilities.add('number_display')
        analysis['existing_implementations'].append('Number display')

    if 'showLeds' in js_code:
        existing_capabilities.add('led_patterns')
        analysis['existing_implementations'].append('Custom LED patterns')

    if 'clearScreen' in js_code:
        existing_capabilities.add('screen_control')
        analysis['existing_implementations'].append('Screen clearing')

    if 'forever' in js_code:
        existing_capabilities.add('continuous_loops')
        analysis['existing_implementations'].append('Continuous execution loops')

    if 'pause(' in js_code:
        existing_capabilities.add('timing_control')
        analysis['existing_implementations'].append('Timing delays')

    # === INPUT SENSORS ===
    if 'lightLevel()' in js_code:
        existing_capabilities.add('light_sensor')
        analysis['existing_implementations'].append('Light level sensing')

    if 'temperature()' in js_code:
        existing_capabilities.add('temperature_sensor')
        analysis['existing_implementations'].append('Temperature sensing')

    if 'soundLevel()' in js_code:
        existing_capabilities.add('sound_sensor')
        analysis['existing_implementations'].append('Sound level measurement')

    if 'compassHeading()' in js_code:
        existing_capabilities.add('compass')
        analysis['existing_implementations'].append('Compass heading')

    if 'acceleration(' in js_code:
        existing_capabilities.add('accelerometer')
        dimensions = re.findall(r'acceleration\(Dimension\.([XYZ])', js_code)
        analysis['existing_implementations'].append(f'Accelerometer: {", ".join(set(dimensions)) or "multiple axes"}')

    if 'runningTime()' in js_code:
        existing_capabilities.add('timing_measurement')
        analysis['existing_implementations'].append('Runtime measurement')

    if 'buttonIsPressed' in js_code:
        existing_capabilities.add('button_polling')
        buttons = re.findall(r'buttonIsPressed\(Button\.([AB]+)', js_code)
        analysis['existing_implementations'].append(f'Button state polling: {", ".join(set(buttons))}')

    # === PIN I/O ===
    if 'digitalReadPin' in js_code:
        existing_capabilities.add('digital_input')
        pins = re.findall(r'digitalReadPin\(DigitalPin\.([A-Z0-9]+)', js_code)
        analysis['existing_implementations'].append(f'Digital pin input: {", ".join(set(pins))}')

    if 'digitalWritePin' in js_code:
        existing_capabilities.add('digital_output')
        pins = re.findall(r'digitalWritePin\(DigitalPin\.([A-Z0-9]+)', js_code)
        analysis['existing_implementations'].append(f'Digital pin output: {", ".join(set(pins))}')

    if 'analogReadPin' in js_code:
        existing_capabilities.add('analog_input')
        pins = re.findall(r'analogReadPin\(AnalogPin\.([A-Z0-9]+)', js_code)
        analysis['existing_implementations'].append(f'Analog pin input: {", ".join(set(pins))}')

    if 'analogWritePin' in js_code:
        existing_capabilities.add('analog_output')
        pins = re.findall(r'analogWritePin\(AnalogPin\.([A-Z0-9]+)', js_code)
        analysis['existing_implementations'].append(f'Analog pin output: {", ".join(set(pins))}')

    # === RADIO COMMUNICATION ===
    if 'setGroup' in js_code:
        existing_capabilities.add('radio_setup')
        groups = re.findall(r'setGroup\((\d+)', js_code)
        analysis['existing_implementations'].append(f'Radio setup: group {", ".join(set(groups))}')

    if 'sendString' in js_code:
        existing_capabilities.add('radio_send_string')
        analysis['existing_implementations'].append('Radio string transmission')

    if 'sendNumber' in js_code:
        existing_capabilities.add('radio_send_number')
        analysis['existing_implementations'].append('Radio number transmission')

    if 'sendValue' in js_code:
        existing_capabilities.add('radio_send_value')
        analysis['existing_implementations'].append('Radio key-value transmission')

    if 'receivedString()' in js_code or 'receivedNumber()' in js_code or 'receivedSignalStrength()' in js_code:
        existing_capabilities.add('radio_receive_data')
        analysis['existing_implementations'].append('Radio data reception')

    # === MUSIC & SOUND ===
    if 'playTone' in js_code or 'ringTone' in js_code:
        existing_capabilities.add('tone_generation')
        analysis['existing_implementations'].append('Tone generation')

    if 'playMelody' in js_code:
        existing_capabilities.add('melody_playback')
        analysis['existing_implementations'].append('Melody playback')

    if 'music.play' in js_code:
        existing_capabilities.add('sound_effects')
        analysis['existing_implementations'].append('Sound effect playback')

    if 'setTempo' in js_code:
        existing_capabilities.add('tempo_control')
        analysis['existing_implementations'].append('Music tempo control')

    if 'stopAllSounds' in js_code:
        existing_capabilities.add('sound_control')
        analysis['existing_implementations'].append('Sound control')

    # === LED CONTROL ===
    if 'plot(' in js_code:
        existing_capabilities.add('led_plotting')
        analysis['existing_implementations'].append('Individual LED control')

    if 'unplot(' in js_code:
        existing_capabilities.add('led_unplotting')
        analysis['existing_implementations'].append('LED turning off')

    if 'toggle(' in js_code:
        existing_capabilities.add('led_toggling')
        analysis['existing_implementations'].append('LED toggling')

    if 'plotBarGraph' in js_code:
        existing_capabilities.add('bar_graphs')
        analysis['existing_implementations'].append('Bar graph visualization')

    if 'point(' in js_code:
        existing_capabilities.add('led_point_detection')
        analysis['existing_implementations'].append('LED point detection')

    # === ADVANCED CONTROL ===
    if 'inBackground' in js_code:
        existing_capabilities.add('background_tasks')
        analysis['existing_implementations'].append('Background task execution')

    if 'waitMicros' in js_code:
        existing_capabilities.add('precise_timing')
        analysis['existing_implementations'].append('Microsecond-precise timing')

    if 'reset()' in js_code:
        existing_capabilities.add('system_reset')
        analysis['existing_implementations'].append('System reset control')

    # === VARIABLES ===
    if re.search(r'let\s+\w+\s*=', js_code):
        existing_capabilities.add('variable_creation')
        analysis['existing_implementations'].append('Variable creation and management')

    # === LOGIC & MATH ===
    if '&&' in js_code and '||' in js_code:
        existing_capabilities.add('complex_logic')
        analysis['existing_implementations'].append('Complex logical operations (AND + OR)')
    elif '&&' in js_code:
        existing_capabilities.add('and_logic')
        analysis['existing_implementations'].append('AND logical operations')
    elif '||' in js_code:
        existing_capabilities.add('or_logic')
        analysis['existing_implementations'].append('OR logical operations')

    if 'Math.randomRange' in js_code or 'Math.random' in js_code:
        existing_capabilities.add('randomization')
        analysis['existing_implementations'].append('Random number generation')

    if 'Math.abs' in js_code or 'Math.min' in js_code or 'Math.max' in js_code:
        existing_capabilities.add('math_functions')
        analysis['existing_implementations'].append('Advanced math functions')

    # === LOOPS ===
    if 'for (' in js_code:
        existing_capabilities.add('for_loops')
        analysis['existing_implementations'].append('For loop structures')

    if 'while (' in js_code:
        existing_capabilities.add('while_loops')
        analysis['existing_implementations'].append('While loop structures')

    # === CONDITIONAL PATTERNS ===
    if 'if (' in js_code and '} else {' in js_code:
        existing_capabilities.add('if_else_branching')
        analysis['existing_implementations'].append('If-else conditional branching')
    elif 'if (' in js_code:
        existing_capabilities.add('simple_conditionals')
        analysis['existing_implementations'].append('Simple conditional statements')

    # === NUMERIC COMPLEXITY ===
    if len(re.findall(r'\b\d{3,}\b', js_code)) > 0:
        existing_capabilities.add('numeric_thresholds')
        thresholds = re.findall(r'\b(\d{3,})\b', js_code)
        analysis['existing_implementations'].append(f'Numeric thresholds: {", ".join(set(thresholds))}')

    # Store for suggestion generation
    analysis['existing_capabilities'] = existing_capabilities

    # Determine sophistication level based on variety and complexity
    if len(existing_capabilities) >= 6 and any(x in existing_capabilities for x in ['complex_logic', 'radio_setup', 'digital_input']):
        analysis['sophistication_level'] = 'expert'
        analysis['code_structure'] = 'highly_complex'
    elif len(existing_capabilities) >= 4 and any(x in existing_capabilities for x in ['or_logic', 'and_logic', 'radio_send']):
        analysis['sophistication_level'] = 'advanced'
        analysis['code_structure'] = 'complex'
    elif len(existing_capabilities) >= 2:
        analysis['sophistication_level'] = 'intermediate'
        analysis['code_structure'] = 'conditional'
    else:
        analysis['sophistication_level'] = 'beginner'

    return analysis

def compute_current_capabilities_from_analysis(analysis):
    """Compute a coarse capability set from the analysis dict."""
    current_capabilities = set()
    for action in analysis.get('actions', []):
        if 'read_digital_pin' in action or 'write_digital_pin' in action:
            current_capabilities.add('pin_io')
        elif 'send_radio_message' in action:
            current_capabilities.add('communication')
        elif 'show_icon' in action or 'show_number' in action:
            current_capabilities.add('visual_output')
        elif 'play_sound' in action or 'play_tone' in action:
            current_capabilities.add('audio_output')

    for sensor in analysis.get('sensors', []):
        if sensor in ['light', 'temperature', 'sound']:
            current_capabilities.add('environmental_sensing')
    if 'conditional' in analysis.get('logic', []):
        current_capabilities.add('conditional_logic')
    return current_capabilities

def compute_used_blocks_and_anchors(analysis):
    """Map analysis to blocks already used and extract plain-English anchors."""
    used_blocks = set()
    anchors = {
        'buttons': analysis.get('specific_details', {}).get('buttons_used', []) or [],
        'pins': analysis.get('pins', []) or [],
        'radio': bool(analysis.get('radio')),
        'displays': []
    }

    actions = set(analysis.get('actions', []))
    if 'show_icon' in actions:
        used_blocks.add('SHOW ICON'); anchors['displays'].append('icons')
    if 'show_number' in actions:
        used_blocks.add('SHOW NUMBER')
    if 'show_string' in actions:
        used_blocks.add('SHOW STRING')
    if 'send_radio_message' in actions or analysis.get('radio'):
        used_blocks.add('SEND STRING')
    if 'read_digital_pin' in actions:
        used_blocks.add('DIGITAL READ PIN')
    if 'write_digital_pin' in actions:
        used_blocks.add('DIGITAL WRITE PIN')
    if 'read_analog_pin' in actions:
        used_blocks.add('ANALOG READ PIN')
    if 'play_tone' in actions:
        used_blocks.add('PLAY TONE')
    if 'read_light' in actions:
        used_blocks.add('LIGHT LEVEL')
    if 'read_temperature' in actions:
        used_blocks.add('TEMPERATURE')

    return used_blocks, anchors

def adjacent_novel_blocks(used_blocks):
    """Suggest adjacent blocks that are novel relative to used_blocks."""
    adjacency = set()
    if 'SEND STRING' in used_blocks:
        adjacency.update(['SET GROUP', 'SEND NUMBER', 'GET A MESSAGE'])
    if 'SHOW ICON' in used_blocks or 'SHOW NUMBER' in used_blocks or 'SHOW STRING' in used_blocks:
        adjacency.update(['PLAY SOUND', 'SHOW LEDS'])
    if 'DIGITAL READ PIN' in used_blocks:
        adjacency.update(['DIGITAL WRITE PIN', 'ANALOG READ PIN'])
    if 'PLAY TONE' in used_blocks:
        adjacency.update(['PLAY MELODY'])
    # Always allow a couple of broadly useful novel actions
    adjacency.update(['PLAY SOUND'])
    return list(dict.fromkeys(adjacency))

def score_and_validate_idea(idea_text, extracted_blocks, used_blocks, anchors, adj_blocks, trigger_labels):
    """Score an idea for novelty and anchoring. Return (is_valid, score, reason)."""
    # Basic block sanity
    if not extracted_blocks:
        return False, -1, 'No blocks extracted'
    triggers = [b for b in extracted_blocks if b in trigger_labels]
    actions = [b for b in extracted_blocks if b not in trigger_labels]
    if len(triggers) != 1:
        return False, -1, 'Must include exactly one trigger'
    if not (2 <= len(extracted_blocks) <= 4):
        return False, -1, 'Must include 2-4 total blocks'

    # Novelty: at least one block not already used
    has_novel = any(b not in used_blocks for b in extracted_blocks)
    if not has_novel:
        return False, -1, 'Must include at least one novel block'

    # Anchoring: mention at least one concrete element from code (button, pin, radio)
    import re as _re
    text_wo_blocks = _re.sub(r'\([^)]+\)', '', idea_text or '').lower()
    mentions = 0
    if anchors.get('buttons'):
        for b in anchors['buttons']:
            if f"button {b.lower()}" in text_wo_blocks:
                mentions += 1
                break
    if anchors.get('pins'):
        for p in anchors['pins']:
            if f"pin {p.lower()}" in text_wo_blocks:
                mentions += 1
                break
    if anchors.get('radio') and 'radio message' in text_wo_blocks:
        mentions += 1
    if mentions == 0:
        return False, -1, 'Must reference a concrete element from the student\'s code (button, pin, or radio)'

    # Score by adjacency and specificity
    adj_bonus = sum(1 for b in extracted_blocks if b in adj_blocks)
    spec_bonus = int(any(b in used_blocks for b in actions)) + int(has_novel)
    score = 2 * adj_bonus + 3 * spec_bonus + mentions
    return True, score, ''

def deterministic_novel_idea(analysis, used_blocks, anchors):
    """Build a small, anchored, novel idea deterministically as a safe fallback."""
    # Choose a trigger phrase and block
    trigger_block = None
    if 'A' in anchors.get('buttons', []):
        trigger_block = 'ON BUTTON A'
        trigger_phrase = 'button A'
    elif 'B' in anchors.get('buttons', []):
        trigger_block = 'ON BUTTON B'
        trigger_phrase = 'button B'
    elif 'AB' in anchors.get('buttons', []):
        trigger_block = 'ON BUTTON AB'
        trigger_phrase = 'both buttons'
    else:
        trigger_block = 'ON SHAKE'
        trigger_phrase = 'when you shake the micro:bit'

    pin_phrase = None
    if anchors.get('pins'):
        pin_phrase = anchors['pins'][0]

    # Pick a novel action
    candidates = ['PLAY SOUND', 'SHOW STRING', 'SET GROUP', 'SEND NUMBER', 'DIGITAL WRITE PIN']
    novel = next((b for b in candidates if b not in used_blocks), 'PLAY SOUND')

    if pin_phrase:
        idea = f"What if you also added a short sound when you press {trigger_phrase}, so there's audio feedback when the {pin_phrase} reading is low? ({trigger_block}) ({novel}) (SHOW ICON)"
    else:
        idea = f"What if you also added a short sound when you press {trigger_phrase}, so there's audio feedback for your action? ({trigger_block}) ({novel}) (SHOW ICON)"

    blocks = [trigger_block, novel, 'SHOW ICON']
    return {"idea": idea, "blocks": blocks}


def generate_context_aware_suggestion_prompts(analysis, js_code):
    """
    Generate sophisticated suggestions that avoid what the user is already doing
    and introduce genuinely novel micro:bit capabilities.
    """
    available_labels, trigger_labels, action_labels, blocks_info = get_cached_block_mappings()
    # Compute current capabilities locally to avoid undefined references
    current_capabilities = compute_current_capabilities_from_analysis(analysis)

    # Get what they're already implementing
    existing_capabilities = analysis.get('existing_capabilities', set())
    existing_implementations = analysis.get('existing_implementations', [])
    sophistication_level = analysis.get('sophistication_level', 'beginner')

    # Define all micro:bit capabilities
    all_capabilities = {
        # Sensors they might not be using
        'accelerometer': ['ACCELEROMETER X', 'ACCELEROMETER Y', 'ACCELEROMETER Z', 'ON SHAKE'],
        'light_sensor': ['LIGHT LEVEL'],
        'temperature_sensor': ['TEMPERATURE'],
        'sound_sensor': ['SOUND LEVEL', 'HEAR LOUD SOUND', 'HEAR QUIET SOUND'],
        'compass': ['COMPASS HEADING'],

        # Advanced input methods
        'gesture_detection': ['ON SHAKE', 'ON SCREEN UP', 'ON SCREEN DOWN', 'ON LOGO UP', 'ON LOGO DOWN'],
        'pin_touch': ['ON PIN PRESSED', 'ON PIN RELEASED'],

        # Advanced outputs
        'custom_led_patterns': ['SHOW LEDS'],
        'audio_advanced': ['PLAY MELODY', 'PLAY TONE'],
        'analog_output': ['ANALOG WRITE PIN'],

        # Communication
        'radio_receive': ['GET A MESSAGE', 'GET A NUMBER', 'GET A VALUE'],
        'radio_advanced': ['SEND VALUE', 'RECEIVED SIGNAL'],

        # Control flow
        'loops': ['FOREVER'],
        'timing': ['PAUSE']
    }

    # Find capabilities they haven't used yet
    unused_capabilities = []
    for capability, blocks in all_capabilities.items():
        if not any(cap in existing_capabilities for cap in [capability, capability.replace('_', '_')]):
            unused_capabilities.append((capability, blocks))

    print(f"DEBUG: User is already using {len(existing_capabilities)} capabilities: {sorted(existing_capabilities)}")
    print(f"DEBUG: Found {len(unused_capabilities)} unused capabilities they could explore")

    # Create sophisticated suggestions based on what they haven't tried
    suggestion_templates = []

    # Now create smart combinations of unused capabilities
    if unused_capabilities:
        suggestion_templates.append({
            'context': 'sensor_network',
            'prompt_focus': 'Create a sensor network where multiple micro:bits share sensor data',
            'novel_combinations': ['DIGITAL READ PIN + SEND NUMBER', 'ANALOG READ PIN + SET GROUP', 'GET A NUMBER + DIGITAL WRITE PIN'],
            'specific_context': f"Since you're using pins {analysis.get('pins', ['P0'])}, you could network multiple devices",
            'complexity_level': 'advanced'
        })

    # Environmental feedback loops
    if 'environmental_sensing' in current_capabilities and 'pin_io' not in current_capabilities:
        suggestion_templates.append({
            'context': 'smart_environment',
            'prompt_focus': 'Create an environmental control system that responds to conditions',
            'novel_combinations': ['LIGHT LEVEL + DIGITAL WRITE PIN', 'TEMPERATURE + ANALOG WRITE PIN', 'SOUND LEVEL + SHOW LEDS'],
            'specific_context': f"Your environmental sensing could control external devices through pins",
            'complexity_level': 'intermediate'
        })

    # Multi-modal interaction patterns
    if 'visual_output' in current_capabilities and 'audio_output' not in current_capabilities:
        suggestion_templates.append({
            'context': 'rich_feedback',
            'prompt_focus': 'Add audio feedback to create richer sensory experiences',
            'novel_combinations': ['ON SHAKE + PLAY MELODY', 'LIGHT LEVEL + PLAY TONE', 'GET A MESSAGE + PLAY SOUND'],
            'specific_context': f"Your visual displays could be enhanced with coordinated sounds",
            'complexity_level': 'beginner'
        })

    # Gesture-based system control
    if len(analysis.get('triggers', [])) <= 1:
        suggestion_templates.append({
            'context': 'gesture_interface',
            'prompt_focus': 'Create gesture-based interfaces using motion sensors',
            'novel_combinations': ['ON SHAKE + SEND STRING', 'ON LOGO UP + DIGITAL WRITE PIN', 'ON SCREEN DOWN + SHOW LEDS'],
            'specific_context': f"Expand beyond {analysis.get('triggers', ['basic buttons'])} to gesture controls",
            'complexity_level': 'intermediate'
        })

    # Data logging and monitoring
    if 'communication' in current_capabilities and 'environmental_sensing' in current_capabilities:
        suggestion_templates.append({
            'context': 'data_monitoring',
            'prompt_focus': 'Build a distributed monitoring system with data sharing',
            'novel_combinations': ['TEMPERATURE + SEND VALUE', 'GET A VALUE + SHOW NUMBER', 'LIGHT LEVEL + RECEIVED SIGNAL'],
            'specific_context': f"Create a network of sensors that share and display environmental data",
            'complexity_level': 'advanced'
        })

    # Interactive gaming/collaborative systems
    if 'communication' not in current_capabilities and len(analysis.get('triggers', [])) >= 2:
        suggestion_templates.append({
            'context': 'multiplayer_interaction',
            'prompt_focus': 'Create interactive games or collaborative systems between micro:bits',
            'novel_combinations': ['ON BUTTON A + SEND STRING', 'GET A MESSAGE + SHOW ICON', 'ON SHAKE + SEND NUMBER'],
            'specific_context': f"Your button interactions could become multiplayer experiences",
            'complexity_level': 'intermediate'
        })

    # Return the most relevant suggestion template
    if suggestion_templates:
        # Pick the template that best matches current capability level
        if len(current_capabilities) >= 3:
            template = next((t for t in suggestion_templates if t['complexity_level'] == 'advanced'), suggestion_templates[0])
        elif len(current_capabilities) >= 2:
            template = next((t for t in suggestion_templates if t['complexity_level'] == 'intermediate'), suggestion_templates[0])
        else:
            template = next((t for t in suggestion_templates if t['complexity_level'] == 'beginner'), suggestion_templates[0])

        return template

    # Fallback for completely novel approaches
    return {
        'context': 'exploration',
        'prompt_focus': 'Explore new micro:bit capabilities you haven\'t used yet',
        'novel_combinations': ['ON SHAKE + PLAY MELODY', 'LIGHT LEVEL + DIGITAL WRITE PIN', 'GET A MESSAGE + SHOW LEDS'],
        'specific_context': 'Try combining sensors with outputs for responsive behaviors',
        'complexity_level': 'beginner'
    }

def get_cache_stats():
    # Caching disabled
    return {"disabled": True}


def get_chat_system_prompt(chat_type, js_code, context):
    """Generate appropriate system prompt based on chat type"""
    
    base_prompt = (
        "You are an enthusiastic, friendly micro:bit mentor for middle school students (ages 12-14). "
        "You help students learn programming concepts and debug their micro:bit code. "
        "Use encouraging, simple language that's easy to understand. "
        "Be excited about their projects and use emojis occasionally to keep things fun! "
        "Always reference specific parts of their code when giving advice. "
        "Keep explanations short and clear - avoid overwhelming them with too much information at once. "
        "FORMATTING: Use line breaks (\\n) between different ideas or questions. Write in short, clear sentences. Never write one long paragraph."
    )
    
    if chat_type == "debug":
        return base_prompt + (
            "\n\nDEBUGGING MODE: The student is having trouble with their code. "
            "Help them figure out what's going wrong in a fun, encouraging way! "
            "Look for common issues like:\n"
            "- Missing pieces or typos in their code\n"
            "- Logic mix-ups (like using the wrong button or condition)\n"
            "- Hardware connections (are their pins hooked up right?)\n"
            "- Radio communication between micro:bits\n\n"
            "Break it down into simple steps and ask them what they expected vs. what actually happened. "
            "Remind them that debugging is totally normal - even professional programmers do it! 🐛✨\n\n"
            "FORMATTING: Use line breaks (\\n) between different ideas or questions. Write in short, clear sentences. Never write one long paragraph."
        )
    
    elif chat_type == "explain":
        return base_prompt + (
            "\n\nEXPLANATION MODE: The student wants to understand how their code works. "
            "Break down their code into simple, understandable parts. Explain:\n"
            "- What each section does\n"
            "- How the different parts work together\n"
            "- Why certain programming concepts are used\n"
            "- How the micro:bit hardware interacts with the code\n\n"
            "Use analogies when helpful. Make sure they understand the 'why' behind the code, not just the 'what'.\n\n"
            "FORMATTING: Use line breaks (\\n) between different ideas or questions. Write in short, clear sentences. Never write one long paragraph."
        )
    
    elif chat_type == "improve":
        return base_prompt + (
            "\n\nIMPROVEMENT MODE: The student wants to make their project even cooler! "
            "Suggest awesome new features they can add like:\n"
            "- New sensors (light, sound, temperature)\n"
            "- Fun outputs (sounds, LED patterns, messages to other micro:bits)\n"
            "- Interactive elements (buttons, gestures, touch)\n"
            "- Making their code work better or faster\n"
            "- Adding new behaviors and features\n\n"
            "Get them excited about what they can build! Show them how to add to their existing code rather than starting over. "
            "Make suggestions that are fun and achievable for their skill level! 🚀\n\n"
            "EXAMPLE FORMAT: Start with enthusiasm, then ask what they want to add, then suggest specific ideas with line breaks between each idea.\n\n"
            "FORMATTING: Use line breaks (\\n) between different ideas or questions. Write in short, clear sentences. Never write one long paragraph."
        )
    
    elif chat_type == "learn_block":
        block_name = context.get("block", "a block")
        return base_prompt + (
            f"\n\nBLOCK LEARNING MODE: The student wants to learn about {block_name}. "
            "Provide comprehensive information including:\n"
            "- What the block does\n"
            "- How to use it in different situations\n"
            "- Common parameters or settings\n"
            "- Examples of how it works with other blocks\n"
            "- Practical projects they could try\n\n"
            "Make it engaging and show them how this block fits into bigger programming concepts.\n\n"
            "FORMATTING: Use line breaks (\\n) between different ideas or questions. Write in short, clear sentences. Never write one long paragraph."
        )
    
    elif chat_type == "narrative":
        return base_prompt + (
            "\n\nNARRATIVE ALIGNMENT MODE: The student wants their code to tell the story they have in mind! "
            "Help them understand:\n"
            "- What their code is actually doing right now\n"
            "- How to change it to match their awesome story idea\n"
            "- What new parts they might need to add\n"
            "- How to make their micro:bit behave the way they want\n\n"
            "Get excited about their story ideas! Help them figure out how to make their code match their creative vision. "
            "Ask them about the cool story they're trying to tell! 🎭✨\n\n"
            "EXAMPLE FORMAT: Start by asking about their story, then explain what the code does now, then suggest how to change it, with line breaks between each part.\n\n"
            "FORMATTING: Use line breaks (\\n) between different ideas or questions. Write in short, clear sentences. Never write one long paragraph."
        )
    
    else:  # general
        return base_prompt + (
            "\n\nGENERAL HELP MODE: The student has a question about their micro:bit project! "
            "Be super helpful and encouraging. If they're asking about:\n"
            "- How something works: Explain it simply with fun examples\n"
            "- What to try next: Suggest cool next steps they can take\n"
            "- Problems they're having: Help them figure it out step by step\n"
            "- New ideas: Get excited and help them explore!\n\n"
            "Remember - learning to code is awesome but can be tricky sometimes. Be patient and celebrate their progress! 🎉\n\n"
            "FORMATTING: Use line breaks (\\n) between different ideas or questions. Write in short, clear sentences. Never write one long paragraph."
        )


def generate_chat_response(chat_type, user_message, js_code, context):
    """Generate a chat response using LM Studio"""
    try:
        client = OpenAI(
            base_url=LM_STUDIO_BASE_URL,
            api_key=LM_STUDIO_API_KEY
        )
        
        system_prompt = get_chat_system_prompt(chat_type, js_code, context)
        
        # Add context information for learn_block type
        context_info = ""
        if chat_type == "learn_block" and context:
            block_name = context.get("block", "")
            category = context.get("category", "")
            description = context.get("description", "")
            if block_name:
                context_info = f"\n\nCONTEXT: The student is asking about the '{block_name}' block from the {category} category. Block description: {description}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"STUDENT'S CODE:\n```javascript\n{js_code}\n```{context_info}\n\nSTUDENT'S QUESTION: {user_message}"}
        ]
        
        response = client.chat.completions.create(
            model="meta-llama-3.1-8b-instruct",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"Error generating chat response: {e}")
        return "I'm having trouble connecting right now. Please try again in a moment!"

# AI analyzes each student's code individually for personalized feedback

# Helper to execute the vision processor reliably (keeps code_file.js intact on errors)
def _execute_vision_processor(image_path: str):
    """Run vision_processor.py; return (ok, stdout, stderr, returncode)."""
    if not image_path or not os.path.exists(image_path):
        return False, "", f"Image not found: {image_path}", 2
    try:
        python_executable = sys.executable
        result = subprocess.run(
            [python_executable, "vision_processor.py", image_path],
            check=False,
            capture_output=True,
        )
        ok = result.returncode == 0
        stdout = result.stdout.decode("utf-8", errors="ignore")
        stderr = result.stderr.decode("utf-8", errors="ignore")
        return ok, stdout, stderr, result.returncode
    except Exception as e:
        return False, "", str(e), 1


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_blocks_from_idea(idea_text, available_labels):
    """
    Extract block labels from idea text by finding parenthesized tokens.
    
    Args:
        idea_text (str): The idea text containing block references in parentheses
        available_labels (list): List of valid block labels to match against
        
    Returns:
        list: List of valid block labels found in the idea text
    """
    if not isinstance(idea_text, str):
        return []
    
    # Build a lowercase index for case-insensitive matching
    label_index_lower = {label.lower(): label for label in available_labels}
    
    # Find all parenthesized tokens
    paren_tokens = []
    start = 0
    while True:
        i = idea_text.find("(", start)
        if i == -1:
            break
        j = idea_text.find(")", i + 1)
        if j == -1:
            break
        token = idea_text[i + 1:j].strip()
        if token:
            paren_tokens.append(token)
        start = j + 1
    
    # Normalize tokens to available labels
    extracted_blocks = []
    for token in paren_tokens:
        # Direct case-insensitive match
        direct_match = label_index_lower.get(token.lower())
        if direct_match:
            extracted_blocks.append(direct_match)
            continue
            
        # Try uppercase normalization for common variations
        normalized = re.sub(r"\s+", " ", token.upper())
        
        # Common trigger phrasing normalizations
        normalized = re.sub(r"^ON\s+PRESS(?:ED)?\s+(?:BUTTON\s+)?(A|B|AB)$", r"ON BUTTON \1", normalized)
        normalized = re.sub(r"^(?:PRESS|PRESSED)\s+(?:BUTTON\s+)?(A|B|AB)$", r"ON BUTTON \1", normalized)
        normalized = re.sub(r"^(?:WHEN\s+YOU\s+PRESS|WHEN\s+PRESSED)\s+(?:BUTTON\s+)?(A|B|AB)$", r"ON BUTTON \1", normalized)
        
        # Minor typos: ON BUTTON AA -> ON BUTTON AB
        if normalized == "ON BUTTON AA":
            normalized = "ON BUTTON AB"
        
        # Check if normalized version matches
        if normalized in available_labels:
            extracted_blocks.append(normalized)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_blocks = []
    for block in extracted_blocks:
        if block not in seen:
            unique_blocks.append(block)
            seen.add(block)
    
    return unique_blocks


def generate_ai_suggestions(js_code):
    """
    Generate AI suggestions for student code using LM Studio with structured output.
    
    This function connects to a local LM Studio server, sends the student's JavaScript code
    to an AI model, and receives structured suggestions in JSON format. The AI provides
    encouraging feedback, creative ideas, and specific MakeCode blocks to explore.
    
    Args:
        js_code (str): The JavaScript code generated from the student's block image
        
    Returns:
        dict: Structured response containing:
            - encouragement (str): Friendly, age-appropriate encouragement message
            - idea (str): One creative question-based idea for the student to try next
            - blocks (list): 2-4 MakeCode block suggestions as strings
    """
    try:
        
        # Analyze the student's code for targeted suggestions
        analysis = analyze_student_code(js_code)
        print(f"Code analysis: {analysis}")
        used_blocks, anchors = compute_used_blocks_and_anchors(analysis)
        adj_blocks = adjacent_novel_blocks(used_blocks)
        current_capabilities = compute_current_capabilities_from_analysis(analysis)

        # Generate context-aware suggestion template
        suggestion_context = generate_context_aware_suggestion_prompts(analysis, js_code)
        print(f"Suggestion context: {suggestion_context['context']} ({suggestion_context['complexity_level']})")

        # Initialize OpenAI client to connect to local LM Studio server
        client = OpenAI(
            base_url=LM_STUDIO_BASE_URL,
            api_key=LM_STUDIO_API_KEY
        )
        
        # We'll prefer function calling; keep a lightweight schema only for fallback
        response_schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "suggestion_response",
                "strict": "true",
                "schema": {
                    "type": "object",
                    "properties": {
                        "encouragement": {"type": "string"},
                        "idea": {"type": "string"}
                    },
                    "required": ["encouragement", "idea"]
                }
            }
        }
        
        # Load cached block mappings (labels and informational text)
        available_labels, trigger_labels, action_labels, blocks_info = get_cached_block_mappings()
        # Prepare a compact analysis summary to ground the model in the student's actual code
        analysis_summary = {
            "actions": analysis.get("actions", []),
            "sensors": analysis.get("sensors", []),
            "pins": analysis.get("pins", []),
            "control_structures": analysis.get("control_structures", []),
            "variables": analysis.get("variables", []),
            "flags": analysis.get("flags", {}),
            "details": analysis.get("specific_details", {})
        }

        # Create conversation messages (improved prompt for question-based ideas)
        user_content_parts = [
            "ADVANCED MICRO:BIT EXTENSION CHALLENGE\n",
            f"CONTEXT: {suggestion_context['context'].upper()} ({suggestion_context['complexity_level']} level)\n",
            f"FOCUS: {suggestion_context['prompt_focus']}\n",
            f"STUDENT CONTEXT: {suggestion_context['specific_context']}\n\n",

            "NOVEL BLOCK COMBINATIONS TO EXPLORE:\n",
            f"- {chr(10).join(['• ' + combo for combo in suggestion_context['novel_combinations']])}\n\n",
            "NOVELTY AND ANCHORING POLICY:\n",
            "- Include at least one block the student has NOT used yet (novel block).\n",
            "- Mention at least one concrete element from their code in plain English (e.g., 'button A', 'pin P0', 'radio message').\n",
            "- Prefer keeping the same trigger they already use; you may introduce a closely related trigger only if it clearly builds on their logic.\n",
            f"- Blocks already used: {', '.join(sorted(used_blocks)) or 'None'}\n",
            f"- Adjacent novel blocks to consider: {', '.join(adj_blocks) or 'None'}\n\n",

            "TASK:\n",
            "- Generate ONE creative 'What if' question that suggests a NOVEL, SOPHISTICATED extension\n",
            "- Reference EXACTLY 3-4 blocks from the available list using (BLOCK NAME) format\n",
            "- Make suggestions that are SPECIFIC to their current code patterns\n",
            "- Encourage CROSS-SYSTEM interactions (sensors + actuators, local + networked, etc.)\n",
            "- Push beyond basic patterns toward multi-device, environmental, or interactive systems\n",
            "- CRITICAL: Sentence must be grammatically correct without parentheses\n\n",

            "CURRENT CODE ANALYSIS:\n",
            f"Capabilities: {', '.join(current_capabilities) if current_capabilities else 'Basic interactions'}\n",
            f"Pins used: {', '.join(analysis.get('pins', ['None']))}\n",
            f"Sensors: {', '.join(analysis.get('sensors', ['None']))}\n",
            f"Actions: {', '.join(analysis.get('actions', ['Basic display']))}\n",
            f"Logic complexity: {analysis.get('code_structure', 'simple')}\n\n",
        ]
        user_content_parts.append(blocks_info)
        user_content_parts.append("STUDENT'S CODE:\n")
        user_content_parts.append(f"```javascript\n{js_code}\n```")
        user_content = "".join(user_content_parts)

        # Few-shot exemplars to demonstrate anchored novelty
        exemplars = [
            {
                "role": "user",
                "content": (
                    "EXEMPLAR\n\n"
                    "Student code uses button A with SHOW ICON and reads pin P0; sends a radio string.\n"
                    "Goal: Suggest a novel block and mention button A or pin P0."
                )
            },
            {
                "role": "assistant",
                "content": (
                    "What if you also played a short sound when you press button A, so there's audio feedback when the P0 reading is low? (ON BUTTON A) (PLAY SOUND) (SHOW ICON)"
                )
            },
            {
                "role": "user",
                "content": (
                    "EXEMPLAR\n\n"
                    "Student code sends a radio string on a condition but doesn't set group.\n"
                    "Goal: Keep the same trigger and add a related radio setup block; mention 'radio message'."
                )
            },
            {
                "role": "assistant",
                "content": (
                    "How about setting a team group first so your radio message reaches only your partners when you press button A? (ON BUTTON A) (SET GROUP) (SEND STRING)"
                )
            }
        ]

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an enthusiastic micro:bit mentor for middle school students (ages 12-14). "
                    "Your job: 1) Give specific, encouraging feedback about what their code does, 2) Suggest one creative, question-based IDEA that builds on their current code. "
                    "Analyze their code carefully and mention specific details like: "
                    "- Which buttons they're using (Button A, B, or both) "
                    "- What sensors they're reading (light, temperature, sound, etc.) "
                    "- What displays they're showing (specific icons, text, LED patterns) "
                    "- What conditions they're checking (if/else logic, comparisons) "
                    "- What actions they're taking (radio messages, sounds, displays) "
                    "- What pins they're using (P0, P1, P2 for digital/analog I/O) "
                    "Use enthusiastic, age-appropriate language. Show you understand their specific programming choices and logic. "
                    "For the IDEA: Analyze their specific code and create a unique question that helps them brainstorm next steps. "
                    "Look at what they're already doing (buttons, sensors, displays, conditions, actions) and suggest something that builds on it. "
                    "DO NOT start with 'Idea to Try:' or 'Try this:' - just start with the question directly. "
                    "Include block references in parentheses using EXACT labels from the available blocks list. "
                    "CRITICAL: The sentence must make complete grammatical sense when the parenthesized block names are removed. "
                    "Make sure to include BOTH a trigger (like ON BUTTON A, ON SHAKE, GET A MESSAGE, ON PIN PRESSED) AND an action (like SHOW ICON, PLAY SOUND, DIGITAL WRITE PIN, SEND STRING) in your idea. "
                    "Important: Use ONLY the exact labels from the lists. Do NOT output API names, category prefixes, or pseudonames (e.g., 'basic.showIcon', 'IconNames.Yes', 'light.on'). "
                    "Use 'ON BUTTON A/B/AB' (not 'ON PRESS ...'). "
                    "Novelty rule: Include at least one block the student has not used yet. "
                    "Anchoring rule: Mention at least one concrete element from their code in plain English (e.g., 'button A', 'pin P0', 'radio message'). "
                    "Preference: Keep the same trigger if possible; closely related triggers are okay if clearly connected. "
                    "MICRO:BIT HARDWARE CONTEXT: The micro:bit has 3 GPIO pins (P0, P1, P2) for connecting sensors, LEDs, motors, and other components. "
                    "Pins can read digital values (0/1) or analog values (0-1023), and write digital (0/1) or analog (0-1023) signals. "
                    "Safe pin usage: P0-P2 are 3.3V tolerant; avoid short circuits; use appropriate resistors for LEDs. "
                    "Radio allows wireless communication between micro:bits within ~10m range. "
                    "Make your encouragement specific to their code and your idea creative and engaging! "
                    "Length: Encouragement 1-2 sentences. IDEA should be 30-60 words (1-2 sentences), concrete and specific."
                )
            },
            *exemplars,
            {
                "role": "user",
                "content": user_content
            }
        ]

        # Define a function for tool calling to return the structured suggestion
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "suggest",
                    "description": "Return encouragement and one unique question-based idea that builds on their specific code. Include 3-4 block references in parentheses using exact labels from the available blocks list (at least 1 trigger and 2+ actions). The idea must include at least one novel block not present in the student's current code and must mention at least one concrete element from their code in plain English (e.g., 'button A', 'pin P0', 'radio message').",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "encouragement": {"type": "string"},
                            "idea": {"type": "string", "description": "Question starting with 'What if' or 'How about' containing 3-4 block labels in parentheses (e.g., (ON BUTTON A), (SHOW ICON), (PLAY SOUND), (SEND STRING)). The sentence must make complete grammatical sense when the parenthesized block names are removed. Use 'ON BUTTON A/B/AB' not 'ON PRESS ...'. Base it on their actual code."}
                        },
                        "required": ["encouragement", "idea"]
                    }
                }
            }
        ]
        
        # Send request to LM Studio with structured output enforcement
        # The response_format parameter ensures the AI returns valid JSON matching our schema
        response = client.chat.completions.create(
            model="meta-llama-3.1-8b-instruct",
            messages=messages,
            tools=tools,
            tool_choice="required",
            response_format=response_schema,  # Fallback if tool calling not honored
            temperature=0.6,  # More creative and specific
            stream=False,
            max_tokens=320  # Allow more detailed ideas
        )
        
        # Parse tool call if present, otherwise parse JSON content
        msg = response.choices[0].message
        if getattr(msg, "tool_calls", None):
            call = msg.tool_calls[0]
            args = call.function.arguments if hasattr(call, "function") else call.get("function", {}).get("arguments")
            result = json.loads(args)
        else:
            result = json.loads(msg.content)

        # Helper to split blocks into triggers vs actions
        def split_trigger_action(labels):
            triggers = [l for l in labels if l in trigger_labels]
            actions = [l for l in labels if l not in trigger_labels]
            return triggers, actions

        # Safety net: ensure unique blocks and cap to 4 items while preserving order
        def dedupe_blocks(blocks_list):
            seen_labels_local = set()
            return [
                label for label in blocks_list
                if isinstance(label, str) and not (label in seen_labels_local or seen_labels_local.add(label))
            ][:4]

        # Validation: require exactly 1 trigger and at least 1 action, 2–4 total, and blocks mentioned in IDEA
        def is_alignment_ok(suggestion):
            if not isinstance(suggestion, dict) or not isinstance(suggestion.get("blocks"), list):
                return False
            triggers, actions = split_trigger_action(suggestion["blocks"])
            total = len(suggestion["blocks"])
            if not (len(triggers) == 1 and len(actions) >= 1 and 2 <= total <= 4):
                return False
            idea_text_local = str(suggestion.get("idea", ""))
            for label in suggestion["blocks"]:
                if f"({label})" not in idea_text_local:
                    return False
            return True

        if isinstance(result, dict):
            # Extract blocks from the idea text using our new function
            idea_text = str(result.get("idea", ""))
            
            # Clean up any remaining prefixes
            idea_text = idea_text.replace("Idea to Try: ", "").replace("Try this: ", "").strip()
            
            # Validate that the sentence makes sense without parentheses
            import re
            text_without_blocks = re.sub(r'\([^)]+\)', '', idea_text).strip()
            # Remove extra spaces
            text_without_blocks = re.sub(r'\s+', ' ', text_without_blocks)
            print(f"DEBUG: Idea without blocks: '{text_without_blocks}'")
            
            result["idea"] = idea_text
            
            # Safety check: ensure we have available labels
            if not available_labels:
                print("WARNING: No available labels loaded, using fallback")
                result["blocks"] = ["ON BUTTON A", "SHOW ICON"]
                return result
            
            extracted_blocks = extract_blocks_from_idea(idea_text, available_labels)
            print(f"DEBUG: Extracted blocks from idea '{idea_text}': {extracted_blocks}")
            is_valid, score, reason = score_and_validate_idea(idea_text, extracted_blocks, used_blocks, anchors, adj_blocks, trigger_labels)
            print(f"DEBUG: Idea validation -> valid={is_valid}, score={score}, reason='{reason}'")
            
            # Validate the extracted blocks
            if extracted_blocks:
                triggers, actions = split_trigger_action(extracted_blocks)
                if is_valid and len(triggers) >= 1 and len(actions) >= 2 and 3 <= len(extracted_blocks) <= 4:
                    result["blocks"] = extracted_blocks
                else:
                    # If extraction doesn't meet constraints, try a corrective retry
                    corrective_messages = messages + [
                        {
                            "role": "user",
                            "content": (
                                "FIX ALIGNMENT\n"
                                "Your idea should reference 3-4 blocks total: at least ONE trigger and 2+ actions from the available blocks. "
                                "Make sure to include the block labels in parentheses in your idea.\n"
                                "Include at least ONE novel block not already used by the student, and mention a concrete element from their code like 'button A', 'pin P0', or 'radio message'.\n"
                                f"TRIGGERS: {', '.join(trigger_labels)}\n"
                                f"ACTIONS: {', '.join(action_labels)}\n"
                            )
                        }
                    ]
                    retry = client.chat.completions.create(
                        model="meta-llama-3.1-8b-instruct",
                        messages=corrective_messages,
                        tools=tools,
                        tool_choice="required",
                        response_format=response_schema,
                        temperature=0.1,
                        stream=False,
                        max_tokens=150
                    )
                    retry_msg = retry.choices[0].message
                    if getattr(retry_msg, "tool_calls", None):
                        rcall = retry_msg.tool_calls[0]
                        rargs = rcall.function.arguments if hasattr(rcall, "function") else rcall.get("function", {}).get("arguments")
                        retry_result = json.loads(rargs)
                    else:
                        retry_result = json.loads(retry_msg.content)
                    
                    # Extract blocks from retry result
                    retry_idea_text = str(retry_result.get("idea", ""))
                    retry_extracted_blocks = extract_blocks_from_idea(retry_idea_text, available_labels)
                    is_valid_retry, score_retry, reason_retry = score_and_validate_idea(retry_idea_text, retry_extracted_blocks, used_blocks, anchors, adj_blocks, trigger_labels)
                    print(f"DEBUG: Retry idea validation -> valid={is_valid_retry}, score={score_retry}, reason='{reason_retry}'")
                    if retry_extracted_blocks and is_valid_retry:
                        retry_result["blocks"] = retry_extracted_blocks
                        return retry_result
                    
                    # Final fallback: deterministic anchored-novel idea
                    fallback = deterministic_novel_idea(analysis, used_blocks, anchors)
                    print("DEBUG: Using deterministic fallback idea")
                    return {
                        "encouragement": result.get("encouragement", "Great job on your code!"),
                        "idea": fallback["idea"],
                        "blocks": fallback["blocks"]
                    }
            else:
                # No blocks extracted, provide fallback
                fallback = deterministic_novel_idea(analysis, used_blocks, anchors)
                result["idea"] = fallback["idea"]
                result["blocks"] = fallback["blocks"]

        return result
        
    except Exception as e:
        # Handle any errors gracefully with fallback suggestions
        # This ensures the app continues working even if LM Studio is unavailable
        print(f"Error generating AI suggestions: {e}")
        fallback_response = {
            "encouragement": "Great job on your code!",
            "idea": "What if you added some sound effects when you press a button and then sent a message to other devices?",
            "blocks": ["ON BUTTON A", "PLAY SOUND", "SEND STRING", "SHOW ICON"]
        }
        return fallback_response





@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if "file" not in request.files:
            return render_template(
                "code_box.html", js_content="pp", error="No file provided"
            )

        file = request.files["file"]

        if file.filename == "" or not allowed_file(file.filename):
            return render_template(
                "code_box.html", js_content="oo", error="Invalid file type"
            )

        file_path = os.path.join(
            app.config["UPLOAD_FOLDER"], secure_filename(file.filename)
        )
        # Clear previous generated code immediately to avoid stale reads
        _write_placeholder_code()
        file.save(file_path)
        print("File saved at:", file_path)
        # Persist path in session for this user
        session['file_path'] = file_path

    return render_template("code_box.html")


 


@app.route("/process_image_path", methods=["POST"])
def process_image_path():
    if "file" not in request.files:
        return jsonify({"error": "No file part"})

    file = request.files["file"]
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        # Clear previous generated code immediately to avoid stale reads
        _write_placeholder_code()
        file.save(file_path)
        print("File saved at:", file_path)
        # Persist path in session for this user
        session['file_path'] = file_path
        
        # Process the image and fail fast if OCR/codegen fails
        ok, out, err, code = _execute_vision_processor(file_path)
        if not ok:
            return jsonify({
                "error": "Processing failed",
                "details": err or out,
                "exit_code": code
            }), 500

        return jsonify({"message": "File uploaded and processed", "path": file_path})
    else:
        return jsonify({"error": "Invalid file type"})


@app.route("/get_js_content", methods=["GET"])
def get_js_content():
    # Require a current uploaded image in this session before serving code
    current_path = session.get('file_path')
    if not current_path:
        return ("No image uploaded in this session. Please upload or capture an image first.", 400)

    code_path = CODE_FILE_PATH
    if not os.path.exists(code_path):
        return ("No generated code yet. Upload an image first to generate MakeCode.", 404)
    try:
        with open(code_path, "r") as file:
            js_content = file.read()
        # Add no-cache headers to prevent stale browser caching
        response = make_response(js_content)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except Exception as e:
        print(f"Error reading file: {e}")
        return str(e), 500


@app.route("/generate_suggestions", methods=["POST"])
def generate_suggestions():
    """Generate AI suggestions for the current generated code"""
    try:
        # Read the current generated code from the file
        with open("static/code_file.js", "r") as file:
            js_code = file.read()
        
        # Generate AI suggestions using the code
        suggestions = generate_ai_suggestions(js_code)
        
        return jsonify({
            "success": True,
            "suggestions": suggestions
        })
        
    except Exception as e:
        print(f"Error generating suggestions: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500






@app.route("/generate_encouragement_stream", methods=["POST"])
def generate_encouragement_stream():
    """Generate encouragement with streaming for word-by-word display"""
    try:
        with open("static/code_file.js", "r") as file:
            js_code = file.read()

        def generate():
            try:

                client = OpenAI(
                    base_url=LM_STUDIO_BASE_URL,
                    api_key=LM_STUDIO_API_KEY
                )

                response_schema = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "encouragement_response",
                        "strict": "true",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "encouragement": {"type": "string"}
                            },
                            "required": ["encouragement"]
                        }
                    }
                }

                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are an enthusiastic micro:bit mentor for middle school students (ages 12-14). "
                            "Give SHORT, specific encouragement (1-2 sentences max) that shows you understand their code. "
                            "Be precise about what their code actually does: "
                            "- pins.digitalReadPin() reads digital values (0 or 1), NOT light sensors "
                            "- input.lightLevel() reads light sensors "
                            "- input.temperature() reads temperature "
                            "- input.soundLevel() reads sound "
                            "- pins.digitalWritePin() controls outputs like LEDs or motors "
                            "- radio.sendString() sends wireless messages to other micro:bits "
                            "- Mention specific buttons (A, B, AB), pins (P0, P1, P2), values, and actions "
                            "- Keep it concise and enthusiastic "
                            "- Use proper English grammar: 'and' and 'or' (lowercase), not 'AND' or 'OR' "
                            "Example: 'Awesome! You're using digital pin P0 and button A to control when to show a 'No' icon or send a radio message - that's smart conditional logic!' "
                            "MICRO:BIT HARDWARE CONTEXT: The micro:bit has 3 GPIO pins (P0, P1, P2) for connecting sensors, LEDs, motors, and other components. "
                            "Radio allows wireless communication between micro:bits within ~10m range. "
                            "Just return the encouragement text directly, no JSON or special formatting."
                        )
                    },
                    {
                        "role": "user",
                        "content": (
                            "CODE\n\n" f"```javascript\n{js_code}\n```"
                        )
                    }
                ]

                # For streaming, we'll use a simpler approach without tool calling
                response = client.chat.completions.create(
                    model="meta-llama-3.1-8b-instruct",
                    messages=messages,
                    temperature=0.4,
                    stream=True,
                    max_tokens=60
                )

                # Stream the response word by word
                full_text = ""
                for chunk in response:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_text += content
                        
                        # Stream each character and group into words
                        for char in content:
                            if char == ' ':
                                # Send a space
                                yield f"data: {json.dumps({'word': ' '})}\n\n"
                            elif char not in ['\n', '\r', '\t']:
                                # Send the character
                                yield f"data: {json.dumps({'word': char})}\n\n"
                            import time
                            time.sleep(0.025)  # Optimized delay for smooth animation


                yield f"data: {json.dumps({'done': True})}\n\n"

            except Exception as e:
                print(f"Error in streaming encouragement: {e}")
                # Fallback to non-streaming
                fallback_text = "Fantastic job! You're learning to code and doing great!"
                for char in fallback_text:
                    if char == ' ':
                        yield f"data: {json.dumps({'word': ' '})}\n\n"
                    elif char not in ['\n', '\r', '\t']:
                        yield f"data: {json.dumps({'word': char})}\n\n"
                    import time
                    time.sleep(0.025)  # Optimized delay for smooth animation
                yield f"data: {json.dumps({'done': True})}\n\n"

        return app.response_class(generate(), mimetype='text/plain')

    except Exception as e:
        print(f"Error generating streaming encouragement: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/generate_idea_stream", methods=["POST"])
def generate_idea_stream():
    """Generate idea with streaming for character-by-character display"""
    try:
        with open("static/code_file.js", "r") as file:
            js_code = file.read()

        def generate():
            # Streaming cleaner state to remove parenthesized block labels as content arrives
            buffer = ""

            def flush_clean_text(text: str, final: bool = False):
                """Remove parenthesized segments like (SHOW ICON) from text.

                We keep an internal buffer to handle cases where '(' and ')' arrive
                in separate chunks. Only emit content up to the last unmatched '(' unless final.
                """
                nonlocal buffer
                buffer += text

                # If not final, keep any trailing unmatched '(' and following text in buffer
                emit_upto = len(buffer)
                if not final:
                    last_open = buffer.rfind("(")
                    last_close = buffer.rfind(")")
                    if last_open > last_close:
                        emit_upto = last_open  # keep the open paren and tail for next chunk

                to_emit = buffer[:emit_upto]
                buffer = buffer[emit_upto:]

                # Remove parenthesized labels and surrounding extra whitespace
                import re
                cleaned = re.sub(r"\s*\([^)]*\)\s*", " ", to_emit)
                cleaned = re.sub(r"\s+", " ", cleaned)
                return cleaned

            try:

                # Load cached block mappings (computed once at startup)
                available_labels, trigger_labels, action_labels, blocks_info = get_cached_block_mappings()

                client = OpenAI(
                    base_url=LM_STUDIO_BASE_URL,
                    api_key=LM_STUDIO_API_KEY
                )

                # Build a brief analysis summary to guide a code-specific extension
                analysis = analyze_student_code(js_code)
                def _list_or_na(items):
                    return ", ".join(items) if items else "N/A"
                analysis_summary = (
                    "TRIGGERS: " + _list_or_na(analysis.get('triggers')) + "\n" +
                    "ACTIONS: " + _list_or_na(analysis.get('actions')) + "\n" +
                    "SENSORS: " + _list_or_na(analysis.get('sensors')) + "\n" +
                    "PINS: " + _list_or_na(analysis.get('pins')) + "\n" +
                    "LOGIC: " + _list_or_na(analysis.get('logic'))
                )

                # For streaming, ask for a small extension tied to existing code
                simple_messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are an enthusiastic micro:bit mentor for middle school students (ages 12-14). "
                            "Generate a creative, question-based idea that is a SMALL EXTENSION to their existing code (not a new, unrelated project). "
                            "Use their current triggers, sensors, displays, and pins where possible. "
                            "Prefer modifying or adding one action to an existing trigger rather than replacing it. "
                            "DO NOT start with 'Idea to Try:' or 'Try this:' - just start with the question directly. "
                            "Include EXACTLY 2 block references in parentheses using EXACT labels from the available blocks list. "
                            "CRITICAL: The sentence must read as proper English when the parenthesized block names are removed. "
                            "Avoid dangling conjunctions or verbs. Always include the missing nouns so the sentence stays grammatical without parentheses. "
                            "Use natural phrases like 'press button A' (not just 'press') and 'get a radio message' (not just 'get a message'). "
                            "Your idea must reference at least one element that ALREADY EXISTS in their code (a trigger, sensor, pin, or display), and extend it incrementally. "
                            "Only use triggers/actions that are relevant to their code. Do NOT suggest unrelated triggers like 'HEAR LOUD SOUND' unless their code uses sound. "
                            "If their code uses a button inline (e.g., button B), prefer 'press button B' and ON BUTTON B. If their code uses a specific pin (e.g., P1), mention 'pin P1'. If it sends a radio string, mention 'a radio message'. "
                            "Include EXACTLY ONE trigger (like ON BUTTON A, ON SHAKE, GET A MESSAGE, ON PIN PRESSED) AND ONE action (like SHOW ICON, PLAY SOUND, DIGITAL WRITE PIN, SEND STRING) in your idea. "
                            "Use 'ON BUTTON A/B/AB' (not 'ON PRESS ...'). "
                            "Do NOT include numbers, strings, or values in parentheses - only block names. "
                            "Do NOT add technical explanations or code snippets after your idea. "
                            "Do NOT mention 'input.buttonIsPressed' or 'basic.showString' or any API names. "
                            "Focus on their actual code elements: buttons they use, sensors they read, displays they show, pins they use. "
                            "MICRO:BIT HARDWARE CONTEXT: The micro:bit has 3 GPIO pins (P0, P1, P2) for connecting sensors, LEDs, motors, and other components. "
                            "Pins can read digital values (0/1) or analog values (0-1023), and write digital (0/1) or analog (0-1023) signals. "
                            "Radio allows wireless communication between micro:bits within ~10m range. "
                            "Return ONLY the question with block names in parentheses. Nothing else. "
                            "GOOD: 'What if you showed a happy face when you press button A (ON BUTTON A) and the light level is low (SHOW ICON)?' → removing parentheses stays grammatical. "
                            "BAD: 'What if you showed an icon when you press and the value from pin P0 is less than 1000 (ON BUTTON A) (SHOW ICON)?' → 'press' must have an object like 'button A'."
                        )
                    },
                    {
                        "role": "user",
                        "content": (
                            f"{blocks_info}"
                            "CURRENT CODE SUMMARY (use this to propose a SMALL extension that keeps existing context):\n" +
                            analysis_summary +
                            "\n\n"
                            "STUDENT'S CODE:\n\n"
                            f"```javascript\n{js_code}\n```\n\n"
                            "Analyze this code and suggest ONE simple extension that builds on what they're already doing. "
                            "Reference at least ONE element already in their code (e.g., 'button B', 'pin P1', 'a radio message'). "
                            "Suggest adding ONE new action that works with their EXISTING trigger (or pairs naturally with it). "
                            "Consider hardware possibilities: pins for sensors/actuators, radio for communication between micro:bits. "
                            "Example format: 'What if you played a sound (PLAY SOUND) when you press (ON BUTTON A)?' "
                            "Return ONLY the question with block names in parentheses. Do not add explanations."
                        )
                    }
                ]

                response = client.chat.completions.create(
                    model="meta-llama-3.1-8b-instruct",
                    messages=simple_messages,
                    temperature=0.3,
                    stream=True,
                    max_tokens=200
                )

                # Stream the response character by character
                full_text = ""
                for chunk in response:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_text += content

                        # Clean and emit safely (without parenthesized labels)
                        cleaned_piece = flush_clean_text(content, final=False)
                        if cleaned_piece:
                            for char in cleaned_piece:
                                if char == ' ':
                                    yield f"data: {json.dumps({'word': ' '})}\n\n"
                                elif char not in ['\n', '\r', '\t']:
                                    yield f"data: {json.dumps({'word': char})}\n\n"
                                import time
                                time.sleep(0.025)  # Optimized delay for smooth animation

                # Clean up the final text and cache it
                if full_text:
                    # Flush remaining buffer and finalize cleaned text
                    final_clean = flush_clean_text("", final=True)
                    import re
                    idea_text_raw = full_text.replace("Idea to Try: ", "").replace("Try this: ", "").strip()
                    idea_text = re.sub(r'\s+', ' ', (final_clean or idea_text_raw)).strip()

                    # Extract blocks from the RAW (un-cleaned) idea so labels are preserved for the UI section
                    extracted_blocks = extract_blocks_from_idea(idea_text_raw, available_labels)
                    # Validate novelty + anchoring and fallback if needed
                    # We need trigger labels for validation
                    _, trigger_labels, _, _ = get_cached_block_mappings()
                    used_blocks, anchors = compute_used_blocks_and_anchors(analysis)
                    adj_blocks = adjacent_novel_blocks(used_blocks)
                    is_valid, score, reason = score_and_validate_idea(idea_text_raw, extracted_blocks, used_blocks, anchors, adj_blocks, trigger_labels)
                    print(f"DEBUG: Stream idea validation -> valid={is_valid}, score={score}, reason='{reason}'")
                    if not is_valid:
                        fallback = deterministic_novel_idea(analysis, used_blocks, anchors)
                        # Overwrite with fallback
                        idea_text = re.sub(r'\s+', ' ', fallback["idea"]).strip()
                        extracted_blocks = fallback["blocks"]
                    if extracted_blocks:
                        # Send a dedicated SSE event with blocks so the UI can populate "Blocks to Explore"
                        yield f"data: {json.dumps({'blocks': extracted_blocks})}\n\n"


                yield f"data: {json.dumps({'done': True})}\n\n"

            except Exception as e:
                print(f"Error in streaming idea: {e}")
                # Fallback to non-streaming
                fallback_idea = "What if you added some sound effects when you press a button?"
                for char in fallback_idea:
                    if char == ' ':
                        yield f"data: {json.dumps({'word': ' '})}\n\n"
                    elif char not in ['\n', '\r', '\t']:
                        yield f"data: {json.dumps({'word': char})}\n\n"
                    import time
                    time.sleep(0.025)  # Optimized delay for smooth animation
                yield f"data: {json.dumps({'done': True})}\n\n"

        return app.response_class(generate(), mimetype='text/event-stream')

    except Exception as e:
        print(f"Error generating streaming idea: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/chat", methods=["POST"])
def chat():
    """Handle chat requests with different conversation types"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        chat_type = data.get("type", "general")
        user_message = data.get("message", "")
        context = data.get("context", {})
        
        # Get the current generated code
        try:
            with open("static/code_file.js", "r") as file:
                js_code = file.read()
        except FileNotFoundError:
            js_code = "// No code generated yet"
        
        # Generate appropriate response based on chat type
        response = generate_chat_response(chat_type, user_message, js_code, context)
        
        return jsonify({
            "success": True,
            "response": response
        })
        
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/chat_stream", methods=["POST"])
def chat_stream():
    """Handle streaming chat requests"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        chat_type = data.get("type", "general")
        user_message = data.get("message", "")
        context = data.get("context", {})
        
        # Get the current generated code
        try:
            with open("static/code_file.js", "r") as file:
                js_code = file.read()
        except FileNotFoundError:
            js_code = "// No code generated yet"
        
        def generate():
            try:
                client = OpenAI(
                    base_url=LM_STUDIO_BASE_URL,
                    api_key=LM_STUDIO_API_KEY
                )
                
                # Get the appropriate system prompt based on chat type
                system_prompt = get_chat_system_prompt(chat_type, js_code, context)
                
                # Add context information for learn_block type
                context_info = ""
                if chat_type == "learn_block" and context:
                    block_name = context.get("block", "")
                    category = context.get("category", "")
                    description = context.get("description", "")
                    if block_name:
                        context_info = f"\n\nCONTEXT: The student is asking about the '{block_name}' block from the {category} category. Block description: {description}"
                
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"STUDENT'S CODE:\n```javascript\n{js_code}\n```{context_info}\n\nSTUDENT'S QUESTION: {user_message}"}
                ]
                
                response = client.chat.completions.create(
                    model="meta-llama-3.1-8b-instruct",
                    messages=messages,
                    temperature=0.7,
                    stream=True,
                    max_tokens=500
                )
                
                # Stream the response character by character
                for chunk in response:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        
                        # Stream each character, converting line breaks to special markers
                        for char in content:
                            if char == ' ':
                                yield f"data: {json.dumps({'word': ' '})}\n\n"
                            elif char == '\n':
                                yield f"data: {json.dumps({'word': '<br>'})}\n\n"
                            elif char not in ['\r', '\t']:
                                yield f"data: {json.dumps({'word': char})}\n\n"
                            import time
                            time.sleep(0.025)  # Smooth animation timing
                
                yield f"data: {json.dumps({'done': True})}\n\n"
                
            except Exception as e:
                print(f"Error in streaming chat: {e}")
                # Fallback response
                fallback_text = "I'm having trouble connecting right now. Please try again in a moment!"
                for char in fallback_text:
                    if char == ' ':
                        yield f"data: {json.dumps({'word': ' '})}\n\n"
                    elif char not in ['\n', '\r', '\t']:
                        yield f"data: {json.dumps({'word': char})}\n\n"
                    import time
                    time.sleep(0.025)
                yield f"data: {json.dumps({'done': True})}\n\n"
        
        return app.response_class(generate(), mimetype='text/event-stream')
        
    except Exception as e:
        print(f"Error in chat_stream endpoint: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/clear_code", methods=["POST"])
def clear_code():
    """Clear the generated code file"""
    try:
        _write_placeholder_code()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/cache_stats")
def cache_stats():
    """Get cache statistics for debugging and monitoring"""
    try:
        stats = get_cache_stats()
        return jsonify({
            "success": True,
            "cache_stats": stats
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


if __name__ == "__main__":
    app.run(debug=True)
