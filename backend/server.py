import os
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.pipeline.ingestor import scan_folder, find_duplicates
from backend.pipeline.tagger import tag_with_ollama, tag_with_claude
from backend.pipeline.sorter import sort_images

# ── Init the web service instance (unnecessary comments but looks cool) ────────────────────
app = FastAPI()
#  Electron's renderer process to call this server
app.add_middleware(
    CORSMiddleware,                             # IMPORTANT for desktop app
    allow_origins=["http://localhost:5173"],    # Vite port
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory session state ──────────────────────────────────────
# Stores the current scan/tag results between requests since FastAPI is stateless between calls
session = {
    "records": [],
    "tags": [],
    "status": "idle",                           # idle | scanning | tagging | sorting | done | error
    "progress": 0,
    "total": 0,
    "errors": [],
}

# ── Request models ───────────────────────────────────────────────
class ScanRequest(BaseModel):
    folder_path: str

class TagRequest(BaseModel):
    backend: str = "ollama"                     # "ollama" or "claude"
    api_key: str = ""                           # Claude API key IF backend use Claude

class SortRequest(BaseModel):
    output_folder: str

# ── Endpoints ────────────────────────────────────────────────────

@app.get("/status")
def get_status():
    """Frontend polls this to show progress bar."""
    return {
        "status":   session["status"],
        "progress": session["progress"],
        "total":    session["total"],
        "errors":   session["errors"],
    }

@app.post("/scan")
def scan(req: ScanRequest):
    """Step 1 — scan folder and detect duplicates."""
    # Normalize path separators regardless of what the frontend sends
    folder_path = req.folder_path.replace("\\", "/")
    if not os.path.exists(folder_path):
        raise HTTPException(status_code=400, detail="Folder not found")

    session["status"] = "scanning"
    session["errors"] = []

    try:
        records = scan_folder(folder_path)
        records = find_duplicates(records)
        session["records"] = records
        session["status"] = "idle"

        # Count duplicate groups
        dup_groups = len(set(
            r.duplicate_group for r in records
            if r.duplicate_group is not None
        ))

        return {
            "total":            len(records),
            "duplicate_groups": dup_groups,
            # Send basic file info to frontend for preview
            "images": [
                {
                    "path":            r.path,
                    "filename":        r.filename,
                    "size_bytes":      r.size_bytes,
                    "width":           r.width,
                    "height":          r.height,
                    "duplicate_group": r.duplicate_group,
                }
                for r in records
            ]
        }
    except Exception as e:
        session["status"] = "error"
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tag")
async def tag(req: TagRequest):
    """
    Step 2 — tag all scanned images.
    Runs async so the frontend can poll /status for progress.
    """
    if not session["records"]:
        raise HTTPException(status_code=400, detail="No images scanned yet. Call /scan first.")

    session["status"]   = "tagging"
    session["progress"] = 0
    session["total"]    = len(session["records"])
    session["tags"]     = []
    session["errors"]   = []

    # Run tagging in the background so the endpoint returns immediately
    asyncio.create_task(_run_tagging(req.backend, req.api_key))

    return {"message": f"Tagging started for {session['total']} images"}


async def _run_tagging(backend: str, api_key: str):
    """Background task — updates session progress as it goes."""
    tags = []
    for i, record in enumerate(session["records"]):
        try:
            if backend == "ollama":
                result = tag_with_ollama(record.path)
            else:
                result = tag_with_claude(record.path, api_key)
            tags.append(result)
        except Exception as e:
            session["errors"].append(f"{record.filename}: {str(e)}")
            # Append a fallback so indexes stay aligned with records
            from backend.pipeline.tagger import ImageTags
            tags.append(ImageTags(
                path=record.path, category="other", tags=[],
                ocr_text="", is_nsfw=False,
                description="error", backend=backend
            ))

        session["progress"] = i + 1

    session["tags"]   = tags
    session["status"] = "done"


@app.get("/results")
def get_results():
    """Return full tag results after tagging is complete."""
    if session["status"] not in ("done", "sorting"):
        raise HTTPException(status_code=400, detail="Tagging not complete yet")

    return {
        "images": [
            {
                "path":            r.path,
                "filename":        r.filename,
                "duplicate_group": r.duplicate_group,
                "category":        t.category,
                "tags":            t.tags,
                "is_nsfw":         t.is_nsfw,
                "ocr_text":        t.ocr_text,
                "description":     t.description,
            }
            for r, t in zip(session["records"], session["tags"])
        ]
    }


@app.post("/sort")
def sort(req: SortRequest):
    """Step 3 — copy images into category folders."""
    if not session["tags"]:
        raise HTTPException(status_code=400, detail="No tags yet. Call /tag first.")

    session["status"] = "sorting"

    try:
        sort_images(session["records"], session["tags"], req.output_folder)
        session["status"] = "done"
        return {"message": f"Images sorted into {req.output_folder}"}
    except Exception as e:
        session["status"] = "error"
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reset")
def reset():
    """Clear session so user can start a new folder."""
    session["records"]  = []
    session["tags"]     = []
    session["status"]   = "idle"
    session["progress"] = 0
    session["total"]    = 0
    session["errors"]   = []
    return {"message": "Session cleared"}