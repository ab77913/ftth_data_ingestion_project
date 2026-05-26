import json
from pathlib import Path

CACHE_FILE = Path("cache/cache.json")


def load_cache():

    if not CACHE_FILE.exists():
        return {}

    with open(CACHE_FILE, "r") as f:
        return json.load(f)


def save_cache(cache_data):

    with open(CACHE_FILE, "w") as f:
        json.dump(cache_data, f, indent=2)


def generate_cache_key(canonical):

    return (
        f"{canonical.raw_address}"
        f"{canonical.city}"
        f"{canonical.state}"
        f"{canonical.zip_code}"
    ).replace(" ", "").lower()


def get_cached_result(cache_key):

    cache_data = load_cache()

    return cache_data.get(cache_key)


def save_cached_result(cache_key, result):

    cache_data = load_cache()

    cache_data[cache_key] = result

    save_cache(cache_data)