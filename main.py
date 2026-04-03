#!/usr/bin/env python3
"""
SimpleAgent 主入口 - 包装 src/main.py
"""

from src.main import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())