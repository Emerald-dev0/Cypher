import pystray
from PIL import Image, ImageDraw
import threading
import os
import logging

log = logging.getLogger("cypher")

def create_tray_image():
    # Create a 64x64 image with a solid color and a simple shape
    image = Image.new("RGB", (64, 64), "#6C63FF")
    draw = ImageDraw.Draw(image)
    # Draw a white square in the middle
    draw.rectangle((16, 16, 48, 48), fill="white")
    return image

def start_tray():
    try:
        def on_show(icon, item):
            # In a real app, this would restore the window
            # For now, we'll just log it
            log.info("Tray: Show Dashboard requested")

        def on_exit(icon, item):
            log.info("Tray: Exit requested")
            icon.stop()
            os._exit(0)

        image = create_tray_image()

        icon = pystray.Icon("Cypher", image, "CYPHER", menu=pystray.Menu(
            pystray.MenuItem("Show Dashboard", on_show),
            pystray.MenuItem("Exit", on_exit)
        ))

        threading.Thread(target=icon.run, daemon=True).start()
        log.info("Tray icon started successfully")
    except Exception as e:
        log.error(f"Tray startup failed: {e}")
