"""Bilancio Medio Standardizzato (BMS) builder.

Implements the sector-average approach described in Scarano/Brughera
(Rivista AIAF n. 65, 2008), in which each peer contributes equally to a
synthetic "Impresa Media Standard" by first normalizing each P&L item
over its own revenues and each balance sheet item over its own total assets.

Formulas (per single fiscal year, across n peers):

    income_statement_share_i   = (1/n) * sum_j (item_{i,j} / revenues_j)
    balance_sheet_share_i      = (1/n) * sum_j (item_{i,j} / total_assets_j)

    average_revenues           = (1/n) * sum_j revenues_j
    average_total_assets       = (1/n) * sum_j total_assets_j

    BMS income_statement_i     = income_statement_share_i * average_revenues
    BMS balance_sheet_i        = balance_sheet_share_i    * average_total_assets

The resulting BMS is the reclassified reporting of a fictitious company
that represents the sector. It is used by the downstream DCF engine and
by the Differential Analyzer to compare the target against the sector.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import ClassVar

import pandas as pd

# -----------------------------------------------------------------------------
# Items included in the BMS output, split by normalization base
# -----------------------------------------------------------------------------

# Voci normalizzate su Fatturato (conto economico e flussi operativi)
INCOME_STATEMENT_ITEMS: tuple[str, ...] = (
    "revenues",
    "operating_costs",
    "ebitda",
    "depreciation_amortization",
    "ebit",
    "interest_expense",
    "pre_tax_income",
    "taxes",
    "net_income",
    "nopat",
    "capex",
)

# Voci normalizzate su Totale Attivo (stato patrimoniale riclassificato)
BALANCE_SHEET_ITEMS: tuple[str, ...] = (
    "net_fixed_assets",
    "net_working_capital",
    "net_invested_capital",
    "gross_debt",
    "cash",
    "net_debt",
    "equity",
    "total_assets",
)


# -----------------------------------------------------------------------------
# Result container
# -----------------------------------------------------------------------------


@dataclass
class BMSResult:
    """Output of a BMS construction.

    Attributes
    ----------
    fiscal_year:
        Anno di bilancio sul quale è costruito il BMS.
    n_companies:
        Numero di imprese nel campione.
    sample_ids:
        Tuple di company_id usati.
    average_revenues:
        Fatturato medio del campione (media aritmetica, pesi uguali).
    average_total_assets:
        Totale attivo medio del campione.
    income_statement_shares:
        Serie indicizzata su ``INCOME_STATEMENT_ITEMS``. Rappresenta la media
        delle quote di ciascuna voce CE sul fatturato.
    balance_sheet_shares:
        Stessa logica per lo stato patrimoniale, normalizzato sul totale attivo.
    income_statement:
        Conto economico del BMS in valori assoluti (shares × average_revenues).
    balance_sheet:
        Stato patrimoniale del BMS in valori assoluti (shares × average_total_assets).
    line_by_line_sum_income / balance:
        Per confronto — somma semplice delle voci sul campione. Serve a
        evidenziare l'effetto dimensionale distortivo che il BMS corregge.
    peer_income_shares / peer_balance_shares:
        DataFrame (una riga per peer) con le normalizzazioni individuali,
        utile per l'ispezione e i grafici.
    income_statement_shares_median / p25 / p75:
        Robust statistics (median, 25th and 75th percentile) of the peer
        shares. Useful for banding and for flagging peers that deviate from
        the central tendency. Not in the original paper but a natural
        extension requested by P4.20.
    balance_sheet_shares_median / p25 / p75:
        Same for balance sheet items.
    below_min_sample:
        True se il campione ha meno di ``min_sample_size`` imprese: il BMS è
        comunque calcolato, ma il chiamante deve valutare la significatività.
    min_sample_size:
        Soglia minima considerata rappresentativa (default 20 secondo il
        paper Scarano/Brughera).
    excluded_as_outliers:
        Tuple di company_id rimossi dal campione per eccesso di dimensione
        (vedi ``BMSBuilder(outlier_sigma=...)``). Vuota se non si applica
        lo screening.
    """

    fiscal_year: int
    n_companies: int
    sample_ids: tuple[str, ...]
    average_revenues: float
    average_total_assets: float
    income_statement_shares: pd.Series
    balance_sheet_shares: pd.Series
    income_statement: pd.Series
    balance_sheet: pd.Series
    line_by_line_sum_income: pd.Series
    line_by_line_sum_balance: pd.Series
    peer_income_shares: pd.DataFrame
    peer_balance_shares: pd.DataFrame
    income_statement_shares_median: pd.Series
    income_statement_shares_p25: pd.Series
    income_statement_shares_p75: pd.Series
    balance_sheet_shares_median: pd.Series
    balance_sheet_shares_p25: pd.Series
    balance_sheet_shares_p75: pd.Series
    below_min_sample: bool
    min_sample_size: int
    excluded_as_outliers: tuple[str, ...] = ()

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def as_dataframe(self) -> pd.DataFrame:
        """Return a single DataFrame with CE and SP for the BMS synthetic company."""
        rows = []
        for item, value in self.income_statement.items():
            rows.append(
                {
                    "statement": "income_statement",
                    "item": item,
                    "bms_value": value,
                    "pct_of_revenues": self.income_statement_shares.get(item, float("nan")),
                }
            )
        for item, value in self.balance_sheet.items():
            rows.append(
                {
                    "statement": "balance_sheet",
                    "item": item,
                    "bms_value": value,
                    "pct_of_total_assets": self.balance_sheet_shares.get(item, float("nan")),
                }
            )
        return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Builder
# -----------------------------------------------------------------------------


class BMSBuilder:
    """Construct a Bilancio Medio Standardizzato from a peer sample.

    Parameters
    ----------
    peers : pd.DataFrame
        Output of ``peer_sample(...)`` or any filtered slice of ``companies.csv``.
        Must contain a single ``fiscal_year`` (pass ``fiscal_year=`` to subset).
    fiscal_year : int, optional
        Restrict to this year if the input spans multiple years.
    min_sample_size : int, default 20
        Soglia di significatività dal paper Scarano/Brughera. Se il campione
        è inferiore il BMS viene comunque calcolato ma ``below_min_sample`` è
        True nel risultato (warning, non errore).

    Raises
    ------
    ValueError
        Se il campione è vuoto o contiene più fiscal year e non è stato
        specificato ``fiscal_year``.
    """

    DEFAULT_MIN_SAMPLE: ClassVar[int] = 20

    def __init__(
        self,
        peers: pd.DataFrame,
        *,
        fiscal_year: int | None = None,
        min_sample_size: int = DEFAULT_MIN_SAMPLE,
        outlier_sigma: float | None = None,
    ) -> None:
        """Initialize the builder.

        Parameters
        ----------
        peers : pd.DataFrame
            Peer sample. If any row has ``is_target == 1``, it is excluded
            with a ``UserWarning`` (the target must not be part of its own
            sector average).
        fiscal_year : int, optional
            Filter the input to a single year if it spans multiple.
        min_sample_size : int, default 20
            Threshold below which the ``below_min_sample`` flag is set.
        outlier_sigma : float, optional
            If set, drop peers whose revenues are more than
            ``outlier_sigma`` standard deviations away from the sample mean.
            Typical value: 2.5. Implements the screening described but not
            prescribed in Scarano/Brughera ("imprese molto più grandi
            possono polarizzare il modello"). Disabled by default.
        """
        if peers.empty:
            raise ValueError("Cannot build BMS from an empty peer sample")

        df = peers.copy()

        # --- Auto-exclude target rows (paper requirement) -----------------
        excluded_targets: list[str] = []
        if "is_target" in df.columns and (df["is_target"] == 1).any():
            target_ids = df.loc[df["is_target"] == 1, "company_id"].tolist()
            warnings.warn(
                f"BMSBuilder: il campione include {len(target_ids)} riga/e "
                f"con is_target=1 ({target_ids}). Verranno escluse dal BMS. "
                f"Usare peer_sample(...) a monte per evitare questo warning.",
                stacklevel=2,
            )
            excluded_targets = target_ids
            df = df[df["is_target"] == 0]
            if df.empty:
                raise ValueError(
                    "After excluding target rows the peer sample is empty"
                )

        if fiscal_year is not None:
            df = df[df["fiscal_year"] == fiscal_year]
            if df.empty:
                raise ValueError(f"No peers found for fiscal_year={fiscal_year}")

        unique_years = sorted(df["fiscal_year"].unique().tolist())
        if len(unique_years) != 1:
            raise ValueError(
                f"BMS must be built on a single fiscal year, got {unique_years}. "
                "Filter upstream or pass fiscal_year=."
            )

        # --- Optional outlier screening on revenues (P4.19) ---------------
        excluded_outliers: list[str] = []
        if outlier_sigma is not None:
            if outlier_sigma <= 0:
                raise ValueError(
                    f"outlier_sigma must be positive, got {outlier_sigma}"
                )
            mean_rev = df["revenues"].mean()
            std_rev = df["revenues"].std(ddof=0)
            if std_rev > 0:
                z = (df["revenues"] - mean_rev).abs() / std_rev
                outlier_mask = z > outlier_sigma
                if outlier_mask.any():
                    excluded_outliers = df.loc[outlier_mask, "company_id"].tolist()
                    df = df[~outlier_mask]
                    if df.empty:
                        raise ValueError(
                            f"outlier_sigma={outlier_sigma} removed all peers"
                        )

        self.peers: pd.DataFrame = df.reset_index(drop=True)
        self.fiscal_year: int = int(unique_years[0])
        self.min_sample_size: int = min_sample_size
        self._excluded_outliers: tuple[str, ...] = tuple(excluded_outliers)
        self._excluded_targets: tuple[str, ...] = tuple(excluded_targets)

    # ------------------------------------------------------------------

    def build(self) -> BMSResult:
        peers = self.peers
        n = len(peers)

        # --- Individual normalizations ----------------------------------
        peer_income_shares = pd.DataFrame(
            {item: peers[item] / peers["revenues"] for item in INCOME_STATEMENT_ITEMS}
        )
        peer_income_shares.insert(0, "company_id", peers["company_id"].values)

        peer_balance_shares = pd.DataFrame(
            {item: peers[item] / peers["total_assets"] for item in BALANCE_SHEET_ITEMS}
        )
        peer_balance_shares.insert(0, "company_id", peers["company_id"].values)

        # --- Equal-weight means of the shares ---------------------------
        income_shares = peer_income_shares[list(INCOME_STATEMENT_ITEMS)].mean(axis=0)
        balance_shares = peer_balance_shares[list(BALANCE_SHEET_ITEMS)].mean(axis=0)

        # --- Robust central-tendency statistics (P4.20) -----------------
        income_median = peer_income_shares[list(INCOME_STATEMENT_ITEMS)].median(axis=0)
        income_p25 = peer_income_shares[list(INCOME_STATEMENT_ITEMS)].quantile(0.25, axis=0)
        income_p75 = peer_income_shares[list(INCOME_STATEMENT_ITEMS)].quantile(0.75, axis=0)
        balance_median = peer_balance_shares[list(BALANCE_SHEET_ITEMS)].median(axis=0)
        balance_p25 = peer_balance_shares[list(BALANCE_SHEET_ITEMS)].quantile(0.25, axis=0)
        balance_p75 = peer_balance_shares[list(BALANCE_SHEET_ITEMS)].quantile(0.75, axis=0)

        # --- Average scaling bases --------------------------------------
        average_revenues = float(peers["revenues"].mean())
        average_total_assets = float(peers["total_assets"].mean())

        # --- BMS absolute values ----------------------------------------
        income_statement = income_shares * average_revenues
        balance_sheet = balance_shares * average_total_assets

        # --- Line-by-line sum (for contrast) ----------------------------
        line_by_line_sum_income = peers[list(INCOME_STATEMENT_ITEMS)].sum(axis=0)
        line_by_line_sum_balance = peers[list(BALANCE_SHEET_ITEMS)].sum(axis=0)

        return BMSResult(
            fiscal_year=self.fiscal_year,
            n_companies=n,
            sample_ids=tuple(peers["company_id"].tolist()),
            average_revenues=average_revenues,
            average_total_assets=average_total_assets,
            income_statement_shares=income_shares,
            balance_sheet_shares=balance_shares,
            income_statement=income_statement,
            balance_sheet=balance_sheet,
            line_by_line_sum_income=line_by_line_sum_income,
            line_by_line_sum_balance=line_by_line_sum_balance,
            peer_income_shares=peer_income_shares,
            peer_balance_shares=peer_balance_shares,
            income_statement_shares_median=income_median,
            income_statement_shares_p25=income_p25,
            income_statement_shares_p75=income_p75,
            balance_sheet_shares_median=balance_median,
            balance_sheet_shares_p25=balance_p25,
            balance_sheet_shares_p75=balance_p75,
            below_min_sample=n < self.min_sample_size,
            min_sample_size=self.min_sample_size,
            excluded_as_outliers=self._excluded_outliers,
        )


# -----------------------------------------------------------------------------
# Time series helper
# -----------------------------------------------------------------------------


def build_bms_timeseries(
    companies: pd.DataFrame,
    gics_sub_industry: str,
    years: list[int] | None = None,
    *,
    min_sample_size: int = BMSBuilder.DEFAULT_MIN_SAMPLE,
) -> dict[int, BMSResult]:
    """Build a BMS for each fiscal year available in the sector sample.

    Useful for the historical analysis described in Scarano/Brughera
    ("individuazione dei punti di flesso negli andamenti tendenziali").
    Target company (``is_target == 1``) is always excluded.
    """
    sector = companies[
        (companies["gics_sub_industry"] == gics_sub_industry)
        & (companies["is_target"] == 0)
    ]
    if years is None:
        years = sorted(sector["fiscal_year"].unique().tolist())

    results: dict[int, BMSResult] = {}
    for year in years:
        slice_year = sector[sector["fiscal_year"] == year]
        if slice_year.empty:
            continue
        results[year] = BMSBuilder(
            slice_year, fiscal_year=year, min_sample_size=min_sample_size
        ).build()
    return results
