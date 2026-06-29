from typing import Any, Literal

from pydantic import BaseModel, Field


GraphNodeType = Literal[
    "claim",
    "evidence",
    "source",
    "verdict",
    "independence_cluster",
]

GraphEdgeType = Literal[
    "has_evidence",
    "from_source",
    "has_stance",
    "has_verdict",
    "belongs_to_cluster",
]


class EvidenceGraphNode(BaseModel):
    node_id: str
    node_type: GraphNodeType
    label: str
    data: dict[str, Any] = Field(default_factory=dict)


class EvidenceGraphEdge(BaseModel):
    edge_id: str
    edge_type: GraphEdgeType
    source_node_id: str
    target_node_id: str
    label: str
    data: dict[str, Any] = Field(default_factory=dict)


class EvidenceGraph(BaseModel):
    graph_id: str
    case_id: str
    nodes: list[EvidenceGraphNode] = Field(default_factory=list)
    edges: list[EvidenceGraphEdge] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
