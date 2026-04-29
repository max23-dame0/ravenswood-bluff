# Alpha 1.0 M5 AI 行为样本

## 摘要

- 评估局数：10
- 每局压力档位：3
- 记录总数：150
- Persona 差异分：0.400
- 多局稳定分：0.960
- 社交信任响应分：1.000
- 弱信号不提名率：1.000
- 强信号提名率：1.000
- 强信号赞成票率：1.000
- Fallback 探针动作数：3
- Fallback 探针触发数：3

## Persona 投票画像

| Persona | Yes Rate | Weak No Rate | Medium/Strong Yes Rate |
| --- | ---: | ---: | ---: |
| aggressive | 1.000 | 0.000 | 1.000 |
| chaos | 0.667 | 1.000 | 1.000 |
| cooperative | 0.667 | 1.000 | 1.000 |
| logic | 0.667 | 1.000 | 1.000 |
| silent | 0.600 | 1.000 | 0.900 |

## 行为分布

```json
{
  "nomination": {
    "weak": {
      "none": 50
    },
    "medium": {
      "nominate": 50
    },
    "strong": {
      "nominate": 50
    }
  },
  "vote": {
    "weak": {
      "no": 40,
      "yes": 10
    },
    "medium": {
      "yes": 48,
      "no": 2
    },
    "strong": {
      "yes": 50
    }
  }
}
```

## Fallback 统计

```json
{
  "action_count": 3,
  "fallback_count": 3,
  "fallback_rate": 1.0,
  "fallback_by_action_type": {
    "nomination_intent": 1,
    "speak": 1,
    "vote": 1
  },
  "fallback_reasons": [
    "llm_error:JSONDecodeError"
  ]
}
```

## 样本记录

| Game | Persona | Pressure | Nomination | Target | Vote |
| ---: | --- | --- | --- | --- | --- |
| 1 | logic | weak | none | None | False |
| 1 | logic | medium | nominate | p2 | True |
| 1 | logic | strong | nominate | p3 | True |
| 1 | aggressive | weak | none | None | True |
| 1 | aggressive | medium | nominate | p2 | True |
| 1 | aggressive | strong | nominate | p3 | True |
| 1 | cooperative | weak | none | None | False |
| 1 | cooperative | medium | nominate | p2 | True |

## 结论

- AI 在弱信号下保留意见、强信号下推动提名与投票，趋势门禁通过。
- Persona 间的投票画像可区分，且同一 persona 多局表现保持稳定。
- 公开发言回归覆盖私密信息与邪恶队友信息的防泄露边界。
