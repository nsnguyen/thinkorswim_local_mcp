"""Factory functions for creating test instances of Pydantic models."""

from datetime import UTC, date, datetime

from src.data.models import OptionContract, OptionsChainData, Quote


def build_quote(
    symbol: str = "SPX",
    last: float = 5900.00,
    bid: float = 5899.50,
    ask: float = 5900.50,
    open: float = 5885.00,
    high: float = 5910.00,
    low: float = 5875.00,
    close: float = 5880.00,
    volume: int = 1500000,
    net_change: float = 20.00,
    net_change_pct: float = 0.34,
    is_delayed: bool = False,
    timestamp: datetime | None = None,
) -> Quote:
    """Build a Quote model with sensible defaults for testing."""
    return Quote(
        symbol=symbol,
        last=last,
        bid=bid,
        ask=ask,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
        net_change=net_change,
        net_change_pct=net_change_pct,
        is_delayed=is_delayed,
        timestamp=timestamp or datetime(2026, 3, 27, 14, 30, 0, tzinfo=UTC),
    )


def build_option_contract(
    symbol: str = "SPXW  260403C05900000",
    underlying_symbol: str = "SPX",
    option_type: str = "CALL",
    strike_price: float = 5900.0,
    expiration_date: date | None = None,
    days_to_expiration: int = 7,
    bid: float = 38.50,
    ask: float = 39.20,
    last: float = 38.80,
    mark: float = 38.85,
    volume: int = 5200,
    open_interest: int = 12000,
    implied_volatility: float = 15.80,
    delta: float = 0.50,
    gamma: float = 0.0068,
    theta: float = -3.50,
    vega: float = 5.80,
    rho: float = 0.10,
    in_the_money: bool = False,
    multiplier: float = 100.0,
) -> OptionContract:
    """Build an OptionContract model with sensible defaults for testing."""
    return OptionContract(
        symbol=symbol,
        underlying_symbol=underlying_symbol,
        option_type=option_type,
        strike_price=strike_price,
        expiration_date=expiration_date or date(2026, 4, 3),
        days_to_expiration=days_to_expiration,
        bid=bid,
        ask=ask,
        last=last,
        mark=mark,
        volume=volume,
        open_interest=open_interest,
        implied_volatility=implied_volatility,
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        rho=rho,
        in_the_money=in_the_money,
        multiplier=multiplier,
    )


def build_options_chain_data(
    symbol: str = "SPX",
    underlying_price: float = 5900.00,
    call_contracts: list[OptionContract] | None = None,
    put_contracts: list[OptionContract] | None = None,
    expirations: list[date] | None = None,
    strikes: list[float] | None = None,
    is_delayed: bool = False,
    timestamp: datetime | None = None,
) -> OptionsChainData:
    """Build an OptionsChainData model with sensible defaults for testing."""
    calls = call_contracts if call_contracts is not None else [build_option_contract()]
    puts = (
        put_contracts
        if put_contracts is not None
        else [
            build_option_contract(
                symbol="SPXW  260403P05900000",
                option_type="PUT",
                delta=-0.50,
                rho=-0.12,
            )
        ]
    )
    return OptionsChainData(
        symbol=symbol,
        underlying_price=underlying_price,
        timestamp=timestamp or datetime(2026, 3, 27, 14, 30, 0, tzinfo=UTC),
        call_contracts=calls,
        put_contracts=puts,
        expirations=expirations or [date(2026, 4, 3)],
        strikes=strikes or [5900.0],
        is_delayed=is_delayed,
    )
