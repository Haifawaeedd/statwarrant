---
title: statwarrant MCP server
emoji: 📏
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# statwarrant MCP server

A remote [MCP](https://modelcontextprotocol.io) server for
[statwarrant](https://github.com/Haifawaeedd/statwarrant): AI assistants such as Claude and
ChatGPT can ask what a statistical result warrants, and have the claims in a sentence judged
by statwarrant's tests.

Endpoint: `https://<your-space>.hf.space/mcp` (Streamable HTTP, no sign-in, read-only tools).

To deploy: create a Docker Space and add this folder's `Dockerfile` and `README.md`. Set
`STATWARRANT_REF` in the Dockerfile to the tag or branch you want to serve.

Sentences sent to a public server leave your computer. For unpublished or confidential text,
run the server locally instead (`pip install "statwarrant[mcp]"`, then `statwarrant-mcp`).
