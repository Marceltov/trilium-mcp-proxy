# Fixture

`trilium-data/` is a committed, disposable Trilium Notes v0.106.1 database for the live tests. It's a
copy of the recall engine's fixture in
[trilium-llm-wiki](https://github.com/Marceltov/trilium-llm-wiki/tree/main/recall-engine/fixture)
(Trilium's demo notes plus a small synthetic wiki), with the option `mcpEnabled` set to `true` while
Trilium was stopped, so the built-in MCP server is on.

The login password is `trilium-mcp`, a throwaway credential for this fixture only. `run-tests.sh` resets
the database before and after each run.
