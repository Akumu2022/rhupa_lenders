from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from . import models  # noqa: F401 — import registers models on SQLModel.metadata
from .config import settings
from .limiter import limiter
from .routers import (
    admin,
    analytics,
    auth,
    platform_security,
    branch_assignment,
    branch_manager,
    committee,
    company_info,
    compliance,
    credit,
    customers,
    finance,
    guarantors,
    internal,
    loans,
    management,
    mfa,
    platform,
    profile,
    signup,
    staff,
    transactions,
)

app = FastAPI(title="Rupha Royals Lending Platform API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_SECURITY_HEADERS = {
    # API responses carry customer PII and money figures: never cache them
    # in the browser or any proxy.
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    for header, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(mfa.router)
app.include_router(admin.router)
app.include_router(company_info.router)
app.include_router(platform.router)
app.include_router(platform_security.router)
app.include_router(staff.router)
app.include_router(signup.router)
app.include_router(profile.router)
app.include_router(compliance.router)
app.include_router(customers.router)
app.include_router(guarantors.router)
app.include_router(loans.router)
app.include_router(credit.router)
app.include_router(transactions.router)
app.include_router(branch_manager.router)
app.include_router(committee.router)
app.include_router(finance.router)
app.include_router(management.router)
app.include_router(analytics.router)
app.include_router(internal.router)
app.include_router(branch_assignment.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
