"""Streamlit page 7 — Data Manager.

Lets the user:

  1. Download the CSV templates (companies, sectors, macro, rating master scale)
     populated with the current dataset, ready to be edited.
  2. Upload a custom CSV and validate it against the schema and balance-sheet
     invariants without overwriting the on-disk dataset.

The uploaded data is shown as a preview only — saving to disk would require
write access to ``data/`` and is intentionally NOT enabled here. Persisting
the upload is a separate, more sensitive operation.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import io

import pandas as pd
import streamlit as st

from app._common import load_bundle, page_header
from rating_valuation.common.data_loader import (
    COMPANY_REQUIRED_COLUMNS,
    MACRO_REQUIRED_COLUMNS,
    RATING_REQUIRED_COLUMNS,
    SECTOR_REQUIRED_COLUMNS,
    SchemaError,
    load_companies,
    load_macro,
    load_rating_master_scale,
    load_sectors,
)
from rating_valuation.common.invariants import check_invariants

st.set_page_config(page_title="Data Manager", page_icon="📂", layout="wide")


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def _empty_template(columns: tuple[str, ...]) -> pd.DataFrame:
    """Return an empty DataFrame with the required columns set."""
    return pd.DataFrame(columns=list(columns))


# -----------------------------------------------------------------------------
# Page
# -----------------------------------------------------------------------------


def main() -> None:
    page_header(
        "Data Manager",
        subtitle="Download dei template CSV e upload di dataset personalizzati con validazione",
        icon="📂",
    )
    bundle = load_bundle()

    tab_download, tab_upload, tab_schema = st.tabs(
        ["⬇️ Download template", "⬆️ Upload & validazione", "📋 Schema"]
    )

    # ------------------------------------------------------------------
    # 1) Download templates
    # ------------------------------------------------------------------
    with tab_download:
        st.markdown(
            """
            Scarica un template CSV già popolato con il dataset corrente.
            Puoi modificarlo e ricaricarlo dal tab successivo, oppure usarlo
            come base per costruire un dataset reale.

            Tutti i template hanno lo stesso schema documentato in `data/schema.md`.
            """
        )

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### `companies.csv`")
            st.caption(
                f"{len(bundle.companies)} righe, {bundle.companies['company_id'].nunique()} aziende, "
                f"{len(COMPANY_REQUIRED_COLUMNS)} colonne"
            )
            st.download_button(
                label="📥 Download dataset corrente",
                data=_df_to_csv_bytes(bundle.companies),
                file_name="companies.csv",
                mime="text/csv",
                use_container_width=True,
            )
            st.download_button(
                label="📥 Download template vuoto (solo header)",
                data=_df_to_csv_bytes(_empty_template(COMPANY_REQUIRED_COLUMNS)),
                file_name="companies_template.csv",
                mime="text/csv",
                use_container_width=True,
            )

            st.markdown("#### `macro.csv`")
            st.caption(f"{len(bundle.macro)} righe (country × year)")
            st.download_button(
                label="📥 Download dataset corrente",
                data=_df_to_csv_bytes(bundle.macro),
                file_name="macro.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_macro",
            )
            st.download_button(
                label="📥 Download template vuoto",
                data=_df_to_csv_bytes(_empty_template(MACRO_REQUIRED_COLUMNS)),
                file_name="macro_template.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_macro_tpl",
            )

        with col2:
            st.markdown("#### `sectors.csv`")
            st.caption(f"{len(bundle.sectors)} sotto-settori GICS")
            st.download_button(
                label="📥 Download dataset corrente",
                data=_df_to_csv_bytes(bundle.sectors),
                file_name="sectors.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_sectors",
            )
            st.download_button(
                label="📥 Download template vuoto",
                data=_df_to_csv_bytes(_empty_template(SECTOR_REQUIRED_COLUMNS)),
                file_name="sectors_template.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_sectors_tpl",
            )

            st.markdown("#### `rating_master_scale.csv`")
            st.caption(f"{len(bundle.rating_master_scale)} classi rating")
            st.download_button(
                label="📥 Download dataset corrente",
                data=_df_to_csv_bytes(bundle.rating_master_scale),
                file_name="rating_master_scale.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_rating",
            )
            st.download_button(
                label="📥 Download template vuoto",
                data=_df_to_csv_bytes(_empty_template(RATING_REQUIRED_COLUMNS)),
                file_name="rating_master_scale_template.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_rating_tpl",
            )

    # ------------------------------------------------------------------
    # 2) Upload & validate
    # ------------------------------------------------------------------
    with tab_upload:
        st.markdown(
            """
            Carica un file CSV per validarlo. La validazione è in memoria:
            il file **non viene salvato** sul disco. Ti mostro:

            - errori di schema (colonne mancanti)
            - errori sulle invarianti di bilancio (solo per `companies.csv`)
            - una preview dei primi 50 record
            - statistiche di base
            """
        )

        target_type = st.radio(
            "Tipo di dataset",
            ["companies", "sectors", "macro", "rating_master_scale"],
            horizontal=True,
        )

        uploaded = st.file_uploader(
            f"Seleziona il file `{target_type}.csv`",
            type=["csv"],
            key=f"upload_{target_type}",
        )

        if uploaded is None:
            st.info("In attesa del file...")
            return

        # Persist the upload to a tmp buffer that the loaders can read
        raw = uploaded.read()
        bio = io.BytesIO(raw)

        try:
            if target_type == "companies":
                df = load_companies(bio)
            elif target_type == "sectors":
                df = load_sectors(bio)
            elif target_type == "macro":
                df = load_macro(bio)
            else:
                df = load_rating_master_scale(bio)
        except SchemaError as exc:
            st.error(f"❌ Schema non valido: {exc}")
            with st.expander("Vedi le prime righe del file caricato"):
                bio.seek(0)
                preview = pd.read_csv(bio, nrows=5)
                st.dataframe(preview, use_container_width=True)
            return
        except Exception as exc:  # noqa: BLE001
            st.error(f"❌ Errore nel parsing del file: {exc}")
            return

        st.success(
            f"✅ Schema OK — {len(df)} righe caricate "
            f"({len(df.columns)} colonne)"
        )

        # Invariant check (only for companies)
        if target_type == "companies":
            violations = check_invariants(df)
            if violations:
                st.error(
                    f"❌ Invarianti di bilancio violate: {len(violations)} errori"
                )
                viol_df = pd.DataFrame([v.as_dict() for v in violations[:50]])
                st.dataframe(viol_df, use_container_width=True, hide_index=True)
                if len(violations) > 50:
                    st.caption(f"... e altri {len(violations) - 50} errori non mostrati")
            else:
                st.success("✅ Tutte le invarianti di bilancio rispettate")

        # Stats and preview
        st.markdown("### Preview")
        st.dataframe(df.head(50), use_container_width=True, hide_index=True)

        st.markdown("### Statistiche")
        col1, col2, col3 = st.columns(3)
        col1.metric("Righe", f"{len(df):,}")
        col2.metric("Colonne", len(df.columns))
        if target_type == "companies":
            col3.metric("Aziende uniche", df["company_id"].nunique())
        elif target_type == "macro":
            col3.metric("Paesi", df["country"].nunique())
        elif target_type == "sectors":
            col3.metric("Settori", df["gics_sub_industry"].nunique())
        else:
            col3.metric("Classi rating", df["rating"].nunique())

        with st.expander("Schema atteso (per riferimento)"):
            schema_map = {
                "companies": COMPANY_REQUIRED_COLUMNS,
                "sectors": SECTOR_REQUIRED_COLUMNS,
                "macro": MACRO_REQUIRED_COLUMNS,
                "rating_master_scale": RATING_REQUIRED_COLUMNS,
            }
            st.code("\n".join(schema_map[target_type]))

    # ------------------------------------------------------------------
    # 3) Schema reference
    # ------------------------------------------------------------------
    with tab_schema:
        st.markdown(
            """
            ### Schema di riferimento dei CSV

            Tutti i CSV usano:
            - separatore: `,`
            - encoding: `UTF-8`
            - decimal separator: `.`
            - valori mancanti: vuoto (no `NaN`/`NULL`)
            - valori monetari in **milioni** della valuta indicata
            - tassi e percentuali in **decimali** (es. 0.28 = 28%)

            Vedi `data/schema.md` nel repository per la documentazione completa.
            """
        )

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### `companies.csv`")
            st.code("\n".join(COMPANY_REQUIRED_COLUMNS), language="text")

            st.markdown("#### `macro.csv`")
            st.code("\n".join(MACRO_REQUIRED_COLUMNS), language="text")

        with col2:
            st.markdown("#### `sectors.csv`")
            st.code("\n".join(SECTOR_REQUIRED_COLUMNS), language="text")

            st.markdown("#### `rating_master_scale.csv`")
            st.code("\n".join(RATING_REQUIRED_COLUMNS), language="text")

        st.markdown(
            """
            **Invarianti automatiche** verificate su `companies.csv`:

            ```
            ebitda  == revenues - operating_costs
            ebit    == ebitda   - depreciation_amortization
            nic     == net_fixed_assets + net_working_capital
            net_debt == gross_debt - cash
            equity  == nic - net_debt
            ```

            Qualsiasi violazione viene segnalata dal validatore.
            """
        )


main()
