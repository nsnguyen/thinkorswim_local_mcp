"""Tests for src/data/models.py — Pydantic v2 data models.

Verifies that all models can be created, validated, and serialized correctly.
These tests protect against accidental field changes or type mismatches.
"""

from datetime import date

import pytest
from pydantic import ValidationError

from src.data.models import (
    CharmShift,
    ExpectedMoveResult,
    GexRegime,
    GexSummary,
    IVContext,
    KeyLevel,
    Quote,
    SkewData,
    TermStructure,
    TermStructurePoint,
    VannaShift,
    VIX3MData,
    VIXContext,
    VIXData,
    VIXTermStructure,
    VolatilityAnalysis,
)
from tests.fixtures.factories import (
    build_option_contract,
    build_options_chain_data,
    build_quote,
    build_strike_gex,
)

# ── Quote Model ────────────────────────────────────────────────────


class TestQuote:
    """Tests for the Quote model."""

    def test_create_quote_with_defaults(self) -> None:
        """Test that a Quote can be created via factory with all fields populated.

        Ensures the factory produces a valid model and all fields are accessible.
        """
        quote = build_quote()
        assert quote.symbol == "SPX"
        assert quote.last == 5900.00
        assert quote.bid == 5899.50
        assert quote.ask == 5900.50
        assert quote.volume == 1500000
        assert quote.is_delayed is False

    def test_quote_serialization_to_json(self) -> None:
        """Test that Quote serializes to JSON-compatible dict.

        Tools return .model_dump(mode='json'), so datetime must serialize properly.
        """
        quote = build_quote()
        data = quote.model_dump(mode="json")
        assert isinstance(data, dict)
        assert data["symbol"] == "SPX"
        assert isinstance(data["timestamp"], str)  # datetime → ISO string

    @pytest.mark.parametrize(
        "field,value",
        [
            ("symbol", "AAPL"),
            ("last", 150.25),
            ("volume", 0),
            ("net_change", -5.50),
            ("net_change_pct", -1.25),
            ("is_delayed", True),
        ],
    )
    def test_quote_accepts_various_values(self, field: str, value: object) -> None:
        """Test that Quote accepts different valid values for each field.

        Covers edge cases like zero volume, negative changes, delayed quotes.
        """
        quote = build_quote(**{field: value})
        assert getattr(quote, field) == value

    def test_quote_rejects_missing_required_field(self) -> None:
        """Test that Quote raises ValidationError when required fields are missing.

        Ensures Pydantic enforcement is active — no silent defaults for required fields.
        """
        with pytest.raises(ValidationError):
            Quote(symbol="SPX")  # missing all other required fields


# ── OptionContract Model ───────────────────────────────────────────


class TestOptionContract:
    """Tests for the OptionContract model."""

    def test_create_call_contract(self) -> None:
        """Test that a CALL OptionContract can be created with correct fields."""
        contract = build_option_contract(option_type="CALL", delta=0.50)
        assert contract.option_type == "CALL"
        assert contract.delta == 0.50
        assert contract.strike_price == 5900.0
        assert contract.multiplier == 100.0

    def test_create_put_contract(self) -> None:
        """Test that a PUT OptionContract can be created with negative delta."""
        contract = build_option_contract(
            symbol="SPXW  260403P05900000",
            option_type="PUT",
            delta=-0.50,
            rho=-0.12,
            in_the_money=False,
        )
        assert contract.option_type == "PUT"
        assert contract.delta == -0.50
        assert contract.rho == -0.12

    def test_contract_serialization_to_json(self) -> None:
        """Test that OptionContract serializes dates correctly for JSON output."""
        contract = build_option_contract()
        data = contract.model_dump(mode="json")
        assert isinstance(data["expiration_date"], str)
        assert data["strike_price"] == 5900.0

    @pytest.mark.parametrize(
        "strike,dte,itm",
        [
            (5800.0, 0, True),  # deep ITM, 0DTE
            (5900.0, 7, False),  # ATM, weekly
            (6100.0, 45, False),  # far OTM, monthly
            (5500.0, 365, True),  # deep ITM, LEAP
        ],
    )
    def test_contract_various_strikes_and_dte(self, strike: float, dte: int, itm: bool) -> None:
        """Test contract creation across different strikes, DTEs, and ITM states."""
        contract = build_option_contract(
            strike_price=strike, days_to_expiration=dte, in_the_money=itm
        )
        assert contract.strike_price == strike
        assert contract.days_to_expiration == dte
        assert contract.in_the_money == itm

    def test_contract_multiplier_defaults_to_100(self) -> None:
        """Test that multiplier defaults to 100.0 (standard option contract size).

        This default is critical for GEX calculations in Phase 2.
        """
        contract = build_option_contract()
        assert contract.multiplier == 100.0


# ── OptionsChainData Model ─────────────────────────────────────────


class TestOptionsChainData:
    """Tests for the OptionsChainData model."""

    def test_create_chain_with_defaults(self) -> None:
        """Test that OptionsChainData can be created via factory with call and put contracts."""
        chain = build_options_chain_data()
        assert chain.symbol == "SPX"
        assert chain.underlying_price == 5900.00
        assert len(chain.call_contracts) == 1
        assert len(chain.put_contracts) == 1
        assert chain.call_contracts[0].option_type == "CALL"
        assert chain.put_contracts[0].option_type == "PUT"

    def test_chain_serialization_to_json(self) -> None:
        """Test that full chain serializes to JSON including nested contracts."""
        chain = build_options_chain_data()
        data = chain.model_dump(mode="json")
        assert isinstance(data, dict)
        assert len(data["call_contracts"]) == 1
        assert len(data["put_contracts"]) == 1
        assert isinstance(data["expirations"][0], str)

    def test_chain_with_multiple_contracts(self) -> None:
        """Test chain creation with multiple call and put contracts.

        Verifies the model handles lists of contracts correctly.
        """
        calls = [
            build_option_contract(strike_price=5850.0, delta=0.62),
            build_option_contract(strike_price=5900.0, delta=0.50),
            build_option_contract(strike_price=5950.0, delta=0.32),
        ]
        puts = [
            build_option_contract(
                symbol="SPXW  260403P05850000",
                option_type="PUT",
                strike_price=5850.0,
                delta=-0.38,
            ),
        ]
        chain = build_options_chain_data(
            call_contracts=calls,
            put_contracts=puts,
            strikes=[5850.0, 5900.0, 5950.0],
        )
        assert len(chain.call_contracts) == 3
        assert len(chain.put_contracts) == 1
        assert len(chain.strikes) == 3

    def test_chain_with_empty_contracts(self) -> None:
        """Test chain creation with no contracts (e.g., market closed, no data).

        The model should accept empty lists — the caller handles empty data logic.
        """
        chain = build_options_chain_data(
            call_contracts=[], put_contracts=[], expirations=[], strikes=[]
        )
        assert len(chain.call_contracts) == 0
        assert len(chain.put_contracts) == 0


# ── StrikeGex Model ──────────────────────────────────────────────


class TestStrikeGex:
    """Tests for the StrikeGex model."""

    def test_create_strike_gex(self) -> None:
        """Test that StrikeGex can be created with all fields."""
        sg = build_strike_gex()
        assert sg.strike == 5900.0
        assert sg.net_gex == sg.call_gex + sg.put_gex

    def test_strike_gex_serialization(self) -> None:
        """Test that StrikeGex serializes to JSON-compatible dict."""
        sg = build_strike_gex()
        data = sg.model_dump(mode="json")
        assert isinstance(data, dict)
        assert data["strike"] == 5900.0

    def test_strike_gex_negative_put_gex(self) -> None:
        """Test that put_gex is negative (puts have -1 sign convention)."""
        sg = build_strike_gex(put_gex=-500000.0, net_gex=500000.0)
        assert sg.put_gex < 0


# ── KeyLevel Model ───────────────────────────────────────────────


class TestKeyLevel:
    """Tests for the KeyLevel model."""

    def test_create_key_level(self) -> None:
        """Test that a KeyLevel can be created with all fields."""
        kl = KeyLevel(price=5850.0, gex=1500000.0, call_oi=8500, put_oi=6200)
        assert kl.price == 5850.0
        assert kl.gex == 1500000.0

    def test_key_level_serialization(self) -> None:
        """Test KeyLevel JSON serialization."""
        kl = KeyLevel(price=5900.0, gex=0.0, call_oi=0, put_oi=0)
        data = kl.model_dump(mode="json")
        assert data["price"] == 5900.0


# ── GexRegime Model ──────────────────────────────────────────────


class TestGexRegime:
    """Tests for the GexRegime model."""

    def test_positive_regime(self) -> None:
        """Test positive regime when spot > zero_gamma."""
        regime = GexRegime(type="positive", zero_gamma=5800.0, spot_vs_zero_gamma=100.0)
        assert regime.type == "positive"
        assert regime.spot_vs_zero_gamma > 0

    def test_negative_regime(self) -> None:
        """Test negative regime when spot < zero_gamma."""
        regime = GexRegime(type="negative", zero_gamma=6000.0, spot_vs_zero_gamma=-100.0)
        assert regime.type == "negative"
        assert regime.spot_vs_zero_gamma < 0


# ── GexSummary Model ─────────────────────────────────────────────


class TestGexSummary:
    """Tests for the GexSummary model."""

    def test_gex_summary_serialization(self) -> None:
        """Test that GexSummary serializes to JSON with timestamp as string."""
        from datetime import UTC, datetime

        summary = GexSummary(
            symbol="SPX",
            spot_price=5900.0,
            timestamp=datetime(2026, 3, 27, 14, 30, 0, tzinfo=UTC),
            total_gex=1000000.0,
            gross_gex=2000000.0,
            total_dex=500000.0,
            total_vex=300000.0,
            aggregate_theta=-150000.0,
            call_gex=1500000.0,
            put_gex=-500000.0,
            gex_ratio=3.0,
            contracts_analyzed=500,
        )
        data = summary.model_dump(mode="json")
        assert isinstance(data["timestamp"], str)
        assert data["gex_ratio"] == 3.0


# ── CharmShift / VannaShift Models ───────────────────────────────


class TestCharmShift:
    """Tests for the CharmShift model."""

    def test_charm_shift_serialization(self) -> None:
        """Test that CharmShift serializes correctly."""
        shift = CharmShift(
            symbol="SPX",
            spot_price=5900.0,
            hours_forward=3.0,
            current_zero_gamma=5850.0,
            projected_zero_gamma=5870.0,
            shift_direction="higher",
            current_total_gex=1000000.0,
            projected_total_gex=900000.0,
        )
        data = shift.model_dump(mode="json")
        assert data["shift_direction"] == "higher"
        assert data["hours_forward"] == 3.0


class TestVannaShift:
    """Tests for the VannaShift model."""

    def test_vanna_shift_serialization(self) -> None:
        """Test that VannaShift serializes correctly."""
        shift = VannaShift(
            symbol="SPX",
            spot_price=5900.0,
            iv_change_pct=2.0,
            current_zero_gamma=5850.0,
            projected_zero_gamma=5830.0,
            current_total_gex=1000000.0,
            projected_total_gex=1100000.0,
        )
        data = shift.model_dump(mode="json")
        assert data["iv_change_pct"] == 2.0


# ── Volatility Models ────────────────────────────────────────────


class TestIVContext:
    """Tests for the IVContext model."""

    def test_create_with_nulls(self) -> None:
        """Test IVContext with None fields (Phase 3A default)."""
        ctx = IVContext(
            percentile=None, rank=None, rv_20d=None,
            iv_rv_premium=None, regime="normal",
        )
        assert ctx.percentile is None
        assert ctx.regime == "normal"

    def test_serialization_preserves_nulls(self) -> None:
        """Test that None fields serialize to null in JSON."""
        ctx = IVContext(
            percentile=None, rank=None, rv_20d=None,
            iv_rv_premium=None, regime="low",
        )
        data = ctx.model_dump(mode="json")
        assert data["percentile"] is None
        assert data["regime"] == "low"


class TestSkewData:
    """Tests for the SkewData model."""

    def test_create_skew(self) -> None:
        """Test SkewData creation with all fields."""
        skew = SkewData(
            put_25d=17.50, call_25d=14.50, skew_25d=3.0,
            skew_10d=3.5, skew_40d=2.0, butterfly=0.15,
            regime="normal_skew",
        )
        assert skew.skew_25d == 3.0
        assert skew.regime == "normal_skew"

    def test_serialization(self) -> None:
        """Test SkewData JSON serialization."""
        skew = SkewData(
            put_25d=17.50, call_25d=14.50, skew_25d=3.0,
            skew_10d=3.5, skew_40d=2.0, butterfly=0.15,
            regime="normal_skew",
        )
        data = skew.model_dump(mode="json")
        assert data["butterfly"] == 0.15


class TestTermStructure:
    """Tests for TermStructure and TermStructurePoint models."""

    def test_term_structure_serialization(self) -> None:
        """Test TermStructure with points serializes correctly."""
        ts = TermStructure(
            shape="contango",
            slope=0.05,
            by_expiration=[
                TermStructurePoint(
                    expiration=date(2026, 4, 3), dte=7, atm_iv=15.85,
                ),
                TermStructurePoint(
                    expiration=date(2026, 4, 26), dte=30, atm_iv=17.20,
                ),
            ],
        )
        data = ts.model_dump(mode="json")
        assert data["shape"] == "contango"
        assert len(data["by_expiration"]) == 2


class TestVolatilityAnalysis:
    """Tests for the VolatilityAnalysis model."""

    def test_serialization(self) -> None:
        """Test full VolatilityAnalysis serializes to JSON."""
        from datetime import UTC, datetime

        va = VolatilityAnalysis(
            symbol="SPX",
            spot_price=5900.0,
            timestamp=datetime(2026, 3, 27, 14, 30, 0, tzinfo=UTC),
            atm_iv=15.85,
            iv_context=IVContext(
                percentile=None, rank=None, rv_20d=None,
                iv_rv_premium=None, regime="normal",
            ),
            skew=SkewData(
                put_25d=17.50, call_25d=14.50, skew_25d=3.0,
                skew_10d=3.5, skew_40d=2.0, butterfly=0.15,
                regime="normal_skew",
            ),
            term_structure=TermStructure(
                shape="contango", slope=0.05, by_expiration=[],
            ),
        )
        data = va.model_dump(mode="json")
        assert data["atm_iv"] == 15.85
        assert isinstance(data["timestamp"], str)


class TestVIXContext:
    """Tests for VIX-related models."""

    def test_vix_context_serialization(self) -> None:
        """Test VIXContext serializes with all nested models."""
        from datetime import UTC, datetime

        ctx = VIXContext(
            timestamp=datetime(2026, 3, 27, 14, 30, 0, tzinfo=UTC),
            vix=VIXData(
                level=18.50, change=-0.80,
                percentile=None, regime="normal",
            ),
            vix3m=VIX3MData(level=19.20),
            term_structure=VIXTermStructure(
                ratio=0.964, shape="contango",
            ),
        )
        data = ctx.model_dump(mode="json")
        assert data["vix"]["level"] == 18.50
        assert data["vix"]["percentile"] is None
        assert data["term_structure"]["shape"] == "contango"


class TestExpectedMoveResult:
    """Tests for the ExpectedMoveResult model."""

    def test_serialization(self) -> None:
        """Test ExpectedMoveResult serializes correctly."""
        em = ExpectedMoveResult(
            symbol="SPX",
            spot_price=5900.0,
            expiration=date(2026, 4, 3),
            dte=7,
            atm_strike=5900.0,
            atm_iv=15.85,
            expected_move_straddle=49.10,
            expected_move_1sd=129.6,
            upper_bound=5949.10,
            lower_bound=5850.90,
            upper_bound_1sd=6029.6,
            lower_bound_1sd=5770.4,
        )
        data = em.model_dump(mode="json")
        assert data["expected_move_straddle"] == 49.10
        assert isinstance(data["expiration"], str)
