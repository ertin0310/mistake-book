"""程序唯一入口。评审只需要这一条命令：

    python run.py

先把项目根放进 sys.path（`config` 与 `src` 两个顶层包才导得到），
建目录、建表这些活全部交给 create_app()。
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.app import create_app  # noqa: E402  必须先补 sys.path 再导入

app = create_app()

if __name__ == "__main__":
    print("错题本已启动 → http://127.0.0.1:5000")
    print("（打开会先到登录页：现在还没有演示账号，自己注册一个就能进；"
          "seed 预置账号要到第 5 步才有）")
    app.run(host="127.0.0.1", port=5000, debug=False)
