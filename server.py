import asyncio
import os
from typing import Annotated
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.auth.providers.bearer import BearerAuthProvider, RSAKeyPair
from mcp.server.auth.provider import AccessToken
from pydantic import Field
from mcstatus import JavaServer
import httpx

# --- Load environment variables ---
load_dotenv()

TOKEN = os.environ.get("AUTH_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
MY_NUMBER = os.environ.get("MY_NUMBER")

assert TOKEN, "Please set AUTH_TOKEN in your .env file"
assert GROQ_API_KEY, "Please set GROQ_API_KEY in your .env file"
assert MY_NUMBER, "Please set MY_NUMBER in your .env file"


# --- Auth Provider ---
class SimpleBearerAuthProvider(BearerAuthProvider):
    def __init__(self, token: str):
        k = RSAKeyPair.generate()
        super().__init__(public_key=k.public_key, jwks_uri=None, issuer=None, audience=None)
        self.token = token

    async def load_access_token(self, token: str) -> AccessToken | None:
        if token == self.token:
            return AccessToken(
                token=token,
                client_id="puch-client",
                scopes=["*"],
                expires_at=None,
            )
        return None


# --- Helper: Suggest Alternatives via Groq ---
async def groq_suggest_alternatives() -> str:
    """Ask Groq LLM for Minecraft server suggestions."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "mixtral-8x7b-32768",
        "messages": [
            {"role": "system", "content": "You suggest popular online Minecraft servers with IP addresses."},
            {"role": "user", "content": "Suggest 5 popular Minecraft servers that are usually online, with their IP addresses."}
        ],
        "temperature": 0.7
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        else:
            return f"⚠️ Error from Groq API: {resp.text}"


# --- MCP Server Setup ---
mcp = FastMCP(
    "Minecraft Server Finder MCP",
    auth=SimpleBearerAuthProvider(TOKEN),
)


# --- Tool: validate ---
@mcp.tool
async def validate() -> str:
    return MY_NUMBER


# --- Tool: minecraft_server_finder ---
@mcp.tool(description="Check Minecraft server status by IP/Domain, and suggest alternatives if offline.")
async def minecraft_server_finder(
    server_address: Annotated[str, Field(description="Minecraft server IP or domain")],
    port: Annotated[int | None, Field(description="Port number, defaults to 25565")] = 25565
) -> str:
    try:
        server = JavaServer.lookup(f"{server_address}:{port}")
        status = server.status()
        return (
            f"🎮 **Minecraft Server Status**\n"
            f"🖥 Server: `{server_address}:{port}`\n"
            f"✅ **Online**\n"
            f"👥 Players: {status.players.online}/{status.players.max}\n"
            f"📢 MOTD: {status.description}\n"
            f"⏱ Latency: {status.latency} ms"
        )
    except Exception:
        suggestions = await groq_suggest_alternatives()
        return (
            f"❌ The server `{server_address}:{port}` appears to be **offline**.\n\n"
            f"💡 **Here are some alternative servers:**\n{suggestions}"
        )


# --- Run MCP Server ---
async def main():
    print("🚀 Starting Minecraft Server Finder MCP on http://0.0.0.0:8086")
    await mcp.run_async("streamable-http", host="0.0.0.0", port=8086)


if __name__ == "__main__":
    asyncio.run(main())
