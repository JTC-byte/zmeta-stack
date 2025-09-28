# ZMeta Stack

This is where we are building the Z-ISR metadata pipeline project.  
Right now, this repo will grow step by step as we add:

- A backend (FastAPI)
- A UDP → WebSocket bridge
- A recorder & replay tool
- Simulators for RF, thermal, and acoustic detections
- A Leaflet dashboard to visualize everything live

---

## Quick Start (Windows PowerShell)

```powershell
# Create & activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies (temporary list)
pip install fastapi uvicorn pydantic[dotenv] websockets pytest python-dotenv

# Run backend (will work once we add main.py)
uvicorn backend.app.main:app --reload
```

---

## Roadmap

- [ ] Harden Z-Meta schema (timestamps, confidence, TTL)
- [ ] Build UDP → WebSocket bridge
- [ ] Add recorder & replay
- [ ] Build rules & alerts engine
- [ ] Add timeline scrubber & trails
- [ ] Ingest real RF/thermal data
- [ ] Implement fusion layer

---

## Dev Tips

- Use feature branches for new work:  
  `git checkout -b feat/udp-ws-bridge`
- Commit small and often with clear messages.
- Save files as **UTF-8** to avoid GitHub display issues.
