"""CAS (Consolidated Account Statement) PDF parser.

Parses CAMS/KFintech CAS PDFs using the ``casparser`` library and
normalises the output into a structure suitable for portfolio import.
"""

import io
from dataclasses import dataclass, field
from typing import Any

import casparser

from ..logging_config import logger


@dataclass
class CASTransaction:
    """A single mutual fund transaction from the CAS PDF."""

    date: str
    description: str
    amount: float
    units: float | None
    nav: float | None
    balance: float | None
    type: str  # PURCHASE, REDEMPTION, STAMP_DUTY_TAX, etc.


@dataclass
class CASScheme:
    """A single mutual fund scheme extracted from the CAS PDF."""

    scheme_name: str
    isin: str
    amfi: str
    rta: str
    scheme_type: str  # EQUITY, DEBT, HYBRID, etc.
    folio: str
    amc: str
    units: float
    cost: float
    current_value: float
    nav: float
    nav_date: str
    transactions: list[CASTransaction] = field(default_factory=list)


@dataclass
class CASParseResult:
    """Complete result of parsing a CAS PDF."""

    investor_name: str
    investor_email: str
    statement_from: str
    statement_to: str
    file_type: str
    schemes: list[CASScheme] = field(default_factory=list)


def parse_cas_pdf(
    file_bytes: bytes, password: str
) -> CASParseResult:
    """Parse a CAS PDF and return normalised data.

    Args:
        file_bytes: Raw PDF file content.
        password: Password to decrypt the PDF.

    Returns:
        CASParseResult with all schemes and transactions.

    Raises:
        ValueError: If the PDF cannot be parsed or password is wrong.
    """
    try:
        data = casparser.read_cas_pdf(
            io.BytesIO(file_bytes),
            password=password,
            output="dict",
        )
    except Exception as exc:
        error_msg = str(exc).lower()
        if "password" in error_msg or "decrypt" in error_msg:
            raise ValueError("Incorrect password. Please try again.") from exc
        logger.exception("CAS PDF parsing failed: %s", exc)
        raise ValueError(
            "Failed to parse the PDF. Please ensure it is a valid"
            " CAMS/KFintech CAS statement."
        ) from exc

    raw = data.model_dump() if hasattr(data, "model_dump") else data

    period = raw.get("statement_period", {})
    investor = raw.get("investor_info", {})

    schemes: list[CASScheme] = []

    for folio_data in raw.get("folios", []):
        folio_num = folio_data.get("folio", "")
        amc = folio_data.get("amc", "")

        for scheme_data in folio_data.get("schemes", []):
            isin = (scheme_data.get("isin") or "").strip().upper()
            if not isin:
                logger.debug(
                    "Skipping scheme with no ISIN: %s",
                    scheme_data.get("scheme"),
                )
                continue

            # Parse transactions
            transactions: list[CASTransaction] = []
            for txn in scheme_data.get("transactions", []):
                txn_type = txn.get("type", "")
                # Skip stamp duty and other non-material entries
                if txn_type in ("STAMP_DUTY_TAX", "STT_TAX"):
                    continue

                transactions.append(
                    CASTransaction(
                        date=str(txn.get("date", "")),
                        description=txn.get("description", ""),
                        amount=_safe_float(txn.get("amount")),
                        units=_safe_float(txn.get("units")),
                        nav=_safe_float(txn.get("nav")),
                        balance=_safe_float(txn.get("balance")),
                        type=txn_type,
                    )
                )

            valuation = scheme_data.get("valuation", {})

            schemes.append(
                CASScheme(
                    scheme_name=scheme_data.get("scheme", ""),
                    isin=isin,
                    amfi=scheme_data.get("amfi", ""),
                    rta=scheme_data.get("rta", ""),
                    scheme_type=scheme_data.get("type", ""),
                    folio=folio_num,
                    amc=amc,
                    units=_safe_float(scheme_data.get("close")),
                    cost=_safe_float(valuation.get("cost")),
                    current_value=_safe_float(valuation.get("value")),
                    nav=_safe_float(valuation.get("nav")),
                    nav_date=str(valuation.get("date", "")),
                    transactions=transactions,
                )
            )

    logger.info(
        "CAS PDF parsed: %d schemes, %d total transactions",
        len(schemes),
        sum(len(s.transactions) for s in schemes),
    )

    return CASParseResult(
        investor_name=investor.get("name", ""),
        investor_email=investor.get("email", ""),
        statement_from=period.get("from_", ""),
        statement_to=period.get("to", ""),
        file_type=raw.get("file_type", ""),
        schemes=schemes,
    )


def serialise_parse_result(result: CASParseResult) -> dict[str, Any]:
    """Convert CASParseResult to a JSON-serialisable dict for the API."""
    return {
        "investor_name": result.investor_name,
        "investor_email": result.investor_email,
        "statement_from": result.statement_from,
        "statement_to": result.statement_to,
        "file_type": result.file_type,
        "schemes": [
            {
                "scheme_name": s.scheme_name,
                "isin": s.isin,
                "amfi": s.amfi,
                "rta": s.rta,
                "scheme_type": s.scheme_type,
                "folio": s.folio,
                "amc": s.amc,
                "units": s.units,
                "cost": s.cost,
                "current_value": s.current_value,
                "nav": s.nav,
                "nav_date": s.nav_date,
                "transaction_count": len(s.transactions),
                "transactions": [
                    {
                        "date": t.date,
                        "description": t.description,
                        "amount": t.amount,
                        "units": t.units,
                        "nav": t.nav,
                        "balance": t.balance,
                        "type": t.type,
                    }
                    for t in s.transactions
                ],
            }
            for s in result.schemes
        ],
    }


def _safe_float(value: Any) -> float:
    """Convert a value to float, returning 0.0 on failure."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0
