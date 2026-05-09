from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import calendar, countries, elections

app = FastAPI(title="ElectWatch API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(calendar.router, prefix="/api")
app.include_router(elections.router, prefix="/api")
app.include_router(countries.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
