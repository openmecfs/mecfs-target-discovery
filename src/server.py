"""
mecfs-target-discovery MCP server

One server, many tools. Registers all tools from src/tools/.
Run via:
    python src/server.py                    # stdio (for Claude Desktop / Cursor)
    fastmcp dev src/server.py               # dev mode with inspector
    fastmcp install src/server.py           # install into Claude Desktop

Claude Desktop config:
    {
      "mcpServers": {
        "mecfs-target-discovery": {
          "command": "python",
          "args": ["/path/to/mecfs-target-discovery/src/server.py"]
        }
      }
    }
"""
from fastmcp import FastMCP

from src.tools import query_decodeme, rank_targets

mcp = FastMCP(
    name="mecfs-target-discovery",
    instructions=(
        "ME/CFS treatment-target discovery toolkit. "
        "Tools chain from DecodeME GWAS loci → causal genes → druggable targets → existing drugs. "
        "Every result carries full provenance. Data-first, genetics-anchored. "
        "Start with rank_targets for a full ranked list, or query_decodeme for raw GWAS signals."
    ),
)

query_decodeme.register(mcp)
rank_targets.register(mcp)


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
