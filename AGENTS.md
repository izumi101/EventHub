<!-- SCOPE: Canonical machine-facing entry point with repo map, critical rules, command overview, and links to detailed documentation ONLY. -->
<!-- DOC_KIND: index -->
<!-- DOC_ROLE: canonical -->
<!-- READ_WHEN: Start here when you need the project map, local rules, or the next canonical document. -->
<!-- SKIP_WHEN: Skip when you already know the exact target document or code area. -->
<!-- PRIMARY_SOURCES: AGENTS.md, docs/README.md -->

# EventHub

Event management platform — Django REST backend + Angular frontend. Users create and attend events; organizers manage tickets, seat maps, and QR check-in.

## Quick Navigation

| Need | Read |
|------|------|
| Frontend source | `EventHub/frontend/src/` |
| Backend source | `EventHub/backend/` |
| Docker setup | `EventHub/docker-compose.yml` |
| API collection | `EventHub/postman_collection.json` |
| Docs | `EventHub/docs/` |

## Agent Entry

- Purpose: Canonical repo map and routing layer for agents.
- Read when: You need the project overview, local rules, or the next canonical doc.
- Skip when: You already know the exact file or code area to inspect.
- Canonical: Yes.
- Read next: `EventHub/docs/` for architecture, then the relevant source directory.

## Critical Rules

| Category | Rule | When to Apply |
|----------|------|---------------|
| Business logic | Organizer cannot buy tickets to their own event | All ticket/booking flows |
| Business logic | Clients cannot cancel confirmed bookings directly | Booking cancellation flows |
| Business logic | Seat selection must persist across page navigation | Seat map and checkout flows |
| Navigation | Respect `SCOPE` and `Agent Entry` in each document | Before reading deep content |
| Task Management | Follow the provider in `.hex-skills/environment_state.json` (file mode) | For all task operations |
| Language | Keep project code and documentation in English | All written project artifacts |
| Research | Use context7 for Angular/Django/Docker documentation | Before stack-specific decisions |

## MCP Tool Preferences

| Need | Preferred flow |
|------|----------------|
| Discover files | `mcp__hex-line__inspect_path` with a narrow path |
| Search text | `mcp__hex-line__grep_search(output_mode="summary")`, then narrow |
| Read code | `mcp__hex-line__read_file` outline or targeted read |
| Edit code | `mcp__hex-line__read_file(edit_ready=true)` → `mcp__hex-line__edit_file(base_revision)` |
| Semantic risk | `mcp__hex-graph__index_project` → symbol/architecture analysis |
| Docs lookup | `mcp__context7__resolve-library-id` → `mcp__context7__query-docs` |
| Fallback | Built-in Read/Edit/Write/Grep/Glob or shell when MCP unavailable |

## Development Commands

| Task | Bash |
|------|------|
| Start full stack | `cd EventHub && docker compose up` |
| Start frontend only | `cd EventHub/frontend && npm start` |
| Install frontend deps | `cd EventHub/frontend && npm install` |
| Run frontend tests | `cd EventHub/frontend && npm test` |
| Build frontend | `cd EventHub/frontend && npm run build` |
| Backend migrations | `docker compose exec backend python manage.py migrate` |
| Backend shell | `docker compose exec backend python manage.py shell` |
| Run backend tests | `docker compose exec backend python manage.py test` |

## Compact Instructions

Preserve during /compact: [Critical Rules], [MCP Tool Preferences table],
[Navigation table], [language/communication rules], [hard boundaries (NEVER/ALWAYS)].
Drop examples and explanations first.

## Maintenance

**Update Triggers:**
- When root navigation or canonical document links change
- When core commands change
- When critical project rules change

**Last Updated:** 2026-06-25
