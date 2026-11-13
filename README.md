# Expense API — Dockerised Flask service with a full CI/CD pipeline

A small Flask REST API that ships itself. Every merge to `main` builds a
container image, smoke-tests it, pushes it to Amazon ECR, and deploys it to an
EC2 host with a health-checked, zero-downtime swap — no manual SSH.

This is **Project 1** of the DevOps portfolio: it exists to prove, in a live
repo, that you can handle Docker, CI/CD, Linux, AWS, networking and Python
automation at once.

| Requirement | Where it lives in this repo |
|---|---|
| Docker: images, Dockerfiles, volumes, container networking | `Dockerfile`, `docker-compose.yml`, `deploy/nginx/local.conf` |
| Linux: services, processes, permissions, logs | `deploy/scripts/*.sh`, `Dockerfile` (non-root user), JSON logs |
| CI/CD with Git | `.github/workflows/ci-cd.yml` |
| AWS | `ECR` (registry), `EC2` (host), `IAM`, `Security Groups` |
| Networking: load balancing, DNS, ports | nginx reverse proxy + upstream swap |
| Python automation & error handling | `app/`, `deploy/scripts/remote-deploy.sh` |
| Monitoring / logging | `/health`, `/version`, JSON logs, deploy log tail + disk check |

---

## Architecture

```
   ┌──────────────┐   pull_request    ┌────────────────────────────┐
   │  Developer   │──────────────────▶│  GitHub Actions            │
   └──────┬───────┘                   │  1. flake8 + pytest (matrix)│
          │ merge to main             │  2. docker build            │
          ▼                           │  3. smoke test container    │
   ┌──────────────┐                   │  4. push → ECR (sha tag)    │
   │   GitHub     │──────────────────▶│  5. ssh → deploy script     │
   └──────────────┘                   └─────────────┬──────────────┘
                                                    │
   ┌────────────────────────────────────────────────▼───────────────┐
   │  EC2 (Ubuntu)                                                  │
   │                                                                │
   │   :80  nginx ──▶ upstream expense_api ──▶ 127.0.0.1:8001       │
   │        │                                    (new container)    │
   │        └──── after health check, upstream flips 8000 ⇄ 8001    │
   │                                                                │
   │   docker volume: expense-data  ──▶ /data/expenses.db           │
   └────────────────────────────────────────────────────────────────┘
```

**Why two ports?** A container's published port is fixed at creation, so you
cannot "respawn onto the same port" without a moment of downtime. Instead the
new container starts on the free port, nginx is repointed only after `/health`
answers, and the old container is removed last. If the health check fails, the
new container is deleted and nginx never moves — that is the rollback.

---

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness + DB check — used by Docker, nginx and the deploy gate |
| GET | `/version` | `git_sha` and environment — proves *which* build is live |
| GET | `/api/expenses` | list (`?category=`, `?month=YYYY-MM`, `?limit=`) |
| POST | `/api/expenses` | create (`amount`, `category` required) |
| GET | `/api/expenses/<id>` | read one |
| PATCH | `/api/expenses/<id>` | partial update |
| DELETE | `/api/expenses/<id>` | delete → 204 |
| GET | `/api/expenses/summary` | totals grouped by category |

```bash
curl -s localhost:8080/health
curl -s -X POST localhost:8080/api/expenses \
  -H 'Content-Type: application/json' \
  -d '{"amount":249.5,"category":"Groceries","description":"Weekly vegetables"}'
curl -s localhost:8080/api/expenses/summary
```

---

## Run it locally

**Option A — compose (closest to production, recommended)**

```bash
make up                 # builds image, starts app + nginx
make health             # -> {"database":"ok","status":"ok","version":"local"}
open http://localhost:8080/health
make down
```

The app container has **no published port** — everything enters through nginx.
`app` is resolved by Docker's embedded DNS on the `expense-net` network. That is
the container-networking story for your interview.

**Option B — plain venv**

```bash
make install
cp .env.example .env
make test               # 31 tests
make lint
make run                # http://localhost:8000
```

**Option C — just the image**

```bash
make docker-build
docker run --rm -p 8000:8000 expense-api:local
docker image ls expense-api:local     # note the size - put it in the README
```

---

## The pipeline, stage by stage

| Stage | Trigger | What happens | Fails if |
|---|---|---|---|
| `lint-and-test` | every PR + push | flake8, then pytest on Python 3.11 **and** 3.12 with `--cov-fail-under=85` | style error, any test fails, coverage drops below 85% |
| `build-and-push` | push to `main` only | buildx build → **run the image and curl `/health`** → push `:<git-sha>` to ECR | image won't build or won't start |
| `deploy` | push to `main` | SSH to EC2, run `remote-deploy.sh <image> <sha>` | health gate fails (auto-rollback), then the job goes red |
| `Verify the new version is live` | after deploy | polls `APP_URL/version` until `git_sha` matches the merged commit | production is serving an old SHA |

Deployment is **immutable and traceable**: the image tag *is* the commit SHA, so
`GET /version` tells you exactly what is running.

---

## One-time AWS setup (about 20 minutes)

1. **ECR repository** — the workflow creates `expense-api` automatically if it
   is missing, but you can pre-create it: *ECR → Create repository →
   `expense-api`, enable scan-on-push*.
2. **EC2 instance** — Ubuntu 24.04 LTS, `t3.micro` (free tier), open inbound
   **22** (your IP only) and **80** (0.0.0.0/0).
3. **IAM role for the instance** — attach an inline policy allowing
   `ecr:GetAuthorizationToken`, `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer`
   so the host can pull without stored keys.
4. **IAM user for the pipeline** — `ecr:*` on your repository + nothing else.
   Put its keys in GitHub secrets.
5. **Bootstrap the server once:**
   ```bash
   scp -i key.pem -r deploy ubuntu@EC2_IP:~/
   ssh -i key.pem ubuntu@EC2_IP 'bash ~/deploy/scripts/bootstrap-server.sh'
   ```
6. **Add repository secrets** (*Settings → Secrets and variables → Actions*):

   | Secret | Value |
   |---|---|
   | `AWS_ACCESS_KEY_ID` | pipeline IAM user key |
   | `AWS_SECRET_ACCESS_KEY` | pipeline IAM user secret |
   | `EC2_HOST` | instance public IP / DNS |
   | `EC2_USER` | `ubuntu` |
   | `EC2_SSH_KEY` | the **private** key contents (`cat key.pem`) |
   | `APP_URL` | `http://EC2_IP` (optional, used by the verify step) |

7. Push to `main` and watch the three stages go green.

> **Cost note:** `t3.micro` + ECR storage is free-tier friendly. Stop the
> instance when you are not demoing, and remember the ECR repo keeps every
> image — add a lifecycle policy (*"expire untagged images after 14 days"*).

---

## Demo script for your interview (5 minutes, rehearsed)

1. `git push` a trivial change → open the Actions tab → walk through the three
   stages while they run.
2. Show the green run, then `curl http://EC2_IP/version` returning the new SHA.
3. **Prove the gate works** — break a test on purpose on a branch, open a PR,
   show the red ❌ and that nothing deployed.
4. **Prove the rollback** — on the server, `docker run` an image with a broken
   env var, run `remote-deploy.sh` by hand, show the log line
   `HEALTH CHECK FAILED - rolling back` and nginx still serving the old build.
5. `docker image ls` → quote the size reduction. `docker ps` → quote the deploy
   time drop. These are your resume numbers.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `permission denied while trying to connect to the Docker daemon` | user not in `docker` group | `sudo usermod -aG docker $USER` then re-login |
| `no basic auth credentials` on the server | ECR login expired / IAM role missing | check the instance profile, re-run `aws ecr get-login-password` |
| nginx 502 right after deploy | new container started before DB was ready | the health gate covers this — check `docker logs expense-api-8001` |
| Workflow green but site shows old SHA | nginx reloaded but upstream file not written | `cat /etc/nginx/conf.d/upstream-expense-api.conf`, `sudo nginx -t` |
| `unhealthy` container | `/health` returns 503 → database unreachable | check `DATABASE_URL` in `/opt/expense-api/app.env` |
| Disk full after a few deploys | old images piling up | script prunes >7d; add an ECR lifecycle policy too |

**Log analysis practice (feeds Project 3):**

```bash
sudo journalctl -u nginx -n 100 --no-pager          # service logs
docker logs --tail 100 expense-api-8001 | grep request
docker logs expense-api-8001 | grep -c '"status": 500'
```

---

## Interview questions this repo lets you answer with evidence

- **Why multi-stage builds?** Build tooling never reaches the runtime image —
  smaller, fewer CVEs, faster pulls. Show `docker image ls`.
- **How do you get zero downtime?** Two ports + nginx upstream flip + health
  gate. Point at `remote-deploy.sh`.
- **What happens if the deploy is broken?** It never receives traffic; the old
  container keeps serving and the job fails loudly.
- **Where do secrets live?** GitHub repo secrets → env vars at runtime.
  `/opt/expense-api/app.env` is `chmod 600`, and nothing is baked into the image.
- **Why is the container non-root?** Privilege escalation inside the container
  becomes far harder; required by most security baselines.
- **How do you trace a request?** `X-Request-ID` is generated or propagated and
  logged on every line, with a duration in ms.
- **What would you improve next?** TLS with Let's Encrypt, a staging
  environment, Postgres instead of SQLite, and alerts on 5xx rate.

---

## Stretch goals (only after the core is green)

- Swap SQLite for Postgres → add a `db` service to compose.
- Add `alembic` migrations instead of `AUTO_CREATE_TABLES`.
- Add a `/metrics` endpoint (prometheus-flask-exporter) — becomes Project 3's
  scrape target.
- Move the EC2 + ECR creation into Terraform — that is Project 2.

---

## Repo layout

```
.
├── app/                  # Flask application (factory pattern)
│   ├── __init__.py       #   app factory, request logging, error handlers
│   ├── config.py         #   env-driven config
│   ├── models.py         #   Expense model
│   └── routes.py         #   REST endpoints + validation
├── tests/                # 31 pytest tests (health, CRUD, validation)
├── deploy/
│   ├── nginx/            # local.conf (compose) + expense-api.conf (EC2)
│   └── scripts/          # bootstrap-server.sh, remote-deploy.sh
├── .github/workflows/ci-cd.yml
├── Dockerfile            # multi-stage, non-root, HEALTHCHECK
├── docker-compose.yml
├── Makefile
└── wsgi.py
```
