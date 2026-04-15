# Fake Agent Demo

这个脚本用于在没有真实模型 key 的情况下，验证下面这条链路已经打通：

1. 手机端通过 websocket 反向连接服务端
2. 服务端把手机控制能力封成 langchain/deep-agent 风格 tools
3. 一个“假模型”脚本调用这些 tools
4. tools 通过 websocket 下发 envelope
5. 手机端 mock 正确执行并回 `actionResult`
6. `before_model remove_old_images` 的逻辑可以独立运行

## 运行

```bash
python fake_agent_demo.py
```

## 它验证了什么

- 不依赖真实 `OPENAI_API_KEY`
- 不依赖真实手机
- 能验证 `phone_gateway.py`
- 能验证 `phone_tools.py`
- 能验证 `custom_deep_agent.py` 里的 `remove_old_images`

## 它没有验证什么

- 真实 LLM 推理
- `create_deep_agent(...).ainvoke(...)` 的在线模型调用

这部分仍然需要真实模型 key（例如 OpenAI 或 OpenRouter）。
