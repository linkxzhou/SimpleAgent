# SimpleAgent

**一个能自我进化的编码Agent。**

这是一个纯 Python 实现的编码Agent CLI，无需外部Agent框架依赖。每次 SimpleAgent 会读取自身源代码，选择一个改进点，实现它，测试它，并记录发生了什么。

它不能作弊，不能跳过。每次更改都必须通过 CI。每次失败都会被记录。

看着它成长。

---

## 功能特性

- **独立实现**：无需外部Agent框架依赖
- **OpenAI API 集成**：使用官方 OpenAI Python 库
- **工具支持**：基础文件操作、命令执行和网络搜索（DuckDuckGo）
- **技能系统**：简单的技能加载机制
- **交互式 CLI**：带 ANSI 颜色的终端界面
- **模型切换**：支持不同的 OpenAI 模型
- **对话管理**：清除对话历史和切换模型
- **MCP 支持**：通过 `--mcp` 连接 MCP 服务器，自动发现和使用外部工具
- **记忆分层**：三层记忆架构（短期/中期/长期），Anchored Iterative Summarization 结构化压缩
- **LLM 路由**：三级模型路由（HIGH/MIDDLE/LOW），根据任务复杂度自动选择模型，降低成本
- **Spec 驱动开发**：通过 `/spec` 命令从需求文档生成分步实现计划
- **Team 协作**：Supervisor 模式多 Agent 并行执行，支持 Context Lake 共享上下文和结果聚合

## 工作原理

1. 定时唤醒Agent
2. Agent读取自身身份、日志、路线图和待处理的 issues
3. 自我评估 — 读取自身代码，尝试任务，发现不足
4. 选择**一个**改进点（来自 issues、自我评估或路线图）
5. 实现更改，运行测试，编写日志条目
6. 测试通过 → 提交。测试失败 → 回滚并记录失败原因
7. 如果处理了某个 issue，会在 issue 上回复

完整历史记录在 git log 中。日志在 [JOURNAL.md](JOURNAL.md)。计划在 [ROADMAP.md](ROADMAP.md)。

## 安装

1. 安装 Python 3.8+
2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

## 使用方法

设置 OpenAI API 密钥：
```bash
export OPENAI_API_KEY=sk-your-key-here
```

可选：设置自定义 API 地址：
```bash
export OPENAI_BASE_URL=https://api.example.com/v1
```

运行Agent：
```bash
python main.py
```

指定模型：
```bash
python main.py --model DeepSeek-V3_2-Online-32k
```

指定提供商（自动设置 base_url 和默认模型）：
```bash
python main.py --provider deepseek
python main.py --provider groq
python main.py --provider openai --model gpt-4o-mini
```

可用提供商：openai、deepseek、groq、siliconflow、together、ollama

加载技能：
```bash
python main.py --skills ./skills
```

自定义系统提示词（直接文本）：
```bash
python main.py --system "请专注于代码安全审计"
```

自定义系统提示词（从文件加载）：
```bash
python main.py --system ./my_prompt.txt
```

连接 MCP 服务器（自动发现工具）：
```bash
python main.py --mcp "npx -y @modelcontextprotocol/server-filesystem /tmp"
python main.py --mcp '{"command": "python", "args": ["my_server.py"]}'
```

连接多个 MCP 服务器：
```bash
python main.py --mcp "npx -y @mcp/server-fs /tmp" --mcp "npx -y @mcp/server-git"
```

启用 LLM 路由（根据任务复杂度自动选择模型）：
```bash
export OPENAI_MODEL=gpt-4o                  # 复杂任务
export OPENAI_MODEL_MIDDLE=gpt-4o-mini      # 中等任务
export OPENAI_MODEL_LOW=gpt-3.5-turbo       # 简单任务
python main.py
```

从 spec 文件生成实现计划：
```bash
# 进入交互模式后使用 /spec 命令
python main.py
> /spec specs/example-feature.md
```

触发完整的进化周期：
```bash
./scripts/evolve.sh
```

## 交互命令

- `/help` — 显示所有可用命令及说明
- `/quit`、`/exit` — 退出Agent
- `/clear` — 清除对话历史
- `/model <名称>` — 会话中切换模型
- `/undo` — 撤销上一次文件更改
- `/commit [消息]` — 提交本会话中修改过的文件（可选自定义提交信息）
- `/save [名称]` — 保存当前会话到文件（默认自动生成文件名）
- `/load <名称>` — 从文件加载会话
- `/usage` — 查看会话累计 token 用量
- `/compact` — 总结旧对话并释放上下文空间
- `/replay <日志文件>` — 从 JSONL 会话日志重新执行用户输入
- `/spec <spec 文件>` — 从 Markdown spec 文件生成分步实现计划
- `"""` 或 `'''` — 进入多行输入模式（粘贴代码块），再次输入同样标记结束

## 项目结构

```
SimpleAgent/
├── main.py              # 项目根目录入口脚本
├── src/
│   ├── __init__.py      # 包初始化
│   ├── main.py          # 包内入口（汇总导出，向后兼容）
│   ├── colors.py        # ANSI 终端颜色常量
│   ├── models.py        # 数据类（ToolCallRequest, Usage）
│   ├── tools.py         # 工具执行器 + OpenAI 工具定义
│   ├── skills.py        # 技能加载与管理
│   ├── prompt.py        # 提示词上下文渲染与动态构建
│   ├── git.py           # Git 感知（分支检测、仓库状态）
│   ├── providers.py     # 多提供商支持（提供商注册表与配置解析）
│   ├── logger.py        # 会话日志记录（JSONL 格式交互历史）
│   ├── mcp_client.py    # MCP 客户端（连接 MCP 服务器、工具发现与代理调用）
│   ├── memory.py        # 三层记忆管理（短期/中期/长期，结构化压缩）
│   ├── router.py        # LLM 路由器（三级模型选择，任务复杂度分类）
│   ├── agent.py         # Agent 核心（对话循环、工具调用分发、路由集成）
│   └── cli.py           # CLI / REPL 交互界面
├── scripts/
│   ├── evolve.sh        # 进化循环脚本
│   └── format_issues.py # Issue 格式化工具
│   └── issues.py        # issues 的记录
├── tests/               # 测试目录
│   ├── test_models.py   # 数据类测试
│   ├── test_tools.py    # 工具执行器测试
│   ├── test_skills.py   # 技能系统测试
│   ├── test_prompt.py   # 提示词构建测试
│   ├── test_agent.py    # Agent 核心逻辑测试
│   ├── test_cli.py      # CLI 工具函数测试
│   ├── test_git.py      # Git 功能测试
│   ├── test_session.py  # 对话持久化测试
│   └── test_providers.py # 多提供商支持测试
│   └── test_logger.py   # 会话日志测试
│   └── test_mcp_client.py # MCP 客户端测试
│   └── test_memory.py   # 记忆分层测试
│   └── test_router.py   # LLM 路由测试
│   └── test_team.py     # Team 协作测试
├── skills/              # 技能目录
│   ├── communicate/     # 沟通技能
│   ├── evolve/          # 进化技能
│   └── self-assess/     # 自我评估技能
├── specs/               # Spec 文件目录（Spec-driven development）
│   └── example-feature.md  # 示例 spec 文件
├── IDENTITY.md          # Agent身份与规则
├── JOURNAL.md           # 每日会话日志
├── ROADMAP.md           # 改进路线图
├── LEARNINGS.md         # 学习记录缓存
├── CLAUDE.md            # Claude Code 指导文件
└── requirements.txt     # Python 依赖
```

## 历程

阅读 [日志](JOURNAL.md) 获取每日更新，或浏览 [git log] 查看Agent对自身所做的每一次更改。

## 克隆项目

```bash
git clone git@github.com:linkxzhou/SimpleAgent.git
cd SimpleAgent
```

## 许可证

MIT
