"""
On-screen recording indicator.

Shows a small always-on-top bar while the node is capturing the screen, so a
person physically at the PC always knows they are being recorded. This is a
consent/privacy feature, not decoration — it is the reason the recorder can be
exposed to a remote peer at all.

The widget is built with customtkinter, which is a Windows/macOS desktop
dependency. Headless Linux nodes and minimal installs do not have it, so the
module degrades to a no-op instead of raising ImportError at node startup: the
recording still works, only the local indicator is absent. The node reports this
via `overlay_manager.available` so the UI can warn the user.

TODO(roadmap P3-L4): replace the Tk overlay with a native, dependency-free
indicator per platform (Win32 layered window / X11-EWMH / Wayland layer-shell).
"""

import logging
import threading

log = logging.getLogger("cypher")

try:
    import customtkinter as ctk
    HAS_TK_OVERLAY = True
except ImportError:  # pragma: no cover - expected on headless/minimal installs
    ctk = None
    HAS_TK_OVERLAY = False
    log.info("customtkinter unavailable — recording overlay disabled")


class RecordingOverlay:
    """Floating 'CYPHER RECORDING' indicator. Safe to call when unavailable."""

    def __init__(self):
        self.root = None
        self.stop_event = threading.Event()
        self.is_active = False

    @property
    def available(self) -> bool:
        """False when the platform cannot draw the indicator."""
        return HAS_TK_OVERLAY

    def start(self):
        if self.is_active or not HAS_TK_OVERLAY:
            return
        self.is_active = True
        self.stop_event.clear()
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self.is_active = False
        self.stop_event.set()
        if self.root:
            try:
                self.root.after(0, self.root.destroy)
            except Exception as exc:
                # The Tk root may already be gone (thread exited, display closed,
                # or customtkinter was unavailable so self.root is a stale ref).
                # Teardown is best-effort: the overlay must not outlive the
                # recording, and a failure here must not propagate into the
                # recording-stop path.
                log.debug("Overlay teardown raced with Tk shutdown: %s", exc)

    def _run(self):
        try:
            self.root = ctk.CTk()

            # Small floating bar, top-centre of the primary display.
            screen_width = self.root.winfo_screenwidth()
            width = 240
            height = 40
            x = (screen_width // 2) - (width // 2)
            y = 10  # 10px from the top edge

            self.root.geometry(f"{width}x{height}+{x}+{y}")
            self.root.overrideredirect(True)   # no title bar
            self.root.attributes("-topmost", True)   # always on top
            self.root.attributes("-alpha", 0.9)      # slightly transparent
            self.root.configure(fg_color="#1A1A1A")

            frame = ctk.CTkFrame(
                self.root, fg_color="#1A1A1A", corner_radius=20,
                border_width=1, border_color="#FF453A",
            )
            frame.pack(fill="both", expand=True)

            self.dot = ctk.CTkLabel(
                frame, text="\u25cf", font=("Segoe UI", 18, "bold"),
                text_color="#FF453A",
            )
            self.dot.pack(side="left", padx=(20, 10))

            ctk.CTkLabel(
                frame, text="CYPHER RECORDING", font=("Segoe UI", 11, "bold"),
                text_color="#FFFFFF",
            ).pack(side="left")

            def blink():
                if not self.is_active:
                    return
                current = self.dot.cget("text_color")
                new_color = "#FF453A" if current != "#FF453A" else "#333333"
                self.dot.configure(text_color=new_color)
                self.root.after(800, blink)

            self.root.after(800, blink)
            self.root.mainloop()
        except Exception as exc:  # never take the node down over an indicator
            log.warning(f"Recording overlay failed to start: {exc}")
            self.is_active = False


# Global instance, imported by core/server.py::get_overlay_manager()
overlay_manager = RecordingOverlay()
