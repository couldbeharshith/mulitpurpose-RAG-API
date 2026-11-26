"""
Hugging Face Spaces entry point for Insurance RAG API
This file is required by Hugging Face Spaces to run the application
"""

import os
import sys

# Include the repository root for the backend package
sys.path.insert(0, os.path.dirname(__file__))

# Set platform environment variable for Hugging Face Spaces
os.environ['PLATFORM'] = 'huggingface'

# Import and run the FastAPI app
from backend.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
 
