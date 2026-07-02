# docudex

Document indexing API with full-text search and AI agent tooling.

## Setup

```bash
# Install dependencies
uv sync

# Configure environment variables
export DOCUDAX_API_KEY=your-api-key
export DOCUDAX_STORAGE_PATH=/path/to/storage  # optional, defaults to ./uploads
```

## Run

```bash
uv run python run.py
```

The app starts on `http://127.0.0.1:5000`.

## Usage

### UI
Open `http://127.0.0.1:5000` in a browser. Drag and drop PDF files or use the queue panel to manage uploads.

### Agent API
All `/agent/*` endpoints require the `X-API-Key` header:

```bash
# Upload files
curl -X POST http://127.0.0.1:5000/api/upload -F "files=@document.pdf"

# Process queue
curl -X POST http://127.0.0.1:5000/agent/categorize -H "X-API-Key: your-api-key"

# Search
curl "http://127.0.0.1:5000/agent/search?q=query" -H "X-API-Key: your-api-key"
```

### Commit & Push

```bash
git add -A
git commit -m "feat: your description"
git push origin main
```
