你可以通过命令行调用 MiroFish 群体智能模拟引擎：上传一份文档 + 一句模拟需求，系统会自动构建知识图谱、生成 AI 代理人群、跑完整场社交媒体推演，最后产出一份 Markdown 分析报告。全程无需浏览器。

准备工作（每个会话执行一次）：

    cd C:/Users/rowla/Projects/MiroFish
    export MIROFISH_ACCESS_CODE=mirofish-voyage-harbor-5282

1. 提交任务

    python cli/mirofish.py submit --file <文档路径> --prompt "<模拟需求>"

- 支持 .docx / .pdf / .md / .txt
- 返回：{"job_id": "tmp_1785855997597_1", "status": "queued"}
- 必须记下 job_id，后续全靠它
- 队列已满时返回 HTTP 429（最多 1 个运行 + 2 个排队），等待后重试

2. 查询进度

    python cli/mirofish.py status <job_id>

返回示例：
    {"job_id":"...","stage":"running","round":34,"total_rounds":72,"simulation_id":"sim_...","report_id":null,"error":null}

stage 依次为：queued -> ontology（本体生成）-> building（图谱构建）-> creating -> preparing（生成代理人设）-> running（推演中，带 round/total_rounds）-> reporting（写报告）-> done。
失败时 stage 为 failed，error 字段是具体原因。

3. 取回报告

    python cli/mirofish.py report <job_id> -o report.md

- 只有 stage 为 done 时可用；未完成会返回 HTTP 409 并给出当前阶段
- 成功后写入指定的 .md 文件（通常 14-18 KB）

轮询策略

一整个任务约需 60-90 分钟（推演阶段占绝大部分）。每 2-5 分钟查询一次，不要更频繁；见到 done 就取报告，见到 failed 就把 error 原样报告给用户，不要自行重试提交（每次提交都会消耗大量 LLM 额度）。

注意事项

- 同一份文档 + 同一段提示词重复提交会自动复用已有知识图谱，跳过前两个阶段，速度更快
- 关闭终端不影响任务，服务端会继续推进
- 结果同时会出现在网页端 https://leeroyy1288-mirofish.hf.space 的历史卡片里
