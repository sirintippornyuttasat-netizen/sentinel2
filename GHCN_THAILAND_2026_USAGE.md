# GHCN-D Thailand 2026

`ghcn_thailand_2026.py` connects to the BigQuery public dataset
`bigquery-public-data.ghcn_d`, filters Thailand stations (`TH`) for 2026,
and creates:

- `outputs/thailand_ghcn_2026.csv`
- `outputs/thailand_ghcn_2026_bar.html`
- `outputs/thailand_ghcn_2026_map.html`

Connection settings are stored in `config.json`.

- `billing_project_id`: Google Cloud project used to run the query
- `source_project_id`: public data project, normally `bigquery-public-data`
- `credentials_path`: service-account JSON path, or `null` to use Application Default Credentials

Install dependencies:

```powershell
pip install -r requirements.txt
```

If using Application Default Credentials:

```powershell
gcloud auth application-default login
```

Run:

```powershell
python .\ghcn_thailand_2026.py
```
