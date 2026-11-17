"""Interactive local Aiven connection setup. Password input is hidden and never printed."""
from getpass import getpass
from pathlib import Path

base = Path(__file__).resolve().parent
host = input('Aiven host [rooster-mysql-rooster.d.aivencloud.com]: ').strip() or 'rooster-mysql-rooster.d.aivencloud.com'
port = input('Aiven port [12088]: ').strip() or '12088'
database = input('Database name [defaultdb]: ').strip() or 'defaultdb'
user = input('Aiven username [avnadmin]: ').strip() or 'avnadmin'
password = getpass('Aiven password (hidden): ')
if not password:
    raise SystemExit('Password cannot be empty.')
content = f'''DB_HOST={host}\nDB_PORT={port}\nDB_NAME={database}\nDB_USER={user}\nDB_PASSWORD={password}\nDB_SSL=true\nDB_SSL_CA=ca.pem\n'''
(base / '.env').write_text(content, encoding='utf-8')
print('Saved connection settings to .env. Password was not displayed.')
