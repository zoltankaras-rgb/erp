# projekt/hygiene_handler.py
# ==============================================================
# HYGIENA / HACCP – robustný handler (adaptívny podľa názvov stĺpcov)
# ==============================================================

from logger import logger
import db_connector
from datetime import datetime, date, timedelta

# ----------------------- Pomocné mapovanie stĺpcov -----------------------

def _cols(table):
    """Vráti set názvov stĺpcov v tabuľke (lower->origin)."""
    rows = db_connector.execute_query(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
        (table,)
    ) or []
    m = {}
    for r in rows:
        name = r["COLUMN_NAME"]
        m[name.lower()] = name
    return m

def _map_task_cols():
    """
    Zistí, ako sa skutočne volajú stĺpce v hygiene_tasks.
    Vracia dict s kľúčmi: task_name, location, frequency, description,
    default_agent_id, default_concentration, default_exposure_time, is_active
    (niečo môže byť None → použije sa default/NULL/alias).
    """
    cols = _cols('hygiene_tasks')
    alias = {}

    def pick(*cands):
        for c in cands:
            if c.lower() in cols:
                return cols[c.lower()]
        return None

    alias['task_name']            = pick('task_name', 'name', 'nazov', 'uloha', 'uloha_nazov')
    alias['location']             = pick('location', 'lokacia', 'miesto', 'area', 'room', 'prevadzka')
    alias['frequency']            = pick('frequency', 'frekvencia')
    alias['description']          = pick('description', 'popis', 'note')
    alias['default_agent_id']     = pick('default_agent_id', 'agent_id', 'default_agent')
    alias['default_concentration']= pick('default_concentration', 'koncentracia', 'koncentracia_default')
    alias['default_exposure_time']= pick('default_exposure_time', 'exposure_time', 'cas_posobenia', 'cas_default')
    alias['is_active']            = pick('is_active', 'active', 'enabled', 'stav')
    return alias

# ----------------------- PLAN / VIEW -----------------------

def get_hygiene_plan_for_date(date=None, **kwargs):
    """
    Vráti plán úloh pre daný dátum s priradenými časmi z hygiene_log (ak existujú).
    Adaptívne voči názvom stĺpcov v hygiene_tasks.
    """
    if not date:
        return {"error": "Chýba dátum."}

    tmap = _map_task_cols()
    task_name_col = tmap['task_name'] or "''"
    location_col  = tmap['location']  or "''"
    default_agent = tmap['default_agent_id']

    # SELECT list – aliasuj na canonical mená
    select_parts = [
        "ht.id AS task_id",
        f"{task_name_col} AS task_name",
        f"{location_col}  AS location",
    ]

    # predvolený prostriedok – buď join alebo NULL
    join_agents = ""
    if default_agent:
        select_parts.append("ha.agent_name AS agent_name")
        join_agents = f"LEFT JOIN hygiene_agents ha ON ht.{default_agent} = ha.id"
    else:
        select_parts.append("NULL AS agent_name")

    # defaultné parametre (nevadí, ak sú None – vrátime prázdne)
    if tmap['default_concentration']:
        select_parts.append(f"ht.{tmap['default_concentration']} AS default_concentration")
    else:
        select_parts.append("NULL AS default_concentration")
    if tmap['default_exposure_time']:
        select_parts.append(f"ht.{tmap['default_exposure_time']} AS default_exposure_time")
    else:
        select_parts.append("NULL AS default_exposure_time")

    # log stĺpce
    select_parts.extend([
        "hl.id AS log_id",
        "hl.start_time",
        "hl.exposure_end",
        "hl.rinse_end",
        "hl.end_time",
        "hl.performed_by"
    ])

    # ORDER BY – preferuj location, task_name; inak id
    order_by = []
    if tmap['location']:
        order_by.append(f"ht.{tmap['location']}")
    if tmap['task_name']:
        order_by.append(f"ht.{tmap['task_name']}")
    if not order_by:
        order_by.append("ht.id")

    query = f"""
        SELECT
            {", ".join(select_parts)}
        FROM hygiene_tasks ht
        {join_agents}
        LEFT JOIN hygiene_log hl
            ON hl.task_id = ht.id AND hl.plan_date = %s
        WHERE COALESCE(ht.{tmap['is_active'] or 'id'} IS NOT NULL, TRUE) -- filter nič nespôsobí ak is_active nemáš
            {"AND ht."+tmap['is_active']+"=1" if tmap['is_active'] else ""}
        ORDER BY {", ".join(order_by)}
    """

    tasks = db_connector.execute_query(query, (date,), fetch="all")
    return {"planDate": date, "tasks": tasks or []}

# ----------------------- AGENTS -----------------------
def get_hygiene_agents(**kwargs):
    return db_connector.execute_query(
        "SELECT id, agent_name, is_active FROM hygiene_agents WHERE is_active=1 ORDER BY agent_name",
        fetch='all'
    )

def save_hygiene_agent(id=None, agent_name=None, **kwargs):
    if not (id or agent_name):
        return {"error": "Chýbajú údaje (id alebo agent_name)."}
    if id:
        db_connector.execute_query(
            "UPDATE hygiene_agents SET agent_name=%s WHERE id=%s",
            (agent_name, id), fetch='none'
        )
        return {"message": "Prostriedok bol aktualizovaný"}
    else:
        new_id = db_connector.execute_query(
            "INSERT INTO hygiene_agents (agent_name, is_active) VALUES (%s,1)",
            (agent_name,), fetch='lastrowid'
        )
        return {"message": "Prostriedok bol pridaný", "id": new_id}

# ----------------------- TASKS -----------------------

def get_all_hygiene_tasks(**kwargs):
    tmap = _map_task_cols()
    task_name_col = tmap['task_name'] or "''"
    location_col  = tmap['location']  or "''"
    frequency_col = tmap['frequency'] or "NULL"
    is_active_col = tmap['is_active'] or "NULL"
    desc_col      = tmap['description'] or "NULL"

    order_by = []
    if tmap['location']:
        order_by.append(f"ht.{tmap['location']}")
    if tmap['task_name']:
        order_by.append(f"ht.{tmap['task_name']}")
    if not order_by:
        order_by.append("ht.id")

    query = f"""
        SELECT
            ht.id,
            {task_name_col} AS task_name,
            {location_col}  AS location,
            {frequency_col} AS frequency,
            {is_active_col} AS is_active,
            {desc_col}      AS description,
            {"ht."+tmap['default_agent_id'] if tmap['default_agent_id'] else "NULL"} AS default_agent_id,
            {"ht."+tmap['default_concentration'] if tmap['default_concentration'] else "NULL"} AS default_concentration,
            {"ht."+tmap['default_exposure_time'] if tmap['default_exposure_time'] else "NULL"} AS default_exposure_time
        FROM hygiene_tasks ht
        ORDER BY {", ".join(order_by)}
    """
    return db_connector.execute_query(query, fetch='all')

def save_hygiene_task(id=None, task_name=None, location=None, frequency=None,
                      description=None, default_agent_id=None,
                      default_concentration=None, default_exposure_time=None,
                      is_active=True, **kwargs):
    """
    Uloží úlohu – ADAPTÍVNE podľa dostupných stĺpcov v hygiene_tasks.
    - Zistí reálne názvy (nazov/miesto/stav/…).
    - Doplní aj povinné NOT NULL stĺpce bez defaultu (napr. plan_datum).
    """
    # mapovanie "logických" mien -> reálne stĺpce podľa tvojej tabuľky
    tmap = _map_task_cols()
    cols_present = _cols('hygiene_tasks')            # {lower_name: OriginalName}

    # načítaj metadáta tabuľky (typy + (ne)null + default)
    meta_rows = db_connector.execute_query(
        "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA, COLUMN_TYPE "
        "FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'hygiene_tasks'"
    ) or []
    meta = { r['COLUMN_NAME']: r for r in meta_rows }
    meta_lower = { k.lower(): v for k,v in meta.items() }  # jednoduchší lookup

    fields = []   # zhromažďujeme (column, value) len pre existujúce stĺpce

    def add(logical, value):
        col = tmap.get(logical)
        if col and col.lower() in cols_present:
            fields.append((col, value))

    # 1) naplň štandardné polia (ak existujú)
    add('task_name', task_name)
    add('location',  location)
    add('frequency', frequency)
    add('description', description)
    add('default_agent_id', default_agent_id or None)
    add('default_concentration', default_concentration)
    add('default_exposure_time', default_exposure_time)
    if tmap['is_active'] and tmap['is_active'].lower() in cols_present:
        ia = 1 if (is_active in (True, 'true', 'True', '1', 1)) else 0
        fields.append((tmap['is_active'], ia))

    # 2) Doplníme POVINNÉ stĺpce bez defaultu (NOT NULL & COLUMN_DEFAULT IS NULL & nie auto_increment)
    provided_lowers = { c.lower() for c,_ in fields }
    for lower_name, col_name in cols_present.items():
        m = meta_lower.get(lower_name) or {}
        if not m: 
            continue
        if lower_name in provided_lowers:
            # už budeme mať hodnotu – ale ak je None a stĺpec je NOT NULL, doplníme default
            pass

        is_not_null = (m.get('IS_NULLABLE') == 'NO')
        has_no_default = (m.get('COLUMN_DEFAULT') is None)
        is_auto = ('auto_increment' in (m.get('EXTRA') or '').lower())
        if not (is_not_null and has_no_default and not is_auto):
            continue  # nič dopĺňať

        if lower_name in provided_lowers:
            # ak už je v fields, ale hodnota je None → nahradíme defaultom
            for i,(c,v) in enumerate(fields):
                if c.lower() == lower_name and (v is None or v == ''):
                    fields[i] = (c, _default_for_type(m))
            continue

        # povinný stĺpec nemáme vôbec → doplň ho
        fields.append((col_name, _default_for_type(m)))

    if not fields:
        return {"error": "V tabuľke hygiene_tasks neexistujú očakávané stĺpce pre uloženie."}

    if id:
        set_clause = ", ".join(f"{c}=%s" for c,_ in fields)
        params = [v for _,v in fields] + [id]
        db_connector.execute_query(
            f"UPDATE hygiene_tasks SET {set_clause}, updated_at=NOW() WHERE id=%s",
            tuple(params), fetch='none'
        )
        return {"message": "Úloha bola aktualizovaná"}
    else:
        columns = ", ".join(c for c,_ in fields)
        ph      = ", ".join(["%s"]*len(fields))
        params  = [v for _,v in fields]
        new_id = db_connector.execute_query(
            f"INSERT INTO hygiene_tasks ({columns}) VALUES ({ph})",
            tuple(params), fetch='lastrowid'
        )
        return {"message": "Úloha bola pridaná", "id": new_id}


def _default_for_type(col_meta):
    """
    Vygeneruje bezpečný default pre potrebný (NOT NULL, bez defaultu) stĺpec.
    Pokrýva: date/datetime/timestamp/time, čísla, texty, enum.
    """
    from datetime import datetime, date as ddate
    dtype = (col_meta.get('DATA_TYPE') or '').lower()
    ctype = (col_meta.get('COLUMN_TYPE') or '').lower()

    if dtype == 'date':
        return ddate.today().isoformat()
    if dtype in ('datetime','timestamp'):
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if dtype == 'time':
        return '00:00:00'
    if dtype in ('int','bigint','decimal','float','double','tinyint','smallint','mediumint'):
        return 0
    if dtype == 'enum':
        # vytiahni prvú enum hodnotu z COLUMN_TYPE, napr. enum('denne','tyzdenne',...)
        try:
            inside = ctype.split('enum(')[1].rsplit(')',1)[0]
            first = inside.split(',',1)[0].strip().strip("'").strip('"')
            return first or ''
        except Exception:
            return ''
    # varchar/text/others
    return ''


# ----------------------- OPERATIONS LOG -----------------------

def _norm_start_time(start_time_str):
    now = datetime.now()
    if start_time_str:
        try:
            h, m = map(int, start_time_str.split(":"))
            return now.replace(hour=h, minute=m, second=0, microsecond=0)
        except Exception:
            return now
    return now

def log_hygiene_start(task_id=None, start_time_str=None, **kwargs):
    if not task_id:
        return {"error": "Chýba task_id."}
    start_time = _norm_start_time(start_time_str)
    exposure_end = start_time + timedelta(minutes=10)
    rinse_end    = start_time + timedelta(minutes=20)

    db_connector.execute_query(
        """INSERT INTO hygiene_log (task_id, plan_date, start_time, exposure_end, rinse_end)
           VALUES (%s,%s,%s,%s,%s)""",
        (int(task_id), start_time.date(), start_time, exposure_end, rinse_end),
        fetch='none'
    )
    return {
        "message": "Začiatok sanitácie uložený",
        "start_time": start_time.isoformat(),
        "exposure_end": exposure_end.isoformat(),
        "rinse_end": rinse_end.isoformat()
    }

def log_hygiene_finish(task_id=None, performed_by=None, **kwargs):
    if not task_id:
        return {"error": "Chýba task_id."}
    end_time = datetime.now()
    db_connector.execute_query(
        """UPDATE hygiene_log
             SET end_time=%s, performed_by=%s
           WHERE task_id=%s AND end_time IS NULL
           ORDER BY id DESC LIMIT 1""",
        (end_time, performed_by, int(task_id)), fetch='none'
    )
    return {"message": "Ukončenie sanitácie uložené", "end_time": end_time.isoformat()}

def log_hygiene_completion(data=None, **kwargs):
    # prijmi buď data dict alebo kwargs a zmerguj (kwargs -> prednosť má 'data')
    data = {**kwargs, **(data or {})}
    task_id = data.get('task_id')
    completion_date = data.get('completion_date')
    performer_name  = data.get('performer_name')

    if not all([task_id, completion_date, performer_name]):
        return {"error": "Chýbajú povinné údaje (task_id/completion_date/performer_name)."}

    exists = db_connector.execute_query(
        "SELECT id FROM hygiene_log WHERE task_id=%s AND plan_date=%s ORDER BY id DESC LIMIT 1",
        (int(task_id), completion_date), fetch='one'
    )
    if exists:
        db_connector.execute_query(
            """UPDATE hygiene_log
               SET agent_id=%s, concentration=%s, exposure_time=%s, notes=%s,
                   performed_by=%s, end_time=IFNULL(end_time, NOW())
               WHERE id=%s""",
            (
                data.get('agent_id') or None,
                data.get('concentration'),
                data.get('exposure_time'),
                data.get('notes', ''),
                performer_name,
                exists['id']
            ),
            fetch='none'
        )
    else:
        db_connector.execute_query(
            """INSERT INTO hygiene_log
               (task_id, plan_date, performed_by, end_time, agent_id, concentration, exposure_time, notes)
               VALUES (%s,%s,%s,NOW(),%s,%s,%s,%s)""",
            (
                int(task_id), completion_date, performer_name,
                data.get('agent_id') or None,
                data.get('concentration'),
                data.get('exposure_time'),
                data.get('notes', '')
            ),
            fetch='none'
        )
    return {"message": "Úloha bola zaznamenaná ako splnená."}

def check_hygiene_log(data=None, **kwargs):
    """Zaznamená kontrolu vykonanej úlohy."""
    data = {**kwargs, **(data or {})}
    log_id = data.get('log_id')
    user   = data.get('user') or {}

    if not log_id:
        return {"error": "Chýba log_id."}
    db_connector.execute_query(
        "UPDATE hygiene_log SET checked_by_fullname=%s, checked_at=%s WHERE id=%s",
        (user.get('full_name') or 'Kontrolór', datetime.now(), int(log_id)),
        fetch='none'
    )
    return {"message": "Úloha skontrolovaná."}

# ----------------------- REPORT -----------------------

def get_hygiene_report_data(date=None, period='denne', task=None, agent_id=None, **kwargs):
    """
    Adaptívny HYGIENE report:
      - stĺpce (Úloha, Miesto, Začiatok, Koniec pôsobenia, Koniec oplachu, Ukončené, Pracovník, Prípravok, Koncentrácia, Čas pôsobenia, Poznámka, Kontroloval, Kontrolované)
      - filtre: task (LIKE podľa názvu úlohy), agent_id (presný ID prípravku)
      - názvy stĺpcov v hygiene_tasks (task_name/location/...) zisťuje dynamicky podľa tvojej schémy
    """
    if not date:
        return None
    try:
        base_date = datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        return None

    # rozsah dátumov
    if period == 'tyzdenne':
        start_date = base_date - timedelta(days=base_date.weekday())
        end_date   = start_date + timedelta(days=4)
        title = f"Týždenný Záznam o Vykonaní Sanitácie ({start_date.strftime('%d.%m.')} - {end_date.strftime('%d.%m.%Y')})"
    elif period == 'mesacne':
        start_date = base_date.replace(day=1)
        end_date   = (start_date + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        title = f"Mesačný Záznam o Vykonaní Sanitácie ({start_date.strftime('%m/%Y')})"
    else:
        start_date = end_date = base_date
        title = f"Denný Záznam o Vykonaní Sanitácie ({start_date.strftime('%d.%m.%Y')})"

    # zisti reálne stĺpce v hygiene_tasks
    ht_cols = _cols('hygiene_tasks')  # {lower: OriginalName}

    def expr_for(candidates):
        present = [f"ht.{ht_cols[c]}" for c in candidates if c in ht_cols]
        return f"COALESCE({', '.join(present)}, '')" if present else "''"

    task_name_expr = expr_for(['task_name','name','nazov','uloha','uloha_nazov'])
    location_expr  = expr_for(['location','lokacia','miesto','area','room','prevadzka'])

    # where + params
    where = ["hl.plan_date BETWEEN %s AND %s"]
    params = [start_date, end_date]

    if task:
        where.append(f"{task_name_expr} LIKE %s")
        params.append(f"%{task}%")

    if agent_id:
        try:
            where.append("hl.agent_id = %s")
            params.append(int(agent_id))
        except Exception:
            pass  # ignoruj nečíselné agent_id

    query = f"""
      SELECT 
        {task_name_expr} AS task_name,
        {location_expr}  AS location,
        hl.start_time,
        hl.exposure_end,
        hl.rinse_end,
        hl.end_time,
        hl.performed_by,
        ha.agent_name,
        hl.concentration,
        hl.exposure_time,
        hl.notes,
        hl.checked_by_fullname,
        hl.checked_at
      FROM hygiene_log hl
      JOIN hygiene_tasks ht ON hl.task_id = ht.id
      LEFT JOIN hygiene_agents ha ON hl.agent_id = ha.id
      WHERE {' AND '.join(where)}
      ORDER BY hl.plan_date, task_name, location, hl.start_time
    """
    records = db_connector.execute_query(query, tuple(params), fetch='all')
    return {
        "records": records or [],
        "title": title,
        "period_str": f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}",
        "filters": {"task": task or "", "agent_id": agent_id or ""}
    }
