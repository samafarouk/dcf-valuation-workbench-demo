import io
from datetime import date

import pandas as pd
import streamlit as st

st.set_page_config(page_title="DCF Valuation Workbench", page_icon="📊", layout="wide")

NAVY = "#10233f"
BLUE = "#2476c7"


def display_excel_preview(frame: pd.DataFrame, *, height=None):
    """Render imported Excel tables robustly when columns mix strings, numbers and blanks."""
    safe = frame.copy()
    for col in safe.columns:
        if safe[col].dtype == "object":
            # Excel workbooks often mix numbers, text labels, and blank cells in the same column.
            # Convert these mixed columns to consistent text for display only; source values stay intact.
            safe[col] = safe[col].map(lambda value: "" if pd.isna(value) else str(value))
    st.dataframe(safe, width="stretch", hide_index=True, height=height)


st.markdown(
    f"""
    <div style="background:linear-gradient(135deg,{NAVY},#174ea6);padding:24px 28px;border-radius:14px;color:white;margin-bottom:18px">
      <div style="font-size:12px;letter-spacing:2px;opacity:.85">FINANCIAL MODELING · EQUITY VALUATION</div>
      <div style="font-size:30px;font-weight:750;margin-top:6px">DCF Valuation Workbench</div>
      <div style="font-size:14px;opacity:.85;margin-top:5px">Forecast cash flows · Test scenarios · Explore valuation sensitivity</div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.caption("Amounts are entered in EGP millions unless the field says otherwise. This is an analytical tool, not investment advice.")

REQUIRED_COLUMNS = ["Year", "EBIT", "Tax_Rate", "D&A", "CapEx", "Receivables", "Inventory", "Payables"]


def calculate_fcff(financial_data: pd.DataFrame) -> pd.DataFrame:
    df = financial_data.copy()
    df = df.sort_values("Year").reset_index(drop=True)
    df["NOPAT"] = df["EBIT"] * (1 - df["Tax_Rate"] / 100)
    df["NWC"] = df["Receivables"] + df["Inventory"] - df["Payables"]
    df["Change_NWC"] = df["NWC"].diff()
    df["FCFF"] = df["NOPAT"] + df["D&A"] - df["CapEx"] - df["Change_NWC"]
    return df


def calculate_dcf(current_fcff, growth_rate, wacc, terminal_growth, forecast_years, net_debt, shares_outstanding):
    if current_fcff <= 0:
        raise ValueError("Starting FCFF must be positive. Check the value or uploaded statements.")
    if growth_rate <= -1:
        raise ValueError("FCFF growth must be greater than -100%.")
    if wacc <= 0 or wacc <= terminal_growth:
        raise ValueError("WACC must be positive and greater than terminal growth.")
    if terminal_growth < 0:
        raise ValueError("Terminal growth cannot be negative.")
    if forecast_years < 1:
        raise ValueError("Forecast years must be at least 1.")
    if shares_outstanding <= 0:
        raise ValueError("Shares outstanding must be positive.")

    years = list(range(1, int(forecast_years) + 1))
    fcff_forecast = [current_fcff * (1 + growth_rate) ** year for year in years]
    discounted_fcff = [cf / (1 + wacc) ** year for year, cf in zip(years, fcff_forecast)]
    pv_cash_flows = sum(discounted_fcff)
    terminal_value = fcff_forecast[-1] * (1 + terminal_growth) / (wacc - terminal_growth)
    pv_terminal = terminal_value / (1 + wacc) ** forecast_years
    enterprise_value = pv_cash_flows + pv_terminal
    equity_value = enterprise_value - net_debt
    return {
        "Enterprise Value": enterprise_value,
        "Equity Value": equity_value,
        "Value per Share": equity_value / shares_outstanding,
        "PV of Forecast Cash Flows": pv_cash_flows,
        "Terminal Value": terminal_value,
        "PV of Terminal Value": pv_terminal,
        "FCFF Forecast": fcff_forecast,
        "Years": years,
    }


COLUMN_ALIASES = {
    "Year": ["year", "fy", "fiscal year", "period", "financial year", "date"],
    "EBIT": ["ebit", "operating profit", "operating income", "profit from operations", "operating earnings"],
    "Tax_Rate": ["tax_rate", "tax rate", "effective tax rate", "tax %", "tax rate %", "tax rate (%)"],
    "D&A": ["d&a", "da", "depreciation and amortization", "depreciation & amortization", "depreciation and amortisation", "depreciation & amortisation", "depreciation amortization", "depreciation", "depreciation and amortization expense"],
    "CapEx": ["capex", "capital expenditure", "capital expenditures", "purchase of property plant and equipment", "purchases of property plant and equipment", "additions to property plant and equipment", "capital spending"],
    "Receivables": ["receivables", "accounts receivable", "trade receivables", "trade and other receivables", "account receivables"],
    "Inventory": ["inventory", "inventories", "stocks"],
    "Payables": ["payables", "accounts payable", "trade payables", "trade and other payables", "account payables"],
}


def normalize_label(value):
    return " ".join(str(value).strip().lower().replace("_", " ").replace("&", " and ").replace("%", " percent").split())


def suggest_column_mapping(columns):
    normalized = {col: normalize_label(col) for col in columns}
    mapping = {}
    for target, aliases in COLUMN_ALIASES.items():
        choices = [normalize_label(target)] + [normalize_label(x) for x in aliases]
        match = next((col for col, norm in normalized.items() if norm in choices), None)
        if match is None:
            # Conservative partial matching for common labels; user confirms every selection.
            match = next((col for col, norm in normalized.items() if any(a in norm for a in choices if len(a) > 4)), None)
        mapping[target] = match if match is not None else "— Select a column —"
    return mapping


def read_uploaded_table(uploaded_file, sheet_name=None):
    uploaded_file.seek(0)
    if uploaded_file.name.lower().endswith(".csv"):
        return pd.read_csv(uploaded_file)
    return pd.read_excel(uploaded_file, sheet_name=sheet_name)


def validate_mapped_data(data):
    missing = [c for c in REQUIRED_COLUMNS if c not in data.columns]
    if missing:
        raise ValueError("Please map every required field before continuing: " + ", ".join(missing))
    data = data[REQUIRED_COLUMNS].copy()
    for col in REQUIRED_COLUMNS:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    if data.empty:
        raise ValueError("The selected sheet has no data rows.")
    blank_cols = [c for c in REQUIRED_COLUMNS if data[c].isna().all()]
    if blank_cols:
        raise ValueError("No numeric values were found for: " + ", ".join(blank_cols) + ". Check your column mapping and selected sheet.")
    if data[REQUIRED_COLUMNS].isna().any().any():
        bad = [c for c in REQUIRED_COLUMNS if data[c].isna().any()]
        raise ValueError("Some cells are blank or non-numeric in: " + ", ".join(bad) + ". Fill or correct these values in the review table.")
    if data["Year"].duplicated().any():
        raise ValueError("Each year should appear only once. Check for duplicate periods.")
    if not data["Year"].mod(1).eq(0).all():
        raise ValueError("Year values should be whole numbers, such as 2024.")
    if ((data["Tax_Rate"] < 0) | (data["Tax_Rate"] > 100)).any():
        raise ValueError("Tax rate must be entered as a percentage from 0 to 100 (for example, 22 for 22%, not 0.22).")
    if len(data) < 2:
        raise ValueError("Upload at least two years of data so the model can calculate the change in working capital.")
    return data.sort_values("Year").reset_index(drop=True)


def make_excel_report(company, summary, forecast, scenarios, sensitivity, history=None):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Valuation Summary", index=False, startrow=3)
        forecast.to_excel(writer, sheet_name="FCFF Forecast", index=False, startrow=3)
        scenarios.to_excel(writer, sheet_name="Scenarios", index=False, startrow=3)
        sensitivity.to_excel(writer, sheet_name="Sensitivity", startrow=3)
        if history is not None:
            history.to_excel(writer, sheet_name="Historical FCFF", index=False, startrow=3)
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
        wb = writer.book
        for ws in wb.worksheets:
            ws.sheet_view.showGridLines = False
            ws.freeze_panes = "A5"
            last_col = max(ws.max_column, 3)
            ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
            ws.cell(1, 1).value = f"{company} | DCF Valuation Report"
            ws.cell(1, 1).font = Font(name="Aptos Display", size=18, bold=True, color="FFFFFF")
            ws.cell(1, 1).fill = PatternFill("solid", fgColor="10233F")
            ws.row_dimensions[1].height = 34
            ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
            ws.cell(2, 1).value = f"{ws.title} | Generated {date.today()} | Amounts in EGP millions unless stated otherwise"
            ws.cell(2, 1).font = Font(size=10, italic=True, color="64748B")
            for cell in ws[4]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="2476C7")
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            ws.row_dimensions[4].height = 30
            for col_cells in ws.columns:
                letter = get_column_letter(col_cells[0].column)
                max_len = max((len(str(c.value)) for c in col_cells if c.value is not None), default=12)
                ws.column_dimensions[letter].width = min(max(max_len + 3, 14), 36)
    output.seek(0)
    return output.getvalue()

with st.sidebar:
    st.header("Valuation inputs")
    company = st.text_input("Company name", "Example Company")
    st.markdown("#### Cash flow assumptions")
    manual_fcff = st.number_input("Starting FCFF (EGP M)", min_value=0.01, value=100.0, step=5.0)
    growth_pct = st.number_input("Annual FCFF growth (%)", min_value=-99.0, max_value=100.0, value=8.0, step=1.0)
    wacc_pct = st.number_input("WACC (%)", min_value=0.1, max_value=100.0, value=12.0, step=0.5)
    terminal_pct = st.number_input("Terminal growth (%)", min_value=0.0, max_value=50.0, value=3.0, step=0.5)
    years = st.number_input("Forecast years", min_value=1, max_value=20, value=5, step=1)
    st.markdown("#### Capital structure")
    net_debt = st.number_input("Net debt (EGP M)", value=250.0, step=25.0)
    shares = st.number_input("Shares outstanding (millions)", min_value=0.01, value=100.0, step=10.0)
    calculate = st.button("Calculate valuation", type="primary", width="stretch")

st.subheader("1. Choose your FCFF source")
source = st.radio("How do you want to provide starting FCFF?", ["Enter FCFF manually", "Calculate FCFF from financial statements"], horizontal=True)
history = None
starting_fcff = manual_fcff
source_label = "Manual input"

if source == "Calculate FCFF from financial statements":
    st.markdown("Upload an Excel workbook or CSV. You can select a specific table inside a worksheet, so separate WACC, assumptions, and valuation blocks won't be treated as one giant table.")
    with st.expander("What can I import?", expanded=False):
        st.markdown("**Historical statements:** map Year, EBIT, Tax Rate, D&A, CapEx, Receivables, Inventory, and Payables to calculate FCFF.\n\n**An existing DCF model:** if your workbook already has a row called Free Cash Flow to Firm (FCFF) or Free Cash Flow (FCF), you can select that row and use its latest forecast value as starting FCFF. This is a shortcut, so confirm that the chosen row represents FCFF and that its units are consistent.")
        st.caption("The importer reads structured Excel/CSV data. It does not automatically extract arbitrary PDF reports.")

    uploaded = st.file_uploader("Upload financial statements or an existing valuation workbook (.xlsx or .csv)", type=["xlsx", "csv"], key="financial_upload")
    if uploaded is not None:
        try:
            if uploaded.name.lower().endswith(".xlsx"):
                uploaded.seek(0)
                workbook = pd.ExcelFile(uploaded)
                sheet = st.selectbox("1. Choose the worksheet", workbook.sheet_names, key="financial_sheet")
                uploaded.seek(0)
                raw_grid = pd.read_excel(uploaded, sheet_name=sheet, header=None)
            else:
                uploaded.seek(0)
                raw_grid = pd.read_csv(uploaded, header=None)
                sheet = "CSV"

            # Remove completely empty edges while preserving positions within the used range.
            raw_grid = raw_grid.dropna(axis=0, how="all").dropna(axis=1, how="all")
            raw_grid = raw_grid.reset_index(drop=True)
            raw_grid.columns = range(raw_grid.shape[1])
            if raw_grid.empty or raw_grid.shape[1] == 0:
                st.error("The selected worksheet appears to be empty.")
            else:
                st.markdown("#### Step A — Preview the worksheet")
                st.caption("This is the raw worksheet, before interpretation. If the sheet contains side-by-side blocks, select only one block at a time using the row and column boundaries below.")
                display_excel_preview(raw_grid.head(30), height=420)
                st.markdown("#### Step B — Select the table you want to use")
                import_mode = st.radio(
                    "What kind of data are you importing?",
                    ["Historical statements (calculate FCFF)", "Existing DCF model (use an existing FCFF/FCF row)"],
                    key="import_mode",
                    help="Choose historical statements when you have operating data and working-capital inputs. Choose existing DCF only when a valid FCFF/FCF row is already calculated in the workbook."
                )
                max_row = max(0, len(raw_grid) - 1)
                max_col = max(0, len(raw_grid.columns) - 1)
                r1, r2 = st.columns(2)
                with r1:
                    row_start = st.number_input("First worksheet row", min_value=1, max_value=max(1, len(raw_grid)), value=1, step=1, key="table_row_start")
                with r2:
                    row_end = st.number_input("Last worksheet row", min_value=1, max_value=max(1, len(raw_grid)), value=min(len(raw_grid), 15), step=1, key="table_row_end")
                c1, c2 = st.columns(2)
                with c1:
                    col_start = st.number_input("First worksheet column (A=1, B=2...)", min_value=1, max_value=max(1, len(raw_grid.columns)), value=1, step=1, key="table_col_start")
                with c2:
                    col_end = st.number_input("Last worksheet column", min_value=1, max_value=max(1, len(raw_grid.columns)), value=len(raw_grid.columns), step=1, key="table_col_end")

                if row_end < row_start or col_end < col_start:
                    st.warning("The ending row/column must be equal to or greater than the starting row/column.")
                else:
                    table = raw_grid.iloc[int(row_start)-1:int(row_end), int(col_start)-1:int(col_end)].copy()
                    table = table.dropna(axis=0, how="all").dropna(axis=1, how="all")
                    st.markdown("##### Selected table preview")
                    display_excel_preview(table, height=420)

                    if import_mode == "Historical statements (calculate FCFF)":
                        orientation = st.radio("How is this table arranged?", ["Each row is a year (standard)", "Metrics are rows and years are columns (horizontal)"], horizontal=False, key="selected_table_orientation")
                        if orientation == "Each row is a year (standard)":
                            header_row = st.number_input("Header row within selected table", min_value=1, max_value=max(1, len(table)), value=1, step=1, key="selected_header_row")
                            hdr = table.iloc[int(header_row)-1].fillna("").astype(str).str.strip().tolist()
                            data = table.iloc[int(header_row):].copy()
                            data.columns = [v if v else f"Unnamed: {i}" for i, v in enumerate(hdr)]
                            data = data.dropna(how="all").reset_index(drop=True)
                        else:
                            st.caption("For this layout, the first column should contain metric labels (EBIT, D&A, etc.) and the first row should contain years.")
                            label_col = st.selectbox("Column containing metric names", list(table.columns), format_func=lambda x: f"Selected-table column {int(x)+1}", key="metric_label_col")
                            header_row = st.number_input("Row containing years within selected table", min_value=1, max_value=max(1, len(table)), value=1, step=1, key="horizontal_year_header")
                            header_values = table.iloc[int(header_row)-1].tolist()
                            label_values = table.iloc[:, int(label_col)].tolist()
                            # Keep only columns whose header looks like a year/period. This avoids
                            # treating blank cells or side-by-side assumptions blocks as data columns.
                            def period_label(value):
                                text = str(value).strip()
                                match = __import__("re").search(r"(19|20)\d{2}", text)
                                return match.group(0) if match else None
                            period_cols = []
                            for j, value in enumerate(header_values):
                                if j == int(label_col):
                                    continue
                                period = period_label(value)
                                if period:
                                    period_cols.append((j, period))
                            rows = []
                            for idx, label_value in enumerate(label_values):
                                label = str(label_value).strip()
                                if idx == int(header_row)-1 or not label or label.lower() == "nan":
                                    continue
                                # Ignore rows that have no numeric values under the detected year columns.
                                metric_values = {}
                                for j, period in period_cols:
                                    cell_value = table.iloc[idx, j]
                                    metric_values[period] = cell_value
                                if any(pd.notna(v) for v in metric_values.values()):
                                    rows.append({"Metric": label, **metric_values})
                            transposed = pd.DataFrame(rows)
                            if not transposed.empty and period_cols:
                                transposed = transposed.drop_duplicates(subset=["Metric"], keep="first").set_index("Metric").T.reset_index().rename(columns={"index": "Year"})
                                transposed.columns = [str(c).strip() for c in transposed.columns]
                                data = transposed
                                st.success(f"Detected {len(period_cols)} year column(s): {', '.join(dict.fromkeys(p for _, p in period_cols))}.")
                            else:
                                data = pd.DataFrame()
                                st.warning("We couldn't identify year columns in the selected header row. Choose the row that contains headings such as 2026, 2027, 2028.")
                        if not data.empty:
                            data.columns = [str(c).strip() for c in data.columns]
                            st.markdown("#### Step C — Confirm the column matches")
                            st.caption("Choose which column contains each financial metric. You can correct every suggestion.")
                            suggestions = suggest_column_mapping(data.columns)
                            options = ["— Select a column —"] + list(data.columns)
                            mapped = {}
                            left, right = st.columns(2)
                            for i, target in enumerate(REQUIRED_COLUMNS):
                                container = left if i % 2 == 0 else right
                                with container:
                                    suggested = suggestions.get(target, "— Select a column —")
                                    index = options.index(suggested) if suggested in options else 0
                                    mapped[target] = st.selectbox(f"{target}" + (" (year)" if target == "Year" else " (percentage, 0–100)" if target == "Tax_Rate" else ""), options, index=index, key=f"map_{target}")
                            unresolved = [target for target, col in mapped.items() if col == "— Select a column —"]
                            if unresolved:
                                st.warning("Please select a source column for: " + ", ".join(unresolved) + ".")
                            else:
                                candidate = pd.DataFrame({target: data[source_col] for target, source_col in mapped.items()})
                                st.markdown("#### Step D — Review and edit the mapped inputs")
                                edited = st.data_editor(candidate, width="stretch", hide_index=True, num_rows="fixed", key="mapped_financial_review")
                                if st.button("Confirm data and calculate historical FCFF", type="primary", key="confirm_financial_data"):
                                    try:
                                        clean = validate_mapped_data(edited)
                                        history = calculate_fcff(clean)
                                        valid = history.dropna(subset=["FCFF"])
                                        if valid.empty:
                                            st.error("No valid FCFF could be calculated from the selected data.")
                                        else:
                                            latest = valid.iloc[-1]
                                            starting_fcff = float(latest["FCFF"])
                                            source_label = f"Uploaded statements — FY {int(latest['Year'])}"
                                            st.session_state["confirmed_financial_history"] = history
                                            st.session_state["confirmed_starting_fcff"] = starting_fcff
                                            st.session_state["confirmed_source_label"] = source_label
                                            st.success(f"Data confirmed. Latest calculated FCFF: {starting_fcff:,.2f} (FY {int(latest['Year'])}).")
                                    except Exception as e:
                                        st.error(f"Please review the mapped data: {e}")
                        else:
                            st.warning("The selected range is empty. Adjust the row and column boundaries to select the table you need.")
                    else:
                        st.caption("Use this when your workbook already contains a calculated FCFF/FCF row. Select a range that includes the metric labels and the year/value columns.")
                        label_col = st.selectbox("Column containing metric labels", list(table.columns), format_func=lambda x: f"Selected-table column {int(x)+1}", key="existing_fcf_label_col")
                        metric_names = table.iloc[:, int(label_col)].fillna("").astype(str).str.strip().tolist()
                        metric_options = [str(m) for m in metric_names if str(m).strip() and str(m).strip().lower() != "nan"]
                        if metric_options:
                            selected_metric = st.selectbox("Choose the row that represents FCFF / FCF", metric_options, key="existing_fcf_metric")
                            matching_positions = [i for i, value in enumerate(metric_names) if value == selected_metric]
                            metric_row = table.iloc[matching_positions[0]]
                            value_columns = [i for i in table.columns if i != label_col]
                            year_values = []
                            fcff_values = []
                            for col in value_columns:
                                val = pd.to_numeric(pd.Series([metric_row[col]]), errors="coerce").iloc[0]
                                if pd.notna(val):
                                    year_values.append(str(table.iloc[0, col]).strip())
                                    fcff_values.append(float(val))
                            if fcff_values:
                                preview_fcff = pd.DataFrame({"Period": year_values, "FCFF / FCF value": fcff_values})
                                display_excel_preview(preview_fcff, height=240)
                                st.warning("Confirm that this row is unlevered free cash flow to the firm (FCFF), not equity free cash flow (FCFE), EBITDA, or a valuation output. The app cannot infer financial meaning from the label alone.")
                                if st.button("Use the last numeric value as starting FCFF", type="primary", key="confirm_existing_fcf"):
                                    starting_fcff = fcff_values[-1]
                                    source_label = f"Existing model row — {selected_metric} ({year_values[-1]})"
                                    history = None
                                    st.session_state["confirmed_starting_fcff"] = starting_fcff
                                    st.session_state["confirmed_source_label"] = source_label
                                    st.session_state["confirmed_financial_history"] = None
                                    st.success(f"Starting FCFF set to {starting_fcff:,.2f} from {selected_metric} ({year_values[-1]}).")
                            else:
                                st.info("No numeric values were found in this row within the selected table. Expand or adjust your selected range.")
                        else:
                            st.info("No metric labels found in the selected first column. Adjust the selected range or choose another label column.")

                saved_history = st.session_state.get("confirmed_financial_history")
                saved_fcff = st.session_state.get("confirmed_starting_fcff")
                if saved_fcff is not None and st.session_state.get("confirmed_source_label"):
                    starting_fcff = float(saved_fcff)
                    source_label = st.session_state["confirmed_source_label"]
                    if saved_history is not None:
                        history = saved_history
                        st.success(f"Using confirmed historical data. Latest FCFF: {starting_fcff:,.2f} — {source_label}.")
                        st.dataframe(history.round(2), width="stretch", hide_index=True)
                    elif str(source_label).startswith("Existing model row"):
                        st.success(f"Using confirmed existing FCFF value: {starting_fcff:,.2f} — {source_label}.")
        except Exception as e:
            st.error(f"We couldn't read this file or sheet: {e}")
            history = st.session_state.get("confirmed_financial_history")

if source == "Calculate FCFF from financial statements" and history is None and not str(source_label).startswith("Existing model row"):
    st.info("Upload a valid file and confirm either historical statements or an existing FCFF/FCF row before calculating.")

if calculate:
    if not company.strip():
        st.error("Please enter a company name.")
    elif source == "Calculate FCFF from financial statements" and history is None and not str(source_label).startswith("Existing model row"):
        st.error("Please upload a valid financial-statement file or confirm an existing FCFF/FCF row before calculating.")
    else:
        try:
            g, r, tg = growth_pct / 100, wacc_pct / 100, terminal_pct / 100
            base = calculate_dcf(starting_fcff, g, r, tg, int(years), net_debt, shares)
            scenario_inputs = {
                "Downside": (g - 0.02, r + 0.02, max(0, tg - 0.01)),
                "Base": (g, r, tg),
            }
            up_r = max(r - 0.02, tg + 0.02)
            up_tg = min(tg + 0.01, up_r - 0.01)
            scenario_inputs["Upside"] = (g + 0.02, up_r, max(0, up_tg))
            scenario_rows = []
            for name, (sg, sr, stg) in scenario_inputs.items():
                if sr <= stg:
                    sr = stg + 0.01
                out = calculate_dcf(starting_fcff, sg, sr, stg, int(years), net_debt, shares)
                scenario_rows.append({"Scenario": name, "FCFF Growth": sg, "WACC": sr, "Terminal Growth": stg,
                                      "Enterprise Value (EGP M)": out["Enterprise Value"], "Equity Value (EGP M)": out["Equity Value"],
                                      "Value per Share (EGP)": out["Value per Share"]})
            scenarios = pd.DataFrame(scenario_rows)
            wacc_rates = sorted(set([max(0.001, r - 0.02), r, r + 0.02]))
            terminal_rates = sorted(set([max(0, tg - 0.01), tg, tg + 0.01]))
            sensitivity = pd.DataFrame(index=[f"{x:.1%}" for x in wacc_rates], columns=[f"{x:.1%}" for x in terminal_rates], dtype=float)
            for sr in wacc_rates:
                for stg in terminal_rates:
                    if sr <= stg:
                        sensitivity.loc[f"{sr:.1%}", f"{stg:.1%}"] = float("nan")
                    else:
                        out = calculate_dcf(starting_fcff, g, sr, stg, int(years), net_debt, shares)
                        sensitivity.loc[f"{sr:.1%}", f"{stg:.1%}"] = out["Enterprise Value"]
            forecast = pd.DataFrame({"Year": [f"Year {y}" for y in base["Years"]], "Projected FCFF (EGP M)": base["FCFF Forecast"]})
            summary = pd.DataFrame([{
                "Company": company, "Valuation Date": str(date.today()), "FCFF Source": source_label,
                "Starting FCFF (EGP M)": starting_fcff, "FCFF Growth": g, "WACC": r,
                "Terminal Growth": tg, "Forecast Years": int(years), "Net Debt (EGP M)": net_debt,
                "Shares Outstanding (M)": shares, "PV of Forecast Cash Flows (EGP M)": base["PV of Forecast Cash Flows"],
                "Terminal Value (EGP M)": base["Terminal Value"], "PV of Terminal Value (EGP M)": base["PV of Terminal Value"],
                "Enterprise Value (EGP M)": base["Enterprise Value"], "Equity Value (EGP M)": base["Equity Value"],
                "Value per Share (EGP)": base["Value per Share"]
            }])
            st.session_state["valuation_package"] = {"company": company, "summary": summary, "base": base,
                "scenarios": scenarios, "sensitivity": sensitivity, "forecast": forecast, "history": history}
        except Exception as e:
            st.error(f"Could not calculate valuation: {e}")

package = st.session_state.get("valuation_package")
if package:
    st.markdown("---")
    st.subheader(f"2. Valuation dashboard — {package['company']}")
    a, b, c = st.columns(3)
    a.metric("Enterprise value", f"EGP {package['base']['Enterprise Value']:,.2f}M")
    b.metric("Equity value", f"EGP {package['base']['Equity Value']:,.2f}M")
    c.metric("Intrinsic value per share", f"EGP {package['base']['Value per Share']:,.2f}")

    st.markdown("#### Forecast free cash flow")
    st.bar_chart(package["forecast"].set_index("Year"), y="Projected FCFF (EGP M)")
    st.dataframe(package["forecast"].round(2), width="stretch", hide_index=True)

    st.markdown("#### Downside / base / upside scenarios")
    st.dataframe(package["scenarios"].style.format({"FCFF Growth":"{:.1%}", "WACC":"{:.1%}", "Terminal Growth":"{:.1%}",
        "Enterprise Value (EGP M)":"{:,.2f}", "Equity Value (EGP M)":"{:,.2f}", "Value per Share (EGP)":"{:,.2f}"}), width="stretch", hide_index=True)

    st.markdown("#### Enterprise value sensitivity")
    st.caption("Rows are WACC; columns are terminal growth. N/A means WACC is not greater than terminal growth.")
    st.dataframe(package["sensitivity"].style.format("{:,.2f}", na_rep="N/A").background_gradient(cmap="RdYlGn", axis=None), width="stretch")

    with st.expander("Detailed valuation components"):
        base = package["base"]
        details = pd.DataFrame({"Component": ["PV of forecast cash flows", "Terminal value (at end of forecast)", "PV of terminal value"],
            "EGP millions": [base["PV of Forecast Cash Flows"], base["Terminal Value"], base["PV of Terminal Value"]]})
        st.dataframe(details.style.format({"EGP millions":"{:,.2f}"}), width="stretch", hide_index=True)

    st.markdown("#### Export your report")
    xlsx_bytes = make_excel_report(package["company"], package["summary"], package["forecast"], package["scenarios"], package["sensitivity"], package["history"])
    safe_name = "_".join(package["company"].strip().split()) or "Company"
    st.download_button("Download Excel valuation report", data=xlsx_bytes, file_name=f"{safe_name}_DCF_Valuation_Report.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
    st.download_button("Download valuation summary (CSV)", data=package["summary"].to_csv(index=False).encode("utf-8"), file_name=f"{safe_name}_DCF_Summary.csv", mime="text/csv")
else:
    st.markdown("---")
    st.subheader("2. Your valuation results will appear here")
    st.write("Enter your assumptions in the left sidebar, choose your FCFF source, then click **Calculate valuation**.")

st.markdown("---")
st.caption("Model note: the valuation depends on the assumptions entered. Verify financial statement inputs, capital structure, and methodology before using results in investment decisions.")
