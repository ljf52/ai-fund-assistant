from pydantic import BaseModel, Field


class HoldingCreate(BaseModel):
    fund_code: str = Field(pattern=r"^\d{6}$")
    fund_name: str = "未命名基金"
    category: str = "混合型"
    risk_level: str = "中高风险"
    shares: float = Field(gt=0)
    cost_nav: float = Field(gt=0)
    target_weight: float = Field(default=0, ge=0, le=100)


class HoldingUpdate(BaseModel):
    shares: float | None = Field(default=None, gt=0)
    cost_nav: float | None = Field(default=None, gt=0)
    target_weight: float | None = Field(default=None, ge=0, le=100)

