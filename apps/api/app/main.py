from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.tracks import router as tracks_router
from app.routes.transitions import router as transitions_router

app = FastAPI(
    title="Song Transition Studio API",
    version="0.1.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tracks_router)
app.include_router(transitions_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
