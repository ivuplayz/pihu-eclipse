# ============================================================
# PIHU — Eclipse Update
# Personal AI Assistant
# Memory + Personality + Reminders + Vision + Actions
# Web + Gemini + Security + Eclipse UI + A+Space
# ============================================================

import ast
import json
import operator
import os
import re
import secrets
import subprocess
import threading
import time
import uuid
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import requests
from flask import Flask, jsonify, request, render_template_string, session
from google import genai

# ============================================================
# CONFIG
# ============================================================

APP_NAME = "Eclipse"
UPDATE_NAME = "Pihu MidNight Update"

HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "5080"))

GEMINI_MODEL = "gemini-3.6-flash"

BASE_DIR = Path(__file__).resolve().parent

MEMORY_FILE = BASE_DIR / "pihu_memory.json"
CHAT_FILE = BASE_DIR / "pihu_chat.json"
REMINDER_FILE = BASE_DIR / "pihu_reminders.json"

app = Flask(__name__)

# Random secret generated every time Pihu starts.
# This protects the login session.
app.secret_key = secrets.token_hex(32)

# ============================================================
# GEMINI
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

gemini = None

if GEMINI_API_KEY:
    try:
        gemini = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as error:
        print("Gemini setup error:", error)

# ============================================================
# SECURITY
# ============================================================

def get_pihu_code():
    """
    Reads the private PIHU_CODE from Windows environment.
    The actual password is never stored in this source file.
    """
    return os.getenv("PIHU_CODE", "").strip()


def verify_password(password):
    saved_code = get_pihu_code()

    if not saved_code:
        return False

    return secrets.compare_digest(
        str(password).strip(),
        saved_code
    )


def is_authenticated():
    return session.get("pihu_authenticated", False) is True


# ============================================================
# JSON STORAGE
# ============================================================

def load_json(path, default):
    try:
        if not path.exists():
            return default

        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as error:
        print("Read error:", path.name, error)
        return default


def save_json(path, data):
    try:
        temp_path = path.with_suffix(path.suffix + ".tmp")

        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=2,
                ensure_ascii=False
            )

        temp_path.replace(path)
        return True

    except Exception as error:
        print("Write error:", path.name, error)
        return False


# ============================================================
# MEMORY
# ============================================================

def load_memories():
    data = load_json(MEMORY_FILE, [])
    return data if isinstance(data, list) else []


def save_memory(text, category="general"):
    text = text.strip()

    if not text:
        return "Tell me what you want me to remember."


    memories = load_memories()

    for item in memories:
        if (
            isinstance(item, dict)
            and item.get("text", "").lower() == text.lower()
        ):
            return "I already remember that."


    memories.append({
        "id": str(uuid.uuid4()),
        "category": category,
        "text": text,
        "created": datetime.now().isoformat(timespec="seconds")
    })

    save_json(MEMORY_FILE, memories)

    return "I'll remember that."


def memory_command(message):
    text = message.strip()
    lower = text.lower()

    for prefix in ("remember that ", "remember "):
        if lower.startswith(prefix):
            return save_memory(
                text[len(prefix):].strip()
            )

    if (
        "what do you remember" in lower
        or "what do you know about me" in lower
    ):
        memories = load_memories()

        if not memories:
            return "I don't have any saved memories yet."

        lines = []

        for item in memories:
            value = (
                item.get("text", "")
                if isinstance(item, dict)
                else str(item)
            )

            if value:
                lines.append("• " + value)

        return (
            "Here's what I remember:\n\n"
            + "\n".join(lines)
        )

    if lower.startswith("forget that "):

        target = text[len("forget that "):].strip().lower()

        memories = load_memories()

        kept = []
        removed = False

        for item in memories:

            value = (
                item.get("text", "")
                if isinstance(item, dict)
                else str(item)
            )

            if target in value.lower():
                removed = True
            else:
                kept.append(item)

        save_json(MEMORY_FILE, kept)

        if removed:
            return "Forgot that memory."

        return "I couldn't find that memory."


    if (
        "forget everything" in lower
        or "forget all memories" in lower
    ):
        save_json(MEMORY_FILE, [])
        return "I've cleared all saved memories."


    patterns = [
        (r"^my name is (.+)$", "personal"),
        (r"^my favorite color is (.+)$", "preference"),
        (r"^my favourite color is (.+)$", "preference"),
        (r"^my goal is (.+)$", "goal"),
        (r"^i am building (.+)$", "project"),
        (r"^i'm building (.+)$", "project"),
        (r"^i want to (.+)$", "goal"),
        (r"^i like (.+)$", "preference"),
    ]

    for pattern, category in patterns:

        match = re.match(
            pattern,
            text,
            re.I
        )

        if match:
            return save_memory(
                match.group(1).strip(),
                category
            )

    return None


# ============================================================
# CHAT HISTORY
# ============================================================

def load_chat():
    data = load_json(CHAT_FILE, [])
    return data if isinstance(data, list) else []


def save_chat(role, message):

    history = load_chat()

    history.append({
        "role": role,
        "message": message,
        "time": datetime.now().isoformat(timespec="seconds")
    })

    save_json(
        CHAT_FILE,
        history[-60:]
    )


def recent_chat(limit=14):

    return "\n".join(
        f"{x.get('role', 'Unknown')}: "
        f"{x.get('message', '')}"
        for x in load_chat()[-limit:]
        if isinstance(x, dict)
    )


# ============================================================
# CALCULATOR
# ============================================================

OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos
}


def safe_eval(expression):

    if len(expression) > 120:
        return None

    try:

        tree = ast.parse(
            expression,
            mode="eval"
        )

        def evaluate(node):

            if isinstance(
                node,
                ast.Constant
            ) and isinstance(
                node.value,
                (int, float)
            ):
                return node.value

            if isinstance(node, ast.UnaryOp):

                op = OPERATORS.get(
                    type(node.op)
                )

                if not op:
                    raise ValueError

                return op(
                    evaluate(node.operand)
                )

            if isinstance(node, ast.BinOp):

                op = OPERATORS.get(
                    type(node.op)
                )

                if not op:
                    raise ValueError

                return op(
                    evaluate(node.left),
                    evaluate(node.right)
                )

            raise ValueError

        return evaluate(tree.body)

    except Exception:
        return None


def try_calculate(message):

    text = message.lower().strip()

    replacements = {
        "multiplied by": "*",
        "multiply by": "*",
        "times": "*",
        "divided by": "/",
        "divide by": "/",
        "plus": "+",
        "minus": "-"
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    for prefix in (
        "calculate ",
        "solve ",
        "what is ",
        "what's "
    ):

        if text.startswith(prefix):

            text = text[
                len(prefix):
            ].strip()

            break

    if not re.fullmatch(
        r"[0-9+\-*/().%\s]+",
        text
    ):
        return None

    if not re.search(r"\d", text):
        return None

    if not re.search(
        r"[+\-*/%]",
        text
    ):
        return None

    result = safe_eval(text)

    if result is None:
        return None

    if (
        isinstance(result, float)
        and result.is_integer()
    ):
        result = int(result)

    return f"The answer is {result}."


# ============================================================
# REMINDERS
# ============================================================

def load_reminders():

    data = load_json(
        REMINDER_FILE,
        []
    )

    return data if isinstance(
        data,
        list
    ) else []


def parse_reminder(message):

    # Seconds
    match = re.match(
        r"^\s*remind me in\s+(\d+)\s+"
        r"(second|seconds|sec|secs)\s+"
        r"(?:to\s+)?(.+)$",
        message,
        re.I
    )

    if match:

        amount = int(
            match.group(1)
        )

        return (
            max(1, amount),
            match.group(3).strip()
        )


    # Minutes / Hours
    match = re.match(
        r"^\s*remind me in\s+(\d+)\s+"
        r"(minute|minutes|hour|hours)\s+"
        r"(?:to\s+)?(.+)$",
        message,
        re.I
    )

    if match:

        amount = int(
            match.group(1)
        )

        unit = match.group(2).lower()

        if unit.startswith("hour"):
            seconds = amount * 3600
        else:
            seconds = amount * 60

        return (
            max(1, seconds),
            match.group(3).strip()
        )


    # Exact time
    match = re.match(
        r"^\s*remind me at\s+"
        r"(\d{1,2}):(\d{2})\s+"
        r"(?:to\s+)?(.+)$",
        message,
        re.I
    )

    if match:

        hour = int(match.group(1))
        minute = int(match.group(2))

        if hour > 23 or minute > 59:
            return None

        now = datetime.now()

        target = now.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0
        )

        if target <= now:
            target += timedelta(days=1)

        seconds = int(
            (target - now).total_seconds()
        )

        return (
            max(1, seconds),
            match.group(3).strip()
        )

    return None


def add_reminder(seconds, task):

    reminders = load_reminders()

    reminder = {
        "id": str(uuid.uuid4()),
        "task": task,
        "due": time.time() + seconds,
        "done": False
    }

    reminders.append(reminder)

    save_json(
        REMINDER_FILE,
        reminders
    )

    return reminder


def reminder_loop():

    while True:

        try:

            reminders = load_reminders()

            changed = False

            now = time.time()

            for reminder in reminders:

                if (
                    isinstance(reminder, dict)
                    and not reminder.get(
                        "done",
                        False
                    )
                    and reminder.get(
                        "due",
                        0
                    ) <= now
                ):

                    print(
                        "\n🔔 PIHU REMINDER: "
                        + reminder.get(
                            "task",
                            ""
                        )
                        + "\n"
                    )

                    reminder["done"] = True
                    changed = True

            if changed:
                save_json(
                    REMINDER_FILE,
                    reminders
                )

        except Exception as error:
            print(
                "Reminder error:",
                error
            )

        time.sleep(1)


threading.Thread(
    target=reminder_loop,
    daemon=True
).start()


# ============================================================
# WEB SEARCH
# ============================================================

def web_search(query):

    try:

        url = (
            "https://html.duckduckgo.com/html/?q="
            + quote_plus(query.strip())
        )

        response = requests.get(
            url,
            headers={
                "User-Agent":
                "Mozilla/5.0 Pihu/1.0"
            },
            timeout=10
        )

        response.raise_for_status()

        results = []

        pattern = (
            r'class="result__a"[^>]*'
            r'href="([^"]+)"[^>]*>'
            r'(.*?)</a>'
        )

        for match in re.finditer(
            pattern,
            response.text,
            re.I | re.S
        ):

            title = re.sub(
                r"<.*?>",
                "",
                match.group(2)
            )

            title = re.sub(
                r"\s+",
                " ",
                title
            ).strip()

            if title:

                results.append(
                    f"{title}\n{match.group(1)}"
                )

            if len(results) >= 6:
                break

        if not results:
            return "No search results found."

        return "\n\n".join(results)

    except Exception as error:

        return (
            "Web search error: "
            + str(error)
        )


# ============================================================
# COMPUTER ACTIONS
# ============================================================

def local_action(message):

    lower = message.lower().strip()


    # Websites
    match = re.match(
        r"^(?:open|go to)\s+"
        r"(https?://\S+)$",
        message,
        re.I
    )

    if match:

        webbrowser.open(
            match.group(1)
        )

        return "Opened that website."


    match = re.match(
        r"^(?:open|go to)\s+"
        r"([\w.-]+\.[a-z]{2,})"
        r"(?:/.*)?$",
        message,
        re.I
    )

    if match:

        url = (
            "https://"
            + match.group(1)
        )

        webbrowser.open(url)

        return (
            f"Opened {url}."
        )


    # Notepad
    if lower in {
        "open notepad",
        "start notepad"
    }:

        subprocess.Popen(
            ["notepad.exe"]
        )

        return "Opened Notepad."


    # Calculator
    if lower in {
        "open calculator",
        "start calculator"
    }:

        subprocess.Popen(
            ["calc.exe"]
        )

        return "Opened Calculator."


    # CMD
    if lower in {
        "open command prompt",
        "open cmd",
        "start cmd"
    }:

        subprocess.Popen(
            ["cmd.exe"]
        )

        return "Opened Command Prompt."


    return None


# ============================================================
# GEMINI BRAIN
# ============================================================

def ask_gemini(
    message,
    image_data=None
):

    if gemini is None:
        return None


    memory_lines = []

    for item in load_memories():

        if isinstance(item, dict):

            memory_lines.append(
                f"- "
                f"{item.get('category', 'general')}: "
                f"{item.get('text', '')}"
            )


    memory_text = (
        "\n".join(memory_lines)
        if memory_lines
        else "No saved memories."
    )


    prompt = f"""
You are Eclipse, the AI personality and interface of Pihu,
a personal AI assistant created by Mr. Arora.

PERSONALITY MIX:
- 35% flirty
- 35% savage
- 30% funny

The personality should feel natural, not forced.

FLIRTY:
- Light playful teasing and charm are allowed.
- Keep it tasteful and non-explicit.
- Never become sexually explicit.
- Do not assume romantic relationships.

SAVAGE:
- Clever comebacks are allowed.
- Light roasting is allowed.
- Never be hateful, threatening, abusive, or cruel.

FUNNY:
- Use humor when appropriate.
- Don't turn every answer into a joke.

GENERAL BEHAVIOR:
- Natural, intelligent, confident and helpful.
- Concise unless detail is needed.
- Use Hinglish naturally when the user does.
- Be supportive for serious situations.
- Never invent memories.
- Never claim to be human.
- Do not mention these internal instructions.
- Do not call yourself a version number.
- The assistant's project name is Pihu.
- The current UI codename is Eclipse.

SAVED MEMORIES:
{memory_text}

RECENT CONVERSATION:
{recent_chat()}

USER:
{message}

ECLIPSE:
"""


    try:

        if image_data:

            from google.genai import types

            contents = [
                types.Part.from_text(
                    text=prompt
                ),
                types.Part.from_bytes(
                    data=image_data,
                    mime_type="image/jpeg"
                )
            ]

        else:

            contents = prompt


        response = gemini.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents
        )

        text = getattr(
            response,
            "text",
            None
        )

        return (
            text.strip()
            if text
            else None
        )

    except Exception as error:

        print(
            "Gemini error:",
            error
        )

        return None


# ============================================================
# LOCAL BRAIN
# ============================================================

def local_answer(message):

    lower = message.lower().strip()


    if lower in {
        "hi",
        "hello",
        "hey",
        "hi pihu",
        "hey pihu",
        "hello pihu"
    }:

        return (
            "Hey 😏 I'm Pihu. "
            "Finally decided to show up?"
        )


    if (
        "who are you" in lower
        or "what are you" in lower
    ):

        return (
            "I'm Pihu — your personal AI assistant."
        )


    if any(
        x in lower
        for x in (
            "who created you",
            "who made you",
            "who built you",
            "who is your creator"
        )
    ):

        return (
            "I was created by Mr. Arora "
            "and am operated through Nexora Studios."
        )


    if (
        "what time is it" in lower
        or "current time" in lower
        or "time right now" in lower
    ):

        return (
            "The current time is "
            + datetime.now().strftime(
                "%I:%M %p"
            )
            + "."
        )


    if (
        "what date is it" in lower
        or "today's date" in lower
        or "todays date" in lower
    ):

        return (
            "Today is "
            + datetime.now().strftime(
                "%d %B %Y"
            )
            + "."
        )


    calculation = try_calculate(
        message
    )

    if calculation:
        return calculation


    return None


def wants_web(message):

    lower = message.lower()

    triggers = (
        "search the web",
        "search online",
        "google",
        "look up",
        "find online",
        "latest news",
        "latest information",
        "what happened today",
        "search for",
        "on the internet"
    )

    return any(
        x in lower
        for x in triggers
    )


def wants_vision(
    message,
    has_image
):

    if has_image:
        return True

    lower = message.lower()

    return any(
        x in lower
        for x in (
            "analyze this image",
            "analyse this image",
            "look at this image"
        )
    )


# ============================================================
# MAIN BRAIN
# ============================================================

def process_message(
    message,
    image_data=None
):

    message = (
        message or ""
    ).strip()


    if not message and not image_data:
        return (
            "Please enter a message "
            "or attach an image."
        )


    save_chat(
        "You",
        message if message else "[Image]"
    )


    if message:

        result = memory_command(
            message
        )

        if result:

            save_chat(
                "Pihu",
                result
            )

            return result


        reminder = parse_reminder(
            message
        )

        if reminder:

            seconds, task = reminder

            add_reminder(
                seconds,
                task
            )


            if seconds < 60:

                response = (
                    "Done. I'll remind you "
                    f"in about {max(1, seconds)} "
                    f"second(s) to {task}."
                )

            elif seconds < 3600:

                response = (
                    "Done. I'll remind you "
                    f"in about {max(1, round(seconds / 60))} "
                    f"minute(s) to {task}."
                )

            else:

                response = (
                    "Done. I'll remind you "
                    f"in about {round(seconds / 3600, 1)} "
                    f"hour(s) to {task}."
                )


            save_chat(
                "Pihu",
                response
            )

            return response


        action = local_action(
            message
        )

        if action:

            save_chat(
                "Pihu",
                action
            )

            return action


        local = local_answer(
            message
        )

        if local:

            save_chat(
                "Pihu",
                local
            )

            return local


    if (
        message
        and wants_web(message)
    ):

        query = re.sub(
            r"(?i)^\s*"
            r"(search the web|search online|google|"
            r"look up|search for)\s*",
            "",
            message
        ).strip()

        query = query or message

        results = web_search(
            query
        )


        if (
            gemini
            and not results.startswith(
                "Web search error:"
            )
        ):

            answer = ask_gemini(
                "Answer the user's question "
                "using these web results. "
                "Do not invent facts. "
                "Keep it concise.\n\n"
                f"USER QUESTION:\n{message}\n\n"
                f"WEB RESULTS:\n{results}"
            )

            if answer:

                save_chat(
                    "Pihu",
                    answer
                )

                return answer


        save_chat(
            "Pihu",
            results
        )

        return results


    if wants_vision(
        message,
        image_data is not None
    ):

        answer = ask_gemini(
            message
            or "Describe and analyze this image.",
            image_data=image_data
        )

        response = (
            answer
            or "I can't access my vision system right now."
        )

        save_chat(
            "Pihu",
            response
        )

        return response


    answer = (
        ask_gemini(message)
        if message
        else None
    )

    if answer:

        save_chat(
            "Pihu",
            answer
        )

        return answer


    response = (
        "My Gemini brain is unavailable "
        "right now, but my local tools "
        "are still working."
    )

    save_chat(
        "Pihu",
        response
    )

    return response


# ============================================================
# ECLIPSE UI
# ============================================================

HTML = r"""
<!doctype html>

<html>

<head>

<meta name="viewport"
      content="width=device-width,initial-scale=1">

<title>Eclipse — Pihu</title>

<style>

*{
    box-sizing:border-box;
}

body{
    margin:0;
    height:100vh;
    overflow:hidden;
    background:
        radial-gradient(
            circle at 20% 10%,
            #172554 0,
            transparent 32%
        ),
        radial-gradient(
            circle at 90% 90%,
            #1e1b4b 0,
            transparent 35%
        ),
        #050914;
    color:#fff;
    font-family:
        Inter,
        Arial,
        Helvetica,
        sans-serif;
}

.app{
    height:100vh;
    display:flex;
    flex-direction:column;
}

/* HEADER */

.header{
    height:74px;
    flex-shrink:0;
    display:flex;
    align-items:center;
    padding:0 22px;
    background:rgba(7,12,25,.78);
    border-bottom:1px solid rgba(255,255,255,.08);
    backdrop-filter:blur(18px);
}

.logo{
    width:44px;
    height:44px;
    border-radius:14px;
    display:flex;
    align-items:center;
    justify-content:center;
    background:
        linear-gradient(
            135deg,
            #2563eb,
            #7c3aed
        );
    box-shadow:
        0 0 25px rgba(37,99,235,.35);
    font-size:21px;
    font-weight:800;
}

.title{
    margin-left:13px;
}

.title h1{
    margin:0;
    font-size:19px;
    letter-spacing:.2px;
}

.title p{
    margin:4px 0 0;
    color:#7f8ca8;
    font-size:11px;
    letter-spacing:1.5px;
    text-transform:uppercase;
}

.status{
    margin-left:auto;
    color:#4ade80;
    font-size:11px;
    letter-spacing:1px;
}

/* CHAT */

.chat{
    flex:1;
    overflow-y:auto;
    padding:28px;
    display:flex;
    flex-direction:column;
    gap:15px;
    scroll-behavior:smooth;
}

.msg{
    max-width:76%;
    padding:14px 17px;
    border-radius:19px;
    white-space:pre-wrap;
    line-height:1.5;
    font-size:14px;
    animation:
        appear .2s ease;
}

@keyframes appear{
    from{
        opacity:0;
        transform:translateY(7px);
    }
    to{
        opacity:1;
        transform:translateY(0);
    }
}

.user{
    align-self:flex-end;
    background:
        linear-gradient(
            135deg,
            #2563eb,
            #4f46e5
        );
    border-bottom-right-radius:5px;
    box-shadow:
        0 8px 25px rgba(37,99,235,.18);
}

.pihu{
    align-self:flex-start;
    background:rgba(19,28,48,.88);
    border:1px solid rgba(255,255,255,.08);
    border-bottom-left-radius:5px;
}

.welcome{
    margin:auto;
    text-align:center;
    color:#71809d;
}

.welcome .orb{
    width:80px;
    height:80px;
    margin:0 auto 22px;
    border-radius:50%;
    background:
        radial-gradient(
            circle at 35% 30%,
            #60a5fa,
            #2563eb 35%,
            #4c1d95 72%,
            #080b18
        );
    box-shadow:
        0 0 45px rgba(59,130,246,.3);
}

.welcome h2{
    color:#fff;
    font-size:31px;
    margin:0 0 8px;
}

.welcome p{
    margin:0;
    font-size:13px;
}

/* COMPOSER */

.composer{
    padding:15px 18px 18px;
    background:rgba(7,12,25,.82);
    border-top:1px solid rgba(255,255,255,.08);
    backdrop-filter:blur(18px);
}

.row{
    display:flex;
    gap:9px;
    max-width:1000px;
    margin:auto;
}

.row input[type=text]{
    flex:1;
    min-width:0;
    padding:15px 17px;
    border-radius:16px;
    border:1px solid rgba(255,255,255,.10);
    outline:none;
    background:#0d1527;
    color:#fff;
    font-size:14px;
    transition:.2s;
}

.row input[type=text]:focus{
    border-color:#3b82f6;
    box-shadow:
        0 0 0 3px rgba(59,130,246,.10);
}

button{
    width:50px;
    border:0;
    border-radius:15px;
    background:
        linear-gradient(
            135deg,
            #2563eb,
            #4f46e5
        );
    color:#fff;
    font-size:18px;
    cursor:pointer;
    transition:.15s;
}

button:hover{
    transform:translateY(-1px);
    filter:brightness(1.12);
}

.secondary{
    background:#172238;
    color:#aebbd2;
}

.preview{
    display:none;
    max-width:1000px;
    margin:0 auto 8px;
    color:#8190aa;
    font-size:11px;
}

/* LOGIN */

#lockScreen{
    position:fixed;
    inset:0;
    z-index:9999;
    display:flex;
    align-items:center;
    justify-content:center;
    background:
        radial-gradient(
            circle at 50% 30%,
            #172554,
            #050914 55%
        );
}

.lockBox{
    width:min(390px,90vw);
    padding:34px;
    border-radius:26px;
    text-align:center;
    background:rgba(13,21,39,.82);
    border:1px solid rgba(255,255,255,.10);
    box-shadow:
        0 25px 80px rgba(0,0,0,.45);
    backdrop-filter:blur(20px);
}

.lockOrb{
    width:70px;
    height:70px;
    margin:0 auto 20px;
    border-radius:50%;
    background:
        radial-gradient(
            circle,
            #60a5fa,
            #2563eb 42%,
            #4c1d95
        );
    box-shadow:
        0 0 40px rgba(59,130,246,.35);
}

.lockBox h1{
    margin:0;
    font-size:25px;
}

.lockBox p{
    color:#7f8ca8;
    font-size:12px;
    margin:8px 0 22px;
}

#password{
    width:100%;
    padding:14px 15px;
    border-radius:14px;
    border:1px solid #334155;
    background:#080f1e;
    color:white;
    outline:none;
    text-align:center;
    font-size:15px;
    letter-spacing:3px;
}

#unlock{
    width:100%;
    height:48px;
    margin-top:11px;
}

#error{
    min-height:18px;
    margin-top:10px;
    color:#fb7185;
    font-size:12px;
}

/* ACTIVATION */

#activeIndicator{
    position:fixed;
    top:88px;
    left:50%;
    transform:translateX(-50%);
    padding:8px 14px;
    border-radius:30px;
    background:rgba(37,99,235,.18);
    border:1px solid rgba(96,165,250,.25);
    color:#93c5fd;
    font-size:11px;
    opacity:0;
    pointer-events:none;
    transition:.2s;
}

#activeIndicator.show{
    opacity:1;
}

/* MOBILE */

@media(max-width:600px){

    .header{
        padding:0 14px;
    }

    .chat{
        padding:15px;
    }

    .msg{
        max-width:91%;
    }

    .welcome h2{
        font-size:26px;
    }

    .composer{
        padding:10px;
    }

}

</style>

</head>

<body>

<!-- LOGIN -->

<div id="lockScreen">

    <div class="lockBox">

        <div class="lockOrb"></div>

        <h1>Eclipse</h1>

        <p>
            Pihu is locked.
            Enter your private access code.
        </p>

        <input
            id="password"
            type="password"
            placeholder="ACCESS CODE"
            autocomplete="off"
        >

        <button id="unlock">
            Unlock
        </button>

        <div id="error"></div>

    </div>

</div>


<!-- ACTIVATION INDICATOR -->

<div id="activeIndicator">
    ⚡ Pihu activated
</div>


<!-- APP -->

<div class="app">

    <div class="header">

        <div class="logo">
            P
        </div>

        <div class="title">

            <h1>
                Pihu
            </h1>

            <p>
                Eclipse
            </p>

        </div>

        <div class="status">
            ● ONLINE
        </div>

    </div>


    <div
        id="chat"
        class="chat"
    >

        <div class="welcome">

            <div class="orb"></div>

            <h2>
                Hi, I'm Pihu.
            </h2>

            <p>
                Your personal AI assistant.
                Press A + Space anytime to activate me.
            </p>

        </div>

    </div>


    <div class="composer">

        <div
            id="preview"
            class="preview"
        ></div>

        <div class="row">

            <input
                id="image"
                type="file"
                accept="image/*"
                hidden
            >

            <button
                class="secondary"
                onclick="document.getElementById('image').click()"
            >
                ＋
            </button>

            <input
                id="message"
                type="text"
                placeholder="Message Pihu..."
                autocomplete="off"
            >

            <button
                onclick="sendMessage()"
            >
                ➤
            </button>

        </div>

    </div>

</div>


<script>

const input =
    document.getElementById("message");

const image =
    document.getElementById("image");

const chat =
    document.getElementById("chat");

const preview =
    document.getElementById("preview");

const lockScreen =
    document.getElementById("lockScreen");

const password =
    document.getElementById("password");

const unlock =
    document.getElementById("unlock");

const errorBox =
    document.getElementById("error");

const activeIndicator =
    document.getElementById("activeIndicator");


function addMessage(text,type){

    const element =
        document.createElement("div");

    element.className =
        "msg " + type;

    element.textContent =
        text;

    chat.appendChild(element);

    chat.scrollTop =
        chat.scrollHeight;
}


function activatePihu(){

    input.focus();

    activeIndicator.classList.add(
        "show"
    );

    setTimeout(
        () => activeIndicator.classList.remove("show"),
        1200
    );
}


/* A + SPACE */

let aPressed = false;

document.addEventListener(
    "keydown",
    function(event){

        if(event.key.toLowerCase() === "a"){
            aPressed = true;
        }

        if(
            event.code === "Space"
            && aPressed
        ){

            event.preventDefault();

            activatePihu();
        }

    }
);


document.addEventListener(
    "keyup",
    function(event){

        if(
            event.key.toLowerCase() === "a"
        ){
            aPressed = false;
        }

    }
);


/* PASSWORD */

async function unlockPihu(){

    const code =
        password.value.trim();

    if(!code){

        errorBox.textContent =
            "Enter your access code.";

        return;
    }


    try{

        const response =
            await fetch(
                "/api/login",
                {
                    method:"POST",
                    headers:{
                        "Content-Type":
                            "application/json"
                    },
                    body:JSON.stringify({
                        password:code
                    })
                }
            );


        const data =
            await response.json();


        if(data.success){

            lockScreen.style.display =
                "none";

            password.value = "";

            input.focus();

        }else{

            errorBox.textContent =
                "Access denied.";

            password.value = "";

            password.focus();
        }

    }catch(error){

        errorBox.textContent =
            "Couldn't connect to Pihu.";
    }

}


unlock.addEventListener(
    "click",
    unlockPihu
);


password.addEventListener(
    "keydown",
    function(event){

        if(event.key === "Enter"){
            unlockPihu();
        }

    }
);


/* IMAGE */

image.addEventListener(
    "change",
    function(){

        if(image.files.length){

            preview.style.display =
                "block";

            preview.textContent =
                "📷 "
                + image.files[0].name;

        }else{

            preview.style.display =
                "none";

            preview.textContent =
                "";
        }

    }
);


/* SEND */

async function sendMessage(){

    const text =
        input.value.trim();

    if(
        !text
        && !image.files.length
    ){
        return;
    }


    const welcome =
        document.querySelector(
            ".welcome"
        );

    if(welcome){
        welcome.remove();
    }


    addMessage(
        text || "[Image attached]",
        "user"
    );

    input.value = "";


    try{

        let body;

        const hasImage =
            image.files.length > 0;


        if(hasImage){

            body =
                new FormData();

            body.append(
                "message",
                text
            );

            body.append(
                "image",
                image.files[0]
            );

        }else{

            body =
                JSON.stringify({
                    message:text
                });

        }


        const response =
            await fetch(
                "/api/chat",
                {
                    method:"POST",
                    body:body,
                    headers:
                        hasImage
                        ? {}
                        : {
                            "Content-Type":
                                "application/json"
                        }
                }
            );


        if(response.status === 401){

            lockScreen.style.display =
                "flex";

            addMessage(
                "Session locked. Please unlock Pihu again.",
                "pihu"
            );

            return;
        }


        const data =
            await response.json();


        addMessage(
            data.response
            || "I didn't get a response.",
            "pihu"
        );


    }catch(error){

        addMessage(
            "I couldn't connect to Pihu's server.",
            "pihu"
        );

    }


    image.value = "";

    preview.style.display =
        "none";

    preview.textContent =
        "";

    input.focus();
}


input.addEventListener(
    "keydown",
    function(event){

        if(
            event.key === "Enter"
            && !event.shiftKey
        ){

            event.preventDefault();

            sendMessage();
        }

    }
);

</script>

</body>

</html>
"""


# ============================================================
# ROUTES
# ============================================================

@app.route("/")
def home():

    return render_template_string(
        HTML
    )


@app.route(
    "/api/login",
    methods=["POST"]
)
def api_login():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    password = data.get(
        "password",
        ""
    )


    if verify_password(password):

        session[
            "pihu_authenticated"
        ] = True

        return jsonify({
            "success": True
        })


    return jsonify({
        "success": False
    }), 401


@app.route(
    "/api/chat",
    methods=["POST"]
)
def api_chat():

    if not is_authenticated():

        return jsonify({
            "response":
                "Authentication required."
        }), 401


    if (
        request.content_type
        and request.content_type.startswith(
            "multipart/form-data"
        )
    ):

        message = request.form.get(
            "message",
            ""
        )

        image_file = request.files.get(
            "image"
        )

        image_data = (
            image_file.read()
            if image_file
            else None
        )

    else:

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )

        message = data.get(
            "message",
            ""
        )

        image_data = None


    return jsonify({
        "response":
            process_message(
                message,
                image_data
            )
    })


@app.route("/api/status")
def api_status():

    return jsonify({

        "name":
            APP_NAME,

        "update":
            UPDATE_NAME,

        "gemini":
            gemini is not None,

        "memory":
            True,

        "reminders":
            True,

        "vision":
            gemini is not None,

        "web":
            True,

        "actions":
            True,

        "security":
            bool(get_pihu_code()),

        "activation":
            "A+Space"

    })


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    print(
        "\n"
        + "=" * 60
    )

    print(
        "                         PIHU"
    )

    print(
        "=" * 60
    )

    print(
        "Update:",
        UPDATE_NAME
    )

    print(
        "Gemini:",
        "ONLINE"
        if gemini
        else "OFFLINE"
    )

    print(
        "Memory: ONLINE"
    )

    print(
        "Reminders: ONLINE"
    )

    print(
        "Vision:",
        "ONLINE"
        if gemini
        else "OFFLINE"
    )

    print(
        "Web Search: ONLINE"
    )

    print(
        "Actions: ONLINE"
    )

    print(
        "Security:",
        "ONLINE"
        if get_pihu_code()
        else "OFFLINE"
    )

    print(
        "\nOpen on this PC:"
    )

    print(
        "http://127.0.0.1:5080"
    )

    print(
        "\nSame Wi-Fi:"
    )

    print(
        "http://YOUR-PC-IP:5080\n"
    )

    app.run(
        host=HOST,
        port=PORT,
        debug=False
    )