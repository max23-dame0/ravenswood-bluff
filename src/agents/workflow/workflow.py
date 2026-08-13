"""声明式 Workflow DSL — PLN-041 Phase 4 T11。

把「隐式调用链」（如说书人裁决链路）显式化为可声明、可调度、可观测的节点图：

- **ToolCallNode**：调用一个可执行函数（handler），支持超时与重试；
- **ConditionNode**：条件分支（then / else）；
- **ParallelNode**：并行分支（各分支独立调度）；
- **Workflow**：节点集合 + 入口 + 顺序边（next_node_map）。

设计约束：
- 纯数据 + 纯函数（handler 注入），无框架依赖；
- handler 签名统一为 `async def handler(ctx: dict, **kwargs) -> dict`；
- 节点参数（params）由引擎在调度时展开传入；
- dataclass 继承下所有字段给默认值（关键字构造），必填字段在
  `__post_init__` 校验。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

Handler = Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]


class WorkflowError(Exception):
    """工作流定义/执行错误。"""


@dataclass
class Node:
    """节点基类。"""

    node_id: str = ""
    kind: str = "node"

    @property
    def children(self) -> list[Node]:
        return []


@dataclass
class ToolCallNode(Node):
    """工具调用节点：调用 handler，支持超时/重试。"""

    tool_name: str = ""
    handler: Handler | None = None
    params: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 10.0
    retry_count: int = 0
    retry_delay_seconds: float = 0.1
    kind: str = "tool_call"

    def __post_init__(self) -> None:
        if not self.node_id:
            raise WorkflowError("ToolCallNode requires node_id")
        if not self.tool_name:
            raise WorkflowError(f"node '{self.node_id}' requires tool_name")
        if self.handler is None:
            raise WorkflowError(f"node '{self.node_id}' requires handler")


@dataclass
class ConditionNode(Node):
    """条件分支节点：condition(ctx) 为真走 then_node，否则走 else_node。"""

    condition: Callable[[dict[str, Any]], bool] | None = None
    then_node: Node | None = None
    else_node: Node | None = None
    kind: str = "condition"

    def __post_init__(self) -> None:
        if not self.node_id:
            raise WorkflowError("ConditionNode requires node_id")
        if self.condition is None:
            raise WorkflowError(f"node '{self.node_id}' requires condition")
        if self.then_node is None:
            raise WorkflowError(f"node '{self.node_id}' requires then_node")

    @property
    def children(self) -> list[Node]:
        nodes = [self.then_node] if self.then_node is not None else []
        if self.else_node is not None:
            nodes.append(self.else_node)
        return nodes


@dataclass
class ParallelNode(Node):
    """并行分支节点：branches 各自独立执行（并发调度）。"""

    branches: list[Node] = field(default_factory=list)
    kind: str = "parallel"

    @property
    def children(self) -> list[Node]:
        return list(self.branches)


@dataclass
class Workflow:
    """工作流：节点集合 + 入口 + 顺序边。

    next_node_map 声明顺序边（node_id -> 下一个 node_id），
    未声明的节点执行后结束该分支。
    """

    workflow_id: str = ""
    nodes: list[Node] = field(default_factory=list)
    entry_node_id: str = ""
    next_node_map: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.workflow_id:
            raise WorkflowError("Workflow requires workflow_id")
        if self.entry_node_id and not self.nodes:
            raise WorkflowError(f"workflow '{self.workflow_id}' has no nodes")
        if self.entry_node_id and self.get_node(self.entry_node_id) is None:
            raise WorkflowError(
                f"workflow '{self.workflow_id}' entry node '{self.entry_node_id}' not found"
            )

    def get_node(self, node_id: str) -> Node | None:
        for node in self._walk():
            if node.node_id == node_id:
                return node
        return None

    def _walk(self) -> list[Node]:
        """遍历全部节点（含嵌套 children）。"""
        seen: dict[str, Node] = {}

        def visit(node: Node) -> None:
            if node.node_id in seen:
                return
            seen[node.node_id] = node
            for child in node.children:
                visit(child)

        for node in self.nodes:
            visit(node)
        return list(seen.values())
