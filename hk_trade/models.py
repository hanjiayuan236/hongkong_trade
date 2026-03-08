from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, List, Optional


@dataclass
class ETFQuote:
    code: str
    name: str
    price: Optional[float]
    change_pct: Optional[float]
    volume: Optional[float]
    status: str
    source: str


@dataclass
class NewsDigest:
    institution_views: List[str] = field(default_factory=list)
    fund_flow_summary: str = ""
    xueqiu_hot_discussions: List[str] = field(default_factory=list)
    source_notes: List[str] = field(default_factory=list)


@dataclass
class OptionContract:
    strike: float
    bid: float
    ask: float
    iv: Optional[float]
    volume: Optional[int]
    open_interest: Optional[int]

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return round((self.bid + self.ask) / 2, 4)
        return round(max(self.bid, self.ask), 4)


@dataclass
class OptionChain:
    symbol: str
    expiry_label: str
    expiry_date: date
    expiry_ts: int
    underlying_price: Optional[float]
    calls: List[OptionContract] = field(default_factory=list)
    puts: List[OptionContract] = field(default_factory=list)
    source: str = "Yahoo Finance"
    fetch_error: Optional[str] = None

    @property
    def has_data(self) -> bool:
        return bool(self.calls or self.puts)


@dataclass
class OptionSymbolData:
    symbol: str
    leverage: str
    spot_price: Optional[float]
    chains: Dict[str, OptionChain] = field(default_factory=dict)
    fetch_errors: List[str] = field(default_factory=list)


@dataclass
class StrategyRow:
    symbol: str
    leverage: str
    expiry_label: str
    expiry_date: date
    strategy: str
    sell_desc: str
    strike_desc: str
    call_price: Optional[float]
    put_price: Optional[float]
    premium: float
    underlying_price: Optional[float]

    @property
    def yield_pct(self) -> Optional[float]:
        if self.underlying_price and self.underlying_price > 0:
            return round((self.premium / self.underlying_price) * 100, 2)
        return None


@dataclass
class RiskAdvice:
    risk_level: str
    allocation: str
    suggestion: str
    key_risk: str


@dataclass
class ReportContext:
    run_id: str
    run_time: datetime
    mode: str
    issue_no: int
    quotes: List[ETFQuote]
    news: NewsDigest
    options_data: Dict[str, OptionSymbolData]
    strategy_rows: List[StrategyRow]
    risk_advice: List[RiskAdvice]
    data_sources: List[str]
    warnings: List[str] = field(default_factory=list)
