import math
import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

EMAIL = "23f3003379@ds.study.iitm.ac.in"
ALLOWED_ORIGIN = "https://app-4ixqwy.example.com"
EXAM_ORIGIN = "https://exam.sanand.workers.dev"   # <-- fill in (scheme + host, no path)

BUCKET = 8          # B requests ...
WINDOW = 10.0       # ... per 10 seconds

app = FastAPI()
client_hits = defaultdict(deque)


# Starlette runs middleware in REVERSE order of registration:
# the one added LAST is the outermost layer.
# We want:  CORS (outer)  ->  request context  ->  rate limiter (inner)
# so we register them in the opposite order: limiter, context, CORS.

# ---------- Middleware 3 (innermost): per-client rate limiting ----------
@app.middleware("http")
async def rate_limit(request: Request, call_next):
    client_id = request.headers.get("x-client-id")
    if client_id:
        now = time.monotonic()
        q = client_hits[client_id]
        while q and now - q[0] >= WINDOW:
            q.popleft()
        if len(q) >= BUCKET:
            retry_after = max(1, math.ceil(WINDOW - (now - q[0])))
            return JSONResponse(
                status_code=429,
                content={"detail": "Too Many Requests"},
                headers={"Retry-After": str(retry_after)},
            )
        q.append(now)
    return await call_next(request)


# ---------- Middleware 1: request context ----------
@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid      # also on 429s
    return response


# ---------- Middleware 2 (outermost): scoped CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN, EXAM_ORIGIN],     # exact origins only, never "*"
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],                             # X-Client-Id, X-Request-ID
    expose_headers=["X-Request-ID", "Retry-After"],  # so browser JS can read them
    allow_credentials=False,
)


@app.get("/")
def health():
    return {"status": "ok"}


@app.get("/ping")
def ping(request: Request):
    return {"email": EMAIL, "request_id": request.state.request_id}
