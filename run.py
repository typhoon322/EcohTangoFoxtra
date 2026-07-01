#!/usr/bin/env python3
"""
ETF Analyzer — Launch Script
Starts the FastAPI backend on http://localhost:8765
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

if __name__ == "__main__":
    import uvicorn
    print("Starting ETF Analyzer on http://localhost:8765")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8765,
        reload=True,
        app_dir=os.path.join(os.path.dirname(__file__), "backend"),
    )
