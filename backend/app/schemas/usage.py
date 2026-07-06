"""Usage analytics API schemas。"""

from pydantic import BaseModel


class UsageOverviewOut(BaseModel):
    call_count: int
    active_user_count: int
    agent_count: int
    skill_trigger_count: int
    plugin_trigger_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    error_count: int
    interrupted_count: int
    avg_duration_ms: float | None


class UsageTimeseriesPointOut(BaseModel):
    bucket: str
    call_count: int
    active_user_count: int
    total_tokens: int
    error_count: int
    input_tokens: int
    output_tokens: int


class UsageAgentRankOut(BaseModel):
    agent_id: int | None
    agent_name: str
    call_count: int
    active_user_count: int
    total_tokens: int
    error_count: int


class UsageSkillRankOut(BaseModel):
    resource_name: str
    trigger_count: int


class UsagePluginRankOut(BaseModel):
    plugin_name: str
    resource_name: str
    trigger_count: int


class UsageStatusBreakdownOut(BaseModel):
    status: str
    count: int


class UsageTokenSummaryOut(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    timeseries: list[UsageTimeseriesPointOut]


class UsageUserOut(BaseModel):
    display_name: str
    department: str | None
    username: str


class UsageSummaryOut(BaseModel):
    range: str
    start: str
    end: str
    granularity: str
    overview: UsageOverviewOut
    timeseries: list[UsageTimeseriesPointOut]
    agents: list[UsageAgentRankOut]
    skills: list[UsageSkillRankOut]
    plugins: list[UsagePluginRankOut]
    tokens: UsageTokenSummaryOut
    status_breakdown: list[UsageStatusBreakdownOut]
