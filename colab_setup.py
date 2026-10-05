import nest_asyncio
import uvicorn
from pyngrok import ngrok
from backend.app import app

# This script is designed to run the FastAPI backend inside a Google Colab Notebook cell.
# Colab runs an existing asyncio event loop, so we need nest_asyncio to allow uvicorn to run.

import os
from dotenv import load_dotenv
load_dotenv()

if __name__ == "__main__":
    nest_asyncio.apply()

    # To expose the Colab port to the internet, we use ngrok.
    ngrok_token = os.getenv("NGROK_AUTH_TOKEN")
    if ngrok_token:
        ngrok.set_auth_token(ngrok_token)
    else:
        print("Warning: NGROK_AUTH_TOKEN not found in .env")
    
    # Open a HTTP tunnel on the default port 8000
    try:
        public_url = ngrok.connect(8000)
        print("="*60)
        print(f"🚀 Public API URL for your frontend: {public_url}")
        print("Update API_BASE_URL and WS_URL in map_gis.js to point to this URL.")
        print("="*60)
    except Exception as e:
        print("Could not start ngrok tunnel. Did you set the auth token?", e)

    # Start the server on 0.0.0.0
    uvicorn.run(app, host="0.0.0.0", port=8000)
