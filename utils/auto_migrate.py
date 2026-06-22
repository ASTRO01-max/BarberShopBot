# utils/auto_migrate.py
import logging
import re

from sqlalchemy import text

logger = logging.getLogger("auto_migrate")

_SA_TO_UDT = {
    "Integer": "int4",
    "BigInteger": "int8",
    "SmallInteger": "int2",
    "String": "varchar",
    "Text": "text",
    "Boolean": "bool",
    "Date": "date",
    "Time": "time",
    "Float": "float8",
    "JSON": "json",
    "JSONB": "jsonb",
    "Numeric": "numeric",
    "LargeBinary": "bytea",
}


def _sa_udt(sa_type):
    name = type(sa_type).__name__
    if name == "DateTime":
        return "timestamptz" if getattr(sa_type, "timezone", False) else "timestamp"
    return _SA_TO_UDT.get(name, name.lower())


def _compile_type(sa_type, dialect):
    return sa_type.compile(dialect=dialect)


def _compile_server_default(col, dialect):
    sd = col.server_default
    if sd is None:
        return None
    arg = sd.arg
    if hasattr(arg, "compile"):
        return str(arg.compile(dialect=dialect))
    return str(arg)


def _normalize_default(val):
    if val is None:
        return None
    s = re.sub(r"::[a-zA-Z_ \[\]()]+", "", val).strip()
    s = s.strip("'\"")
    return s


async def _get_existing_tables(conn):
    result = await conn.execute(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
    ))
    return {row[0] for row in result.fetchall()}


async def _get_db_columns(conn, table_name):
    result = await conn.execute(text(
        "SELECT column_name, data_type, udt_name, "
        "       character_maximum_length, numeric_precision, numeric_scale, "
        "       is_nullable, column_default "
        "FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = :tbl "
        "ORDER BY ordinal_position"
    ), {"tbl": table_name})

    cols = {}
    for row in result.fetchall():
        cols[row[0]] = {
            "data_type": row[1],
            "udt_name": row[2],
            "max_len": row[3],
            "num_prec": row[4],
            "num_scale": row[5],
            "is_nullable": row[6] == "YES",
            "default": row[7],
        }
    return cols


async def _get_db_indexes(conn, table_name):
    result = await conn.execute(text(
        "SELECT indexname, indexdef FROM pg_indexes "
        "WHERE schemaname = 'public' AND tablename = :tbl"
    ), {"tbl": table_name})
    return {row[0]: row[1] for row in result.fetchall()}


async def _get_db_constraints(conn, table_name):
    fk_result = await conn.execute(text("""
        SELECT
            tc.constraint_name,
            kcu.column_name,
            ccu.table_name  AS ref_table,
            ccu.column_name AS ref_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
        WHERE tc.table_schema = 'public'
          AND tc.table_name = :tbl
          AND tc.constraint_type = 'FOREIGN KEY'
    """), {"tbl": table_name})

    constraints = {}
    for row in fk_result.fetchall():
        constraints[row[0]] = {
            "type": "FOREIGN KEY",
            "column": row[1],
            "ref_table": row[2],
            "ref_column": row[3],
        }

    uq_result = await conn.execute(text("""
        SELECT tc.constraint_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = 'public'
          AND tc.table_name = :tbl
          AND tc.constraint_type = 'UNIQUE'
    """), {"tbl": table_name})

    uq_groups = {}
    for row in uq_result.fetchall():
        uq_groups.setdefault(row[0], []).append(row[1])

    for cname, cols in uq_groups.items():
        constraints[cname] = {"type": "UNIQUE", "columns": sorted(cols)}

    return constraints


async def _add_column(conn, table_name, col, dialect):
    type_ddl = _compile_type(col.type, dialect)

    parts = [f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{col.name}" {type_ddl}']

    sd_compiled = _compile_server_default(col, dialect)
    if sd_compiled is not None:
        parts.append(f"DEFAULT {sd_compiled}")

    if not col.nullable and sd_compiled is not None:
        parts.append("NOT NULL")

    sql = " ".join(parts)
    await conn.execute(text(sql))
    logger.info("  ✅ Ustun qo'shildi: %s.%s  (%s)", table_name, col.name, type_ddl)

    if not col.nullable and sd_compiled is None and not col.primary_key:
        logger.warning(
            "  ⚠️  %s.%s NOT NULL bo'lishi kerak, lekin default yo'q. "
            "Jadvalda ma'lumot bo'lsa, qo'lda NOT NULL qo'ying!",
            table_name, col.name,
        )


async def _alter_column_type(conn, table_name, col_name, new_type_ddl):
    sql = (
        f'ALTER TABLE "{table_name}" '
        f'ALTER COLUMN "{col_name}" TYPE {new_type_ddl} '
        f'USING "{col_name}"::{new_type_ddl}'
    )
    nested = await conn.begin_nested()
    try:
        await conn.execute(text(sql))
        await nested.commit()
        logger.info("  🔄 Tur o'zgartirildi: %s.%s → %s", table_name, col_name, new_type_ddl)
    except Exception as exc:
        await nested.rollback()
        logger.error(
            "  ❌ Tur o'zgartirib bo'lmadi: %s.%s → %s | Xato: %s",
            table_name, col_name, new_type_ddl, exc,
        )


async def _alter_nullable(conn, table_name, col_name, nullable):
    action = "DROP NOT NULL" if nullable else "SET NOT NULL"
    sql = f'ALTER TABLE "{table_name}" ALTER COLUMN "{col_name}" {action}'
    nested = await conn.begin_nested()
    try:
        await conn.execute(text(sql))
        await nested.commit()
        logger.info("  🔄 Nullable o'zgartirildi: %s.%s → %s", table_name, col_name, action)
    except Exception as exc:
        await nested.rollback()
        logger.error(
            "  ❌ Nullable o'zgartirib bo'lmadi: %s.%s | Xato: %s",
            table_name, col_name, exc,
        )


async def _set_default(conn, table_name, col_name, default_expr):
    sql = f'ALTER TABLE "{table_name}" ALTER COLUMN "{col_name}" SET DEFAULT {default_expr}'
    await conn.execute(text(sql))
    logger.info("  🔄 Default o'zgartirildi: %s.%s → %s", table_name, col_name, default_expr)


async def _drop_default(conn, table_name, col_name):
    sql = f'ALTER TABLE "{table_name}" ALTER COLUMN "{col_name}" DROP DEFAULT'
    await conn.execute(text(sql))
    logger.info("  🔄 Default olib tashlandi: %s.%s", table_name, col_name)


async def _drop_column(conn, table_name, col_name):
    sql = f'ALTER TABLE "{table_name}" DROP COLUMN IF EXISTS "{col_name}" CASCADE'
    await conn.execute(text(sql))
    logger.info("  🗑️  Ustun o'chirildi: %s.%s", table_name, col_name)



async def _sync_column(conn, table_name, model_col, db_col_info, dialect):
    col_name = model_col.name

    model_udt = _sa_udt(model_col.type)
    db_udt = db_col_info["udt_name"]

    type_changed = model_udt != db_udt

    if not type_changed and model_udt == "varchar":
        model_len = getattr(model_col.type, "length", None)
        db_len = db_col_info["max_len"]
        if model_len is not None and db_len is not None and model_len != db_len:
            type_changed = True

    if not type_changed and model_udt == "numeric":
        m_prec = getattr(model_col.type, "precision", None)
        m_scale = getattr(model_col.type, "scale", None)
        if m_prec is not None and m_prec != db_col_info["num_prec"]:
            type_changed = True
        if m_scale is not None and m_scale != db_col_info["num_scale"]:
            type_changed = True

    if type_changed:
        new_type_ddl = _compile_type(model_col.type, dialect)
        await _alter_column_type(conn, table_name, col_name, new_type_ddl)

    model_nullable = model_col.nullable if model_col.nullable is not None else True
    if model_col.primary_key:
        model_nullable = False

    db_nullable = db_col_info["is_nullable"]

    if model_nullable != db_nullable:
        await _alter_nullable(conn, table_name, col_name, model_nullable)

    db_default = db_col_info["default"]
    is_sequence = db_default and "nextval(" in str(db_default)

    if is_sequence:
        return

    model_default = _compile_server_default(model_col, dialect)

    if model_default is not None and db_default is None:
        await _set_default(conn, table_name, col_name, model_default)
    elif model_default is None and db_default is not None:
        await _drop_default(conn, table_name, col_name)
    elif model_default is not None and db_default is not None:
        norm_model = _normalize_default(model_default)
        norm_db = _normalize_default(db_default)
        if norm_model != norm_db:
            await _set_default(conn, table_name, col_name, model_default)


async def _sync_indexes(conn, table_name, table, db_indexes):
    """Modelda belgilangan indekslarni bazaga qo'shish."""
    for col in table.columns:
        if not col.index:
            continue
        # Primary key indeksini o'tkazib yuboramiz
        if col.primary_key:
            continue

        idx_name = f"ix_{table_name}_{col.name}"

        # Mavjud indekslar orasida tekshirish (nom yoki ustun bo'yicha)
        already_exists = False
        for existing_name, existing_def in db_indexes.items():
            if idx_name == existing_name:
                already_exists = True
                break
            # Indeks definitionda ustun nomi borligini tekshirish
            if f"({col.name})" in existing_def or f'("{col.name}")' in existing_def:
                already_exists = True
                break

        if not already_exists:
            sql = f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON "{table_name}" ("{col.name}")'
            nested = await conn.begin_nested()
            try:
                await conn.execute(text(sql))
                await nested.commit()
                logger.info("  📇 Indeks yaratildi: %s → %s", table_name, idx_name)
            except Exception as exc:
                await nested.rollback()
                logger.error("  ❌ Indeks yaratib bo'lmadi: %s | Xato: %s", idx_name, exc)


# ────────────────────────────────────────────────────────────
# Foreign Key larni sinxronlash
# ────────────────────────────────────────────────────────────

async def _sync_foreign_keys(conn, table_name, table, db_constraints):
    """Modelda belgilangan foreign keylarni bazaga qo'shish."""
    for fkc in table.foreign_key_constraints:
        # FK ustunlari va referenslar
        fk_cols = [col.name for col in fkc.columns]
        ref_cols = [elem.column.name for elem in fkc.elements]
        ref_table = list(fkc.elements)[0].column.table.name

        # Constraint nomi
        fk_name = fkc.name or f"fk_{table_name}_{'_'.join(fk_cols)}"

        # Bazada mavjudligini tekshirish
        already_exists = False
        for cname, cinfo in db_constraints.items():
            if cinfo["type"] != "FOREIGN KEY":
                continue
            if cinfo["column"] in fk_cols and cinfo["ref_table"] == ref_table:
                already_exists = True
                break

        if not already_exists:
            cols_str = ", ".join(f'"{c}"' for c in fk_cols)
            ref_cols_str = ", ".join(f'"{c}"' for c in ref_cols)
            on_delete = ""
            if fkc.ondelete:
                on_delete = f" ON DELETE {fkc.ondelete}"

            sql = (
                f'ALTER TABLE "{table_name}" '
                f'ADD CONSTRAINT "{fk_name}" '
                f'FOREIGN KEY ({cols_str}) REFERENCES "{ref_table}" ({ref_cols_str}){on_delete}'
            )
            nested = await conn.begin_nested()
            try:
                await conn.execute(text(sql))
                await nested.commit()
                logger.info("  🔗 FK qo'shildi: %s.%s → %s.%s", table_name, fk_cols, ref_table, ref_cols)
            except Exception as exc:
                await nested.rollback()
                logger.error("  ❌ FK qo'shib bo'lmadi: %s | Xato: %s", fk_name, exc)


# ────────────────────────────────────────────────────────────
# Unique Constraint larni sinxronlash
# ────────────────────────────────────────────────────────────

async def _sync_unique_constraints(conn, table_name, table, db_constraints):
    """Modelda belgilangan unique constraintlarni bazaga qo'shish."""
    # __table_args__ dagi UniqueConstraint lar
    for constraint in table.constraints:
        from sqlalchemy import UniqueConstraint
        if not isinstance(constraint, UniqueConstraint):
            continue

        uq_cols = sorted([col.name for col in constraint.columns])
        if not uq_cols:
            continue

        uq_name = constraint.name or f"uq_{table_name}_{'_'.join(uq_cols)}"

        # Bazada mavjudligini tekshirish
        already_exists = False
        for cname, cinfo in db_constraints.items():
            if cinfo["type"] != "UNIQUE":
                continue
            if sorted(cinfo.get("columns", [])) == uq_cols:
                already_exists = True
                break

        if not already_exists:
            cols_str = ", ".join(f'"{c}"' for c in uq_cols)
            sql = f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{uq_name}" UNIQUE ({cols_str})'
            nested = await conn.begin_nested()
            try:
                await conn.execute(text(sql))
                await nested.commit()
                logger.info("  🔒 Unique qo'shildi: %s → %s (%s)", table_name, uq_name, uq_cols)
            except Exception as exc:
                await nested.rollback()
                logger.error("  ❌ Unique qo'shib bo'lmadi: %s | Xato: %s", uq_name, exc)

    # Ustun darajasida unique=True belgilangan ustunlar
    for col in table.columns:
        if not col.unique:
            continue
        if col.primary_key:
            continue

        uq_name = f"{table_name}_{col.name}_key"

        already_exists = False
        for cname, cinfo in db_constraints.items():
            if cinfo["type"] != "UNIQUE":
                continue
            if cinfo.get("columns") == [col.name]:
                already_exists = True
                break

        if not already_exists:
            sql = (
                f'ALTER TABLE "{table_name}" '
                f'ADD CONSTRAINT "{uq_name}" UNIQUE ("{col.name}")'
            )
            nested = await conn.begin_nested()
            try:
                await conn.execute(text(sql))
                await nested.commit()
                logger.info("  🔒 Unique qo'shildi: %s.%s", table_name, col.name)
            except Exception as exc:
                await nested.rollback()
                # Balki indeks sifatida mavjud
                if "already exists" not in str(exc).lower():
                    logger.error("  ❌ Unique qo'shib bo'lmadi: %s.%s | Xato: %s", table_name, col.name, exc)


# ────────────────────────────────────────────────────────────
# ASOSIY FUNKSIYA
# ────────────────────────────────────────────────────────────

async def auto_migrate(conn, metadata, *, drop_columns=False):
    """
    SQLAlchemy modellarini PostgreSQL bazasi bilan sinxronlashtirish.

    Bot ishga tushganda chaqiriladi. Barcha jadvallarni tekshirib,
    kerakli o'zgarishlarni avtomatik qo'llaydi.

    Args:
        conn:          AsyncConnection (engine.begin() ichida)
        metadata:      Base.metadata — barcha model jadvallar
        drop_columns:  True bo'lsa, modelda yo'q ustunlar bazadan o'chiriladi.
                       Default False — xavfsizlik uchun faqat log yoziladi.
    """
    dialect = conn.dialect
    existing_tables = await _get_existing_tables(conn)
    model_tables = metadata.tables

    logger.info("=" * 60)
    logger.info("🔄 AUTO-MIGRATE boshlandi")
    logger.info("   Model jadvallari: %d | Bazadagi jadvallar: %d",
                len(model_tables), len(existing_tables))
    logger.info("=" * 60)

    changes_count = 0

    # ── 1) MODELDA YO'Q BO'LGAN JADVALLARNI O'CHIRISH (DROP TABLE) ──
    for db_table_name in existing_tables:
        if db_table_name not in model_tables:
            logger.info("🗑️  [%s] — modelda yo'q jadval. Bazadan o'chirilmoqda...", db_table_name)
            sql = f'DROP TABLE IF EXISTS "{db_table_name}" CASCADE'
            try:
                await conn.execute(text(sql))
                logger.info("  ✅ Jadval o'chirildi: %s", db_table_name)
                changes_count += 1
            except Exception as exc:
                logger.error("  ❌ Jadvalni o'chirib bo'lmadi: %s | Xato: %s", db_table_name, exc)

    # ── 2) JADVALLARNI YARATISH VA SINXRONLASH ──
    for table_name, table in model_tables.items():

        # Yangi jadval — bazada yo'q bo'lsa yaratamiz
        if table_name not in existing_tables:
            logger.info("📋 [%s] — yangi jadval. Bazada yaratilmoqda...", table_name)
            try:
                await conn.run_sync(table.create)
                logger.info("  ✅ Jadval yaratildi: %s", table_name)
                changes_count += 1
            except Exception as exc:
                logger.error("  ❌ Jadvalni yaratib bo'lmadi: %s | Xato: %s", table_name, exc)
            continue

        logger.info("📋 [%s] tekshirilmoqda...", table_name)

        # ── Bazadagi ma'lumotlarni olish ──
        db_columns = await _get_db_columns(conn, table_name)
        db_indexes = await _get_db_indexes(conn, table_name)
        db_constraints = await _get_db_constraints(conn, table_name)

        model_columns = {col.name: col for col in table.columns}

        # ── 1) YANGI USTUNLAR QO'SHISH ──
        for col_name, col in model_columns.items():
            if col_name not in db_columns:
                await _add_column(conn, table_name, col, dialect)
                changes_count += 1

        # ── 2) ORTIQCHA USTUNLARNI BOSHQARISH ──
        for col_name in db_columns:
            if col_name not in model_columns:
                if drop_columns:
                    await _drop_column(conn, table_name, col_name)
                    changes_count += 1
                else:
                    logger.warning(
                        "  ⚠️  Ortiqcha ustun: %s.%s — modelda yo'q "
                        "(drop_columns=True qo'ying o'chirish uchun)",
                        table_name, col_name,
                    )

        # ── 3) MAVJUD USTUNLARNI SINXRONLASH (tur, nullable, default) ──
        for col_name, col in model_columns.items():
            if col_name in db_columns:
                await _sync_column(conn, table_name, col, db_columns[col_name], dialect)

        # ── 4) INDEKSLAR ──
        await _sync_indexes(conn, table_name, table, db_indexes)

        # ── 5) FOREIGN KEYS ──
        await _sync_foreign_keys(conn, table_name, table, db_constraints)

        # ── 6) UNIQUE CONSTRAINTS ──
        await _sync_unique_constraints(conn, table_name, table, db_constraints)

    logger.info("=" * 60)
    logger.info("✅ AUTO-MIGRATE tugadi. O'zgarishlar soni: %d", changes_count)
    logger.info("=" * 60)
