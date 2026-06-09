# FreeCADAI Web Console

This is the Phase 4 technical-plan web frontend implementation:

- Next.js
- TypeScript
- Ant Design
- TanStack Query
- Zustand
- ECharts

## Development

Start the FastAPI backend on port 8000 first, then run:

```powershell
cd web
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:3000/login
http://127.0.0.1:3000/admin
```

The Next.js dev server proxies these paths to the backend:

```text
/api/*
/health
```

Set `FREECADAI_API_BASE_URL` if the API is not at `http://127.0.0.1:8000`.

For deployment under a reverse-proxy prefix such as `/freecadai`, build with:

```text
NEXT_PUBLIC_ASSET_PREFIX=/freecadai
NEXT_PUBLIC_API_PREFIX=/freecadai
NEXT_PUBLIC_ROUTE_PREFIX=/freecadai
```
