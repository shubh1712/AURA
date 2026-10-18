"""AURA Backend Cloud Run and Local Entrypoint Shim."""

import os
import uvicorn
from app.config import settings

if __name__ == "__main__":
    port = int(os.environ.get("PORT", settings.PORT))
    host = os.environ.get("HOST", settings.HOST)
    uvicorn.run("app.main:app", host=host, port=port, reload=settings.DEBUG)
