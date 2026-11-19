import os
import sys
import base64
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, List

BASE_DIR = Path(__file__).resolve().parent

def load_env_token():
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("GITHUB_TOKEN=") and not line.startswith("#"):
                    return line.split("=", 1)[1].strip()
    return None

def api_request(url: str, token: str, method: str = "GET", data: Optional[dict] = None) -> tuple:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Antigravity-Sync"
    }
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode("utf-8")
            status = response.status
            return status, json.loads(res_body) if res_body else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            parsed = json.loads(err_body)
        except Exception:
            parsed = {"message": err_body}
        return e.code, parsed
    except Exception as e:
        return 0, {"message": str(e)}

def get_current_user(token: str) -> Optional[str]:
    status, res = api_request("https://api.github.com/user", token)
    if status == 200:
        return res.get("login")
    return None

def create_repo(username: str, repo_name: str, token: str, private: bool = False) -> bool:
    url = "https://api.github.com/user/repos"
    payload = {
        "name": repo_name,
        "description": "CLI tool to download torrents, translate subtitles to Hinglish (.ass), and burn into 480p/720p video.",
        "private": private,
        "auto_init": False
    }
    status, res = api_request(url, token, method="POST", data=payload)
    if status in (201, 422):
        return True
    print(f"❌ Failed to create repo: {status} - {res}")
    return False

def get_file_sha(username: str, repo_name: str, file_path_in_repo: str, token: str) -> Optional[str]:
    url = f"https://api.github.com/repos/{username}/{repo_name}/contents/{file_path_in_repo}"
    status, res = api_request(url, token, method="GET")
    if status == 200:
        return res.get("sha")
    return None

def upload_file_to_github(
    username: str,
    repo_name: str,
    local_path: Path,
    repo_path: str,
    token: str,
    commit_msg: str
) -> bool:
    with open(local_path, "rb") as f:
        content_bytes = f.read()

    b64_content = base64.b64encode(content_bytes).decode("utf-8")
    sha = get_file_sha(username, repo_name, repo_path, token)

    url = f"https://api.github.com/repos/{username}/{repo_name}/contents/{repo_path}"
    payload = {
        "message": commit_msg,
        "content": b64_content,
        "branch": "main"
    }
    if sha:
        payload["sha"] = sha

    status, res = api_request(url, token, method="PUT", data=payload)
    if status in (200, 201):
        action = "Updated" if sha else "Uploaded"
        print(f"✅ {action}: {repo_path}")
        return True
    else:
        print(f"❌ Error uploading {repo_path}: {status} - {res}")
        return False

def sync_all_files(token: str, username: Optional[str] = None, repo_name: str = "torrent-hinglish-burner", commit_msg: str = "Initial commit via Antigravity"):
    if not username:
        username = get_current_user(token)
        if not username:
            print("❌ Invalid GitHub Token or authentication failed!")
            sys.exit(1)

    print(f"🚀 Authenticated as GitHub user: @{username}")
    create_repo(username, repo_name, token)

    files_to_upload = [
        "README.md",
        "requirements.txt",
        ".env.example",
        "config.py",
        "downloader.py",
        "subtitles.py",
        "translator.py",
        "encoder.py",
        "cli.py",
        "ui.py",
        "install.sh",
        "setup.sh",
        "fonts/Helvetica_Rounded_LT_Std_Bold_Condensed.otf",
        "github_sync.py"
    ]

    for fname in files_to_upload:
        fpath = BASE_DIR / fname
        if fpath.exists():
            upload_file_to_github(
                username=username,
                repo_name=repo_name,
                local_path=fpath,
                repo_path=fname,
                token=token,
                commit_msg=commit_msg
            )

    print(f"\n🎉 All files successfully synced to GitHub!")
    print(f"👉 Repo URL: https://github.com/{username}/{repo_name}\n")

if __name__ == "__main__":
    token = load_env_token()
    if not token and len(sys.argv) > 1:
        token = sys.argv[1]

    if not token:
        print("Please provide GITHUB_TOKEN in .env or as CLI arg!")
        sys.exit(1)

    sync_all_files(token)
