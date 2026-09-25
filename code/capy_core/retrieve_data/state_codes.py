"""State codes used in raw-data requests, with coverage specific to each source."""

# fmt: off
# The 50 states, District of Columbia (11), and Puerto Rico (72).
STATE_FIPS_CODES: tuple[str, ...] = (
    "01", "02", "04", "05", "06", "08", "09", "10", "11", "12", "13", "15",
    "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27",
    "28", "29", "30", "31", "32", "33", "34", "35", "36", "37", "38", "39",
    "40", "41", "42", "44", "45", "46", "47", "48", "49", "50", "51", "53",
    "54", "55", "56", "72",
)
# fmt: on


# The original 1980 STF1A archives cover the 50 states and DC, without Puerto Rico.
# fmt: off
STF1A_STATE_ABBREVIATIONS = (
    "ak", "al", "ar", "az", "ca", "co", "ct", "dc", "de", "fl", "ga", "hi", "ia",
    "id", "il", "in", "ks", "ky", "la", "ma", "md", "me", "mi", "mn", "mo", "ms",
    "mt", "nc", "nd", "ne", "nh", "nj", "nm", "nv", "ny", "oh", "ok", "or", "pa",
    "ri", "sc", "sd", "tn", "tx", "ut", "va", "vt", "wa", "wi", "wv", "wy",
)
# fmt: on
