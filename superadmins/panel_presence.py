import time
from typing import Dict

_BARBER_LAST_SEEN: Dict[int, float] = {}

# Barber panel active deb hisoblanadigan TTL
PRESENCE_TTL = 10 * 60  # 10 daqiqa

def touch_barber(barber_tg_id: int) -> None:
    _BARBER_LAST_SEEN[int(barber_tg_id)] = time.time()

def is_barber_active(barber_tg_id: int) -> bool:
    ts = _BARBER_LAST_SEEN.get(int(barber_tg_id))
    if not ts:
        return False
    return (time.time() - ts) <= PRESENCE_TTL
