from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from . import models  # noqa: F401 — import registers models on SQLModel.metadata
from .config import settings
from .limiter import limiter
from .routers import (
    admin,
    auth,
    company_info,
    compliance,
    credit,
    customers,
    loans,
    platform,
    profile,
    signup,
    staff,
    transactions,
)

app = FastAPI(title="Rupha Royals Lending Platform API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(company_info.router)
app.include_router(platform.router)
app.include_router(staff.router)
app.include_router(signup.router)
app.include_router(profile.router)
app.include_router(compliance.router)
app.include_router(customers.router)
app.include_router(loans.router)
app.include_router(credit.router)
app.include_router(transactions.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
