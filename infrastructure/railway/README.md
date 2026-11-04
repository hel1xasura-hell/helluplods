Railway services (create each from this one GitHub repo; see docs/RAILWAY_DEPLOYMENT.md):

| Service        | Root / Dockerfile             | Start command                    |
|----------------|-------------------------------|----------------------------------|
| api            | backend/Dockerfile            | (default, runs migrations first) |
| worker-default | workers/Dockerfile.default    | (default)                        |
| worker-browser | workers/Dockerfile.browser    | (default)                        |
| worker-render  | workers/Dockerfile.render     | (default)                        |
| frontend       | frontend/Dockerfile           | (default)                        |
| Postgres, Redis| Railway plugins               | -                                |
