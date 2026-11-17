# Roosters Operations Dashboard

Streamlit dashboard for the Roosters MySQL database. It reads the live tuples from Aiven and provides browsing, search, pagination, CRUD forms and CSV reports for the 10 Roosters tables.

## Aiven connection setup (local)
1. Extract the ZIP and open PowerShell in `roosters_dashboard`.
2. Install Python 3.10+ and run `python -m venv .venv`.
3. Activate it: `.venv\\Scripts\\Activate.ps1`.
4. Install packages: `pip install -r requirements.txt`.
5. Run `python configure_connection.py`. It prompts for the database name and password; password entry is hidden and written only to local `.env`.
6. The supplied `ca.pem` is the Aiven CA certificate. SSL verification is enabled.
7. Run `streamlit run app.py`.

The Aiven screenshot shows database `defaultdb`, host `rooster-mysql-rooster.d.aivencloud.com`, port `12088`, and user `avnadmin`. The SQL dump identifies the schema as `roosters_db`; if the Roosters tables were imported into another database, enter that actual database name when the setup script asks. Do not assume the SQL dump's database name is the live Aiven database name.

## Existing tuples and pagination
The dashboard queries the selected live database. Table pages show a matching-row count and paginate through records instead of truncating the table at 500 rows. The overview and reports also query the live database. A successful connection and matching table names are required before the data can appear.

## Streamlit Community Cloud
Push the source folder to GitHub without `.env`. In Streamlit app settings, add secrets in TOML format:

```toml
DB_HOST = "rooster-mysql-rooster.d.aivencloud.com"
DB_PORT = "12088"
DB_NAME = "defaultdb"
DB_USER = "avnadmin"
DB_PASSWORD = "enter-your-password-in-streamlit-secrets"
DB_SSL = "true"
DB_SSL_CA = "ca.pem"
```

For cloud deployment, make sure the CA file is included in the repository. Configure Aiven networking to allow the Streamlit app to connect. Avoid exposing an admin database account in a public production app; use a dedicated least-privilege account and add authentication/authorization before public release.

## Look and feel
- `.streamlit/config.toml` holds the theme (colours, fonts, corner radius). It switches between light and dark automatically based on your system setting.
- `assets/` holds the logo shown at the top of the sidebar.
- Navigation is grouped into Dashboard, Inventory, Quality & maintenance, People and Reports.

## Notes
- `Employee_Password_Hash` is never shown in table listings or edit forms.
- Sourcing spend reports calculate `Sourcing_Quantity * Sourcing_Unit_Price` rather than depending on a stored derived total.
- Inventory transaction entries do not automatically mutate stock quantities, to avoid double-counting the existing ledger.
- Deletions remain subject to MySQL foreign-key constraints.
