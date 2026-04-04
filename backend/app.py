#"""
#app.py  —  Nakshatra (updated)
#================================
#Root FastAPI app — mounts all routers including new services.
#Replace the existing backend/app.py with this file.
#"""
#
#from fastapi import FastAPI
#from fastapi.middleware.cors import CORSMiddleware
#
## Existing router
#from backend.api.server import router as core_router
#
## ── NEW routers ──────────────────────────────────────────────────
#from backend.api.session_manager import router as session_manager_router
#from backend.api.cognitive_service import router as cognitive_router
#from backend.api.server_additions import router as additions_router
## ────────────────────────────────────────────────────────────────
#
#app = FastAPI(
#    title="Nakshatra — AI Neuro-Rehabilitation System",
#    version="2.0.0",
#)
#
#app.add_middleware(
#    CORSMiddleware,
#    allow_origins=["*"],    # restrict in production
#    allow_credentials=True,
#    allow_methods=["*"],
#    allow_headers=["*"],
#)
#
## Mount all routers under /api/v1
#app.include_router(core_router,            prefix="/api/v1")
#app.include_router(session_manager_router, prefix="/api/v1")
#app.include_router(cognitive_router,       prefix="/api/v1")
#app.include_router(additions_router,       prefix="/api/v1")
#
#
#@app.get("/", tags=["health"])
#def health():
#    return {"status": "online", "version": "2.0.0"}
#
#
#if __name__ == "__main__":
#    import uvicorn
#    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)