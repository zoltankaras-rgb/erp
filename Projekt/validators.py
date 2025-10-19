def validate_required_fields(data: dict, required_fields: list):
    """
    Overí, či všetky povinné polia sú prítomné a nie sú prázdne.
    """
    missing = [f for f in required_fields if not data.get(f)]
    return (len(missing) == 0, missing)

def safe_get_float(value, default=0.0):
    """
    Bezpečne prevedie hodnotu na float, vráti default pri chybe.
    """
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default

def safe_get_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
