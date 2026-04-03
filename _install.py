"""
OpenHouse Bot — Visual Installer
Run via:  python _install.py
"""
import sys
import os
import subprocess
import shutil
import time
import random

# ── ANSI Colors (work on Windows 10+ CMD and all terminals) ──────────────────
R  = "\033[31m"   # red
G  = "\033[32m"   # green
Y  = "\033[33m"   # yellow
B  = "\033[34m"   # blue
M  = "\033[35m"   # magenta
C  = "\033[36m"   # cyan
W  = "\033[37m"   # white
BLD= "\033[1m"    # bold
DIM= "\033[2m"    # dim
RST= "\033[0m"    # reset
BG = "\033[44m"   # blue bg

def enable_ansi():
    """Enable ANSI on Windows CMD."""
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

enable_ansi()

# ── Housing quotes & facts ────────────────────────────────────────────────────
QUOTES = [
    '"Home is not a place, it\'s a feeling." — Cecelia Ahern',
    '"The ache for home lives in all of us." — Maya Angelou',
    '"A house is made of walls and beams; a home is made of love and dreams."',
    '"Every house where love abides is home, and home, sweet home." — Henry van Dyke',
    '"Home is wherever I\'m with you." — Edward Sharpe',
    '"Where we love is home — home that our feet may leave, but not our hearts." — Holmes',
    '"No matter where you are, you\'re always a little homesick." — Clemens',
]

FACTS = [
    "🏠 FACT: The average person moves 11 times in their lifetime.",
    "🏙️ FACT: Berlin has one of Europe's highest renter populations — over 85% rent!",
    "💶 FACT: In Amsterdam, the average wait for social housing is 10+ years.",
    "📈 FACT: Global city rents rose 5.8% on average in 2023.",
    "🔑 FACT: The word 'mortgage' comes from Old French meaning 'death pledge'.",
    "🌍 FACT: Tokyo has more 7-Eleven stores than apartments in some districts.",
    "🧱 FACT: The oldest known apartment building dates to ancient Rome, 2nd century AD.",
    "📊 FACT: London renters spend ~40% of income on rent vs. EU average of 28%.",
    "🤖 FACT: AI-powered bots like OpenHouse save hours of manual apartment searching.",
    "⏱️ FACT: The average apartment hunter spends 3+ hours/day searching listings.",
]

# ── House ASCII animation frames ──────────────────────────────────────────────
HOUSE_FRAMES = [
    # Frame 1 - foundation
    [
        f"  {DIM}                                {RST}",
        f"  {Y}████████████████████████████{RST}",
        f"  {Y}█                          █{RST}",
        f"  {Y}████████████████████████████{RST}",
        f"  {G}▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓{RST}",
    ],
    # Frame 2 - walls
    [
        f"  {DIM}                                {RST}",
        f"  {Y}████████████████████████████{RST}",
        f"  {Y}█  {W}┃{Y}                    {W}┃{Y}  █{RST}",
        f"  {Y}█  {W}┃{Y}       WALLS         {W}┃{Y}  █{RST}",
        f"  {Y}█  {W}┃{Y}                    {W}┃{Y}  █{RST}",
        f"  {Y}████████████████████████████{RST}",
        f"  {G}▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓{RST}",
    ],
    # Frame 3 - roof going up
    [
        f"  {R}         /\\\\          {RST}",
        f"  {R}        /  \\\\         {RST}",
        f"  {R}       /    \\\\        {RST}",
        f"  {Y}████████████████████████████{RST}",
        f"  {Y}█  {W}┃{Y}                    {W}┃{Y}  █{RST}",
        f"  {Y}█  {W}┃{Y}                    {W}┃{Y}  █{RST}",
        f"  {Y}████████████████████████████{RST}",
        f"  {G}▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓{RST}",
    ],
    # Frame 4 - full house
    [
        f"  {R}         /\\\\          {RST}",
        f"  {R}        /  \\\\         {RST}",
        f"  {R}       / 🏠 \\\\        {RST}",
        f"  {R}      /──────\\\\──     {RST}",
        f"  {Y}  ██████████████████  {RST}",
        f"  {Y}  █  {C}▓▓▓▓{Y}    {C}▓▓▓▓{Y}  █  {RST}",
        f"  {Y}  █  {C}▓▓▓▓{Y}    {C}▓▓▓▓{Y}  █  {RST}",
        f"  {Y}  █    {M}┃┃┃┃┃┃{Y}      █  {RST}",
        f"  {Y}  █    {M}┃┃┃┃┃┃{Y}      █  {RST}",
        f"  {Y}  ██████████████████  {RST}",
        f"  {G}▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓{RST}",
    ],
]

LOGO = f"""
{C}{BLD}
   ██████╗ ██████╗ ███████╗███╗   ██╗██╗  ██╗ ██████╗ ██╗   ██╗███████╗███████╗
  ██╔═══██╗██╔══██╗██╔════╝████╗  ██║██║  ██║██╔═══██╗██║   ██║██╔════╝██╔════╝
  ██║   ██║██████╔╝█████╗  ██╔██╗ ██║███████║██║   ██║██║   ██║███████╗█████╗
  ██║   ██║██╔═══╝ ██╔══╝  ██║╚██╗██║██╔══██║██║   ██║██║   ██║╚════██║██╔══╝
  ╚██████╔╝██║     ███████╗██║ ╚████║██║  ██║╚██████╔╝╚██████╔╝███████║███████╗
   ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═══╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚══════╝╚══════╝
{RST}{DIM}              AI-Powered Apartment Hunter · v1.0.0{RST}
"""

def clear():
    os.system("cls" if sys.platform == "win32" else "clear")

def hr(char="─", color=C):
    print(f"{color}{char * 62}{RST}")

def status(icon, label, color=G):
    print(f"  {color}{BLD}{icon}{RST}  {label}")

def step_header(n, label):
    print()
    hr("═", C)
    print(f"  {C}{BLD}Step {n}/5  —  {label}{RST}")
    hr("═", C)

def show_quote():
    q = random.choice(QUOTES + FACTS)
    print(f"\n  {DIM}{Y}💬  {q}{RST}\n")

def animate_house(frame_idx):
    """Print one house frame."""
    frame = HOUSE_FRAMES[min(frame_idx, len(HOUSE_FRAMES)-1)]
    for line in frame:
        print(f"    {line}")

def spinner_check(label, check_fn):
    """Run check_fn, show spinner, return result."""
    chars = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    sys.stdout.write(f"  {C}  Checking {label}...{RST}")
    sys.stdout.flush()
    result = check_fn()
    print(f"\r  {G}{BLD}✔{RST}  {label:<25} {result}")
    return result

def run(cmd, capture=False):
    if capture:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return r.stdout.strip(), r.returncode
    else:
        return subprocess.run(cmd, shell=True).returncode

def main():
    clear()
    print(LOGO)
    show_quote()
    time.sleep(1)

    # ─── Step 1: Python ────────────────────────────────────────────────────────
    step_header(1, "Checking Python")
    animate_house(0)
    show_quote()

    py_ver, _ = run("python --version", capture=True)
    if not py_ver:
        py_ver, _ = run("python3 --version", capture=True)
    status("✔", f"Python found: {py_ver}", G)

    # Verify 3.9+
    try:
        major = int(py_ver.split()[1].split(".")[0])
        minor = int(py_ver.split()[1].split(".")[1])
        if major < 3 or (major == 3 and minor < 9):
            status("✘", f"Python 3.9+ required. Found {py_ver}. Install at https://python.org", R)
            sys.exit(1)
    except Exception:
        pass

    # ─── Step 2: pip ──────────────────────────────────────────────────────────
    step_header(2, "Checking pip")
    animate_house(1)
    show_quote()

    pip_ver, rc = run("pip --version", capture=True)
    if rc == 0:
        status("✔", "pip is available", G)
    else:
        status("…", "pip not found. Installing via ensurepip...", Y)
        run("python -m ensurepip --upgrade")
        status("✔", "pip installed", G)

    # ─── Step 3: Git ──────────────────────────────────────────────────────────
    step_header(3, "Checking Git")
    animate_house(1)
    show_quote()

    git_ver, rc = run("git --version", capture=True)
    if rc == 0:
        status("✔", f"Git found: {git_ver}", G)
    else:
        status("✘", "Git not found. Install at https://git-scm.com/downloads", R)
        sys.exit(1)

    # ─── Step 4: Existing install ─────────────────────────────────────────────
    step_header(4, "Checking existing installation")
    animate_house(2)
    show_quote()

    _, rc = run("pip show openhouse-bot", capture=True)
    already_installed = (rc == 0)

    if already_installed:
        ver, _ = run('pip show openhouse-bot | findstr Version', capture=True)
        status("ℹ", f"OpenHouse Bot already installed ({ver.strip()})", C)
        print()
        ans = input(f"  {Y}Reinstall / upgrade? (y/N):{RST} ").strip().lower()
        skip = ans not in {"y","yes","ya","ja","yep","sure"}
    else:
        status("ℹ", "OpenHouse Bot not yet installed.", C)
        skip = False

    # ─── Step 5: Install ──────────────────────────────────────────────────────
    step_header(5, "Installing OpenHouse Bot")
    animate_house(3)
    show_quote()

    if skip:
        status("✔", "Skipping installation (already up to date)", G)
    else:
        print(f"\n  {C}Running pip install ...{RST}\n")
        rc = run("pip install . --quiet --progress-bar off")
        print()
        if rc == 0:
            status("✔", "OpenHouse Bot installed successfully!", G)
        else:
            status("✘", "Installation failed. Check the output above.", R)
            sys.exit(1)

    # ─── Done! ────────────────────────────────────────────────────────────────
    print()
    hr("═", G)
    print(f"\n{G}{BLD}  🏠  OpenHouse Bot is ready!{RST}\n")
    print(f"  Run anytime with:  {C}{BLD}python -m openhouse.cli{RST}")
    hr("═", G)
    show_quote()

    ans = input(f"  {Y}Launch OpenHouse Bot now? (y/N):{RST} ").strip().lower()
    if ans in {"y","yes","ya","ja","yep","sure"}:
        print()
        hr()
        run("python -m openhouse.cli")

if __name__ == "__main__":
    main()
