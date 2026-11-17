import os, re, hashlib
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
import pandas as pd
import altair as alt
import streamlit as st
import pymysql
from pymysql.cursors import DictCursor
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent


def setting(name, default=None):
    value = os.getenv(name)
    if value not in (None, ''): return value
    try: return st.secrets.get(name, default)
    except Exception: return default


st.set_page_config(page_title='Roosters | Operations Dashboard', page_icon=str(BASE_DIR / 'assets' / 'icon.svg'), layout='wide', initial_sidebar_state='expanded')

TABLES = ['Employee','Initial_Test','Inventory_Transaction','Machine','Maintenance','Material','Object_Guideline','Sourcing','Supplier','Technical_Record']
LABELS = {
'Employee':'Employees','Initial_Test':'Initial Tests','Inventory_Transaction':'Inventory Transactions','Machine':'Machines','Maintenance':'Maintenance','Material':'Materials','Object_Guideline':'Object Guidelines','Sourcing':'Sourcing','Supplier':'Suppliers','Technical_Record':'Technical Records'}
ICONS = {
'Employee':':material/badge:','Initial_Test':':material/science:','Inventory_Transaction':':material/swap_horiz:','Machine':':material/construction:','Maintenance':':material/build:','Material':':material/inventory_2:','Object_Guideline':':material/rule:','Sourcing':':material/local_shipping:','Supplier':':material/storefront:','Technical_Record':':material/description:'}
DESCRIPTIONS = {
'Employee':'Staff accounts, roles and reporting lines.',
'Initial_Test':'Tests carried out when an item first arrives, marked Passed or Failed.',
'Inventory_Transaction':'Stock movements in and out of the yard.',
'Machine':'Equipment on record, with stock and reorder levels.',
'Maintenance':'Servicing history and upcoming due dates for machines.',
'Material':'Building materials, quantities and reorder levels.',
'Object_Guideline':'Versioned criteria each material or machine is tested against.',
'Sourcing':'Deliveries from suppliers, with batch and pricing details.',
'Supplier':'Approved and pending suppliers.',
'Technical_Record':'Versioned documentation for each initial test.'}
HIDDEN_COLUMNS = {'Employee_Password_Hash'}

# Status colours. Always shown with a text label, never colour alone.
STATUS = {'good':'#0CA30C','warning':'#FAB219','critical':'#D03B3B'}

st.markdown('''<style>
.block-container {padding-top:3.4rem;padding-bottom:3rem;max-width:1440px;}
h1 {letter-spacing:-.025em;}
h2,h3 {letter-spacing:-.015em;}
.rs-eyebrow {font-size:.72rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--st-primary-color, #C2410C);margin-bottom:.15rem;}
.rs-sub {opacity:.68;font-size:.95rem;margin-top:-.35rem;margin-bottom:.4rem;}
.rs-footer {opacity:.5;font-size:.78rem;text-align:center;margin-top:2.5rem;}
[data-testid="stMetric"] {padding:16px 18px;}
[data-testid="stMetricValue"] {font-size:1.9rem;}
[data-testid="stSidebar"] [data-testid="stCode"] code {font-size:.78rem;}
div[data-testid="stTabs"] button p {font-weight:600;}
</style>''', unsafe_allow_html=True)


def pretty(name):
    return name.replace('_', ' ')


def page_header(eyebrow, title, subtitle=None):
    st.markdown(f'<div class="rs-eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.title(title, anchor=False)
    if subtitle: st.markdown(f'<div class="rs-sub">{subtitle}</div>', unsafe_allow_html=True)


def show_df(df, height='auto', column_config=None):
    """Display a dataframe with readable column headers. Data itself is unchanged."""
    view = df.rename(columns={c: pretty(c) for c in df.columns})
    config = {pretty(k): v for k, v in (column_config or {}).items()}
    st.dataframe(view, width='stretch', hide_index=True, height=height, column_config=config)


def get_conn():
    required = ['DB_HOST','DB_NAME','DB_USER','DB_PASSWORD']
    missing = [k for k in required if not setting(k)]
    if missing: raise RuntimeError('Missing database settings: '+', '.join(missing)+'. Add them to your .env file.')
    ssl_cfg = None
    if str(setting('DB_SSL','true')).lower() == 'true':
        ca_path = setting('DB_SSL_CA', 'ca.pem')
        if ca_path and not os.path.isabs(ca_path): ca_path = os.path.join(os.path.dirname(__file__), ca_path)
        ssl_cfg = {'ca': ca_path, 'check_hostname': True} if ca_path and os.path.isfile(ca_path) else {}
    return pymysql.connect(host=setting('DB_HOST'), port=int(setting('DB_PORT','3306')), user=setting('DB_USER'), password=setting('DB_PASSWORD'), database=setting('DB_NAME'), cursorclass=DictCursor, charset='utf8mb4', connect_timeout=15, read_timeout=30, write_timeout=30, ssl=ssl_cfg, autocommit=False)


def query(sql, args=None):
    conn=get_conn()
    try:
        with conn.cursor() as cur: cur.execute(sql,args or ()); rows=cur.fetchall()
        return rows
    finally: conn.close()


def execute(sql,args=None):
    conn=get_conn()
    try:
        with conn.cursor() as cur: cur.execute(sql,args or ()); count=cur.rowcount
        conn.commit(); return count
    except Exception:
        conn.rollback(); raise
    finally: conn.close()


def schema():
    rows=query("SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,EXTRA,COLUMN_KEY,DATA_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME,ORDINAL_POSITION",(setting('DB_NAME'),))
    fks=query("SELECT TABLE_NAME,COLUMN_NAME,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=%s AND REFERENCED_TABLE_NAME IS NOT NULL",(setting('DB_NAME'),))
    out={t:[] for t in TABLES}
    for r in rows:
        if r['TABLE_NAME'] in out: out[r['TABLE_NAME']].append(r)
    return out,fks


def safe_ident(s):
    if not re.fullmatch(r'[A-Za-z0-9_]+',s): raise ValueError('Invalid database identifier')
    return '`'+s+'`'


def get_pk(cols): return next((c['COLUMN_NAME'] for c in cols if c['COLUMN_KEY']=='PRI'),None)

@st.cache_data(ttl=60)
def lookup_rows(table, pk, label):
    return query(f"SELECT {safe_ident(pk)} AS id, {safe_ident(label)} AS label FROM {safe_ident(table)} ORDER BY {safe_ident(label)} LIMIT 1000")


def fk_map(fks, table): return {x['COLUMN_NAME']:x for x in fks if x['TABLE_NAME']==table}


CHOICES = {
    'Employee_Role':['Engineer','Admin'],
    'Employee_Account_Status':['Active','Inactive'],
    'Supplier_Approval_Status':['Active','Inactive','Pending'],
    'Initial_Test_Result':['Passed','Failed'],
    'Initial_Test_Type':['Stress Test','Quality Control Notes','Laser Scan','Material Dimension'],
    'Transaction_Type':['IN','OUT'],
    'Material_Stock_Status':['In Stock','Low Stock','Out of Stock'],
    'Machine_Stock_Status':['In Stock','Low Stock','Out of Stock'],
    'Maintenance_Type':['Preventive','Corrective','Calibration']
}


def input_for(col, fk, current=None, key_prefix="field"):
    widget_key = lambda suffix="": f"{key_prefix}_{col['COLUMN_NAME']}{suffix}"
    name=col['COLUMN_NAME']; dtype=col['DATA_TYPE']; nullable=col['IS_NULLABLE']=='YES'; extra=col['EXTRA'] or ''
    label=pretty(name)
    if 'auto_increment' in extra.lower(): return None
    if name in CHOICES:
        options=CHOICES[name]
        return st.selectbox(label,options,index=options.index(current) if current in options else 0,key=widget_key())
    if name in HIDDEN_COLUMNS:
        if current is not None: return None
        pw=st.text_input('Employee Password',type='password',help='The password is hashed with SHA-256 before being stored. The hash is never displayed.',key=widget_key())
        return hashlib.sha256(pw.encode()).hexdigest() if pw else None
    if fk and name in fk:
        ref=fk[name]; ref_table=ref['REFERENCED_TABLE_NAME']; ref_pk=ref['REFERENCED_COLUMN_NAME']
        ref_cols=st.session_state.db_schema.get(ref_table,[])
        ref_label=next((c['COLUMN_NAME'] for c in ref_cols if c['COLUMN_NAME'].endswith('_Name')),ref_pk)
        opts=lookup_rows(ref_table,ref_pk,ref_label)
        values=[None]+[int(o['id']) for o in opts] if nullable else [int(o['id']) for o in opts]
        default_val=int(current) if current is not None else (None if nullable else (values[0] if values else None))
        idx=values.index(default_val) if default_val in values else 0
        return st.selectbox(label,options=values,format_func=lambda x: 'Not set' if x is None else next((f"{o['label']} (#{o['id']})" for o in opts if int(o['id'])==x),str(x)),index=idx,key=widget_key())
    if dtype in ('text','mediumtext','longtext'):
        return st.text_area(label,value='' if current is None else str(current),height=100,key=widget_key())
    if dtype in ('date',):
        val=current.date() if isinstance(current,datetime) else current
        return st.date_input(label,value=val if val else date.today(),key=widget_key())
    if dtype in ('datetime','timestamp'):
        val=current if isinstance(current,datetime) else datetime.now()
        d_col,t_col=st.columns(2)
        with d_col: d=st.date_input(label+' (date)',value=val.date(),key=widget_key('_d'))
        with t_col: tm=st.time_input(label+' (time)',value=val.time().replace(microsecond=0),key=widget_key('_t'))
        return datetime.combine(d,tm)
    if dtype in ('tinyint','smallint','mediumint','int','bigint'):
        if name=='Guideline_Version' or name=='Record_Version_Number': return st.number_input(label,min_value=1,step=1,value=int(current or 1),key=widget_key())
        if name.endswith('Quantity') or name.endswith('Reorder_Level'): return st.number_input(label,min_value=0,step=1,value=int(current or 0),key=widget_key())
        return st.number_input(label,value=int(current or 0),step=1,key=widget_key())
    if dtype in ('decimal','numeric','float','double','real'):
        return st.number_input(label,value=float(current or 0),format='%.3f' if '3)' in col['COLUMN_TYPE'] else '%.2f',key=widget_key())
    return st.text_input(label,value='' if current is None else str(current),key=widget_key())


def form_fields(cols, fks, key_prefix, current=None, skip=()):
    """Lay the inputs out in two columns. Long text fields span the full width."""
    vals={}
    short=[c for c in cols if c['COLUMN_NAME'] not in skip and c['DATA_TYPE'] not in ('text','mediumtext','longtext')]
    long=[c for c in cols if c['COLUMN_NAME'] not in skip and c['DATA_TYPE'] in ('text','mediumtext','longtext')]
    grid=st.columns(2, gap='medium')
    for i,c in enumerate(short):
        with grid[i%2]:
            vals[c['COLUMN_NAME']]=input_for(c,fks,None if current is None else current.get(c['COLUMN_NAME']),key_prefix=key_prefix)
    for c in long:
        vals[c['COLUMN_NAME']]=input_for(c,fks,None if current is None else current.get(c['COLUMN_NAME']),key_prefix=key_prefix)
    return vals


def search_clause(cols, search_term):
    searchable=[c['COLUMN_NAME'] for c in cols if c['DATA_TYPE'] in ('varchar','char','text','int','decimal') and c['COLUMN_NAME'] not in HIDDEN_COLUMNS]
    if not (search_term and searchable): return '',[]
    return ' WHERE '+' OR '.join(f"CAST({safe_ident(c)} AS CHAR) LIKE %s" for c in searchable),[f'%{search_term}%']*len(searchable)


def count_records(table, search_term=''):
    where,args=search_clause(st.session_state.db_schema[table],search_term)
    return query(f'SELECT COUNT(*) AS total FROM {safe_ident(table)}'+where,args)[0]['total']


def get_records(table, search_term='', page=1, page_size=50):
    cols=st.session_state.db_schema[table]; pk=get_pk(cols)
    visible=[c['COLUMN_NAME'] for c in cols if c['COLUMN_NAME'] not in HIDDEN_COLUMNS]
    where,args=search_clause(cols,search_term)
    sql=f"SELECT {', '.join(safe_ident(c) for c in visible)} FROM {safe_ident(table)}"+where
    sql+=f' ORDER BY {safe_ident(pk)} DESC LIMIT %s OFFSET %s'
    return query(sql,args+[page_size,(page-1)*page_size]),pk


# ---------------------------------------------------------------- charts

def stock_chart(df):
    """Horizontal stacked bar of stock health per category, using status colours."""
    long=df.melt(id_vars='category',var_name='status',value_name='items')
    long['status']=long['status'].map({'healthy':'In stock','low':'Low stock','out_of_stock':'Out of stock'})
    long['items']=pd.to_numeric(long['items']).fillna(0).astype(int)
    order=['In stock','Low stock','Out of stock']
    long['order']=long['status'].map({s:i for i,s in enumerate(order)})
    return alt.Chart(long).mark_bar(cornerRadius=4).encode(
        y=alt.Y('category:N',title=None,sort=['Materials','Machines'],scale=alt.Scale(paddingInner=0.4,paddingOuter=0.2),axis=alt.Axis(labelFontSize=13,labelFontWeight=600,labelPadding=8)),
        x=alt.X('sum(items):Q',title='Items',stack='zero',axis=alt.Axis(tickMinStep=1,grid=True)),
        color=alt.Color('status:N',scale=alt.Scale(domain=order,range=[STATUS['good'],STATUS['warning'],STATUS['critical']]),legend=alt.Legend(title=None,orient='right',labelFontSize=12,symbolType='square')),
        order=alt.Order('order:Q'),
        tooltip=[alt.Tooltip('category:N',title='Category'),alt.Tooltip('status:N',title='Status'),alt.Tooltip('items:Q',title='Items')]
    ).properties(height=150)


def test_chart(df):
    """Passed vs failed tests per test type."""
    order=['Passed','Failed']
    n=max(1,df['test_type'].nunique())
    return alt.Chart(df).mark_bar(cornerRadius=4).encode(
        y=alt.Y('test_type:N',title=None,sort='-x',scale=alt.Scale(paddingInner=0.35,paddingOuter=0.2),axis=alt.Axis(labelLimit=220,labelPadding=8)),
        x=alt.X('sum(total):Q',title='Tests',stack='zero',axis=alt.Axis(tickMinStep=1)),
        color=alt.Color('result:N',scale=alt.Scale(domain=order,range=[STATUS['good'],STATUS['critical']]),legend=alt.Legend(title=None,orient='right',labelFontSize=12,symbolType='square')),
        order=alt.Order('result:N',sort='descending'),
        tooltip=[alt.Tooltip('test_type:N',title='Test type'),alt.Tooltip('result:N',title='Result'),alt.Tooltip('total:Q',title='Tests')]
    ).properties(height=max(150,44*n))


def spend_chart(df):
    """Total sourcing spend per supplier. One series, so one colour and no legend."""
    df=df.copy(); df['Total_Spend']=pd.to_numeric(df['Total_Spend']).fillna(0).astype(float)
    bars=alt.Chart(df).mark_bar(cornerRadiusEnd=4,color='#3B6FD8').encode(
        y=alt.Y('Supplier_Name:N',title=None,sort='-x',scale=alt.Scale(paddingInner=0.35,paddingOuter=0.2),axis=alt.Axis(labelLimit=240,labelPadding=8)),
        x=alt.X('Total_Spend:Q',title='Total spend (RM)',axis=alt.Axis(format='~s',tickCount=5)),
        tooltip=[alt.Tooltip('Supplier_Name:N',title='Supplier'),alt.Tooltip('Orders:Q',title='Orders'),alt.Tooltip('Total_Spend:Q',title='Total spend (RM)',format=',.2f')])
    return bars.properties(height=max(150,46*len(df)))


# ---------------------------------------------------------------- pages

def page_dashboard():
    page_header('Overview','Operations overview','Live snapshot of the Roosters construction inventory and compliance database.')
    try:
        metrics=query("SELECT (SELECT COUNT(*) FROM Employee) employees,(SELECT COUNT(*) FROM Supplier) suppliers,(SELECT COUNT(*) FROM Material) materials,(SELECT COUNT(*) FROM Machine) machines,(SELECT COUNT(*) FROM Initial_Test) tests,(SELECT COUNT(*) FROM Maintenance) maintenance") [0]
        lowmat=query('SELECT COUNT(*) n FROM Material WHERE Material_Quantity <= Material_Reorder_Level')[0]['n']
        lowmach=query('SELECT COUNT(*) n FROM Machine WHERE Machine_Quantity <= Machine_Reorder_Level')[0]['n']
        failed=query("SELECT COUNT(*) n FROM Initial_Test WHERE Initial_Test_Result='Failed'")[0]['n']
        due=query('SELECT COUNT(*) n FROM Maintenance WHERE Maintenance_Next_Due_Date IS NOT NULL AND Maintenance_Next_Due_Date <= CURDATE()')[0]['n']

        st.space('small')
        c=st.columns(4)
        c[0].metric('Employees',f"{metrics['employees']:,}",icon=':material/badge:',border=True,height=136)
        c[1].metric('Suppliers',f"{metrics['suppliers']:,}",icon=':material/storefront:',border=True,height=136)
        c[2].metric('Materials',f"{metrics['materials']:,}",icon=':material/inventory_2:',border=True,height=136)
        c[3].metric('Machines',f"{metrics['machines']:,}",icon=':material/construction:',border=True,height=136)

        def alert(n, word):
            return (f'{n:,} {word}', 'inverse') if n else ('All clear', 'off')
        c=st.columns(4)
        c[0].metric('Initial tests',f"{metrics['tests']:,}",icon=':material/science:',border=True,height=136)
        d,col=alert(failed,'failed')
        c[1].metric('Failed tests',f'{failed:,}',delta=d,delta_color=col,delta_arrow='off',icon=':material/cancel:',border=True,height=136)
        d,col=alert(lowmat+lowmach,'to reorder')
        c[2].metric('Low-stock items',f'{lowmat+lowmach:,}',delta=d,delta_color=col,delta_arrow='off',icon=':material/production_quantity_limits:',border=True,height=136)
        d,col=alert(due,'overdue or due')
        c[3].metric('Maintenance due',f'{due:,}',delta=d,delta_color=col,delta_arrow='off',icon=':material/event_busy:',border=True,height=136)

        st.space('small')
        left,right=st.columns(2,gap='medium')
        with left:
            with st.container(border=True):
                st.subheader(':material/inventory: Inventory health',anchor=False)
                stock=query("SELECT 'Materials' AS category, SUM(CASE WHEN Material_Quantity > Material_Reorder_Level THEN 1 ELSE 0 END) AS healthy, SUM(CASE WHEN Material_Quantity <= Material_Reorder_Level AND Material_Quantity>0 THEN 1 ELSE 0 END) AS low, SUM(CASE WHEN Material_Quantity=0 THEN 1 ELSE 0 END) AS out_of_stock FROM Material UNION ALL SELECT 'Machines' AS category, SUM(CASE WHEN Machine_Quantity > Machine_Reorder_Level THEN 1 ELSE 0 END) AS healthy, SUM(CASE WHEN Machine_Quantity <= Machine_Reorder_Level AND Machine_Quantity>0 THEN 1 ELSE 0 END) AS low, SUM(CASE WHEN Machine_Quantity=0 THEN 1 ELSE 0 END) AS out_of_stock FROM Machine")
                st.altair_chart(stock_chart(pd.DataFrame(stock)),width='stretch')
        with right:
            with st.container(border=True):
                st.subheader(':material/fact_check: Test outcomes',anchor=False)
                tests=query("SELECT Initial_Test_Type test_type, Initial_Test_Result result, COUNT(*) total FROM Initial_Test GROUP BY Initial_Test_Type, Initial_Test_Result")
                if tests: st.altair_chart(test_chart(pd.DataFrame(tests)),width='stretch')
                else: st.caption('No tests recorded yet.')

        try:
            spend=query('SELECT sp.Supplier_Name,COUNT(s.Sourcing_ID) Orders,SUM(s.Sourcing_Quantity * s.Sourcing_Unit_Price) Total_Spend FROM Supplier sp LEFT JOIN Sourcing s ON s.Supplier_ID=sp.Supplier_ID GROUP BY sp.Supplier_ID,sp.Supplier_Name ORDER BY Total_Spend DESC LIMIT 10')
            if spend:
                with st.container(border=True):
                    st.subheader(':material/payments: Sourcing spend by supplier',anchor=False)
                    st.altair_chart(spend_chart(pd.DataFrame(spend)),width='stretch')
        except Exception:
            pass

        st.space('small')
        st.subheader('Needs attention',anchor=False)
        a,b=st.columns(2,gap='medium')

        def attention_card(title, icon, rows, column_config=None, empty='Nothing here right now.'):
            with st.container(border=True):
                head,badge=st.columns([4,1],vertical_alignment='center')
                head.markdown(f'**{icon} {title}**')
                with badge:
                    if rows: st.badge(f'{len(rows)}',icon=':material/warning:',color='orange')
                    else: st.badge('Clear',icon=':material/check_circle:',color='green')
                if rows: show_df(pd.DataFrame(rows),column_config=column_config)
                else: st.caption(empty)

        with a:
            mats=query('SELECT Material_ID,Material_Name,Material_Quantity,Material_Reorder_Level FROM Material WHERE Material_Quantity <= Material_Reorder_Level ORDER BY Material_Quantity')
            attention_card('Materials at or below reorder level',':material/inventory_2:',mats,
                           {'Material_ID':st.column_config.NumberColumn(format='%d',width='small')},'All materials are above their reorder level.')
            machs=query('SELECT Machine_ID,Machine_Name,Machine_Quantity,Machine_Reorder_Level FROM Machine WHERE Machine_Quantity <= Machine_Reorder_Level ORDER BY Machine_Quantity')
            attention_card('Machines at or below reorder level',':material/construction:',machs,
                           {'Machine_ID':st.column_config.NumberColumn(format='%d',width='small')},'All machines are above their reorder level.')
        with b:
            maint=query('SELECT m.Maintenance_ID,mc.Machine_Name,m.Maintenance_Type,m.Maintenance_Next_Due_Date FROM Maintenance m JOIN Machine mc ON mc.Machine_ID=m.Machine_ID WHERE m.Maintenance_Next_Due_Date <= CURDATE() ORDER BY m.Maintenance_Next_Due_Date')
            attention_card('Maintenance due or overdue',':material/build:',maint,
                           {'Maintenance_Next_Due_Date':st.column_config.DateColumn(format='D MMM YYYY')},'No maintenance is due.')
            fails=query("SELECT t.Initial_Test_ID,t.Initial_Test_Type,t.Initial_Test_Date,t.Initial_Test_Notes,e.Employee_Name FROM Initial_Test t JOIN Employee e ON e.Employee_ID=t.Employee_ID WHERE t.Initial_Test_Result='Failed' ORDER BY t.Initial_Test_Date DESC LIMIT 10")
            attention_card('Recent failed tests',':material/cancel:',fails,
                           {'Initial_Test_Date':st.column_config.DatetimeColumn(format='D MMM YYYY')},'No failed tests.')
    except Exception as e: st.error(f'Could not load dashboard: {e}',icon=':material/error:')


def page_table(table):
    cols=st.session_state.db_schema[table]; pk=get_pk(cols); fks=fk_map(st.session_state.db_fks,table)
    page_header('Records',LABELS[table],DESCRIPTIONS.get(table))

    with st.container(border=True):
        s_col,size_col,page_col=st.columns([4,1,1],vertical_alignment='bottom')
        with s_col: search=st.text_input('Search records',placeholder=f'Search {LABELS[table].lower()}...',key=f'search_{table}',icon=':material/search:')
        with size_col: page_size=st.selectbox('Rows per page',[25,50,100,250,500],index=1,key=f'page_size_{table}')
        total=count_records(table,search)
        total_pages=max(1,(total+page_size-1)//page_size)
        with page_col: page=st.number_input('Page',min_value=1,max_value=total_pages,value=1,step=1,key=f'page_number_{table}')
        rows,pk=get_records(table,search,int(page),page_size)
        st.caption(f'{total:,} matching record(s) · page {int(page)} of {total_pages}')
        view=pd.DataFrame(rows)
        if not view.empty: show_df(view,height=min(38+35*len(view),560),column_config={pk:st.column_config.NumberColumn(format='%d',width='small')})
        else: st.info('No records found.',icon=':material/search_off:')

    st.space('small')
    add_tab,edit_tab,delete_tab=st.tabs([':material/add: Add record',':material/edit: Edit record',':material/delete: Delete record'])

    # ADD: this form always creates a brand-new row. It never loads an
    # existing record and never issues UPDATE statements.
    with add_tab:
        st.caption('Creates a new record. Existing records are never changed here.')
        with st.form(f'add_{table}',clear_on_submit=True,border=True):
            skip={c['COLUMN_NAME'] for c in cols if c['COLUMN_NAME']==pk or 'auto_increment' in (c['EXTRA'] or '').lower()}
            # current=None so the form always starts blank or with defaults.
            vals=form_fields(cols,fks,f'add_{table}',current=None,skip=skip)
            create_submitted=st.form_submit_button('Create new record',type='primary',icon=':material/add:')
            if create_submitted:
                missing=[c['COLUMN_NAME'] for c in cols
                         if c['COLUMN_NAME']!=pk
                         and 'auto_increment' not in (c['EXTRA'] or '').lower()
                         and c['IS_NULLABLE']=='NO'
                         and c['COLUMN_DEFAULT'] is None
                         and vals.get(c['COLUMN_NAME']) in (None,'')
                         and c['COLUMN_NAME'] not in HIDDEN_COLUMNS]
                if missing:
                    st.error('Required fields missing: '+', '.join(pretty(m) for m in missing))
                else:
                    try:
                        data={k:v for k,v in vals.items()
                              if v is not None or next(x for x in cols if x['COLUMN_NAME']==k)['IS_NULLABLE']=='YES'}
                        if not data:
                            raise ValueError('There are no values to insert.')
                        names=list(data)
                        insert_sql=(f"INSERT INTO {safe_ident(table)} "
                                    f"({', '.join(safe_ident(x) for x in names)}) "
                                    f"VALUES ({', '.join(['%s']*len(names))})")
                        execute(insert_sql,[data[x] for x in names])
                        st.toast('New record created.',icon=':material/check_circle:')
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f'Create failed: {e}')

    # EDIT: the user must explicitly choose an existing primary key. Only
    # this section issues UPDATE statements, and its WHERE clause targets
    # exactly the selected primary key.
    with edit_tab:
        st.caption('Changes are saved only to the record you pick below.')
        all_ids=query(f'SELECT {safe_ident(pk)} FROM {safe_ident(table)} ORDER BY {safe_ident(pk)} DESC')
        ids=[r[pk] for r in all_ids]
        if ids:
            selected=st.selectbox('Record to edit',ids,format_func=lambda x:f'{pretty(pk)} #{x}',key=f'edit_select_{table}')
            current_rows=query(f'SELECT * FROM {safe_ident(table)} WHERE {safe_ident(pk)}=%s',(selected,))
            if current_rows:
                current=current_rows[0]
                with st.form(f'edit_{table}_{selected}',border=True):
                    st.markdown(f'**Editing {pretty(pk)} #{selected}**')
                    vals=form_fields(cols,fks,f'edit_{table}_{selected}',current=current,skip={pk}|HIDDEN_COLUMNS)
                    save_submitted=st.form_submit_button('Save changes',type='primary',icon=':material/save:')
                    if save_submitted:
                        try:
                            names=list(vals)
                            if not names:
                                raise ValueError('There are no editable fields.')
                            update_sql=(f"UPDATE {safe_ident(table)} SET "
                                        + ', '.join(f'{safe_ident(n)}=%s' for n in names)
                                        + f' WHERE {safe_ident(pk)}=%s')
                            affected=execute(update_sql,[vals[n] for n in names]+[selected])
                            if affected == 0:
                                st.toast('No values changed. The record is the same as before.',icon=':material/info:')
                            else:
                                st.toast(f'{pretty(pk)} #{selected} updated.',icon=':material/check_circle:')
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f'Update failed: {e}')
        else:
            st.info('There are no existing records to edit.',icon=':material/info:')

    with delete_tab:
        if rows:
            with st.container(border=True):
                del_id=st.selectbox('Record to delete',[r[pk] for r in rows],format_func=lambda x:f'{pretty(pk)} #{x}',key=f'del_{table}')
                st.warning('This cannot be undone. MySQL will block the delete if another table still references this record.',icon=':material/warning:')
                confirm=st.checkbox('I understand and want to delete this record',key=f'confirm_{table}')
                if st.button('Delete record',disabled=not confirm,key=f'delete_btn_{table}',icon=':material/delete:'):
                    try:
                        execute(f'DELETE FROM {safe_ident(table)} WHERE {safe_ident(pk)}=%s',(del_id,))
                        st.toast('Record deleted.',icon=':material/check_circle:'); st.cache_data.clear(); st.rerun()
                    except Exception as e: st.error(f'Delete failed: {e}')
        else: st.info('There are no records to delete.',icon=':material/info:')


REPORTS = {
    'Material stock report':(':material/inventory_2:','SELECT Material_ID,Material_Name,Material_Unit_Of_Measure,Material_Quantity,Material_Reorder_Level,CASE WHEN Material_Quantity=0 THEN \'Out of Stock\' WHEN Material_Quantity<=Material_Reorder_Level THEN \'Low Stock\' ELSE \'In Stock\' END AS Calculated_Status FROM Material ORDER BY Material_Name'),
    'Machine stock report':(':material/construction:','SELECT Machine_ID,Machine_Name,Machine_Model,Machine_Serial_Number,Machine_Quantity,Machine_Reorder_Level,CASE WHEN Machine_Quantity=0 THEN \'Out of Stock\' WHEN Machine_Quantity<=Machine_Reorder_Level THEN \'Low Stock\' ELSE \'In Stock\' END AS Calculated_Status FROM Machine ORDER BY Machine_Name'),
    'Supplier sourcing spend':(':material/payments:','SELECT sp.Supplier_Name,COUNT(s.Sourcing_ID) Orders,SUM(s.Sourcing_Quantity * s.Sourcing_Unit_Price) Total_Spend FROM Supplier sp LEFT JOIN Sourcing s ON s.Supplier_ID=sp.Supplier_ID GROUP BY sp.Supplier_ID,sp.Supplier_Name ORDER BY Total_Spend DESC'),
    'Initial test results':(':material/science:','SELECT t.*,e.Employee_Name FROM Initial_Test t JOIN Employee e ON e.Employee_ID=t.Employee_ID ORDER BY t.Initial_Test_Date DESC'),
    'Maintenance schedule':(':material/build:','SELECT m.*,mc.Machine_Name,e.Employee_Name FROM Maintenance m JOIN Machine mc ON mc.Machine_ID=m.Machine_ID JOIN Employee e ON e.Employee_ID=m.Employee_ID ORDER BY m.Maintenance_Next_Due_Date'),
    'Inventory transaction ledger':(':material/swap_horiz:','SELECT it.*,e.Employee_Name,ma.Material_Name,mc.Machine_Name FROM Inventory_Transaction it JOIN Employee e ON e.Employee_ID=it.Employee_ID LEFT JOIN Material ma ON ma.Material_ID=it.Material_ID LEFT JOIN Machine mc ON mc.Machine_ID=it.Machine_ID ORDER BY it.Transaction_Date DESC'),
    'Employee directory':(':material/badge:','SELECT Employee_ID,Employee_Name,Employee_Email,Employee_Phone,Employee_Username,Employee_Account_Status,Employee_Role,Supervisor_ID FROM Employee ORDER BY Employee_Name')}


def page_reports():
    page_header('Reports','Reports & exports','Generate an operational report and download it as CSV.')
    with st.container(border=True):
        pick,go=st.columns([4,1],vertical_alignment='bottom')
        with pick: report=st.selectbox('Report type',list(REPORTS))
        with go:
            if st.button('Generate report',type='primary',icon=':material/play_arrow:',width='stretch'):
                try: st.session_state.report_df=pd.DataFrame(query(REPORTS[report][1])); st.session_state.report_name=report
                except Exception as e: st.error(f'Report failed: {e}')
    if 'report_df' in st.session_state:
        st.space('small')
        df=st.session_state.report_df
        with st.container(border=True):
            head,dl=st.columns([4,1],vertical_alignment='center')
            head.subheader(f'{REPORTS[st.session_state.report_name][0]} {st.session_state.report_name}',anchor=False)
            dl.download_button('Download CSV',df.to_csv(index=False).encode('utf-8-sig'),file_name=st.session_state.report_name.lower().replace(' ','_')+'.csv',mime='text/csv',icon=':material/download:',width='stretch')
            st.caption(f'{len(df):,} row(s) · generated {datetime.now():%d %b %Y, %I:%M %p}')
            if df.empty: st.info('This report has no rows.',icon=':material/info:')
            else: show_df(df)


def connection_error(e):
    page_header('Setup','Connect to your Roosters database')
    with st.container(border=True):
        st.error(str(e),icon=':material/link_off:')
        st.markdown('Create a `.env` file beside `app.py` using the supplied `.env.example`. Confirm the database name shown in Aiven, paste your password locally, then restart the app.')
        st.code('python configure_connection.py\nstreamlit run app.py',language='bash')


def make_page(table):
    def render(): page_table(table)
    render.__name__=f'page_{table.lower()}'
    return st.Page(render,title=LABELS[table],icon=ICONS[table],url_path=table.lower())


def main():
    st.logo(str(BASE_DIR/'assets'/'logo.svg'),size='large',icon_image=str(BASE_DIR/'assets'/'icon.svg'))
    try:
        if 'db_schema' not in st.session_state:
            sch,fks=schema(); st.session_state.db_schema=sch; st.session_state.db_fks=fks
        connected=True
    except Exception as e:
        connected=False; err=e

    if not connected:
        st.sidebar.badge('Disconnected',icon=':material/link_off:',color='red')
        connection_error(err)
        st.stop()

    pages={
        'Dashboard':[st.Page(page_dashboard,title='Overview',icon=':material/dashboard:',default=True)],
        'Inventory':[make_page(t) for t in ['Material','Machine','Inventory_Transaction','Sourcing','Supplier']],
        'Quality & maintenance':[make_page(t) for t in ['Object_Guideline','Initial_Test','Technical_Record','Maintenance']],
        'People':[make_page('Employee')],
        'Reports':[st.Page(page_reports,title='Reports & exports',icon=':material/summarize:',url_path='reports')],
    }
    nav=st.navigation(pages,expanded=True)

    with st.sidebar:
        st.space('small')
        with st.container(border=True):
            st.badge('Connected',icon=':material/cloud_done:',color='green')
            st.caption(f"Database **{setting('DB_NAME','defaultdb')}**")
            if st.button('Refresh data',icon=':material/refresh:',width='stretch'):
                st.cache_data.clear()
                for k in ('db_schema','db_fks'): st.session_state.pop(k,None)
                st.rerun()

    nav.run()
    st.markdown('<div class="rs-footer">Roosters Operations Dashboard · Changes are written directly to the connected MySQL database.</div>',unsafe_allow_html=True)


if __name__=='__main__': main()
