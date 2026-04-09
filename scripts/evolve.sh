#!/bin/bash
# scripts/evolve.sh — 一次进化循环。可通过定时任务每小时运行或手动执行。
#
# 用法：
#   ./scripts/evolve.sh
#
# 环境变量：
#   REPO               — Git 仓库地址（默认: git@github.com:linkxzhou/SimpleAgent.git）
#   MODEL              — LLM 模型（默认: claude-opus-4.6）
#   TIMEOUT            — 最大会话时间，单位秒（默认: 6000）

set -euo pipefail

python3 -m pip install -r requirements.txt

# 兼容 macOS：macOS 默认没有 timeout 命令，尝试使用 gtimeout（brew install coreutils）
if command -v timeout &>/dev/null; then
    TIMEOUT_CMD="timeout"
elif command -v gtimeout &>/dev/null; then
    TIMEOUT_CMD="gtimeout"
else
    TIMEOUT_CMD=""
    echo "⚠ 未找到 timeout/gtimeout 命令，将不限制会话时间。"
fi

REPO="${REPO:-git@github.com:linkxzhou/SimpleAgent.git}"
MODEL="${MODEL:-claude-opus-4.6}"
TIMEOUT="${TIMEOUT:-6000}"
HOUR=$(cat RUN_COUNT 2>/dev/null || echo 1)
DATE=$(date +"%Y-%m-%d %H:00")

echo "=== 第 $HOUR 次: $DATE ==="
echo "模型: $MODEL"
echo "超时: ${TIMEOUT}s"
echo ""

# ── 步骤 1: 验证初始状态 ──
echo "→ 检查构建..."
python3 -c "import src.main" 2>/dev/null && echo "  构建正常。" || echo "  警告: 导入检查失败，继续执行。"
echo ""

# ── 步骤 2: 从本地 issues.md 读取 issue ──
ISSUES_FILE="ISSUES_TODAY.md"
echo "→ 读取本地 issue 列表..."
if [ -f scripts/issues.md ]; then
    python3 scripts/format_issues.py scripts/issues.md > "$ISSUES_FILE" 2>/dev/null || echo "今天没有待处理的 issue。" > "$ISSUES_FILE"
    ISSUE_COUNT=$(grep -c '^### ' "$ISSUES_FILE" 2>/dev/null || echo 0)
    echo "  已加载 $ISSUE_COUNT 个 issue。"
else
    echo "  scripts/issues.md 文件不存在，跳过 issue 读取。"
    echo "今天没有待处理的 issue（issues.md 文件不存在）。" > "$ISSUES_FILE"
fi
echo ""

# ── 步骤 3: 运行进化会话 ──
echo "→ 开始进化会话..."
echo ""

# 构建运行命令（带或不带超时限制）
TIMEOUT_PREFIX=""
if [ -n "$TIMEOUT_CMD" ]; then
    TIMEOUT_PREFIX="$TIMEOUT_CMD $TIMEOUT"
fi

# 构建 prompt 并写入临时文件（避免 heredoc 内容被 shell 解析）
PROMPT_DATE_SHORT="${DATE%% *}"
PROMPT_FILE=$(mktemp)
cat > "$PROMPT_FILE" <<PROMPT_EOF
当前是第 ${HOUR} 次（${DATE}）。

按以下顺序阅读这些文件：
1. IDENTITY.md（你的身份和规则）
2. CLAUDE.md（仓库工作指南 — 包含完整架构、模块结构和约束）
3. ROADMAP.md（你的进化路线图）
4. JOURNAL.md（你最近的历史记录 — 最近 10 条）
5. ISSUES_TODAY.md（待处理的 issue）

=== 阶段 1: 自我评估 ===

仔细阅读你自己的源代码。然后尝试一个小任务来测试自己 —
例如，读取一个文件、编辑某些内容、运行一个命令。
记录任何摩擦、bug、崩溃或缺失的功能。

=== 阶段 2: 审查 Issue ===

阅读 ISSUES_TODAY.md。这些是需要你改进的真实需求。
优先级为"高"的 issue 应该优先处理。

=== 阶段 3: 决策 ===

**本次会话只选择一个最重要的问题来解决。** 不要贪多。
按以下优先级选择唯一的目标：
1. 自我发现的崩溃或数据丢失 bug
2. 优先级最高的 issue（如果今天可以处理）
3. 自我发现的用户体验摩擦或缺失的错误处理
4. 当前级别的路线图计划项

选定后，明确说出："本次目标：[具体描述]"。
如果在实现过程中发现了其他问题，记录到 ROADMAP.md 或 JOURNAL.md，但不要在本次会话中处理。

=== 阶段 4: 实现 ===

围绕你在阶段 3 选定的唯一目标，遵循进化技能规则：
- 只做与该目标直接相关的改动，不要顺手做无关优化
- 如果可能，先编写测试
- 使用 edit_file 进行精确修改
- 修改后运行 python3 -c "import src.main" 检查
- 如果检查失败，尝试修复。如果无法修复，使用以下命令回退: bash git checkout -- src/
- 完成后提交: git add -A && git commit -m "第 ${HOUR} 次: <简短描述>"
- **提交后停止实现，进入阶段 5 写日志。不要继续做下一个改进。**

=== 阶段 5: 日志 ===

在 JOURNAL.md 的顶部（# 日志 标题之后）写入今天的条目。格式：
## 第 ${HOUR} 次 — [标题]（${PROMPT_DATE_SHORT}）

[1-2 句问题背景]

**改了什么：**
- [文件名]：[变更描述]

**验证：** [运行了什么验证、结果如何]

**附带发现（不处理）：**（如果有则写，没有则省略此段）
- [发现内容]

**下一步（推荐）：**
1. [最推荐的下一步]
2. [次推荐]
3. [第三推荐]

=== 阶段 6: 更新路线图 ===

如果你完成了路线图项目，在 ROADMAP.md 中标记完成：
- [x] 项目描述（第 ${HOUR} 次）

如果你发现了新问题，将其添加到相应级别。

=== 阶段 7: Issue 响应 ===

如果你处理了某个 issue，写入 ISSUE_RESPONSE.md：
issue_number: [N]
status: fixed / partial / wontfix
comment: [你对该 issue 的 2-3 句回复]

现在开始。先阅读 IDENTITY.md。
PROMPT_EOF

$TIMEOUT_PREFIX python3 main.py \
    --model "$MODEL" \
    < "$PROMPT_FILE" || true

rm -f "$PROMPT_FILE"

echo ""
echo "→ 会话完成。检查结果..."

# ── 步骤 4: 验证构建并处理遗留问题 ──
if python3 -c "import src.main" 2>/dev/null; then
    echo "  构建: 通过"
else
    echo "  构建: 失败 — 回退源代码修改"
    git checkout -- src/
fi

# 递增运行计数器
echo "$((HOUR + 1))" > RUN_COUNT

# 提交所有未提交的更改（日志、路线图、运行计数器等）
git add -A
if ! git diff --cached --quiet; then
    git commit -m "第 $HOUR 次: 会话收尾"
    echo "  已提交会话收尾。"
else
    echo "  没有未提交的更改。"
fi

# ── 步骤 5: 处理 issue 响应 ──
if [ -f ISSUE_RESPONSE.md ]; then
    echo ""
    echo "→ 记录 issue 响应..."
    
    ISSUE_NUM=$(grep "^issue_number:" ISSUE_RESPONSE.md | awk '{print $2}' || echo "")
    STATUS=$(grep "^status:" ISSUE_RESPONSE.md | awk '{print $2}' || echo "")
    COMMENT=$(sed -n '/^comment:/,$ p' ISSUE_RESPONSE.md | sed '1s/^comment: //' || echo "")
    
    if [ -n "${ISSUE_NUM:-}" ]; then
        echo "  Issue #$ISSUE_NUM 状态: ${STATUS:-unknown}"
        echo "  回复: ${COMMENT:-无}"
    fi
    
    rm -f ISSUE_RESPONSE.md
fi

# ── 步骤 6: 推送 ──
echo ""
echo "→ 推送到远程仓库..."
git push || echo "  推送失败（可能没有远程仓库或认证问题）"

echo ""
echo "=== 第 $HOUR 次完成 ==="
