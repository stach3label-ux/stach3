"""Vektra Open - AI MCP server package.

Serves a Model Context Protocol endpoint from the bot's own HTTP server:

  - /mcp                                        stateless JSON-RPC endpoint
  - /oauth/authorize                            password-based OAuth authorize page
  - /oauth/token                                token endpoint (code + refresh)
  - /oauth/revoke                               token revocation
  - /.well-known/oauth-authorization-server     RFC 8414 metadata

Auth is a single shared password (MCP_PASSWORD env var) entered during the
connector flow - no Discord login, no server selection (the bot is
single-server by design).
"""
