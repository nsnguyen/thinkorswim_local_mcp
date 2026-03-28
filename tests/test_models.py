"""Tests for src/data/models.py — Pydantic v2 data models.

Verifies that all models can be created, validated, and serialized correctly.
These tests protect against accidental field changes or type mismatches.
"""

import pytest
from pydantic import ValidationError

from src.data.models import Quote
from tests.fixtures.factories import (
    build_option_contract,
    build_options_chain_data,
    build_quote,
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
