"""
Desktop UI automation — find ComfyUI window and interact with it (mouse focus/click).

Requires: pygetwindow, pyautogui (install with pip install pygetwindow pyautogui).
Used so the user can see the mouse interacting with the ComfyUI desktop window
when running manual flows.
"""

import sys


def focus_comfyui_and_click(click_inside: bool = True) -> bool:
    """
    Find the ComfyUI desktop window, bring it to front, and optionally
    move the mouse to the window and click (so the user sees interaction).

    Returns True if the window was found and activated, False otherwise.
    """
    try:
        import pygetwindow as gw
        import pyautogui
    except ImportError as e:
        print(
            "Desktop UI automation skipped: install pygetwindow and pyautogui "
            "(pip install pygetwindow pyautogui)",
            file=sys.stderr,
        )
        return False

    # Find window whose title contains "ComfyUI" (case-insensitive)
    candidates = []
    for w in gw.getAllWindows():
        if not w.title:
            continue
        if "comfyui" in w.title.lower():
            candidates.append(w)

    if not candidates:
        print("ComfyUI window not found (no window title containing 'ComfyUI').", file=sys.stderr)
        return False

    win = candidates[0]
    try:
        win.activate()
    except Exception as e:
        # Windows sometimes raises "Error code 0 - The operation completed successfully"
        if "completed successfully" in str(e).lower() or "0" in str(e):
            pass  # Assume it worked
        else:
            print(f"Could not activate ComfyUI window: {e}", file=sys.stderr)
            return False

    # Small delay so the window comes to front
    pyautogui.PAUSE = 0.3
    pyautogui.sleep(0.5)

    try:
        left, top, width, height = win.left, win.top, win.width, win.height
    except Exception:
        return True  # We activated at least

    # Move mouse to center of window (visible interaction)
    center_x = left + width // 2
    center_y = top + height // 2
    pyautogui.moveTo(center_x, center_y, duration=0.25)

    if click_inside:
        pyautogui.click()
        pyautogui.sleep(0.2)

    return True


def main():
    """CLI entry: focus ComfyUI window and click inside it."""
    ok = focus_comfyui_and_click(click_inside=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
