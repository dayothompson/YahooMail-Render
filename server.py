from __future__ import annotations

import os

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from yahoo_mail.mcp_server import mcp


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


# Wrap FastMCP's SSE app alongside a /health endpoint for Render's health check.
app = Starlette(
    routes=[
        Route("/health", health),
        Mount("/", app=mcp.sse_app()),
    ]
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
