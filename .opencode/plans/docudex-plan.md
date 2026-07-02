# Docudex — Plan

## Architecture Overview

```
docudex/
├── app/
│   ├── __init__.py              # App factory
│   ├── config.py                # Configuration (storage path, API key, etc.)
│   ├── models/                  # SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── queue.py             # Queue model
│   │   ├── pdf.py               # PDF metadata model
│   │   ├── pdf_text.py          # Per-page text content
│   │   └── pdf_tag.py           # Tags model
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── api.py               # Agent search + categorization endpoints
│   │   └── ui.py                # UI + file management endpoints
│   ├── services/
│   │   ├── __init__.py
│   │   ├── pdf_processor.py     # PDF text extraction, hashing, indexing
│   │   └── file_storage.py      # File upload, storage, deletion
│   ├── templates/               # Jinja2 templates
│   │   └── index.html           # Single page (table + queue panel)
│   └── static/
│       └── style.css            # Styles
├── uploads/                     # File storage (configurable via config.py)
├── instance/                    # SQLite DB (gitignored)
├── run.py
├── pyproject.toml
└── README.md
```

## Database Schema

### `queue` — Files waiting to be indexed
| Column        | Type     | Notes                        |
|---------------|----------|------------------------------|
| id            | INTEGER  | PK, autoincrement            |
| filename      | TEXT     | Original filename            |
| file_path     | TEXT     | Path on disk                 |
| file_size     | INTEGER  | Byte size                    |
| added_at      | DATETIME | Auto on insert               |
| status        | TEXT     | `queued`, `processing`, `done`, `failed` |
| error_message | TEXT     | Nullable                     |

### `pdfs` — Indexed PDF metadata
| Column        | Type     | Notes                        |
|---------------|----------|------------------------------|
| id            | INTEGER  | PK, autoincrement            |
| filename      | TEXT     | Original filename            |
| file_path     | TEXT     | Path on disk                 |
| file_size     | INTEGER  | Byte size                    |
| sha256_hash   | TEXT     | Unique, for dedup            |
| total_pages   | INTEGER  | Page count                   |
| summary       | TEXT     | 3-sentence LLM summary       |
| uploaded_at   | DATETIME | Auto on insert               |
| indexed_at    | DATETIME | When indexing completed      |

### `pdf_text` — Per-page extracted text
| Column        | Type     | Notes                        |
|---------------|----------|------------------------------|
| id            | INTEGER  | PK, autoincrement            |
| pdf_id        | INTEGER  | FK → pdfs.id                 |
| page_number   | INTEGER  | 1-based                      |
| content       | TEXT     | Extracted text               |

### `pdf_tags` — Keywords/categories
| Column        | Type     | Notes                        |
|---------------|----------|------------------------------|
| id            | INTEGER  | PK, autoincrement            |
| pdf_id        | INTEGER  | FK → pdfs.id                 |
| tag           | TEXT     | Tag string                   |

### `pdfs_fts` — FTS5 virtual table
```sql
CREATE VIRTUAL TABLE pdfs_fts USING fts5(
    filename,
    page_content,
    content='pdfs',
    content_rowid='id'
);
```

## Endpoints

### UI / File Management (served by `ui.py`)
| Method | Path                    | Description                              |
|--------|-------------------------|------------------------------------------|
| GET    | /                       | Main UI page                             |
| POST   | /api/upload             | Upload file(s) → adds to queue           |
| GET    | /api/queue              | List queued files                        |
| DELETE | /api/queue/<id>         | Remove from queue + delete file          |
| GET    | /api/documents          | List indexed documents (20/page)         |
| DELETE | /api/documents/<id>     | Delete indexed file + all related records|

### AI Agent Search (served by `api.py`) — requires API key
| Method | Path                    | Description                              |
|--------|-------------------------|------------------------------------------|
| GET    | /agent/search           | FTS5 full-text search                    |
| GET    | /agent/documents        | List indexed documents (agent format)    |
| GET    | /agent/documents/<id>   | Get document metadata + pages            |
| POST   | /agent/categorize       | Process all queued files                 |

## Confirmed Decisions

1. **Database**: SQLite
2. **PDF library**: `pdfplumber`
3. **Frontend**: Flask Jinja2 + vanilla JS (no build step)
4. **File storage**: Configurable path via `config.py` (default: `uploads/`)
5. **Processing**: Synchronous (blocking)
6. **Tags**: LLM categorization via `POST /agent/categorize` (cron-triggered)
7. **Queue processing**: Cron job on host triggers `/agent/categorize`
8. **Auth**: UI = Nginx Auth, Agent API = API key header
9. **Pagination**: 20 documents per page
10. **Queue panel refresh**: Manual refresh button
11. **API key**: Env var `DOCUDAX_API_KEY`
12. **Duplicate handling**: Prompt user for resolution (skip vs update)
13. **Categorize endpoint**: Processes all queued files in one call
14. **Summary storage**: 3-sentence LLM summary in `pdfs` table
15. **Queue panel columns**: filename, file_path, file_size, added_at, status
16. **Document table columns**: filename, file_path, summary, total_pages, indexed_at, tags
