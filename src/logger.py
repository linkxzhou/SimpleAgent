"""会话日志模块 - 自动记录完整交互历史到 JSONL 文件。"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# 默认日志目录
DEFAULT_LOG_DIR = "logs"


class SessionLogger:
    """将完整会话交互记录到 JSONL 文件。
    
    每个会话创建一个 `transcript-YYYYMMDD-HHMMSS.jsonl` 文件，
    每行一个 JSON 对象，包含时间戳和事件类型。
    
    JSONL 格式的优势：
    - 逐行追加写入，不需要维护 JSON 数组结构
    - 进程崩溃不会损坏已写入的行
    - 大文件可逐行读取，不需要一次性加载
    
    Usage:
        with SessionLogger(log_dir="logs", model="gpt-4") as logger:
            logger.log("user_input", {"content": "hello"})
            logger.log("agent_response", {"content": "hi"})
    """

    def __init__(self, log_dir: str = DEFAULT_LOG_DIR, model: str = ""):
        """初始化会话日志。
        
        自动创建日志目录和文件，并写入 session_start 事件。
        
        Args:
            log_dir: 日志文件保存目录
            model: 当前使用的模型名称
        """
        self._log_dir = log_dir
        self._model = model
        self._event_count = 0
        self._closed = False
        
        # 创建日志目录
        os.makedirs(log_dir, exist_ok=True)
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"transcript-{timestamp}.jsonl"
        self.filepath = os.path.join(log_dir, filename)
        
        # 打开文件
        self._file = open(self.filepath, "a", encoding="utf-8")
        
        # 写入 session_start 事件
        self._write_entry({
            "type": "session_start",
            "model": model,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def log(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """记录一条事件。
        
        Args:
            event_type: 事件类型（如 'user_input', 'agent_response', 'tool_call'）
            data: 事件数据字典（可选）
        """
        if self._closed:
            return
        
        entry = {"type": event_type, "timestamp": datetime.now(timezone.utc).isoformat()}
        if data:
            entry.update(data)
        
        self._write_entry(entry)
        self._event_count += 1

    def close(self) -> None:
        """关闭日志，写入 session_end 事件。
        
        幂等操作，多次调用安全。
        """
        if self._closed:
            return
        
        self._closed = True
        
        # 写入 session_end 事件
        self._write_entry({
            "type": "session_end",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_count": self._event_count,
        })
        
        self._file.close()

    def _write_entry(self, entry: Dict[str, Any]) -> None:
        """将一条 JSON 对象写入文件并 flush。"""
        try:
            line = json.dumps(entry, ensure_ascii=False, default=str)
            self._file.write(line + "\n")
            self._file.flush()
        except Exception:
            pass  # 日志写入失败不应影响主流程

    def __enter__(self) -> "SessionLogger":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def load_transcript(filepath: str) -> Dict[str, Any]:
    """从 JSONL 会话日志文件中加载用户输入列表。
    
    Args:
        filepath: JSONL 日志文件路径
    
    Returns:
        字典，包含：
        - success: bool
        - inputs: list[str] — 按顺序排列的用户输入内容
        - model: str — 会话使用的模型（来自 session_start 事件）
        - error: str — 错误信息（仅 success=False 时）
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return {"success": False, "inputs": [], "model": "", "error": f"文件不存在：{filepath}"}
    except Exception as e:
        return {"success": False, "inputs": [], "model": "", "error": str(e)}
    
    inputs = []
    model = ""
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue  # 跳过损坏的行
        
        if entry.get("type") == "session_start":
            model = entry.get("model", "")
        elif entry.get("type") == "user_input":
            content = entry.get("content", "")
            if content:
                inputs.append(content)
    
    return {"success": True, "inputs": inputs, "model": model}
