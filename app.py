import os
import subprocess
import json
import re
import sys

from flask import Flask, jsonify, render_template, request, session
from werkzeug.utils import secure_filename
from openai import OpenAI

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
file_path = None

# Smart in-memory cache for AI responses to reduce latency
ai_response_cache = {}

def get_code_signature(js_code):
    """
    Create a pattern-based signature for caching similar code snippets.
    
    This function extracts key patterns from JavaScript code to create a signature
    that can match similar code variations, not just exact duplicates.
    
    Args:
        js_code (str): The JavaScript code to analyze
        
    Returns:
        str: A signature string representing the code pattern
    """
    import re
    
    # Extract key patterns
    triggers = re.findall(r'on(\w+)', js_code)
    actions = re.findall(r'(show|play|send|radio|digital|analog)', js_code)
    sensors = re.findall(r'(light|temp|accel|sound|compass)', js_code)
    pins = re.findall(r'P[0-2]', js_code)
    
    # Create normalized signature
    signature_parts = [
        f"triggers:{sorted(triggers)}",
        f"actions:{sorted(actions)}", 
        f"sensors:{sorted(sensors)}",
        f"pins:{sorted(pins)}",
        f"length:{len(js_code.split())}"  # Rough complexity measure
    ]
    
    return "|".join(signature_parts)

def get_cached_suggestion(js_code, cache_type="suggestion"):
    """
    Check if we have a cached response for similar code patterns.
    
    Args:
        js_code (str): The JavaScript code to check
        cache_type (str): Type of cache to check ("suggestion", "encouragement", "idea")
        
    Returns:
        dict or None: Cached response if found, None otherwise
    """
    signature = get_code_signature(js_code)
    cache_key = f"{cache_type}_{signature}"
    
    if cache_key in ai_response_cache:
        print(f"Cache hit for {cache_type}: {signature}")
        return ai_response_cache[cache_key]
    
    print(f"Cache miss for {cache_type}: {signature}")
    return None

def cache_suggestion(js_code, response, cache_type="suggestion"):
    """
    Cache a response for future similar code patterns.
    
    Args:
        js_code (str): The JavaScript code that generated this response
        response (dict): The response to cache
        cache_type (str): Type of cache ("suggestion", "encouragement", "idea")
    """
    signature = get_code_signature(js_code)
    cache_key = f"{cache_type}_{signature}"
    ai_response_cache[cache_key] = response
    print(f"Cached {cache_type} response for pattern: {signature}")

def analyze_student_code(js_code):
    """
    Analyze student code to extract specific details for targeted suggestions.
    
    Args:
        js_code (str): The JavaScript code to analyze
        
    Returns:
        dict: Detailed analysis of the student's code
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
        'code_structure': 'simple'
    }
    
    # Extract specific triggers
    if 'onButtonPressed' in js_code:
        buttons = re.findall(r'Button\.([AB]+)', js_code)
        analysis['triggers'].append(f"button_{buttons[0] if buttons else 'unknown'}")
        analysis['specific_details']['buttons_used'] = buttons
    
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
    
    return analysis

def generate_targeted_suggestion(analysis, js_code):
    """
    Generate a targeted suggestion based on detailed code analysis.
    
    Args:
        analysis (dict): Detailed analysis of the student's code
        js_code (str): The original JavaScript code
        
    Returns:
        dict: Targeted suggestion with specific encouragement and idea
    """
    details = analysis['specific_details']
    
    # Build specific encouragement based on what they're actually doing
    encouragement_parts = []
    
    # Mention specific buttons used
    if 'buttons_used' in details and details['buttons_used']:
        buttons = ', '.join(details['buttons_used'])
        encouragement_parts.append(f"using button{'s' if len(details['buttons_used']) > 1 else ''} {buttons}")
    
    # Mention specific pins used
    if 'digital_pins_read' in details and details['digital_pins_read']:
        pins = ', '.join(details['digital_pins_read'])
        encouragement_parts.append(f"reading digital pin{'s' if len(details['digital_pins_read']) > 1 else ''} {pins}")
    
    if 'digital_pins_written' in details and details['digital_pins_written']:
        pins = ', '.join(details['digital_pins_written'])
        encouragement_parts.append(f"controlling digital pin{'s' if len(details['digital_pins_written']) > 1 else ''} {pins}")
    
    # Mention specific icons shown
    if 'icons_shown' in details and details['icons_shown']:
        icons = ', '.join(details['icons_shown'])
        encouragement_parts.append(f"showing {icons} icon{'s' if len(details['icons_shown']) > 1 else ''}")
    
    # Mention radio messages
    if 'radio_messages' in details and details['radio_messages']:
        messages = ', '.join([f'"{msg}"' for msg in details['radio_messages']])
        encouragement_parts.append(f"sending radio message{'s' if len(details['radio_messages']) > 1 else ''} {messages}")
    
    # Mention logic complexity
    if 'conditional' in analysis['logic']:
        if 'and_condition' in analysis['logic']:
            encouragement_parts.append("using AND logic")
        if 'comparison' in analysis['logic']:
            encouragement_parts.append("comparing values")
    
    # Build encouragement
    if encouragement_parts:
        encouragement = f"Great work! You're {' and '.join(encouragement_parts)} - that's smart programming!"
    else:
        encouragement = "Excellent coding! You're building interactive programs!"
    
    # Generate targeted idea based on what they're doing
    idea = generate_targeted_idea(analysis, details)
    
    # Extract blocks for the idea
    blocks = extract_blocks_from_idea(idea, [])
    
    return {
        "encouragement": encouragement,
        "idea": idea,
        "blocks": blocks
    }

def generate_targeted_idea(analysis, details):
    """
    Generate a specific idea based on the student's code analysis.
    """
    # Pin reading + button + icon pattern (even if button is in condition, not trigger)
    if ('read_digital_pin' in analysis['actions'] and 
        'show_icon_No' in analysis['actions'] and
        'and_condition' in analysis['logic']):
        
        pins = details.get('digital_pins_read', ['P0'])
        pin = pins[0] if pins else 'P0'
        return f"What if you displayed the actual value of pin {pin} (SHOW NUMBER) after showing the 'No' icon?"
    
    # Pin reading + comparison + radio pattern
    if ('read_digital_pin' in analysis['actions'] and 
        'comparison' in analysis['logic'] and
        'send_radio_message' in analysis['actions']):
        
        pins = details.get('digital_pins_read', ['P0'])
        pin = pins[0] if pins else 'P0'
        return f"What if you displayed the actual value of pin {pin} (SHOW NUMBER) instead of just sending a radio message?"
    
    # Pin reading + comparison pattern
    if ('read_digital_pin' in analysis['actions'] and 
        'comparison' in analysis['logic']):
        
        pins = details.get('digital_pins_read', ['P0'])
        pin = pins[0] if pins else 'P0'
        return f"What if you used the light sensor (LIGHT LEVEL) to compare with pin {pin} values?"
    
    # Button + icon pattern
    if ('button_A' in analysis['triggers'] and 
        'show_icon' in analysis['actions'] and 
        'radio' not in analysis['actions']):
        
        icons = details.get('icons_shown', ['Heart'])
        icon = icons[0] if icons else 'Heart'
        return f"What if you added sound effects (PLAY SOUND) when you press (ON BUTTON A) to go with your {icon} icon?"
    
    # Radio + icon pattern
    if ('send_radio_message' in analysis['actions'] and 
        'show_icon' in analysis['actions']):
        
        return f"What if you changed the icon (SHOW ICON) based on radio messages you receive (GET A MESSAGE)?"
    
    # Sound detection pattern
    if ('sound_Loud' in analysis['triggers'] or 'sound_Quiet' in analysis['triggers']):
        return f"What if you used the temperature sensor (TEMPERATURE) to show different icons (SHOW ICON) based on how hot it is?"
    
    # Simple button pattern
    if ('button_A' in analysis['triggers'] and 
        len(analysis['actions']) == 1):
        
        return f"What if you added button B (ON BUTTON B) to do something different (SHOW ICON)?"
    
    # Default fallback
    return f"What if you added a light sensor (LIGHT LEVEL) to make your program respond to the environment?"

def get_cache_stats():
    """
    Get statistics about the current cache state.
    
    Returns:
        dict: Cache statistics including hit rates and pattern counts
    """
    total_entries = len(ai_response_cache)
    suggestion_entries = len([k for k in ai_response_cache.keys() if k.startswith("suggestion_")])
    encouragement_entries = len([k for k in ai_response_cache.keys() if k.startswith("encouragement_")])
    idea_entries = len([k for k in ai_response_cache.keys() if k.startswith("idea_")])
    
    return {
        "total_entries": total_entries,
        "suggestion_entries": suggestion_entries,
        "encouragement_entries": encouragement_entries,
        "idea_entries": idea_entries,
        "unique_patterns": len(set([k.split("_", 1)[1] for k in ai_response_cache.keys()]))
    }

# Removed generic preloaded responses - they weren't specific enough
# Now the AI analyzes each student's code individually for personalized feedback

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
        # Check smart cache first
        cached_response = get_cached_suggestion(js_code, "suggestion")
        if cached_response:
            return cached_response
        
        # Analyze the student's code for targeted suggestions
        analysis = analyze_student_code(js_code)
        print(f"Code analysis: {analysis}")
        
        # Try to generate a targeted suggestion first
        targeted_response = generate_targeted_suggestion(analysis, js_code)
        if targeted_response and targeted_response.get("idea"):
            # Cache and return the targeted response
            cache_suggestion(js_code, targeted_response, "suggestion")
            return targeted_response
        # Initialize OpenAI client to connect to local LM Studio server
        # LM Studio provides an OpenAI-compatible API on localhost:1234
        client = OpenAI(
            base_url="http://localhost:1234/v1",
            api_key="lm-studio"  # Dummy key for local LM Studio server
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
        
        # Load the current block mapping system to provide available blocks to the AI
        available_labels = []
        trigger_labels = []
        action_labels = []
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

            # Do not force-add radio labels; rely on mapper entries so suggestions stay relevant

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
            print(f"DEBUG: Loaded {len(available_labels)} suggestable labels")
            print(f"DEBUG: First 12 labels: {available_labels[:12]}")
            print(f"DEBUG: Trigger labels: {trigger_labels}")
            print(f"DEBUG: Action labels: {action_labels}")

            # Note: We removed blocks from the response schema since we extract them automatically
            
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
            # Note: We removed blocks from the response schema since we extract them automatically
        
        # Create conversation messages (improved prompt for question-based ideas)
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
                    "MICRO:BIT HARDWARE CONTEXT: The micro:bit has 3 GPIO pins (P0, P1, P2) for connecting sensors, LEDs, motors, and other components. "
                    "Pins can read digital values (0/1) or analog values (0-1023), and write digital (0/1) or analog (0-1023) signals. "
                    "Safe pin usage: P0-P2 are 3.3V tolerant; avoid short circuits; use appropriate resistors for LEDs. "
                    "Radio allows wireless communication between micro:bits within ~10m range. "
                    "Make your encouragement specific to their code and your idea creative and engaging!"
                )
            },
            {
                "role": "user",
                "content": (
                    "INSTRUCTIONS\n"
                    "- Return suggestions via the provided function only (no prose).\n"
                    "- Provide: encouragement (1 short paragraph) and one IDEA (question starting with 'What if' or 'How about').\n"
                    "- DO NOT start the idea with 'Idea to Try:' or 'Try this:' - just start with the question directly.\n"
                    "- In the IDEA sentence, reference block labels in parentheses using EXACT labels from the lists.\n"
                    "- CRITICAL: The sentence must make complete grammatical sense when the parenthesized block names are removed.\n"
                    "- Include BOTH a trigger (ON BUTTON A, ON SHAKE, GET A MESSAGE, ON PIN PRESSED, etc.) AND an action (SHOW ICON, PLAY SOUND, DIGITAL WRITE PIN, SEND STRING, etc.) in your idea.\n"
                    "- Create a UNIQUE idea based on their specific code - analyze what they're doing and suggest something that builds on it.\n"
                    "- Do not use generic examples - make it specific to their code.\n"
                    "- Consider hardware possibilities: pins for sensors/actuators, radio for communication between micro:bits.\n\n"

                    f"{blocks_info}"
                    "CODE\n\n"
                    f"```javascript\n{js_code}\n```"
                )
            }
        ]

        # Define a function for tool calling to return the structured suggestion
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "suggest",
                    "description": "Return encouragement and one unique question-based idea that builds on their specific code. Include BOTH a trigger and action block references in parentheses using exact labels from the available blocks list.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "encouragement": {"type": "string"},
                            "idea": {"type": "string", "description": "Question starting with 'What if' or 'How about' containing BOTH trigger and action block labels in parentheses (e.g., (ON BUTTON A), (SHOW ICON)). The sentence must make complete grammatical sense when the parenthesized block names are removed. Use 'ON BUTTON A/B/AB' not 'ON PRESS ...'. Base it on their actual code."}
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
            temperature=0.3,  # Increased for more creative responses
            stream=False,
            max_tokens=200  # Increased for more detailed responses
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
            
            # Validate the extracted blocks
            if extracted_blocks:
                triggers, actions = split_trigger_action(extracted_blocks)
                if len(triggers) == 1 and len(actions) >= 1 and 2 <= len(extracted_blocks) <= 4:
                    result["blocks"] = extracted_blocks
                else:
                    # If extraction doesn't meet constraints, try a corrective retry
                    corrective_messages = messages + [
                        {
                            "role": "user",
                            "content": (
                                "FIX ALIGNMENT\n"
                                "Your idea should reference exactly ONE trigger and 1-2 actions from the available blocks. "
                                "Make sure to include the block labels in parentheses in your idea.\n"
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
                    if retry_extracted_blocks:
                        retry_triggers, retry_actions = split_trigger_action(retry_extracted_blocks)
                        if len(retry_triggers) == 1 and len(retry_actions) >= 1 and 2 <= len(retry_extracted_blocks) <= 4:
                            retry_result["blocks"] = retry_extracted_blocks
                            return retry_result
                    
                    # Fallback: use original result with extracted blocks even if not perfect
                    result["blocks"] = extracted_blocks[:4]  # Cap at 4 blocks
            else:
                # No blocks extracted, provide fallback
                result["blocks"] = ["ON BUTTON A", "SHOW ICON"]

        # Cache the result for future similar code patterns
        cache_suggestion(js_code, result, "suggestion")
        return result
        
    except Exception as e:
        # Handle any errors gracefully with fallback suggestions
        # This ensures the app continues working even if LM Studio is unavailable
        print(f"Error generating AI suggestions: {e}")
        fallback_response = {
            "encouragement": "Great job on your code!",
            "idea": "What if you added some sound effects when you press a button?",
            "blocks": ["ON BUTTON A", "PLAY SOUND"]
        }
        # Cache the fallback too
        cache_suggestion(js_code, fallback_response, "suggestion")
        return fallback_response


def generate_ai_encouragement(js_code):
    """
    Generate only a short encouragement message based on the student's code.
    Uses the same LM Studio local API for fast, lightweight output.
    """
    try:
        # Check smart cache first
        cached_response = get_cached_suggestion(js_code, "encouragement")
        if cached_response:
            return cached_response
        
        
        client = OpenAI(
            base_url="http://localhost:1234/v1",
            api_key="lm-studio"
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
                    "Do not include ideas or blocks yet."
                )
            },
            {
                "role": "user",
                "content": (
                    "CODE\n\n" f"```javascript\n{js_code}\n```"
                )
            }
        ]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "encourage",
                    "description": "Return only an encouragement message.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "encouragement": {"type": "string"}
                        },
                        "required": ["encouragement"]
                    }
                }
            }
        ]

        response = client.chat.completions.create(
            model="meta-llama-3.1-8b-instruct",
            messages=messages,
            tools=tools,
            tool_choice="required",
            response_format=response_schema,
            temperature=0.4,  # Increased for more engaging encouragement
            stream=False,  # Disabled streaming for non-streaming function
            max_tokens=60  # Reduced for shorter encouragement
        )

        msg = response.choices[0].message
        if getattr(msg, "tool_calls", None):
            call = msg.tool_calls[0]
            args = call.function.arguments if hasattr(call, "function") else call.get("function", {}).get("arguments")
            result = json.loads(args)
        else:
            result = json.loads(msg.content)

        if isinstance(result, dict) and isinstance(result.get("encouragement"), str):
            # Cache the result for future similar code patterns
            cache_suggestion(js_code, result, "encouragement")
            return result
        fallback_response = {"encouragement": "Amazing work! You're becoming a real programmer!"}
        cache_suggestion(js_code, fallback_response, "encouragement")
        return fallback_response
    except Exception as e:
        print(f"Error generating encouragement: {e}")
        fallback_response = {"encouragement": "Fantastic job! You're learning to code and doing great!"}
        cache_suggestion(js_code, fallback_response, "encouragement")
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
        file.save(file_path)
        print("File saved at:", file_path)
        # Persist path in session for this user
        session['file_path'] = file_path

    return render_template("code_box.html")


@app.route("/run_script")
def run_script():
    # Prefer session-scoped file path; fallback to global if needed
    current_path = session.get('file_path') or file_path
    if not current_path:
        return "File path is not set. Please set the file path first."

    print(f"File path: {current_path}")
    ok, out, err, code = _execute_vision_processor(current_path)
    if ok:
        return f"Python script executed successfully! Output: {out}"
    return (f"Error executing Python script (exit {code}). Error output: {err or out}", 500)


@app.route("/process_image_path", methods=["POST"])
def process_image_path():
    if "file" not in request.files:
        return jsonify({"error": "No file part"})

    file = request.files["file"]
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
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

    code_path = "./static/code_file.js"
    if not os.path.exists(code_path):
        return ("No generated code yet. Upload an image first to generate MakeCode.", 404)
    try:
        with open(code_path, "r") as file:
            js_content = file.read()
        return js_content
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
                # Check smart cache first
                cached_response = get_cached_suggestion(js_code, "encouragement")
                if cached_response:
                    print("Using cached encouragement response")
                    encouragement_text = cached_response.get("encouragement", "Great job on your code!")
                    # Stream the cached response character by character
                    for char in encouragement_text:
                        if char == ' ':
                            yield f"data: {json.dumps({'word': ' '})}\n\n"
                        elif char not in ['\n', '\r', '\t']:
                            yield f"data: {json.dumps({'word': char})}\n\n"
                        import time
                        time.sleep(0.05)  # Small delay between characters
                    yield f"data: {json.dumps({'done': True})}\n\n"
                    return

                client = OpenAI(
                    base_url="http://localhost:1234/v1",
                    api_key="lm-studio"
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
                            time.sleep(0.05)  # Small delay between characters

                # Cache the result for future similar code patterns
                if full_text:
                    result = {"encouragement": full_text}
                    cache_suggestion(js_code, result, "encouragement")

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
                    time.sleep(0.05)
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
            try:
                # Check smart cache first
                cached_response = get_cached_suggestion(js_code, "idea")
                if cached_response:
                    print("Using cached idea response")
                    idea_text = cached_response.get("idea", "What if you added some sound effects?")
                    # Stream the cached response character by character
                    for char in idea_text:
                        if char == ' ':
                            yield f"data: {json.dumps({'word': ' '})}\n\n"
                        elif char not in ['\n', '\r', '\t']:
                            yield f"data: {json.dumps({'word': char})}\n\n"
                        import time
                        time.sleep(0.05)  # Small delay between characters
                    yield f"data: {json.dumps({'done': True})}\n\n"
                    return

                # Load the current block mapping system to provide available blocks to the AI
                available_labels = []
                trigger_labels = []
                action_labels = []
                try:
                    with open("static/blocks_map.json", "r") as f:
                        blocks_map = json.load(f)

                    # Build a list of human-visible block labels (exact strings students see)
                    suggestable_categories = {
                        "events", "basic", "input", "music", "led", "control", "variables", "logic", "loops", "math", "pins", "radio"
                    }
                    exclude_categories = {"synonyms", "templates", "icons", "sounds", "on"}

                    available_labels = []
                    trigger_labels = []
                    for category, blocks in blocks_map.items():
                        if category in exclude_categories:
                            continue
                        if category not in suggestable_categories:
                            continue
                        if not isinstance(blocks, dict):
                            continue
                        for block_name, block_info in blocks.items():
                            if isinstance(block_info, dict) and "template" in block_info:
                                available_labels.append(block_name)
                                if category == "events":
                                    trigger_labels.append(block_name)

                    # De-duplicate while preserving order
                    seen = set()
                    available_labels = [x for x in available_labels if not (x in seen or seen.add(x))]

                    # Compute actions = all available minus triggers
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
                    
                except Exception as e:
                    print(f"Warning: Could not load block mapping: {e}")
                    # Fallback minimal sets
                    trigger_labels = [
                        "ON BUTTON A", "ON BUTTON B", "ON BUTTON AB", "ON SHAKE", "GET A MESSAGE", "HEAR LOUD SOUND", "HEAR QUIET SOUND", "ON PIN PRESSED"
                    ]
                    action_labels = [
                        "SHOW ICON", "SHOW STRING", "SHOW LEDS", "PLAY SOUND", "PLAY MELODY", "PLAY TONE", "LIGHT LEVEL", "TEMPERATURE", "PLOT", "CLEAR SCREEN", "DIGITAL WRITE PIN", "SEND STRING"
                    ]
                    seen = set()
                    available_labels = [x for x in trigger_labels + action_labels if not (x in seen or seen.add(x))]
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

                client = OpenAI(
                    base_url="http://localhost:1234/v1",
                    api_key="lm-studio"
                )

                # For streaming, we'll use a simpler approach - just ask for the idea directly
                simple_messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are an enthusiastic micro:bit mentor for middle school students (ages 12-14). "
                            "Generate a creative, question-based idea that builds on the student's code. "
                            "Look at their specific code and suggest something that builds on what they're already doing. "
                            "DO NOT start with 'Idea to Try:' or 'Try this:' - just start with the question directly. "
                            "Include EXACTLY 2 block references in parentheses using EXACT labels from the available blocks list. "
                            "CRITICAL: The sentence must make complete grammatical sense when the parenthesized block names are removed. "
                            "Include EXACTLY ONE trigger (like ON BUTTON A, ON SHAKE, GET A MESSAGE, ON PIN PRESSED) AND ONE action (like SHOW ICON, PLAY SOUND, DIGITAL WRITE PIN, SEND STRING) in your idea. "
                            "Use 'ON BUTTON A/B/AB' (not 'ON PRESS ...'). "
                            "Do NOT include numbers, strings, or values in parentheses - only block names. "
                            "Do NOT add technical explanations or code snippets after your idea. "
                            "Do NOT mention 'input.buttonIsPressed' or 'basic.showString' or any API names. "
                            "Focus on their actual code elements: buttons they use, sensors they read, displays they show, pins they use. "
                            "MICRO:BIT HARDWARE CONTEXT: The micro:bit has 3 GPIO pins (P0, P1, P2) for connecting sensors, LEDs, motors, and other components. "
                            "Pins can read digital values (0/1) or analog values (0-1023), and write digital (0/1) or analog (0-1023) signals. "
                            "Radio allows wireless communication between micro:bits within ~10m range. "
                            "Return ONLY the question with block names in parentheses. Nothing else."
                        )
                    },
                    {
                        "role": "user",
                        "content": (
                            f"{blocks_info}"
                            "STUDENT'S CODE:\n\n"
                            f"```javascript\n{js_code}\n```\n\n"
                            "Analyze this code and suggest ONE simple idea that builds on what they're already doing. "
                            "Look at: which buttons they use, what sensors they read, what they display, what pins they use. "
                            "Suggest adding ONE new action that works with their existing trigger. "
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
                        
                        # Stream each character and group into words
                        for char in content:
                            if char == ' ':
                                # Send a space
                                yield f"data: {json.dumps({'word': ' '})}\n\n"
                            elif char not in ['\n', '\r', '\t']:
                                # Send the character
                                yield f"data: {json.dumps({'word': char})}\n\n"
                            import time
                            time.sleep(0.05)

                # Clean up the final text and cache it
                if full_text:
                    idea_text = full_text.replace("Idea to Try: ", "").replace("Try this: ", "").strip()
                    
                    # Additional cleanup: remove any invalid parenthesized content
                    import re
                    # Remove parenthesized content that's not valid block names
                    def clean_parentheses(match):
                        content = match.group(1).strip()
                        # Only keep if it looks like a valid block name (all caps, no numbers, no quotes)
                        if re.match(r'^[A-Z\s]+$', content) and len(content) > 2:
                            return match.group(0)  # Keep the original
                        else:
                            return ''  # Remove invalid content
                    
                    idea_text = re.sub(r'\(([^)]+)\)', clean_parentheses, idea_text)
                    
                    # Remove any technical explanations that might have been added
                    # Look for patterns like "ON BUTTON A (input.buttonIsPressed(Button.A))"
                    idea_text = re.sub(r'\s*[A-Z\s]+\s*\([^)]*input\.[^)]*\)', '', idea_text)
                    idea_text = re.sub(r'\s*[A-Z\s]+\s*\([^)]*basic\.[^)]*\)', '', idea_text)
                    idea_text = re.sub(r'\s*[A-Z\s]+\s*\([^)]*pins\.[^)]*\)', '', idea_text)
                    
                    # Clean up extra spaces
                    idea_text = re.sub(r'\s+', ' ', idea_text).strip()
                    
                    result = {"idea": idea_text}
                    cache_suggestion(js_code, result, "idea")

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
                    time.sleep(0.05)
                yield f"data: {json.dumps({'done': True})}\n\n"

        return app.response_class(generate(), mimetype='text/event-stream')

    except Exception as e:
        print(f"Error generating streaming idea: {e}")
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
