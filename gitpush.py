import subprocess

def gitpush():
    # ── Get status of all changed/new/deleted files ──
    result = subprocess.run(
        ['git', 'status', '--porcelain'],
        capture_output=True, text=True
    )

    lines = result.stdout.strip().splitlines()

    if not lines:
        print("✦ Nothing to commit. Repo is up to date.")
        return

    # ── Parse the status output ──
    added    = []
    modified = []
    deleted  = []
    other    = []

    for line in lines:
        status = line[:2].strip()
        filename = line[3:].strip()

        if status == '??':
            added.append(filename)
        elif status == 'M':
            modified.append(filename)
        elif status == 'D':
            deleted.append(filename)
        else:
            other.append(filename)

    # ── Print summary ──
    print("\n✦ PUSH UPDATE SUMMARY ✦")
    print("─" * 35)

    if added:
        print(f"\n  NEW ({len(added)})")
        for f in added:
            print(f"    + {f}")

    if modified:
        print(f"\n  UPDATED ({len(modified)})")
        for f in modified:
            print(f"    ~ {f}")

    if deleted:
        print(f"\n  DELETED ({len(deleted)})")
        for f in deleted:
            print(f"    - {f}")

    if other:
        print(f"\n  OTHER ({len(other)})")
        for f in other:
            print(f"    ? {f}")

    total = len(added) + len(modified) + len(deleted) + len(other)
    print(f"\n  TOTAL: {total} file(s) changed")
    print("─" * 35)

    # ── Stage all changes ──
    subprocess.run(['git', 'add', '.'], check=True)

    # ── Commit ──
    subprocess.run(
        ['git', 'commit', '-m', 'git push update'],
        check=True
    )

    # ── Push to main ──
    subprocess.run(['git', 'push', 'origin', 'main'], check=True)

    print("\n✦ Pushed to GitHub successfully.\n")


if __name__ == '__main__':
    gitpush()
