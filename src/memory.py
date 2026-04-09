"""记忆分层模块 — 实现长、中、短三层记忆管理。

架构（参考 Letta/MemGPT + Factory.ai Anchored Iterative Summarization）：

- 短期记忆（short-term）：conversation_history 中最近的完整消息（由 Agent 管理）
- 中期记忆（working summary）：当前会话的结构化增量摘要（4 个锚定字段）
- 长期记忆（archival）：跨会话持久化的关键事实（保存到文件）

核心思想：
- compaction 不再"从头生成一段文字摘要"，而是将旧消息增量合并到结构化的 working_summary
- working_summary 包含 4 个锚定字段：intent / changes / decisions / next_steps
- 每次 compaction 只处理新增的旧消息段，合并到已有摘要中（Anchored Iterative）
- 重要事实可提取到 archival memory，跨会话可用
"""

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional


@dataclass
class WorkingSummary:
    """中期记忆：结构化的当前会话摘要。
    
    4 个锚定字段（参考 Factory.ai Anchored Iterative Summarization）：
    - intent: 用户的主要目标/请求
    - changes: 已完成的具体操作和修改
    - decisions: 关键决策及其原因
    - next_steps: 待完成的后续步骤
    """
    intent: str = ""
    changes: str = ""
    decisions: str = ""
    next_steps: str = ""
    # 已合并到摘要中的消息数量（用于增量更新）
    merged_message_count: int = 0

    def is_empty(self) -> bool:
        return not any([self.intent, self.changes, self.decisions, self.next_steps])

    def to_context_message(self) -> Optional[Dict[str, Any]]:
        """将 working summary 转为可注入 conversation_history 的消息。
        
        Returns:
            role=user 的消息字典，或 None（如果摘要为空）
        """
        if self.is_empty():
            return None
        
        parts = ["[会话摘要 — 之前对话的结构化总结]"]
        if self.intent:
            parts.append(f"## 目标\n{self.intent}")
        if self.changes:
            parts.append(f"## 已完成的操作\n{self.changes}")
        if self.decisions:
            parts.append(f"## 关键决策\n{self.decisions}")
        if self.next_steps:
            parts.append(f"## 后续步骤\n{self.next_steps}")
        
        return {
            "role": "user",
            "content": "\n\n".join(parts),
        }

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkingSummary':
        return cls(
            intent=data.get("intent", ""),
            changes=data.get("changes", ""),
            decisions=data.get("decisions", ""),
            next_steps=data.get("next_steps", ""),
            merged_message_count=data.get("merged_message_count", 0),
        )


@dataclass
class ArchivalEntry:
    """长期记忆条目：跨会话持久化的单条事实。"""
    content: str
    timestamp: str = ""
    source: str = ""  # 来自哪次对话

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class MemoryManager:
    """三层记忆管理器。
    
    - 短期记忆由 Agent.conversation_history 管理（不在本类中）
    - 中期记忆：self.working_summary（WorkingSummary）
    - 长期记忆：self.archival（List[ArchivalEntry]），可持久化到文件
    """
    
    DEFAULT_ARCHIVAL_DIR = ".memory"
    DEFAULT_ARCHIVAL_FILE = "archival.jsonl"
    MAX_ARCHIVAL_ENTRIES = 200
    # 注入 system prompt 时，archival memory 最多使用的字符数
    MAX_ARCHIVAL_CONTEXT_CHARS = 2000

    def __init__(self, archival_dir: Optional[str] = None):
        self.working_summary = WorkingSummary()
        self.archival: List[ArchivalEntry] = []
        self._archival_dir = archival_dir or self.DEFAULT_ARCHIVAL_DIR
        self._archival_path = os.path.join(self._archival_dir, self.DEFAULT_ARCHIVAL_FILE)

    def load_archival(self) -> int:
        """从文件加载长期记忆。
        
        Returns:
            加载的条目数量
        """
        if not os.path.isfile(self._archival_path):
            return 0
        
        loaded = []
        try:
            with open(self._archival_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            loaded.append(ArchivalEntry(
                                content=data.get("content", ""),
                                timestamp=data.get("timestamp", ""),
                                source=data.get("source", ""),
                            ))
                        except json.JSONDecodeError:
                            continue
        except Exception:
            return 0
        
        self.archival = loaded[-self.MAX_ARCHIVAL_ENTRIES:]
        return len(self.archival)

    def save_archival(self) -> bool:
        """将长期记忆持久化到文件。
        
        使用 write-to-temp-then-rename 原子写入模式，防止崩溃时丢失已有长期记忆。
        
        Returns:
            是否成功保存
        """
        import tempfile
        try:
            os.makedirs(self._archival_dir, exist_ok=True)
            # 原子写入：先写临时文件，再 rename 替换目标
            fd, tmp_path = tempfile.mkstemp(dir=self._archival_dir, suffix=".tmp")
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    for entry in self.archival[-self.MAX_ARCHIVAL_ENTRIES:]:
                        json.dump({
                            "content": entry.content,
                            "timestamp": entry.timestamp,
                            "source": entry.source,
                        }, f, ensure_ascii=False)
                        f.write("\n")
                os.replace(tmp_path, self._archival_path)
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            return True
        except Exception:
            return False

    def add_archival(self, content: str, source: str = "") -> ArchivalEntry:
        """添加一条长期记忆并自动持久化到磁盘。
        
        Args:
            content: 记忆内容
            source: 来源描述
            
        Returns:
            新创建的条目
        """
        entry = ArchivalEntry(content=content, source=source)
        self.archival.append(entry)
        # 超过上限时删除最旧的
        if len(self.archival) > self.MAX_ARCHIVAL_ENTRIES:
            self.archival = self.archival[-self.MAX_ARCHIVAL_ENTRIES:]
        # 自动持久化，确保长期记忆不丢失
        self.save_archival()
        return entry

    def get_archival_context(self) -> str:
        """获取长期记忆的上下文文本（用于注入 system prompt）。
        
        返回最近的 archival entries，截断到 MAX_ARCHIVAL_CONTEXT_CHARS。
        
        Returns:
            格式化的长期记忆文本，或空字符串
        """
        if not self.archival:
            return ""
        
        lines = []
        total_chars = 0
        # 从最新到最旧遍历
        for entry in reversed(self.archival):
            line = f"- {entry.content}"
            if total_chars + len(line) > self.MAX_ARCHIVAL_CONTEXT_CHARS:
                break
            lines.append(line)
            total_chars += len(line) + 1  # +1 for newline
        
        if not lines:
            return ""
        
        lines.reverse()  # 恢复时间顺序
        return "\n".join(lines)

    def build_compaction_prompt(self, old_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """构建增量摘要的 LLM prompt。
        
        如果已有 working_summary，让 LLM 在其基础上合并新消息段。
        如果是首次 compaction，从零开始生成结构化摘要。
        
        Args:
            old_messages: 要压缩的旧消息列表
            
        Returns:
            用于 LLM 调用的 messages 列表
        """
        if self.working_summary.is_empty():
            # 首次 compaction：从零开始
            system_content = (
                "你是一个对话摘要助手。请将以下对话内容总结为结构化摘要，使用以下 4 个字段（每个字段用中文简洁描述）：\n\n"
                "## 目标\n用户的主要目标和请求是什么？\n\n"
                "## 已完成的操作\n已经完成了哪些具体操作？（包括文件修改、命令执行等）\n\n"
                "## 关键决策\n做了哪些重要决策？为什么？\n\n"
                "## 后续步骤\n接下来还需要做什么？\n\n"
                "要求：\n"
                "- 每个字段不超过 200 字\n"
                "- 保留具体的文件名、命令、数值等关键细节\n"
                "- 只输出这 4 个字段的内容，不要输出其他内容\n"
                "- 严格使用上述 ## 标题格式"
            )
        else:
            # 增量合并：在已有摘要基础上更新
            existing = self.working_summary
            system_content = (
                "你是一个对话摘要助手。以下是当前的会话摘要和一段新的对话内容。\n"
                "请将新对话内容合并到已有摘要中，更新以下 4 个字段：\n\n"
                f"### 当前摘要\n\n"
                f"## 目标\n{existing.intent or '(无)'}\n\n"
                f"## 已完成的操作\n{existing.changes or '(无)'}\n\n"
                f"## 关键决策\n{existing.decisions or '(无)'}\n\n"
                f"## 后续步骤\n{existing.next_steps or '(无)'}\n\n"
                "### 要求\n"
                "- 将新对话中的信息合并到对应字段\n"
                "- 已完成的操作应追加新内容，不要丢弃旧内容\n"
                "- 如果后续步骤已完成，从「后续步骤」移到「已完成的操作」\n"
                "- 每个字段不超过 300 字\n"
                "- 保留具体的文件名、命令、数值等关键细节\n"
                "- 只输出更新后的 4 个字段，严格使用 ## 标题格式"
            )

        return [
            {"role": "system", "content": system_content},
        ] + old_messages + [
            {"role": "user", "content": "请根据以上对话内容生成/更新结构化摘要。"},
        ]

    @staticmethod
    def parse_structured_summary(text: str) -> WorkingSummary:
        """从 LLM 输出中解析结构化摘要。
        
        期望格式：
        ## 目标
        ...
        ## 已完成的操作
        ...
        ## 关键决策
        ...
        ## 后续步骤
        ...
        
        如果解析失败，将整个文本放入 intent 字段作为 fallback。
        
        Args:
            text: LLM 输出文本
            
        Returns:
            WorkingSummary 实例
        """
        import re
        
        summary = WorkingSummary()
        
        # 用正则按 ## 标题分段
        # 匹配 "## 目标" / "## 已完成的操作" / "## 关键决策" / "## 后续步骤"
        sections = re.split(r'^##\s+', text, flags=re.MULTILINE)
        
        parsed_any = False
        for section in sections:
            section = section.strip()
            if not section:
                continue
            
            # 提取标题和内容
            lines = section.split('\n', 1)
            title = lines[0].strip()
            content = lines[1].strip() if len(lines) > 1 else ""
            
            if '目标' in title:
                summary.intent = content
                parsed_any = True
            elif '已完成' in title or '操作' in title:
                summary.changes = content
                parsed_any = True
            elif '决策' in title:
                summary.decisions = content
                parsed_any = True
            elif '后续' in title or '步骤' in title:
                summary.next_steps = content
                parsed_any = True
        
        # Fallback：如果完全无法解析，把整段文本放入 intent
        if not parsed_any:
            summary.intent = text[:600]  # 截断防止过长
        
        return summary

    def update_working_summary(self, new_summary: WorkingSummary, merged_count: int) -> None:
        """更新 working summary。
        
        Args:
            new_summary: 新的结构化摘要
            merged_count: 本次合并的消息数量
        """
        new_summary.merged_message_count = (
            self.working_summary.merged_message_count + merged_count
        )
        self.working_summary = new_summary

    def compact_with_summary(
        self, 
        conversation_history: List[Dict[str, Any]], 
        summary: WorkingSummary,
        keep_recent: int = 10,
    ) -> Dict[str, Any]:
        """使用结构化摘要执行 compaction。
        
        Args:
            conversation_history: 当前对话历史（会被原地修改）
            summary: 结构化摘要
            keep_recent: 保留最近多少条消息
            
        Returns:
            {"compacted": bool, "removed": int, "kept": int, 
             "new_history": list}
        """
        total = len(conversation_history)
        
        if total <= keep_recent:
            return {"compacted": False, "removed": 0, "kept": total, 
                    "new_history": conversation_history}
        
        kept_messages = conversation_history[-keep_recent:]
        removed_count = total - keep_recent
        
        # 构造摘要消息
        summary_msg = summary.to_context_message()
        if summary_msg:
            new_history = [summary_msg] + kept_messages
        else:
            new_history = kept_messages
        
        return {
            "compacted": True,
            "removed": removed_count,
            "kept": keep_recent,
            "new_history": new_history,
        }

    def export_state(self) -> Dict[str, Any]:
        """导出记忆状态（用于会话保存）。"""
        return {
            "working_summary": self.working_summary.to_dict(),
            "archival_count": len(self.archival),
            "archival": [
                {"content": e.content, "timestamp": e.timestamp, "source": e.source}
                for e in self.archival
            ],
        }

    def import_state(self, data: Dict[str, Any]) -> None:
        """导入记忆状态（用于会话加载）。
        
        无论 data 中是否包含 working_summary/archival 字段，
        都会重置对应状态，防止旧数据泄漏到新会话。
        """
        ws_data = data.get("working_summary")
        if ws_data:
            self.working_summary = WorkingSummary.from_dict(ws_data)
        else:
            self.working_summary = WorkingSummary()
        # 恢复 archival memory（无数据时重置为空列表）
        archival_data = data.get("archival")
        if archival_data and isinstance(archival_data, list):
            self.archival = [
                ArchivalEntry(
                    content=e.get("content", ""),
                    timestamp=e.get("timestamp", ""),
                    source=e.get("source", ""),
                )
                for e in archival_data
                if isinstance(e, dict) and e.get("content")
            ]
        else:
            self.archival = []
