请阅读下面的视频转写内容，生成一份结构化课程讲义。
注意：你必须返回合法的 json 对象，且只返回 json。

## 目标

生成一份信息密度高、适合学习和复习的课程讲义。

## 强约束

1. 必须输出合法 JSON，对象顶层只允许包含 title、overview、prerequisites、sections、summary、references 六个字段。
2. title 必须是讲义标题，简洁概括视频主题。
3. overview 必须是 2 到 4 句中文，概括课程核心内容和目标。
4. prerequisites 是前置知识要求列表，0 到 3 条，每条不超过 40 字。如果没有明确前置知识，返回空数组。
5. sections 是讲义章节，3 到 8 个，每个章节必须包含 title、start、key_concepts、explanation、examples、quiz。
   - title: 章节标题，简短有力
   - start: 视频时间点（秒），使用转写中真实出现的时间
   - key_concepts: 核心概念列表，2 到 4 个，每个 10 到 30 字
   - explanation: 详细讲解，80 到 250 字，内容忠实原文
   - examples: 示例或案例列表，0 到 2 个，每个 20 到 80 字
   - quiz: 随堂思考题列表，1 到 2 个，每个 15 到 50 字
6. summary 是课程总结，2 到 4 句，概括核心收获。
7. references 是延伸阅读建议，0 到 3 条，每条 10 到 40 字。
8. 不要写"本视频介绍了"这种空话，直接写内容。
9. 不要引用不存在的数据，不要补充外部背景。

## 写作要求

- 保持中文自然、紧凑、具体
- 优先提炼观点、结论、核心概念
- chapters 应体现内容推进，而不是机械平均切分
- key_concepts 应是可独立理解的知识点
- quiz 应引导思考而非简单记忆

## 输出格式

```json
{
  "title": "",
  "overview": "",
  "prerequisites": [],
  "sections": [
    {
      "title": "",
      "start": 0,
      "key_concepts": [],
      "explanation": "",
      "examples": [],
      "quiz": []
    }
  ],
  "summary": "",
  "references": []
}
```

## 输入数据

视频标题：{title}

转写内容：
{transcript}

分段数据：
{segments_json}
