# DM-Exp-Tourism-GroupX-2026Fall

《数据挖掘》探索性实验：景区游览指南程序性知识挖掘。

项目采用 `src/tourism_mining/` 源码布局。实验三实现路线解析、层级构建和路线对比。

## 环境要求

- Python 3.9 或更高版本
- pip 和 setuptools

以下命令在仓库根目录的 PowerShell 中执行。`py -3` 会选择本机可用的 Python 3；项目最低支持 3.9。若已有虚拟环境，请先激活它；也可以直接使用虚拟环境里的 Python，避免 `python` 指向系统环境。

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -c "import sys; print(sys.executable); print(sys.version)"
```

输出路径应指向仓库的 `.venv`。如果 PowerShell 不允许激活脚本，跳过激活，改用 `.venv\Scripts\python.exe` 执行下面命令。

## 安装并运行实验三

```powershell
python -m pip install --no-build-isolation -e .
python -m tourism_mining.cli experiment3
```

本项目同时提供 `pyproject.toml` 和 `setup.py`，以支持新旧 pip 的 editable 安装。安装前可用 `python --version` 和 `python -m pip --version` 确认当前解释器及 pip。`--no-build-isolation` 使用当前环境已安装的 setuptools，避免构建时联网下载；若提示缺少 setuptools，请先安装它，或在可联网环境中运行 `python -m pip install --upgrade pip setuptools` 后重试。若错误提示 Python 版本低于 3.9，请使用 Python 3.9+ 重建虚拟环境。

默认读取 `data/processed/clean_documents.json`，输出至 `data/processed/experiment3/`。可通过 `--input` 和 `--output` 覆盖输入与输出路径，例如：

```powershell
python -m tourism_mining.cli experiment3 --input data\processed\clean_documents.json --output data\processed\experiment3
```

运行测试：

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

若不激活虚拟环境，将命令中的 `python` 替换为 `.venv\Scripts\python.exe`。也可使用 `py -3.9 -m venv .venv` 显式指定 Python 3.9。请确保从仓库根目录运行，这样默认输入和输出路径才能正确解析。
