import os
import sys
import asyncio
import requests
from dotenv import load_dotenv
from pydantic import BaseModel

from fastmcp import McpServer, Content
from fastmcp.transport.http import HttpServerTransport

# Load environment variables from a .env file
load_dotenv()

# --- Constants ---
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama3-8b-8192" # Using a current Groq model
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# --- Create MCP Server ---
server = McpServer(
    name="puchcraft-mcp-py",
    version="1.0.0",
)

# --- Define Tool Input Schema ---
class ServerStatusInput(BaseModel):
    """Input schema for the get_server_status tool."""
    server_ip: str

# --- Tool: get_server_status ---
@server.tool(
    name="get_server_status",
    input_model=ServerStatusInput,
    description="Gets the status of a Minecraft server. If it's offline, suggests alternatives."
)
async def get_server_status(params: ServerStatusInput) -> Content:
    """
    Checks Minecraft server status and provides alternatives if offline.
    """
    server_ip = params.server_ip
    try:
        # 1) Check server status via mcsrvstat.us
        res = requests.get(f"https://api.mcsrvstat.us/2/{server_ip}")
        res.raise_for_status()  # Raise an exception for bad status codes
        data = res.json()

        if data.get("online"):
            # Server is online, return its details
            players = data.get("players", {})
            motd_lines = data.get("motd", {}).get("clean", ["N/A"])
            return Content(
                content=[
                    {"type": "text", "text": f"Server {server_ip} is ONLINE."},
                    {"type": "text", "text": f"Players: {players.get('online', 0)}/{players.get('max', 0)}"},
                    {"type": "text", "text": f"MOTD: {' '.join(motd_lines)}"},
                ],
                metadata={"raw": data},
            )

        # 2) If offline, ask Groq for suggested alternatives
        prompt = f"""
You are PuchCraft AI, an expert on popular public Minecraft servers.
A server is offline.

Hostname: {server_ip}
Please suggest 3 similar, active and popular Minecraft servers (Name — IP — 1-line reason each).
Format as:
1. Name — IP — Reason
2. ...
3. ...
        """.strip()

        groq_resp = requests.post(
            GROQ_API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {GROQ_API_KEY}",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
            },
        )

        if not groq_resp.ok:
            # Handle Groq API errors
            error_text = groq_resp.text
            print(f"Groq error: {groq_resp.status_code}, {error_text}", file=sys.stderr)
            return Content(
                content=[
                    {"type": "text", "text": f"Server {server_ip} is OFFLINE."},
                    {"type": "text", "text": f"Unable to fetch alternatives from Groq (status {groq_resp.status_code})."},
                ],
                metadata={"mcsrv": data},
            )

        groq_json = groq_resp.json()
        suggestions = groq_json.get("choices", [{}])[0].get("message", {}).get("content", "No suggestions returned.").strip()

        return Content(
            content=[
                {"type": "text", "text": f"Server {server_ip} is OFFLINE."},
                {"type": "text", "text": "Suggested alternatives:"},
                {"type": "text", "text": suggestions},
            ],
            metadata={"mcsrv": data, "groq": groq_json},
        )

    except requests.RequestException as e:
        print(f"Network error: {e}", file=sys.stderr)
        return Content(
            content=[{"type": "text", "text": f"Network error checking {server_ip}: {e}"}],
            metadata={"error": str(e)},
        )
    except Exception as e:
        print(f"Tool error: {e}", file=sys.stderr)
        return Content(
            content=[{"type": "text", "text": f"An unexpected error occurred while checking {server_ip}."}],
            metadata={"error": str(e)},
        )

# --- Main execution block ---
async def main():
    """Sets up and runs the MCP server."""
    port = int(os.getenv("PORT", 3000))
    transport = HttpServerTransport(port=port, host="0.0.0.0")
    try:
        await server.connect(transport)
        print(f"✅ MCP server running on http://0.0.0.0:{port}", file=sys.stderr)
        # Keep the server running
        while True:
            await asyncio.sleep(3600)
    except Exception as e:
        print(f"❌ Failed to start MCP server: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    # Ensure you have a GROQ_API_KEY in your .env file or environment
    if not GROQ_API_KEY:
        print("❌ GROQ_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)
        
    asyncio.run(main())