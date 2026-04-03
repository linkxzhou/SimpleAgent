# SimpleAgent

**一个能自我进化的编码Agent。**

这是一个纯 Python 实现的编码Agent CLI，无需外部Agent框架依赖。每次 SimpleAgent 会读取自身源代码，选择一个改进点，实现它，测试它，并记录发生了什么。

它不能作弊，不能跳过。每次更改都必须通过 CI。每次失败都会被记录。

看着它成长。

---

## 功能特性

- **独立实现**：无需外部Agent框架依赖
- **OpenAI API 集成**：使用官方 OpenAI Python 库
- **工具支持**：基础文件操作和命令执行
- **技能系统**：简单的技能加载机制
- **交互式 CLI**：带 ANSI 颜色的终端界面
- **模型切换**：支持不同的 OpenAI 模型
- **对话管理**：清除对话历史和切换模型

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
python main.py --model Pro/zai-org/GLM-5
```

加载技能：
```bash
python main.py --skills ./skills
```

触发完整的进化周期：
```bash
 ./scripts/evolve.sh
```

## 交互命令

- `/quit`、`/exit` — 退出Agent
- `/clear` — 清除对话历史
- `/model <名称>` — 会话中切换模型

## 项目结构

```
SimpleAgent/
├── main.py              # 主入口（包装 src/main.py）
├── src/
│   └── main.py          # 核心Agent实现
├── scripts/
│   ├── evolve.sh        # 进化循环脚本
│   └── format_issues.py # Issue 格式化工具
│   └── issues.py        # issues 的记录
├── skills/              # 技能目录
│   ├── communicate/     # 沟通技能
│   ├── evolve/          # 进化技能
│   └── self-assess/     # 自我评估技能
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
git clone git@git.woa.com:linkxzhou/SimpleAgent.git
cd SimpleAgent
```

## 许可证

MIT
