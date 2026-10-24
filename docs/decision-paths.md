# 从事件到业务提醒 / Risk decision paths

事件记录现在可以与航线、港口、供应商或项目关联。先保存业务对象的编号、重要程度与关键日期，再把来源所支持的事件关联到相应编号。没有明确对象编号时，只能说明国区或主题匹配，不能宣称某条供应链已经受损。

## 实际路径

1. 在“事件跟踪与业务影响”打开项目，新增或修改关注对象。`object_type` 可选 `route/port/supplier/project/country/other`；`entity_keys` 是你自己维护的业务对象编号。
2. 新增来源支持的事件，在 `entity_keys` 填对应编号。双方均填编号时，只有交集才匹配；一方未填时，仍沿用国区与主题匹配，并说明匹配依据。
3. 点击本地检查。关注顺序参考已保存严重程度、业务重要程度与关键日期；它是定性排序，不是事件发生概率。对象条件改变也会重新对比，重复检查同样状态不会重复提醒。
4. 查看前后判断、来源及下一步。旧提醒和事件版本保留；新的关注队列只显示启用对象对应的最近一次有效提醒，已结束事件移出队列。

A high-severity event receives urgent attention when an operator deadline is within seven days or importance is high; critical severity is urgent. Otherwise severity and the deadline determine watch/routine. Reasons are displayed. An elapsed deadline remains explicit, and an operator can deactivate or revise the exposure. This only evaluates saved local records; it neither refreshes sources nor executes routing changes.

## 别名与合并

同一件事可能有不同名称。智能体不会仅凭相似名称自动合并。

- `event_alias` registers an operator-confirmed subject/location/day identity pointing to a saved event. Later matching updates retain the canonical identity and source-linked revision history.
- `event_merge` explicitly joins two saved dossiers. Set its record ID to `source_id`, provide `target_id` and `reason`. Both events must overlap in country/topic scope. Source references join the target while the original dossier/history remains readable; duplicate matching alerts are avoided.
- Merge chains cannot cycle. A saved merge cannot be silently rewritten. Alias conflicts with another saved dossier require an explicit merge.

These are operator actions through the existing browser form, `project-save` or authenticated `POST /api/project`. Models may propose event assessments but cannot create aliases/merges or edit private exposures. A merge confirms dossier organization; it does not prove independent corroboration, source reliability or a new severity.

```json
{"kind":"event_alias","id":"vessel-name","expected_revision":0,"data":{"subject":"Alternative vessel name","location":"Illustrative location","occurred_at":"2024-02-18","target_event_id":"saved-event-id","reason":"Fictional example: operator confirmed the same incident"}}
```

## 公开案例与范围

Existing [public project replay](../examples/public-project-case.json) follows the IMO/UNOSAT Rubymar historical material with fictional business exposure. New tests extend that saved path with aliases, explicit dossier merge, entity mismatch, deadlines, changed exposure and repeated checks. They are deterministic behavior tests, not a live current-warning evaluation. Use registered or explicitly permitted sources for current research.

通用工作流与定性排序规则公开。专用提示词、私有研究知识、客户资料及内部研发材料不随项目发布；希望进一步交流可[联系作者](https://github.com/workstonedai-collab)。
