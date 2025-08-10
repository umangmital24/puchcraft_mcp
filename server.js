
import dotenv from "dotenv";
dotenv.config();

import fetch from "node-fetch";
import { McpServer, HttpServerTransport } from "@modelcontextprotocol/sdk/server";

import { z } from "zod";

const GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions";
const GROQ_MODEL = "openai/gpt-oss-20b"; // change if you use a different model

// Create MCP server
const server = new McpServer({
  name: "puchcraft-mcp",
  version: "1.0.0",
});

// Tool: get_server_status
server.tool(
  "get_server_status",
  // Input schema using zod
  { server_ip: z.string() },
  async ({ server_ip }) => {
    try {
      // 1) Check server status via mcsrvstat.us
      const res = await fetch(`https://api.mcsrvstat.us/2/${server_ip}`);
      const data = await res.json();

      if (data.online) {
        // Return MCP-style content
        return {
          content: [
            { type: "text", text: `Server ${server_ip} is ONLINE.` },
            { type: "text", text: `Players: ${data.players?.online || 0}/${data.players?.max || 0}` },
            { type: "text", text: `MOTD: ${data.motd?.clean?.join(" ") || "N/A"}` },
          ],
          metadata: { raw: data },
        };
      }

      // 2) If offline, ask Groq for suggested alternatives
      const prompt = `
You are PuchCraft AI, an expert on popular public Minecraft servers.
A server is offline.

Hostname: ${server_ip}
Please suggest 3 similar, active and popular Minecraft servers (Name — IP — 1-line reason each).
Format as:
1. Name — IP — Reason
2. ...
3. ...
      `.trim();

      const groqResp = await fetch(GROQ_API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${process.env.GROQ_API_KEY}`,
        },
        body: JSON.stringify({
          model: GROQ_MODEL,
          messages: [{ role: "user", content: prompt }],
        }),
      });

      if (!groqResp.ok) {
        const text = await groqResp.text();
        console.error("Groq error:", groqResp.status, text);
        return {
          content: [
            { type: "text", text: `Server ${server_ip} is OFFLINE.` },
            { type: "text", text: `Unable to fetch alternatives from Groq (status ${groqResp.status}).` },
          ],
          metadata: { mcsrv: data },
        };
      }

      const groqJson = await groqResp.json();
      // Groq response shape assumed similar to OpenAI; guard for safety:
      const suggestions =
        groqJson?.choices?.[0]?.message?.content?.trim() ||
        groqJson?.choices?.[0]?.text ||
        "No suggestions returned.";

      return {
        content: [
          { type: "text", text: `Server ${server_ip} is OFFLINE.` },
          { type: "text", text: "Suggested alternatives:" },
          { type: "text", text: suggestions },
        ],
        metadata: { mcsrv: data, groq: groqJson },
      };
    } catch (err) {
      console.error("Tool error:", err);
      return {
        content: [{ type: "text", text: `Error checking ${server_ip}: ${err.message}` }],
        metadata: { error: String(err) },
      };
    }
  }
);

// Connect server over stdio so MCP hosts/clients can launch it and talk via stdin/stdout.
// Wrap in async IIFE to await connect at top-level.
(async () => {
  try {
    const transport = new HttpServerTransport({
      port: process.env.PORT || 3000,
      host: "0.0.0.0", // Listen on all interfaces
    });
    await server.connect(transport);
    console.error(`✅ MCP server running on port ${process.env.PORT || 3000}`);
  } catch (e) {
    console.error("❌ Failed to start MCP server:", e);
    process.exit(1);
  }
})();

