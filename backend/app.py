import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import the router we just built
from api.server import router as api_router

# Initialize FastAPI
app = FastAPI(title="Nakshatra Rehab API", version="1.0")

# CRITICAL: CORS allows your React frontend to talk to this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the router under the /api/v1 prefix
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
def health_check():
    return {"status": "online", "message": "Nakshatra API is running and ready for frontend requests."}

if __name__ == "__main__":
    # Run the server on port 8000. host="0.0.0.0" makes it available on your local Wi-Fi.
    uvicorn.run("app:app", host="[IP_ADDRESS]", port=8000, reload=True)