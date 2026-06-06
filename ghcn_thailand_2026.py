from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import bigquery


CONFIG_PATH = Path("config.json")


def fallback_path(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return path.with_name(f"{path.stem}_{timestamp}{path.suffix}")


def write_csv_safely(df: pd.DataFrame, path: Path) -> Path:
    try:
        df.to_csv(path, index=False)
        return path
    except PermissionError:
        path = fallback_path(path)
        df.to_csv(path, index=False)
        return path


def write_html_safely(fig, path: Path) -> Path:
    try:
        fig.write_html(path)
        return path
    except PermissionError:
        path = fallback_path(path)
        fig.write_html(path)
        return path


def load_config(path: Path = CONFIG_PATH) -> dict:
    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    required = [
        "billing_project_id",
        "source_project_id",
        "dataset",
        "observations_table",
        "stations_table",
        "country_code",
        "year",
        "output_dir",
    ]
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError(f"Missing config values: {', '.join(missing)}")

    return config


def make_client(config: dict) -> bigquery.Client:
    credentials_path = config.get("credentials_path")
    if credentials_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(Path(credentials_path))

    try:
        return bigquery.Client(project=config["billing_project_id"])
    except DefaultCredentialsError as exc:
        raise RuntimeError(
            "BigQuery credentials were not found. Run "
            "`gcloud auth application-default login`, or set "
            "`credentials_path` in config.json to a service-account JSON file."
        ) from exc


def fetch_thailand_ghcn_daily(client: bigquery.Client, config: dict) -> pd.DataFrame:
    source = f"`{config['source_project_id']}.{config['dataset']}.{config['observations_table']}`"
    stations = f"`{config['source_project_id']}.{config['dataset']}.{config['stations_table']}`"

    query = f"""
        SELECT
            obs.id AS station_id,
            stations.name AS station_name,
            stations.latitude,
            stations.longitude,
            stations.elevation,
            obs.date,
            obs.element,
            obs.value
        FROM {source} AS obs
        JOIN {stations} AS stations
            ON obs.id = stations.id
        WHERE SUBSTR(obs.id, 1, 2) = @country_code
            AND EXTRACT(YEAR FROM obs.date) = @year
            AND obs.element IN ('TAVG', 'TMAX', 'TMIN', 'PRCP')
            AND (obs.qflag IS NULL OR obs.qflag = '')
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("country_code", "STRING", config["country_code"]),
            bigquery.ScalarQueryParameter("year", "INT64", config["year"]),
        ]
    )
    return client.query(query, job_config=job_config).to_dataframe()


def normalize_units(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["value_normalized"] = df["value"]
    df.loc[df["element"].isin(["TAVG", "TMAX", "TMIN"]), "value_normalized"] = (
        df.loc[df["element"].isin(["TAVG", "TMAX", "TMIN"]), "value"] / 10
    )
    df.loc[df["element"].eq("PRCP"), "value_normalized"] = (
        df.loc[df["element"].eq("PRCP"), "value"] / 10
    )
    df["metric"] = df["element"].map(
        {
            "TAVG": "Average temperature (C)",
            "TMAX": "Max temperature (C)",
            "TMIN": "Min temperature (C)",
            "PRCP": "Precipitation (mm)",
        }
    )
    return df


def build_bar_chart(df: pd.DataFrame, output_dir: Path) -> Path:
    temperature = (
        df[df["element"].isin(["TAVG", "TMAX", "TMIN"])]
        .groupby(["month", "element", "metric"], as_index=False)
        .agg(value=("value_normalized", "mean"))
    )

    precipitation = (
        df[df["element"].eq("PRCP")]
        .groupby(["month", "station_id"], as_index=False)
        .agg(station_month_total=("value_normalized", "sum"))
        .groupby("month", as_index=False)
        .agg(value=("station_month_total", "mean"))
    )
    precipitation["element"] = "PRCP"
    precipitation["metric"] = "Average station precipitation total (mm)"

    monthly = pd.concat([temperature, precipitation], ignore_index=True).sort_values(
        ["month", "element"]
    )

    fig = px.bar(
        monthly,
        x="month",
        y="value",
        color="metric",
        barmode="group",
        title="Thailand GHCN-D observations in 2026",
        labels={"month": "Month", "value": "Value", "metric": "Metric"},
    )
    fig.update_layout(
        legend_title_text="",
        legend={
            "orientation": "h",
            "yanchor": "top",
            "y": -0.25,
            "xanchor": "center",
            "x": 0.5,
        },
        xaxis_tickangle=-45,
        margin={"b": 120},
    )

    path = output_dir / "thailand_ghcn_2026_bar.html"
    return write_html_safely(fig, path)


def build_station_map(df: pd.DataFrame, output_dir: Path) -> Path:
    temperature = df[df["element"].isin(["TAVG", "TMAX", "TMIN"])]
    tavg = temperature[temperature["element"].eq("TAVG")]
    if not tavg.empty:
        station_temperature = (
            tavg.groupby("station_id", as_index=False)
            .agg(avg_temperature_c=("value_normalized", "mean"))
        )
    else:
        daily_temperature = (
            temperature[temperature["element"].isin(["TMAX", "TMIN"])]
            .pivot_table(
                index=["station_id", "date"],
                columns="element",
                values="value_normalized",
                aggfunc="mean",
            )
            .dropna(subset=["TMAX", "TMIN"])
        )
        daily_temperature["daily_avg_temperature_c"] = (
            daily_temperature["TMAX"] + daily_temperature["TMIN"]
        ) / 2
        station_temperature = (
            daily_temperature.reset_index()
            .groupby("station_id", as_index=False)
            .agg(avg_temperature_c=("daily_avg_temperature_c", "mean"))
        )

    stations = (
        df.groupby(["station_id", "station_name", "latitude", "longitude"], as_index=False)
        .agg(
            observations=("value", "size"),
            first_date=("date", "min"),
            last_date=("date", "max"),
        )
        .sort_values("observations", ascending=False)
        .merge(station_temperature, on="station_id", how="left")
    )

    fig = px.scatter_map(
        stations,
        lat="latitude",
        lon="longitude",
        size="observations",
        color="avg_temperature_c",
        color_continuous_scale=["#fff176", "#ffb300", "#f4511e", "#b71c1c"],
        hover_name="station_name",
        hover_data={
            "station_id": True,
            "observations": True,
            "avg_temperature_c": ":.2f",
            "first_date": True,
            "last_date": True,
            "latitude": ":.4f",
            "longitude": ":.4f",
        },
        zoom=5,
        height=720,
        title="Thailand GHCN-D stations in 2026",
    )
    fig.update_layout(
        coloraxis_colorbar={
            "title": {"text": "Avg temp (C)", "side": "bottom"},
            "orientation": "h",
            "yanchor": "top",
            "y": -0.08,
            "xanchor": "center",
            "x": 0.5,
            "len": 0.72,
            "thickness": 18,
        },
        map_style="open-street-map",
        margin={"r": 0, "t": 50, "l": 0, "b": 95},
    )

    path = output_dir / "thailand_ghcn_2026_map.html"
    return write_html_safely(fig, path)


def main() -> None:
    config = load_config()
    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    client = make_client(config)
    df = fetch_thailand_ghcn_daily(client, config)
    if df.empty:
        raise RuntimeError("No Thailand GHCN-D records were returned for the configured year.")

    df = normalize_units(df)
    csv_path = output_dir / "thailand_ghcn_2026.csv"
    csv_path = write_csv_safely(df, csv_path)

    bar_path = build_bar_chart(df, output_dir)
    map_path = build_station_map(df, output_dir)

    print(f"Saved data: {csv_path}")
    print(f"Saved bar chart: {bar_path}")
    print(f"Saved station map: {map_path}")


if __name__ == "__main__":
    main()
