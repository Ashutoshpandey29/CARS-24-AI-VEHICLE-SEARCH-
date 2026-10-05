# API

Try it in the browser at `/docs` (Swagger): open **GET /search**, click **Try it out**, enter a query and press **Execute**.

![Swagger UI](images/swagger.png)

## `GET /search`

| Param | Type | Notes |
|---|---|---|
| `q` | string, 2 to 300 chars, required | The query |
| `limit` | int, 1 to 100, default 20 | Page size |
| `cursor` | string, optional | `next_cursor` from the previous response. Use this for paging. |
| `offset` | int, 0 to 10,000, default 0 | Simple paging for shallow pages |

Response fields:

| Field | Meaning |
|---|---|
| `parser` | `llm`, `model` or `rules` |
| `filters` | The structured version of the query. Useful for checking why a car did or did not show up. |
| `relaxed` | Filters dropped because the strict search found nothing |
| `total`, `total_exact` | Number of matches. Counting stops at 10,000 (`COUNT_CAP`); past that `total_exact` is `false` and the UI shows "10,000+". |
| `next_cursor` | Pass as `cursor` to get the next page. `null` on the last page. |
| `took_ms` | Server-side time for the search |
| `results` | The cars |

## `GET /cars/{id}`

One car. `404` if the id does not exist.

## `GET /health`

`{"status": "ok", "parser": "model", "fallbacks": ["rules"]}`: the parser that handles queries first, then its fallbacks in order. Returns `503` if the database is unreachable.

Bad input (query too short or too long, limit over 100, malformed cursor) returns `422` or `400` with a message.

## Example

![curl output](images/terminal-curl.png)

When nothing matches exactly, soft filters are relaxed and listed in `relaxed`:

![Relaxed search](images/ui-relaxed.png)
