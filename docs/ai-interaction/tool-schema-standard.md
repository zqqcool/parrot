# Agent Runtime Tool Schema Standard

## Purpose

Parrot 内置 Agent Tool 使用一套轻量、集中、可读的 Schema authoring model。设计参考 Skyler 的
`JsonSchema + ToolSpec` 表达方式，但保持 Parrot 现有 `ToolDefinition`、Provider 适配和执行授权边界。

目标：

- Tool 定义在一个代码块内即可完整阅读；
- 不手写易错的 JSON Schema 字典；
- 不为每种字段类型建立独立 Python class；
- 不把每个 Tool 参数拆成大量 Pydantic 字段模型；
- Provider 发送和执行前校验使用同一份 Schema。

远端 MCP Tool 的 `input_schema` 由发现协议提供，不属于本标准的内置 Tool Schema。

## Canonical Model

源代码：`backend/app/modules/agent_runtime/tool_schema.py`

```pseudo
JsonSchema
  type_name
  description
  enum / const
  properties / required / additional_properties
  items
  minimum / maximum
  min_length / max_length
  min_items / max_items

ToolDefinition
  name: string
  description: string
  parameters: JsonSchema
```

`JsonSchema` 是一个不可变 authoring value object，并通过 classmethod 提供紧凑构造接口：

- `S.string()` / `S.integer()` / `S.number()` / `S.boolean()`；
- `S.scalar_union()`；
- `S.array()`；
- `S.object()`，默认 `additionalProperties=false`；
- `S.open_object()`，只用于真正不透明的对象载荷。

Tool 模块统一使用短别名：

```python
from app.modules.agent_runtime.tool_schema import JsonSchema as S
```

## Definition Style

Schema 与 Tool 描述放在同一个 `ToolDefinition` 中，不再建立 `FooArguments`、`StringField` 或
`tool_parameters()` 等平行类型层：

```python
ToolDefinition(
    name="knowledge_search",
    description="在当前 Agent 已绑定且生效的知识空间中检索。",
    parameters=S.object(
        {
            "query": S.string(
                "检索查询，应具体到实体或问题焦点。",
                min_length=1,
                max_length=1_000,
            ),
            "limit": S.integer("返回条数上限。", minimum=1, maximum=12),
        },
        required=("query",),
    ),
)
```

复杂 Tool 可以先声明 2–3 个有业务含义的局部 Schema 片段再组合，例如 `skill_reference`、
`capability_scope`、`task`。不要把每个标量字段提取成模块级常量，也不要为了复用一行描述引入公共抽象。

## Construction Rules

- 根参数必须是 `S.object(...)`，且禁止未知属性；
- 结构化嵌套对象使用 `S.object(...)`，同样默认禁止未知属性；
- 不透明对象仅使用 `S.open_object(...)`；
- 必填字段只在所属对象的 `required` 中声明；
- 枚举使用 `enum`，固定字符串使用 `const`；
- `string|number` 等简单联合使用 `S.scalar_union()`；
- 动态运行时上限直接传给 `min_items` / `max_items`，Provider 与执行校验不得分叉；
- 每个公开顶层参数写简短中文 description；嵌套 item 在上下文已经清晰时无需重复描述。

## Wire And Validation

`JsonSchema.to_dict()` 输出新的 JSON Schema 字典，不暴露内部 canonical mapping：

```pseudo
provider_request:
  parameters = tool.argument_schema()

tool_preflight:
  if not tool.accepts_arguments(call.arguments):
    reject TOOL_ARGUMENTS_INVALID
```

`ToolDefinition` 构造时验证：

- 根节点是 `type=object`；
- 根节点 `additionalProperties=false`；
- 最终结果是有效的 Draft 2020-12 Schema。

执行前使用同一 Schema 校验参数。领域 Runtime 继续负责依赖当前状态、权限、action 分支或跨字段关系的语义
校验，例如来源文本跨度、并发版本、审批状态和 Agent 绑定；这些约束不能仅依赖模型按 description 遵守。

## Provider-Compatible Subset

当前内置 Tool 只使用：

- `type`，包括简单标量 type 数组；
- `description`、`enum`、`const`；
- `properties`、`required`、`additionalProperties`；
- `items`、`minItems`、`maxItems`；
- `minimum`、`maximum`、`minLength`、`maxLength`。

禁止 `$ref`、`oneOf`、`anyOf`、`allOf`、`not` 和 `patternProperties`。这些关键字在标准 JSON Schema 中
有效，但 OpenAI-compatible 端点的实际支持程度不一致。需要新增组合结构时，必须先扩展 Provider 能力合同与
兼容性测试，不能静默退化为开放对象。

## Description UX

- Tool 描述写清做什么、何时调用、何时不要调用；
- 参数描述优先简洁说明语义、关键格式和必要示例；
- 不在多个 Field class、Pydantic model 和 ToolDefinition 之间重复同一段说明；
- Tool `name` 保持稳定英文 `verb_noun`，避免因作者体验重构破坏模型与运行时合同。

## Tests

`backend/tests/test_runtime_tool_schemas.py` 必须覆盖：

- 所有内置 Tool 使用 `JsonSchema`；
- Provider Schema 是有效 Draft 2020-12 且只使用保守子集；
- 根对象与嵌套结构化对象禁止未知属性；
- 顶层参数 description 完整；
- 未知字段、显式 `null`、越界值和错误枚举被执行前校验拒绝；
- `argument_schema()` 返回新字典，调用方不能篡改 canonical Schema。

## Non-Goals

- 不把 MCP 发现的原始 `input_schema` 转换为本地 authoring model；MCP 继续使用服务端策略、schema hash 与
  JSON Schema 校验边界。
- 不在本层默认启用 Provider `strict: true`；是否支持 strict 仍由已验证的模型能力合同决定。
- 不因 Schema 表达方式重构拆分或重命名稳定 Tool；Tool 粒度调整属于独立运行时合同变更。
