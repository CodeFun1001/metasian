import sys
import os
import threading
import time

sys.path.insert(0, os.path.dirname(__file__))

import uvicorn
from server.app import app

def _start_gradio():
    time.sleep(2)
    try:
        from ui.dashboard import launch
        launch(port=7861, share=False)
    except Exception as e:
        print(f"[UI] Gradio failed to start: {e}", flush=True)

def main():
    
    if os.getenv("ENABLE_UI") == "true":
        threading.Thread(target=_start_gradio, daemon=True).start()
    uvicorn.run("server.app:main", host="0.0.0.0", port=7860, reload=False)

if __name__ == "__main__":
    main()