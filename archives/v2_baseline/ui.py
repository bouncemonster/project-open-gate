"""
PROOF OF SIMULATION — Terminal UI
Live ANSI terminal display with fallback to plain mode.
"""
import sys
import os
import time

WIDTH = 60
HEIGHT = 30
ASCII_PALETTE = " .:-=+*#%@"
SPARKLINE = "▁▂▃▄▅▆▇█"


def is_tty():
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def clear_screen():
    if is_tty():
        sys.stdout.write("\033[2J\033[H")
    else:
        sys.stdout.write("\n" * 3)


def move_home():
    if is_tty():
        sys.stdout.write("\033[H")


def color(text, code):
    if is_tty():
        return f"\033[{code}m{text}\033[0m"
    return text


def bold(text):
    return color(text, "1")


def green(text):
    return color(text, "32")


def yellow(text):
    return color(text, "33")


def red(text):
    return color(text, "31")


def cyan(text):
    return color(text, "36")


def render_field_ascii(field, width=WIDTH, height=HEIGHT):
    """Render a field as ASCII art."""
    lines = []
    for row in range(height):
        line = ""
        for col in range(width):
            idx = row * width + col
            if idx < len(field):
                level = int(field[idx] * len(ASCII_PALETTE))
                level = max(0, min(len(ASCII_PALETTE) - 1, level))
                line += ASCII_PALETTE[level]
            else:
                line += " "
        lines.append(line)
    return "\n".join(lines)


def sparkline(values, max_len=40):
    """Render values as sparkline characters."""
    if not values:
        return ""
    vals = values[-max_len:]
    vmin = min(vals)
    vmax = max(vals)
    vrange = vmax - vmin
    if vrange < 1e-15:
        return SPARKLINE[3] * len(vals)
    chars = []
    for v in vals:
        idx = int((v - vmin) / vrange * (len(SPARKLINE) - 1))
        idx = max(0, min(len(SPARKLINE) - 1, idx))
        chars.append(SPARKLINE[idx])
    return "".join(chars)


class TerminalUI:
    """Live terminal UI for the experiment."""

    def __init__(self, quiet=False):
        self.quiet = quiet
        self.tty = is_tty()
        self.last_render = 0
        self.fps = 8
        self.status_messages = []

    def should_render(self):
        if self.quiet:
            return False
        now = time.time()
        if now - self.last_render >= 1.0 / self.fps:
            self.last_render = now
            return True
        return False

    def render(self, state):
        """
        Render the full screen.
        state: dict with keys:
            phase, step, total_steps, model, driver, cr, ci,
            current_score, best_score,
            pearson01, spectral01, gradient01, autocorrelation01,
            prime_uplift, shuffle_degradation,
            current_field, target_field,
            score_history, status
        """
        if self.quiet:
            return

        if self.tty:
            move_home()
        else:
            if self.should_render():
                pass
            else:
                return

        lines = []
        lines.append(bold("=" * 62))
        lines.append(bold("         PROOF OF SIMULATION — Live Observatory"))
        lines.append(bold("=" * 62))
        lines.append("")

        # Phase and step
        phase = state.get("phase", "INIT")
        step = state.get("step", 0)
        total = state.get("total_steps", 100)
        lines.append(f"  PHASE: {cyan(phase)}    STEP: {step}/{total}")
        lines.append("")

        # Model info
        model = state.get("model", "N/A")
        driver = state.get("driver", "N/A")
        cr = state.get("cr", 0)
        ci = state.get("ci", 0)
        lines.append(f"  Model: {model}   Driver: {driver}")
        lines.append(f"  C: {cr:.6f} + {ci:.6f}i")
        lines.append("")

        # Scores
        current = state.get("current_score", 0)
        best = state.get("best_score", 0)
        lines.append(f"  Current Score: {current:.6f}    Best Score: {green(f'{best:.6f}')}")
        lines.append("")

        # Metric components
        p01 = state.get("pearson01", 0)
        sp01 = state.get("spectral01", 0)
        g01 = state.get("gradient01", 0)
        a01 = state.get("autocorrelation01", 0)
        lines.append(f"  Pearson: {p01:.4f}  Spectral: {sp01:.4f}  "
                      f"Gradient: {g01:.4f}  AutoCorr: {a01:.4f}")
        lines.append("")

        # Uplifts
        pu = state.get("prime_uplift", 0)
        sd = state.get("shuffle_degradation", 0)
        pu_str = green(f"+{pu:.4f}") if pu > 0 else red(f"{pu:.4f}")
        sd_str = green(f"+{sd:.4f}") if sd > 0 else red(f"{sd:.4f}")
        lines.append(f"  Prime Uplift: {pu_str}    Shuffle Degradation: {sd_str}")
        lines.append("")

        # Sparkline
        history = state.get("score_history", [])
        if history:
            spark = sparkline(history)
            lines.append(f"  Score History: {spark}")
            lines.append("")

        # Maps (compact)
        current_field = state.get("current_field")
        target_field = state.get("target_field")
        if current_field and target_field:
            lines.append("  CURRENT MAP              TARGET MAP")
            cf_lines = render_field_ascii(current_field).split("\n")
            tf_lines = render_field_ascii(target_field).split("\n")
            for i in range(min(len(cf_lines), len(tf_lines))):
                lines.append(f"  {cf_lines[i]}  {tf_lines[i]}")
            lines.append("")

        # Status messages
        status = state.get("status", "")
        if status:
            lines.append(f"  STATUS: {yellow(status)}")

        for msg in self.status_messages[-3:]:
            lines.append(f"  {yellow(msg)}")

        output = "\n".join(lines)
        sys.stdout.write(output)
        sys.stdout.flush()

    def announce(self, msg):
        """Add a status announcement."""
        self.status_messages.append(msg)
        if not self.tty:
            print(msg)

    def quiet_update(self, state):
        """Print a single-line update for quiet mode."""
        if not self.quiet:
            return
        phase = state.get("phase", "?")
        step = state.get("step", 0)
        best = state.get("best_score", 0)
        status = state.get("status", "")
        line = f"[{phase}] step={step} best={best:.6f}"
        if status:
            line += f" {status}"
        print(line)

    def final_screen(self, result):
        """Display the final result screen."""
        status = result.get("status", "FINISHED")
        best_score = result.get("best_score", 0)
        best_cr = result.get("best_cr", 0)
        best_ci = result.get("best_ci", 0)
        model = result.get("model", "N/A")
        prime_uplift = result.get("prime_uplift", 0)
        shuffle_deg = result.get("shuffle_degradation", 0)
        null_max = result.get("null_max", 0)
        depth_stable = result.get("depth_stable", "N/A")
        res_stable = result.get("resolution_stable", "N/A")
        holdout = result.get("holdout", "N/A")

        border = "╔" + "═" * 58 + "╗"
        mid = "╠" + "═" * 58 + "╣"
        bottom = "╚" + "═" * 58 + "╝"

        print()
        print(border)
        print("║" + "       PROOF OF SIMULATION — FINISHED".center(58) + "║")
        print(mid)
        print(f"║ STATUS:              {status:<37}║")
        print(f"║ BEST SCORE:          {best_score:.6f}{' ' * 31}║")
        print(f"║ BEST C:              {best_cr:.6f} + {best_ci:.6f}i{' ' * 22}║")
        print(f"║ MODEL:               {model:<37}║")
        pu_sign = "+" if prime_uplift >= 0 else ""
        print(f"║ PRIME UPLIFT:        {pu_sign}{prime_uplift:.4f}{' ' * 32}║")
        sd_sign = "+" if shuffle_deg >= 0 else ""
        print(f"║ SHUFFLE DEGRADATION: {sd_sign}{shuffle_deg:.4f}{' ' * 32}║")
        print(f"║ NULL MAX:            {null_max:.6f}{' ' * 31}║")
        print(f"║ DEPTH STABLE:        {str(depth_stable):<37}║")
        print(f"║ RESOLUTION STABLE:   {str(res_stable):<37}║")
        print(f"║ HOLDOUT:             {str(holdout):<37}║")
        print("║" + " " * 58 + "║")
        print("║ REPORT: report.md" + " " * 40 + "║")
        print(bottom)
