import asyncio
from typing import Annotated
import os
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.auth.providers.bearer import BearerAuthProvider, RSAKeyPair
from mcp import ErrorData, McpError
from mcp.server.auth.provider import AccessToken
from mcp.types import INVALID_PARAMS
from pydantic import Field
from mcstatus import JavaServer
import httpx

# --- Load environment variables ---
load_dotenv()

TOKEN = os.environ.get("AUTH_TOKEN")
MY_NUMBER = os.environ.get("MY_NUMBER")

assert TOKEN is not None, "Please set AUTH_TOKEN in your .env file"
assert MY_NUMBER is not None, "Please set MY_NUMBER in your .env file"

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

# --- Helper: DuckDuckGo Search ---
async def google_search_links(query: str, num_results: int = 5) -> list[str]:
    """Perform a DuckDuckGo search and return a list of URLs."""
    ddg_url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
    links = []

    async with httpx.AsyncClient() as client:
        resp = await client.get(ddg_url, headers={"User-Agent": "MinecraftServerFinder/1.0"})
        if resp.status_code != 200:
            return ["<error>Failed to perform search.</error>"]

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "html.parser")
    for a in soup.find_all("a", class_="result__a", href=True):
        href = a["href"]
        if "http" in href:
            links.append(href)
        if len(links) >= num_results:
            break

    return links or ["<error>No results found.</error>"]

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
        # If offline, suggest alternatives
        alt_links = await google_search_links("public Minecraft servers list")
        return (
            f"❌ The server `{server_address}:{port}` appears to be **offline**.\n\n"
            f"💡 **Here are some alternative servers:**\n" +
            "\n".join(f"- {link}" for link in alt_links)
        )

# --- Run MCP Server ---
async def main():
    print("🚀 Starting Minecraft Server Finder MCP on http://0.0.0.0:8086")
    await mcp.run_async("streamable-http", host="0.0.0.0", port=8086)

if __name__ == "__main__":
    asyncio.run(main())
