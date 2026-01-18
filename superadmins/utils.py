#superadmins/utils.py
def is_barber(db, tg_id: int) -> bool:
    return bool(db.fetch_one(
        "SELECT 1 FROM barbers WHERE tg_id=%s",
        (tg_id,)
    ))

def get_barber_id(db, tg_id: int) -> int:
    row = db.fetch_one(
        "SELECT id FROM barbers WHERE tg_id=%s",
        (tg_id,)
    )
    return row["id"]
