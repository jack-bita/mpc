---
paths:
  - "deploy/**"
  - ".github/**"
  - "**/Dockerfile"
  - "compose*.yml"
  - "Makefile"
---

# Deploys, CI and the server (ADR-0027, ADR-0028, ADR-0029)

<!-- Source: 03 §12, §13; 04 stage 3. Loads when Claude reads or edits deploy, CI or Docker files. -->

- Real shop data lives only on the production server in Dar es Salaam and in its backups in Tanzania. Never copy it into CI, the demo or the repo.
- Secrets live in the root-only `.env` on the server and in GitHub environment secrets — never in files, logs, images or workflow output.
- Containers never run as root. Pin image versions.
- Production deploys only from a release: approval → migrations rehearsed on a scratch copy on the server → deploy → smoke test. The deploy runs as a job of the release workflow, because a tag made with the default token starts no other workflow (03 §12).
- Every merge to `main` deploys the demo, which holds fake data only.
- Jobs are safe to run twice, take IDs, work one shop at a time, log their start and end, and ping a heartbeat.
- A backup only counts once a restore has been tested.
- `make check` runs exactly what CI runs.
