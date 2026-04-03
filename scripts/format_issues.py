#!/usr/bin/env python3
"""从本地 issues.md 文件中读取并格式化 issue 列表。"""

import re
import sys


def parse_issues_md(content: str):
    """
    解析 issues.md 文件内容。
    
    支持的格式（每个 issue 用 ### 开头）：
    
    ### Issue #1: 标题
    状态: 待处理
    优先级: 高
    标签: bug, enhancement
    
    issue 描述内容...
    
    ---
    """
    if not content or not content.strip():
        return []

    # 移除 HTML 注释（<!-- ... -->），避免模板注释被误解析
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)

    if not content.strip():
        return []

    issues = []
    # 按 ### 分割
    blocks = re.split(r'^### ', content, flags=re.MULTILINE)

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.split('\n')
        # 解析标题行，例如 "Issue #1: 标题" 或直接 "标题"
        title_line = lines[0].strip().rstrip('---').strip()
        
        match = re.match(r'Issue\s*#?(\d+)\s*[:：]\s*(.*)', title_line)
        if match:
            number = int(match.group(1))
            title = match.group(2).strip()
        else:
            number = None
            title = title_line

        # 解析元数据和正文
        priority = ""
        labels = []
        status = "待处理"  # 默认状态
        body_lines = []
        
        for line in lines[1:]:
            stripped = line.strip()
            if stripped == '---':
                continue
            
            # 解析状态
            status_match = re.match(r'状态\s*[:：]\s*(.*)', stripped)
            if status_match:
                status = status_match.group(1).strip()
                continue
            
            # 解析优先级
            prio_match = re.match(r'优先级\s*[:：]\s*(.*)', stripped)
            if prio_match:
                priority = prio_match.group(1).strip()
                continue
            
            # 解析标签
            label_match = re.match(r'标签\s*[:：]\s*(.*)', stripped)
            if label_match:
                labels = [l.strip() for l in label_match.group(1).split(',') if l.strip()]
                continue
            
            body_lines.append(line)

        body = '\n'.join(body_lines).strip()

        issues.append({
            "number": number,
            "title": title,
            "body": body,
            "priority": priority,
            "labels": labels,
            "status": status,
        })

    return issues


def format_issues(issues, show_completed=False):
    """将解析后的 issue 列表格式化为可读的 markdown 文本。
    
    参数:
        issues: 解析后的 issue 列表
        show_completed: 是否显示已完成的 issue，默认为 False
    """
    if not issues:
        return "今天没有待处理的 issue。"

    # 过滤已完成的 issue
    completed = [i for i in issues if i.get("status", "") == "已完成"]
    pending = [i for i in issues if i.get("status", "") != "已完成"]

    # 根据参数决定显示哪些 issue
    display_issues = issues if show_completed else pending

    if not display_issues:
        if completed:
            return f"所有 {len(completed)} 个 issue 均已完成，没有待处理的 issue。"
        return "今天没有待处理的 issue。"

    # 按优先级排序（高 > 中 > 低 > 无）
    priority_order = {"高": 0, "中": 1, "低": 2, "": 3}
    display_issues.sort(key=lambda i: priority_order.get(i.get("priority", ""), 3))

    lines = ["# 待处理 Issue 列表\n"]
    if show_completed:
        lines.append(f"共 {len(display_issues)} 个 issue（待处理: {len(pending)}，已完成: {len(completed)}）。\n")
    else:
        lines.append(f"共 {len(display_issues)} 个待处理 issue。\n")
        if completed:
            lines.append(f"_另有 {len(completed)} 个已完成的 issue 已被过滤。_\n")

    for issue in display_issues:
        num = issue.get("number")
        title = issue.get("title", "无标题")
        body = issue.get("body", "").strip()
        priority = issue.get("priority", "")
        labels = issue.get("labels", [])
        status = issue.get("status", "待处理")
        if num is not None:
            prefix = "✅ " if status == "已完成" else ""
            lines.append(f"### {prefix}Issue #{num}: {title}")
        else:
            prefix = "✅ " if status == "已完成" else ""
            lines.append(f"### {prefix}{title}")

        lines.append(f"状态: {status}")
        if priority:
            lines.append(f"优先级: {priority}")
        if labels:
            lines.append(f"标签: {', '.join(labels)}")
        lines.append("")

        # 截断过长的描述
        if len(body) > 500:
            body = body[:500] + "\n[... 已截断]"
        if body:
            lines.append(body)
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    # 默认读取 scripts/issues.md，也可通过命令行参数指定文件路径
    # 用法: python3 format_issues.py [文件路径] [--all]
    #   --all  显示所有 issue（包括已完成的）
    show_all = "--all" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    
    if args:
        filepath = args[0]
    else:
        filepath = "scripts/issues.md"

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        issues = parse_issues_md(content)
        print(format_issues(issues, show_completed=show_all))
    except FileNotFoundError:
        print("今天没有待处理的 issue。")
