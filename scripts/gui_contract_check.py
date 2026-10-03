"""Real Tk widget checks with explicit local state fixture. No Codex or listener."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
import tkinter as tk
from codex_vita.gui import Window

root = tk.Tk()
window = Window(root)
try:
    root.update_idletasks()
    assert not window.controller.busy
    def poll_once():
        if window.timer:
            root.after_cancel(window.timer)
        window.poll()
        root.update_idletasks()
    window.controller._set(phase='prepared', config='TEST-FIXTURE-A.json')
    poll_once()
    assert window.config.get() == 'TEST-FIXTURE-A.json'
    window.config.set('TEST-FIXTURE-USER-SELECTED.json')
    poll_once()
    assert window.config.get() == 'TEST-FIXTURE-USER-SELECTED.json', 'Polling overwrote the selected configuration'
    window.controller._set(phase='prepared', config='TEST-FIXTURE-B.json')
    poll_once()
    assert window.config.get() == 'TEST-FIXTURE-B.json'
    def layout(widget):
        for child in widget.winfo_children():
            if child.winfo_ismapped():
                x = child.winfo_rootx() - root.winfo_rootx()
                y = child.winfo_rooty() - root.winfo_rooty()
                assert x >= 0 and y >= 0
                assert x + child.winfo_width() <= root.winfo_width() + 2
                assert y + child.winfo_height() <= root.winfo_height() + 2
            layout(child)
    layout(root)
    assert not window.controller.busy and not window.controller.snapshot().pin
    print('Real Tk: idle state, selected configuration and window bounds passed. No account or runtime.')
finally:
    window.destroy()
