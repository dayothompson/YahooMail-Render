from __future__ import annotations

import os

import uvicorn

from yahoo_mail.mcp_server import mcp

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(mcp.sse_app(), host="0.0.0.0", port=port)
