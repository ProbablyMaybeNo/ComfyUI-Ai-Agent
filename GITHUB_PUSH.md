# Pushing ComfyUI Agent to a New GitHub Repo

Use these steps when the project lives inside a larger repo and you want to publish **only** the ComfyUI Agent folder as its own GitHub repository.

---

## Option A: New repo from this folder (recommended)

### 1. Create the new repo on GitHub

1. Go to [github.com/new](https://github.com/new).
2. Set **Repository name** (e.g. `comfyui-agent` or `ComfyUI-Agent`).
3. Choose Public or Private. Do **not** initialize with a README, .gitignore, or license (we already have them).
4. Click **Create repository**.

### 2. Initialize git in ComfyUI Agent and push

From the **ComfyUI Agent** directory (this project root):

```powershell
cd "D:\AI-Workstation\Antigravity\apps\ComfyUI Agent"

# Initialize a new git repo (only if this folder is not already a git repo)
git init

# Add all files (respects .gitignore)
git add .

# First commit
git commit -m "Initial commit: ComfyUI Builder CLI, chat, tests, and docs"

# Add your new GitHub repo as remote (replace YOUR_USERNAME and REPO_NAME)
git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git

# Push (use main or master to match GitHub default)
git branch -M main
git push -u origin main
```

Replace `YOUR_USERNAME` and `REPO_NAME` with your GitHub username and the new repository name.

### 3. If you use SSH

```powershell
git remote add origin git@github.com:YOUR_USERNAME/REPO_NAME.git
git push -u origin main
```

---

## Option B: Subtree or filter-branch (keep history in parent repo)

If the ComfyUI Agent folder is part of a larger repo and you want to **extract only this folder** into a new repo while preserving history:

```powershell
# From the parent repo root (e.g. Antigravity)
git subtree split -P apps/ComfyUI\ Agent -b comfyui-agent-branch

# Create new folder, init, pull the branch
mkdir comfyui-agent-standalone
cd comfyui-agent-standalone
git init
git pull ..\..\..\Antigravity comfyui-agent-branch

# Add GitHub remote and push (as in Option A step 2)
git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git
git branch -M main
git push -u origin main
```

Paths may need adjusting for your machine.

---

## Before you push

- **.env** — Already in `.gitignore`; do not commit secrets. Use `.env.example` as a template.
- **Large files** — `comfy_builder/schema/node_schema.json` can be large; it’s in `.gitignore`. If you want it in the repo, remove that line from `.gitignore` and run `schema refresh` after cloning.
- **ComfyUI References/** — If you want to avoid committing large reference images, add `ComfyUI References/` to `.gitignore`.

---

## After first push

1. On GitHub: **Settings → General** — set default branch to `main` if needed.
2. Add a **Description** and **Topics** (e.g. `comfyui`, `workflow`, `ai`, `sdxl`).
3. Optional: add a **LICENSE** file and a short **README.md** in the project root (see README.md in this folder if created).
