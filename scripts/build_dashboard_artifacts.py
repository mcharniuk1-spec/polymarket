from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from textwrap import shorten

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_edge.dashboard_data import build_dashboard_payload
from sports_edge.intelligence import load_latest_intelligence


REPORTS_DIR = ROOT / "reports"
DOWNLOADS_DIR = ROOT / "web" / "downloads"
EXPORT_PAYLOAD_PATH = REPORTS_DIR / "dashboard_export_payload.json"
PDF_REPORT_PATH = REPORTS_DIR / "polymarket_workflow_report.pdf"
DOWNLOAD_PDF_PATH = DOWNLOADS_DIR / "polymarket_workflow_report.pdf"
STATIC_INTELLIGENCE_PATH = ROOT / "data" / "generated" / "intelligence" / "latest.json"
PRODUCTION_STATE_INTELLIGENCE_PATH = ROOT / "data" / "generated" / "production_state" / "latest_intelligence.json"


def pct(value: object) -> str:
    return f"{float(value or 0) * 100:.1f}%"


def coins(value: object) -> str:
    return f"{float(value or 0):.2f}"


def short_text(value: object, width: int = 86) -> str:
    return shorten(str(value or ""), width=width, placeholder="...")


def sync_static_intelligence_snapshot() -> None:
    if not PRODUCTION_STATE_INTELLIGENCE_PATH.exists():
        return
    payload = json.loads(PRODUCTION_STATE_INTELLIGENCE_PATH.read_text(encoding="utf-8"))
    has_model_outputs = any(
        row.get("multiModelForecast", {}).get("outputs")
        for row in payload.get("marketAnalysisResults", [])
    )
    if has_model_outputs:
        STATIC_INTELLIGENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATIC_INTELLIGENCE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def build_export_payload() -> dict[str, object]:
    sync_static_intelligence_snapshot()
    dashboard = build_dashboard_payload(source_mode="fixture", target_count=300, use_cache=False)
    intelligence = load_latest_intelligence()
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dashboard": dashboard,
        "intelligence": intelligence,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_PAYLOAD_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def add_section(story: list[object], title: str, body: list[str], styles: dict[str, ParagraphStyle]) -> None:
    story.append(Paragraph(title, styles["Heading2"]))
    for paragraph in body:
        story.append(Paragraph(paragraph, styles["Body"]))
    story.append(Spacer(1, 0.12 * inch))


def build_pdf(payload: dict[str, object]) -> None:
    dashboard = payload["dashboard"]["multi_agent"]  # type: ignore[index]
    intelligence = payload["intelligence"]  # type: ignore[assignment]
    metrics = dashboard.get("metrics", {})
    daily_bets = [row for row in dashboard.get("recommendations", []) if row.get("decision") == "PAPER_BET"]
    daily_bets.sort(key=lambda row: float(row.get("rank_score") or 0), reverse=True)
    model_rows = [
        row for row in intelligence.get("marketAnalysisResults", []) if row.get("multiModelForecast", {}).get("outputs")
    ]
    model_output_count = sum(
        len(row.get("multiModelForecast", {}).get("outputs", []))
        for row in intelligence.get("marketAnalysisResults", [])
    )

    base = getSampleStyleSheet()
    styles = {
        "Title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#17202E"),
            spaceAfter=14,
        ),
        "Heading2": ParagraphStyle(
            "Heading2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#17202E"),
            spaceBefore=10,
            spaceAfter=6,
        ),
        "Body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#344054"),
            spaceAfter=5,
        ),
    }

    story: list[object] = [
        Paragraph("Polymarket Paper Research Dashboard - Workflow Report", styles["Title"]),
        Paragraph(f"Generated: {payload['generated_at']}", styles["Body"]),
        Paragraph("Boundary: public/read-only research, paper bankroll only, no wallet, no credentials, no order execution.", styles["Body"]),
        Spacer(1, 0.15 * inch),
    ]

    summary_data = [
        ["Metric", "Value"],
        ["Candidates", str(metrics.get("candidate_count", 0))],
        ["Daily paper bets", str(len(daily_bets))],
        ["Monitoring/watchlist", str(metrics.get("watchlist_count", 0))],
        ["Rejected", str(metrics.get("rejected_count", 0))],
        ["Paper bankroll", coins(metrics.get("deployment_budget_units", 100))],
        ["Staked", coins(metrics.get("total_staked_units", 0))],
        ["Simulated ROI", pct(metrics.get("simulated_roi", 0))],
        ["Win/loss", f"{metrics.get('wins', 0)} / {metrics.get('losses', 0)}"],
        ["Multi-model markets", str(len(model_rows))],
        ["Multi-model output rows", str(model_output_count)],
    ]
    summary = Table(summary_data, colWidths=[2.3 * inch, 3.8 * inch])
    summary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17202E")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D0D5DD")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F8FAFC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ]
        )
    )
    story.append(summary)
    story.append(Spacer(1, 0.18 * inch))

    add_section(
        story,
        "Why the website looked unchanged",
        [
            "The prior deployment updated graph readability and mobile layout, but it did not add a dedicated Daily Bets page or downloadable model-output artifacts.",
            "The Approved Bet Book shows only PAPER_BET records with positive paper stake. Monitoring, no-bet, and rejected records remain available as research context, but they are not counted as bets.",
        ],
        styles,
    )
    add_section(
        story,
        "How the system works",
        [
            "1. Collect public market snapshots and fixture-mode source context for the current research cycle.",
            "2. Score each candidate through odds modeling, market/news context, and category expert agents.",
            "3. Blend agent probabilities into a final paper forecast, expected value, confidence, risk tier, and stake size.",
            "4. Run the intelligence layer: reliability checks, lifecycle timestamps, news monitor, correlated-odds instrument, and multi-model forecast outputs.",
            "5. Produce a daily PAPER_BET shortlist plus monitoring and rejected records. Nothing posts orders or touches funds.",
            "6. Persist the full model and agent output workbook for audit and review.",
        ],
        styles,
    )
    add_section(
        story,
        "Model families included in the XLSX",
        [
            "The workbook includes odds_modeling, market_context_news, category_expert, forecast_blend, news-weighted rule, online logistic ML, OLS-style linear probability, IV-style correlated odds, deterministic tree ensemble, and final ensemble fields where available.",
            "Each row keeps market, outcome, forecast, market price, expected value, stake, state, model probability, explanation, risk flags, news score, correlation score, and raw JSON output for auditability.",
        ],
        styles,
    )

    top_rows = [["Rank", "Category", "Market", "Forecast", "Price", "EV", "Stake", "Risk"]]
    for index, item in enumerate(daily_bets[:15], start=1):
        candidate = item.get("candidate", {})
        top_rows.append(
            [
                index,
                candidate.get("category", ""),
                short_text(candidate.get("market_title"), 48),
                pct(item.get("blended_probability")),
                pct(candidate.get("price")),
                pct(item.get("expected_value")),
                coins(item.get("stake_units")),
                item.get("risk_tier", ""),
            ]
        )
    story.append(Paragraph("Top Daily Paper Bets", styles["Heading2"]))
    top_table = Table(top_rows, colWidths=[0.35 * inch, 0.7 * inch, 2.25 * inch, 0.62 * inch, 0.52 * inch, 0.52 * inch, 0.48 * inch, 0.65 * inch])
    top_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2457D6")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D0D5DD")),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ]
        )
    )
    story.append(top_table)
    story.append(Spacer(1, 0.15 * inch))
    add_section(
        story,
        "Files produced",
        [
            "PDF workflow report: web/downloads/polymarket_workflow_report.pdf",
            "Full model workbook: web/downloads/polymarket_model_outputs.xlsx",
            "Both files are linked from the Daily Bets page on the website.",
        ],
        styles,
    )
    add_section(
        story,
        "Limitations",
        [
            "Fixture mode is deterministic and suitable for product/reproducibility checks. It is not evidence of a live market edge.",
            "Public API mode remains read-only. This system does not implement real-money betting, wallets, credentials, or automatic execution.",
            "Model quality remains provisional until larger historical settlement data and out-of-sample diagnostics are validated.",
        ],
        styles,
    )

    PDF_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(PDF_REPORT_PATH),
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title="Polymarket Paper Research Dashboard Workflow Report",
    )
    doc.build(story)
    shutil.copyfile(PDF_REPORT_PATH, DOWNLOAD_PDF_PATH)


def main() -> int:
    payload = build_export_payload()
    build_pdf(payload)
    print(json.dumps({"exportPayload": str(EXPORT_PAYLOAD_PATH), "pdf": str(PDF_REPORT_PATH), "downloadPdf": str(DOWNLOAD_PDF_PATH)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
