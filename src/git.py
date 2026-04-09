"""Git 感知模块 - 检测 Git 仓库状态，提供分支名等信息。"""

import subprocess
from typing import Optional


def is_git_repo(cwd: Optional[str] = None) -> bool:
    """检测指定目录是否在 Git 仓库中。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def get_git_branch(cwd: Optional[str] = None) -> Optional[str]:
    """获取当前 Git 分支名。不在仓库中或无法检测时返回 None。"""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def get_git_status_summary(cwd: Optional[str] = None) -> Optional[str]:
    """获取简要的 Git 状态摘要（如 '3 modified, 1 untracked'）。不在仓库中时返回 None。"""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
        if not lines:
            return "clean"

        modified = sum(1 for l in lines if l[0:2].strip() in ("M", "MM"))
        untracked = sum(1 for l in lines if l.startswith("??"))
        added = sum(1 for l in lines if l[0] == "A" and l[1] != "?")
        deleted = sum(1 for l in lines if "D" in l[0:2])

        parts = []
        if added:
            parts.append(f"{added} added")
        if modified:
            parts.append(f"{modified} modified")
        if deleted:
            parts.append(f"{deleted} deleted")
        if untracked:
            parts.append(f"{untracked} untracked")

        # 如果以上分类都没匹配到，直接报总数
        if not parts:
            parts.append(f"{len(lines)} changed")

        return ", ".join(parts)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def git_add_and_commit(files: list, message: str, cwd: Optional[str] = None) -> dict:
    """将指定文件 git add 并 git commit。
    
    Args:
        files: 要提交的文件路径列表
        message: 提交信息
        cwd: 工作目录（可选）
    
    Returns:
        包含 success 和 message/error 的结果字典
    """
    if not files:
        return {"success": False, "error": "没有指定要提交的文件"}
    
    try:
        # Step 1: git add
        add_result = subprocess.run(
            ["git", "add"] + list(files),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if add_result.returncode != 0:
            error_msg = add_result.stderr.strip() or add_result.stdout.strip() or "git add 失败"
            return {"success": False, "error": f"git add 失败：{error_msg}"}
        
        # Step 2: git commit
        commit_result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if commit_result.returncode != 0:
            error_msg = commit_result.stderr.strip() or commit_result.stdout.strip() or "git commit 失败"
            return {"success": False, "error": f"git commit 失败：{error_msg}"}
        
        return {
            "success": True,
            "message": message,
            "output": commit_result.stdout.strip(),
            "files": list(files),
        }
    except FileNotFoundError:
        return {"success": False, "error": "git 命令未找到，请确认已安装 Git"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "git 操作超时"}
    except OSError as e:
        return {"success": False, "error": f"git 操作失败：{e}"}


def git_diff_files(files: list, cwd: Optional[str] = None) -> dict:
    """获取指定文件相对于 HEAD 的 git diff。

    同时包含已暂存（staged）和未暂存（unstaged）的差异，
    以及未被 Git 跟踪的新文件内容。

    Args:
        files: 要查看差异的文件路径列表
        cwd: 工作目录（可选）

    Returns:
        {"success": True, "diff": "...", "files": [...]} 或
        {"success": False, "error": "..."}
    """
    if not files:
        return {"success": False, "error": "没有指定要查看差异的文件"}

    try:
        diff_parts = []

        # 1. 已跟踪文件：git diff HEAD -- <files>
        #    包含 staged + unstaged 相对于最近提交的全部差异
        tracked_result = subprocess.run(
            ["git", "diff", "HEAD", "--"] + list(files),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if tracked_result.returncode == 0 and tracked_result.stdout.strip():
            diff_parts.append(tracked_result.stdout.strip())

        # 2. 未跟踪的新文件：git diff 不会显示它们，需要单独处理
        status_result = subprocess.run(
            ["git", "status", "--porcelain", "--"] + list(files),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if status_result.returncode == 0:
            for line in status_result.stdout.strip().splitlines():
                if line.startswith("?? "):
                    untracked_path = line[3:].strip()
                    diff_parts.append(f"新文件（未跟踪）：{untracked_path}")

        diff_text = "\n".join(diff_parts) if diff_parts else ""

        return {
            "success": True,
            "diff": diff_text,
            "files": list(files),
        }
    except FileNotFoundError:
        return {"success": False, "error": "git 命令未找到，请确认已安装 Git"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "git 操作超时"}
    except OSError as e:
        return {"success": False, "error": f"git 操作失败：{e}"}
