# Running this project on your laptop (Windows / macOS / Linux)

> **The short version:** install **Docker Desktop** (the engine), open this folder
> in VS Code, and run `docker compose up -d --build` in the terminal.
> The VS Code "Docker" extension is optional — it is only a UI on top of the same
> engine. You never *need* it, but it is handy.

---

## 1. What to install (and what is optional)

| Thing | Required? | What it is |
|---|---|---|
| **Docker Desktop** | ✅ required | The actual Docker engine + `docker` CLI + `docker compose`. Without it, nothing in this project's container half works. |
| **VS Code** | ✅ you already have it | Editor + integrated terminal. |
| **Docker extension for VS Code** (`ms-azuretools.vscode-docker`) | optional | Adds a Containers/Images/Volumes sidebar, right-click "Compose Up", Dockerfile syntax help. |
| **WSL extension** (`ms-vscode-remote.remote-wsl`) | optional (Windows) | Lets VS Code work *inside* WSL, which is faster for file-heavy projects. |
| **Git** | ✅ required | To push the repo so GitHub Actions can run. |
| **Python 3.11+** | ✅ required | To run tests/lint without Docker. |
| **AWS account** | later | Only for the deploy stage. Everything else works without it. |

### ⚠️ Important
The **CI/CD pipeline does not need Docker on your laptop.** GitHub Actions runs
the build on GitHub's own machines. You install Docker locally so you can
*understand* and *demo* the container part — which is what the interview will
probe. Do not skip it.

---

## 2. Install Docker Desktop

### Windows 10/11
1. Download from <https://www.docker.com/products/docker-desktop/> → **Docker Desktop for Windows**.
2. Run the installer. Keep **"Use WSL 2 instead of Hyper-V"** ticked.
3. If it complains that WSL is missing, open **PowerShell as Administrator**:
   ```powershell
   wsl --install
   ```
   Reboot, then start Docker Desktop again.
4. Launch Docker Desktop and wait until the bottom-left says **"Engine running"**.
5. Verify in a terminal (PowerShell or VS Code terminal):
   ```powershell
   docker --version
   docker compose version
   docker run --rm hello-world
   ```
   The last one printing `Hello from Docker!` means you are done.

**Free?** Yes — Docker Desktop is free for personal use, education and small
businesses. You are a student, so you are fine.

**Laptop requirements:** 8 GB RAM recommended, virtualisation enabled in BIOS
(Intel VT-x / AMD-V). If Docker refuses to start on a low-spec machine, see
§8 — you can still do 90% of this project without it.

### macOS
Docker Desktop `.dmg` → drag to Applications → open → wait for "Engine running".
Choose **Apple Silicon** or **Intel** correctly.

### Linux (Ubuntu/Debian) — no Desktop needed
```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER     # then log out and back in
docker run --rm hello-world
```

---

## 3. Get the project onto your machine

Download **`flask-cicd-pipeline.zip`** from this workspace and unzip it, or copy
the folder across. Then:

```bash
cd flask-cicd-pipeline
code .          # opens the folder in VS Code
```

In VS Code open a terminal: **Terminal → New Terminal** (`` Ctrl+` ``).

Optionally add the Docker extension: **Extensions** (`Ctrl+Shift+X`) → search
`Docker` → install the one by **Microsoft**.

---

## 4. Run it — the commands

### Option A: Docker Compose (the one you want)

```bash
docker compose up -d --build      # build the image, start app + nginx
docker compose ps                 # both should be "running (healthy)"
```

Then open <http://localhost:8080/health> in your browser. You should see:

```json
{"database":"ok","status":"ok","version":"local"}
```

Try the API:

```bash
# PowerShell 7+ / macOS / Linux / Git Bash
curl.exe http://localhost:8080/health

curl.exe -X POST http://localhost:8080/api/expenses -H "Content-Type: application/json" -d "{\"amount\":249.5,\"category\":\"Groceries\"}"

curl.exe http://localhost:8080/api/expenses/summary
```

> On old Windows PowerShell, `curl` is an alias for `Invoke-WebRequest` and will
> not behave. Use **`curl.exe`** (note the `.exe`) or use Git Bash. In VS Code,
> picking **Git Bash** as the terminal profile avoids the whole problem.

Watch the logs, then shut down:

```bash
docker compose logs -f --tail=50     # JSON request logs, Ctrl+C to stop
docker compose down                  # stop (keeps data volume)
docker compose down -v                # stop and delete the data volume
```

**What to notice (this is your interview material):**
- `docker compose ps` shows `(healthy)` — that is the `HEALTHCHECK` in the Dockerfile.
- The app container has **no published port**. You cannot reach it directly.
  All traffic goes through nginx on `:8080`. Open `deploy/nginx/local.conf` and
  see `server app:8000;` — `app` is a container name resolved by Docker's DNS.
- `docker image ls expense-api:local` → write down the size, that is your
  "image size reduced from X to Y" bullet.

### Option B: no Docker at all (tests + lint only)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q                            # 31 passed
flake8 app tests wsgi.py             # silent = clean
```

Then run the API bare (no container, no nginx):

```powershell
python wsgi.py
```

<http://localhost:8000/health> — same JSON, one less moving part.

### About `make`
The `make` commands in the README (`make up`, `make test`) are a convenience.
`make` is not installed on Windows by default. Either run the raw commands
above, or use **Git Bash** / **WSL** where `make` is available
(`sudo apt install make` in WSL). Nothing in the project *depends* on make.

---

## 5. Put it on GitHub (needed for the pipeline to run)

```bash
git init
git add .
git commit -m "feat: dockerised expense API with CI/CD pipeline"
git branch -M main
git remote add origin https://github.com/rithika58/<repo-name>.git
git push -u origin main
```

Create the empty repo on GitHub first (no README, no .gitignore — you already
have one).

**A useful demo you can do immediately, with zero AWS setup:** create a branch,
deliberately break a test, and open a pull request. The `lint-and-test` job goes
red and nothing deploys. That single screenshot proves the gate works.

```bash
git checkout -b break-a-test
# edit tests/test_health.py: change an assertion to something false
git commit -am "test: intentionally failing"
git push -u origin break-a-test
```

Then push to `main` with it fixed and watch the full three stages.

---

## 6. Add AWS only when the local half is solid

Follow **README → "One-time AWS setup"** (≈20 min):
ECR repo → `t3.micro` Ubuntu EC2 → IAM role on the instance → bootstrap script →
6 GitHub secrets → push to `main`.

Until then, `build-and-push` and `deploy` will fail on missing secrets — that is
expected, not a bug in the code.

---

## 7. Costs & cleanup (do not skip)

- **EC2 `t3.micro`** — free tier for 750 hrs/month in the first 12 months. **Stop**
  the instance when you are not demoing.
- **ECR** — storage is pennies but grows with every image. Add a lifecycle rule:
  *expire untagged images after 14 days*.
- **No load balancer, no NAT gateway, no EKS** in this project — those are the
  things that quietly cost money. Nothing here bills per hour except EC2.
- After the interview: `docker compose down -v`, stop EC2, delete the ECR images.

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `docker: command not found` | Docker Desktop is not installed **or** not launched. Start it, wait for "Engine running". |
| `error during connect ... pipe/docker_engine` (Windows) | Same thing — the engine is not running. Open Docker Desktop. |
| `WSL 2 installation is incomplete` | `wsl --install` in an admin PowerShell, reboot. |
| `port 8080 is already allocated` | Something else uses 8080. Change the compose mapping to `"8090:80"` and use :8090. |
| Container shows `unhealthy` | `docker compose logs app` — usually the DB path. Check `DATABASE_URL` in compose. |
| `docker compose up` builds but nginx returns 502 | App not ready yet; nginx waits on `service_healthy`, so check the app logs first. |
| Docker Desktop uses too much RAM | Settings → Resources → limit to 2–4 GB. This project needs very little. |
| Docker won't start on a 4 GB / old laptop | Skip Docker locally. Do Option B for tests, push to GitHub, and let Actions do the building — then demo from the Actions log. Say so honestly if asked. |
| `Activate.ps1 cannot be loaded` (PowerShell) | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` then re-run. |

---

## 9. Order of operations (checklist)

- [ ] Docker Desktop installed, `docker run --rm hello-world` works
- [ ] Project unzipped and opened in VS Code
- [ ] `docker compose up -d --build` → `http://localhost:8080/health` returns ok
- [ ] Noted the image size from `docker image ls`
- [ ] `docker compose ps` shows `(healthy)` — screenshot this
- [ ] Tests run locally: `pytest -q` → 31 passed
- [ ] Repo pushed to GitHub
- [ ] Failing-PR screenshot captured (proves the gate)
- [ ] AWS half done: ECR + EC2 + IAM + 6 secrets + bootstrap script
- [ ] One full green pipeline run → merge → live SHA matches
- [ ] Rollback demo recorded (bad env var → `HEALTH CHECK FAILED - rolling back`)
- [ ] Two real numbers measured → update the resume bullets
