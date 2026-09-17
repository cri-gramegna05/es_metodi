"""scout CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from .config import load_config
from .db import Database
from .dedupe import brand_slug
from .log import setup_logging
from .pipeline import Pipeline

app = typer.Typer(help="Scout — nightly M&A target discovery for Italian footwear brands.",
                  no_args_is_help=True)
console = Console()

ConfigOpt = Annotated[Path, typer.Option("--config", "-c", help="Path to config.yaml")]


def _boot(config: Path) -> tuple:
    settings = load_config(config)
    setup_logging(settings.log_level, settings.log_file)
    return settings, Database(settings.db_path)


@app.command()
def run(
    config: ConfigOpt = Path("config.yaml"),
    source: Annotated[str | None, typer.Option(help="Run a single source (even if disabled)")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Do not write to the database")] = False,
    classify: Annotated[bool | None, typer.Option(
        "--classify/--no-classify", help="Override classify.enabled from the config")] = None,
    enrich: Annotated[bool | None, typer.Option(
        "--enrich/--no-enrich", help="Override enrich.enabled from the config")] = None,
    publish: Annotated[bool, typer.Option(
        "--publish/--no-publish", help="Send Telegram and write the Google Sheet")] = True,
    as_json: Annotated[bool, typer.Option("--json", help="Print the summary as JSON")] = False,
) -> None:
    """Run the whole pipeline: collect, dedupe, rules, classify, enrich, publish."""
    settings, db = _boot(config)
    if classify is not None:
        settings.classify.enabled = classify
    if enrich is not None:
        settings.enrich.enabled = enrich
    if not publish:
        settings.notify.telegram.enabled = False
        settings.sheets.enabled = False
    try:
        summary = Pipeline(settings, db).run(only_source=source, dry_run=dry_run)
    finally:
        db.close()

    if as_json:
        console.print_json(json.dumps(summary.as_counters() | {"candidates": summary.candidates},
                                      default=str))
        return

    console.print(
        f"\n[bold]Run {summary.run_id or '(dry)'}[/] — sources: {', '.join(summary.sources) or '-'} | "
        f"items: {summary.items} | brands: {summary.brands_seen} "
        f"([green]{summary.brands_new} new[/]) | passed: [green]{summary.passed}[/] | "
        f"dropped: [yellow]{summary.dropped}[/] | classified: {summary.classified}"
        + (f" ([red]{summary.classify_failed} failed[/])" if summary.classify_failed else "")
        + f" | enriched: {summary.enriched} | notified: [green]{summary.notified}[/]"
        + (f" | sheet rows: {summary.sheet_rows}" if summary.sheet_rows else "")
    )
    for err in summary.errors:
        console.print(f"[red]error[/] {err}")

    if not summary.candidates:
        console.print("[yellow]No brand passed the rules.[/]")
        return
    table = Table(title="Candidates", header_style="bold")
    for col in ("brand", "score", "pre", "price", "disc%", "items", "positioning",
                "founder", "revenue", "red flags"):
        table.add_column(col, overflow="fold")
    for c in summary.candidates[:40]:
        price = f"{c['price_min']:.0f}-{c['price_max']:.0f}" if c["price_min"] else "-"
        cls = c.get("classification") or {}
        delta = ""
        if c["old_score"] is not None and c["old_score"] != c["score"]:
            delta = f" ({c['score'] - c['old_score']:+d})"
        table.add_row(
            f"{c['brand']}{' [green]NEW[/]' if c['is_new'] else ''}",
            f"{c['score']}{delta}", str(c["prescore"]), price,
            f"{c['discount_pct']:.0f}" if c["discount_pct"] is not None else "-",
            str(c["n_items"]), cls.get("positioning", "-"), cls.get("founder_type", "-"),
            f"{c['revenue_estimate_eur']:,.0f}" if c.get("revenue_estimate_eur") else "-",
            ", ".join(cls.get("red_flags") or []) or "-",
        )
    console.print(table)


@app.command()
def show(
    brand: Annotated[str, typer.Argument(help="Brand name or slug")],
    config: ConfigOpt = Path("config.yaml"),
) -> None:
    """Show everything stored about one brand."""
    settings, db = _boot(config)
    try:
        row = db.get_brand_by_slug(brand) or db.get_brand_by_slug(brand_slug(brand))
        if row is None:
            alias_id = db.find_brand_id_by_alias(brand)
            row = db.conn.execute("SELECT * FROM brands WHERE id=?", (alias_id,)).fetchone() \
                if alias_id else None
        if row is None:
            console.print(f"[red]Brand not found:[/] {brand}")
            raise typer.Exit(1)

        console.print(f"\n[bold]{row['display_name']}[/] ({row['slug']})")
        console.print(
            f"country: {row['country'] or '?'} | score: {row['current_score'] if row['current_score'] is not None else '-'} "
            f"| stage: {row['current_stage']} | first seen: {row['first_seen_at'][:10]} "
            f"| last seen: {row['last_seen_at'][:10]}"
        )

        table = Table(title="Latest observations", header_style="bold")
        for col in ("source", "items", "price", "disc%", "on sale", "sneaker", "gender", "url"):
            table.add_column(col, overflow="fold")
        for o in db.latest_observations(row["id"]):
            price = f"{o['price_min']:.0f}-{o['price_max']:.0f}" if o["price_min"] else "-"
            table.add_row(
                o["source"], str(o["n_items"]), price,
                f"{o['discount_pct']:.0f}" if o["discount_pct"] is not None else "-",
                f"{o['discounted_share']:.0%}" if o["discounted_share"] is not None else "-",
                f"{o['sneaker_share']:.0%}" if o["sneaker_share"] is not None else "-",
                o["gender"] or "?", o["url"] or "",
            )
        console.print(table)

        classification = db.latest_classification(row["id"])
        if classification:
            console.print(
                f"\nclassification ({classification['model']}): score "
                f"[bold]{classification['score']}[/] | italian={bool(classification['is_italian'])} "
                f"| mens={bool(classification['is_mens'])} | {classification['positioning']} "
                f"| founder={classification['founder_type']}"
            )
            flags = json.loads(classification["red_flags_json"] or "[]")
            console.print(f"red flags: {', '.join(flags) or '-'}")
            console.print(f"rationale: {classification['rationale']}")

        enrichment = db.latest_enrichment(row["id"])
        if enrichment:
            estimate = enrichment["revenue_estimate_eur"]
            console.print(
                f"brief ({enrichment['model']}, {enrichment['created_at'][:10]}): "
                f"stima fatturato "
                + (f"~{estimate:,.0f} EUR" if estimate else "n/d")
                + "  —  vedi [bold]scout brief[/]"
            )

        last_rule = db.conn.execute(
            "SELECT * FROM rule_results WHERE brand_id=? ORDER BY id DESC LIMIT 1", (row["id"],)
        ).fetchone()
        if last_rule:
            verdict = "[green]passed[/]" if last_rule["passed"] else "[yellow]dropped[/]"
            console.print(f"rules: {verdict} | prescore {last_rule['prescore']} "
                          f"| signals: {', '.join(json.loads(last_rule['signals_json']))or '-'} "
                          f"| reasons: {', '.join(json.loads(last_rule['reasons_json'])) or '-'}")
    finally:
        db.close()


@app.command()
def brief(
    brand: Annotated[str, typer.Argument(help="Brand name or slug")],
    config: ConfigOpt = Path("config.yaml"),
) -> None:
    """Print the latest Claude brief for a brand, as Markdown."""
    settings, db = _boot(config)
    try:
        row = db.get_brand_by_slug(brand) or db.get_brand_by_slug(brand_slug(brand))
        if row is None:
            console.print(f"[red]Brand not found:[/] {brand}")
            raise typer.Exit(1)
        enrichment = db.latest_enrichment(row["id"])
        if enrichment is None:
            console.print(f"[yellow]No brief yet for[/] {row['display_name']} "
                          f"(score {row['current_score']}, stage {row['current_stage']})")
            raise typer.Exit(1)
        console.print(Markdown(enrichment["markdown"]))
        sources = json.loads(enrichment["sources_json"] or "[]")
        if sources:
            console.print("\n[bold]Fonti:[/]")
            for url in sources:
                console.print(f"- {url}")
    finally:
        db.close()


@app.command()
def stats(config: ConfigOpt = Path("config.yaml")) -> None:
    """Database and last-run statistics."""
    settings, db = _boot(config)
    try:
        s = db.stats()
        console.print(
            f"\nbrands: [bold]{s['brands']}[/] | observations: {s['observations']} | "
            f"runs: {s['runs']} | passed last run: [green]{s['passed_last_run']}[/]"
        )
        if s["by_source"]:
            console.print("brands per source: " +
                          ", ".join(f"{k}={v}" for k, v in s["by_source"].items()))
        if s["top"]:
            table = Table(title="Top brands by score", header_style="bold")
            for col in ("brand", "slug", "score", "stage"):
                table.add_column(col)
            for r in s["top"]:
                table.add_row(r["display_name"], r["slug"],
                              str(r["current_score"]), r["current_stage"])
            console.print(table)
    finally:
        db.close()


@app.command()
def sources(config: ConfigOpt = Path("config.yaml")) -> None:
    """List configured sources and whether they are enabled."""
    settings, _db = load_config(config), None
    table = Table(title="Sources", header_style="bold")
    for col in ("name", "type", "enabled", "notes"):
        table.add_column(col, overflow="fold")
    for name, cfg in settings.sources.items():
        table.add_row(name, cfg.type,
                      "[green]yes[/]" if cfg.enabled else "[yellow]no[/]", cfg.notes)
    console.print(table)


@app.command("init-db")
def init_db(config: ConfigOpt = Path("config.yaml")) -> None:
    """Create the SQLite database and schema."""
    settings, db = _boot(config)
    console.print(f"[green]ok[/] schema ready at {settings.db_path}")
    db.close()


if __name__ == "__main__":  # pragma: no cover
    app()
