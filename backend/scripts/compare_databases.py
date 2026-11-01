"""Prove two PostgreSQL databases hold the same data: per table, the row count and a checksum of every row.

    python scripts/compare_databases.py <source-url> <restored-url>

Exits 1 on any difference. Used by scripts/verify_backup.sh to show that a backup actually restores (an untested backup is a hope, not a backup).
"""

import sys

import psycopg


def _url(u: str) -> str:
    return u.replace("postgresql+psycopg://", "postgresql://")


def fingerprint(url: str) -> dict[str, tuple[int, str]]:
    out = {}
    with psycopg.connect(_url(url)) as conn:
        tables = [r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")]
        for t in tables:
            n, digest = conn.execute(f'SELECT count(*), coalesce(md5(string_agg(x::text, \'|\' ORDER BY x::text)), \'\') FROM "{t}" x').fetchone()
            out[t] = (n, digest)
    return out


def main(argv: list[str]) -> int:
    a, b = fingerprint(argv[1]), fingerprint(argv[2])
    bad = 0
    for t in sorted(set(a) | set(b)):
        same = a.get(t) == b.get(t)
        bad += 0 if same else 1
        if not same or "-v" in argv:
            print(f"{'ok  ' if same else 'DIFF'} {t:28} source={a.get(t, ('missing',))[0]} restored={b.get(t, ('missing',))[0]}")
    rows = sum(n for n, _ in a.values())
    print(f"{len(a)} tables, {rows} rows compared: {'IDENTICAL' if not bad else f'{bad} table(s) differ'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
