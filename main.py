#!/usr/bin/env python3
"""SimpleAgent — 顶层入口脚本。

从项目根目录运行：
  python main.py
  python main.py --model DeepSeek-V3_2-Online-32k
  python main.py --skills ./skills
"""

import asyncio
from src.cli import main

if __name__ == "__main__":
    asyncio.run(main())
