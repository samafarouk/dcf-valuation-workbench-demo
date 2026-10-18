import io
from datetime import date

import pandas as pd
import streamlit as st

st.set_page_config(page_title="DCF Valuation Workbench", page_icon="📊", layout="wide")

NAVY = "#10233f"
BLUE = "#2476c7"

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


def read_financial_file(uploaded_file):
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        data = pd.read_csv(uploaded_file)
    else:
        data = pd.read_excel(uploaded_file)
    data.columns = [str(c).strip() for c in data.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in data.columns]
    if missing:
        raise ValueError("The file is missing these required columns: " + ", ".join(missing))
    data = data[REQUIRED_COLUMNS].copy()
    for col in REQUIRED_COLUMNS:
        data[col] = pd.to_numeric(data[col], errors="raise")
    if data.empty:
        raise ValueError("The uploaded file has no rows.")
    if data[REQUIRED_COLUMNS].isna().any().any():
        raise ValueError("Some required cells are blank. Fill them in before uploading.")
    if data["Year"].duplicated().any():
        raise ValueError("Each year should appear only once.")
    if not data["Year"].mod(1).eq(0).all():
        raise ValueError("Year values should be whole numbers, such as 2024.")
    if ((data["Tax_Rate"] < 0) | (data["Tax_Rate"] > 100)).any():
        raise ValueError("Tax_Rate must be entered as a number from 0 to 100 (for example, 22 for 22%).")
    if len(data) < 2:
        raise ValueError("Upload at least two years of financial data to calculate the change in working capital.")
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
    calculate = st.button("Calculate valuation", type="primary", use_container_width=True)

st.subheader("1. Choose your FCFF source")
source = st.radio("How do you want to provide starting FCFF?", ["Enter FCFF manually", "Calculate FCFF from financial statements"], horizontal=True)
history = None
starting_fcff = manual_fcff
source_label = "Manual input"

if source == "Calculate FCFF from financial statements":
    st.markdown("Upload a CSV or Excel file containing the historical financial data listed below.")
    with st.expander("What columns does my file need?", expanded=True):
        st.code("Year, EBIT, Tax_Rate, D&A, CapEx, Receivables, Inventory, Payables", language="text")
        st.caption("Use one row per year. Enter Tax_Rate as 22 for 22%, not 0.22. Use at least two years so the model can calculate the change in working capital.")
    uploaded = st.file_uploader("Upload financial statements (.xlsx or .csv)", type=["xlsx", "csv"])
    if uploaded is not None:
        try:
            raw = read_financial_file(uploaded)
            history = calculate_fcff(raw)
            valid = history.dropna(subset=["FCFF"])
            if valid.empty:
                st.error("No valid FCFF could be calculated from this file.")
            else:
                latest = valid.iloc[-1]
                starting_fcff = float(latest["FCFF"])
                source_label = f"Uploaded statements — FY {int(latest['Year'])}"
                st.success(f"Calculated latest FCFF: EGP {starting_fcff:,.2f} million (FY {int(latest['Year'])}).")
                st.dataframe(history.round(2), use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Could not read this file: {e}")
            history = None

if source == "Calculate FCFF from financial statements" and history is None:
    st.info("Upload a valid file first. The model will use the calculated latest FCFF after the upload is successful.")

if calculate:
    if not company.strip():
        st.error("Please enter a company name.")
    elif source == "Calculate FCFF from financial statements" and history is None:
        st.error("Please upload a valid financial-statement file before calculating.")
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
    st.dataframe(package["forecast"].round(2), use_container_width=True, hide_index=True)

    st.markdown("#### Downside / base / upside scenarios")
    st.dataframe(package["scenarios"].style.format({"FCFF Growth":"{:.1%}", "WACC":"{:.1%}", "Terminal Growth":"{:.1%}",
        "Enterprise Value (EGP M)":"{:,.2f}", "Equity Value (EGP M)":"{:,.2f}", "Value per Share (EGP)":"{:,.2f}"}), use_container_width=True, hide_index=True)

    st.markdown("#### Enterprise value sensitivity")
    st.caption("Rows are WACC; columns are terminal growth. N/A means WACC is not greater than terminal growth.")
    st.dataframe(package["sensitivity"].style.format("{:,.2f}", na_rep="N/A").background_gradient(cmap="RdYlGn", axis=None), use_container_width=True)

    with st.expander("Detailed valuation components"):
        base = package["base"]
        details = pd.DataFrame({"Component": ["PV of forecast cash flows", "Terminal value (at end of forecast)", "PV of terminal value"],
            "EGP millions": [base["PV of Forecast Cash Flows"], base["Terminal Value"], base["PV of Terminal Value"]]})
        st.dataframe(details.style.format({"EGP millions":"{:,.2f}"}), use_container_width=True, hide_index=True)

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
