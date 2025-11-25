from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import status, stream, control, production

app = FastAPI(title="BM9 WrapSafe API")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(status.router, prefix="/api/status", tags=["Status"])
app.include_router(stream.router, prefix="/api/stream", tags=["Stream"])
app.include_router(control.router, prefix="/api/control", tags=["Control"])
app.include_router(production.router, prefix="/api/production", tags=["Production"])

@app.get("/")
def read_root():
    return {"message": "BM9 WrapSafe API is running"}
