# 实验七：程序性知识应用——旅游规划 Agent

基于实验六构建的多源程序性知识图谱与大语言模型（LLM），实现支持意图解析、图谱工具调用、路线规划校验与异常回退的 ReAct 旅游规划 Agent。

## 核心模块

- `graph_tools.py`：封装知识图谱查询工具 `query_routes`（路线及步骤序列查询）、`query_pois`（景点候选查询）和 `query_advice`（条件建议查询），提供统一的输入输出 Schema 与异常处理。
- `agent.py`：实现自然语言约束解析（识别景区、游客类型、天数/小时数与否定表达）、ReAct 决策闭环、OpenAI-compatible Chat Completions 接口调用、基于 `visit_id` 与出入口完整性的行程校验及回退机制。
- `cli.py`：支持单次问答与多轮交互的命令行入口，输出推荐路线、条件建议、完整路线参考及 JSON 执行轨迹。
- `run_scenarios.py`、`test_agent.py`：17 类多约束与边界场景回归测试及 23 项单元测试。

## 运行方法

核心代码仅依赖 Python 3.9+ 标准库。在 `task7` 目录下执行：

```powershell
python -m unittest test_agent -v
python run_scenarios.py
python cli.py --mode demo --question "带孩子去故宫一天" --output results/single_demo.json
python cli.py --mode demo --interactive
```

### 在线 LLM 模式配置

通过环境变量配置兼容 OpenAI Chat Completions 协议的模型服务（参考 `.env.example`）：

```powershell
$env:TOURISM_LLM_BASE_URL = "https://api.example.com/v1"
$env:TOURISM_LLM_MODEL = "your-model-name"
$env:TOURISM_LLM_API_KEY = "your-api-key"
python cli.py --mode api --question "带孩子去故宫一天" --output results/llm_api_run.json
```
