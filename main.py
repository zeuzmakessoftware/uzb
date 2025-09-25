#!/usr/bin/env python3
import argparse
import os
import shutil
import sys
import difflib

def iter_files(root_dir):
    uzb_dir = os.path.join(root_dir, "uzb")
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if os.path.join(dirpath, d) != uzb_dir]
        for fn in filenames:
            abs_p = os.path.join(dirpath, fn)
            if not os.path.isfile(abs_p):
                continue
            rel_p = os.path.relpath(abs_p, root_dir)
            yield abs_p, rel_p

def score_file(rel_path, query, abs_path, content_sample_bytes=1_000_000):
    """
    Score how well a file matches `query`.
    - Filename/relpath fuzzy similarity (difflib ratio)
    - Bonus if query is a substring of the name/path
    - Small bonus if query appears in the (first ~1MB) of file text
    Scores are heuristic and comparable only within a run.
    """
    q = query.lower()
    name = os.path.basename(rel_path).lower()
    rel = rel_path.lower()

    # Fuzzy similarity primarily on filename, lightly on relpath
    name_sim = difflib.SequenceMatcher(None, name, q).ratio()
    rel_sim  = difflib.SequenceMatcher(None, rel,  q).ratio()

    score = name_sim * 1.0 + rel_sim * 0.25

    if q in name:
        score += 0.50
    elif q in rel:
        score += 0.25

    content_bonus = 0.0
    try:
        with open(abs_path, "rb") as f:
            sample = f.read(content_sample_bytes)
        text = sample.decode("utf-8", errors="ignore").lower()
        if q in text:
            occurrences = text.count(q)
            content_bonus = min(0.50, 0.05 * occurrences)
    except Exception:
        pass

    return score + content_bonus

def ensure_clean_uzb(root_dir):
    uzb_dir = os.path.join(root_dir, "uzb")
    if os.path.exists(uzb_dir):
        for entry in os.scandir(uzb_dir):
            try:
                if entry.is_file() or entry.is_symlink():
                    os.unlink(entry.path)
                elif entry.is_dir():
                    shutil.rmtree(entry.path)
            except Exception as e:
                print(f"Warning: failed to remove {entry.path}: {e}", file=sys.stderr)
    else:
        os.makedirs(uzb_dir, exist_ok=True)
    return uzb_dir

def unique_flat_name(rel_path, used_names):
    base = rel_path.replace(os.sep, "__")
    candidate = base
    i = 1
    while candidate in used_names:
        root, ext = os.path.splitext(base)
        candidate = f"{root}__{i}{ext}"
        i += 1
    used_names.add(candidate)
    return candidate

def main():
    parser = argparse.ArgumentParser(
        description="Copy best-matching files into ./uzb (inside the given directory). "
                    "Previous copies in uzb are deleted on each run."
    )
    parser.add_argument("directory", help="Directory to scan recursively")
    parser.add_argument("query", help="Search query (matched against names/paths and lightly against content)")
    parser.add_argument("-n", type=int, default=1,
                        help="Number of top matches to copy (default: 1)")
    args = parser.parse_args()

    root_dir = os.path.abspath(args.directory)
    if not os.path.isdir(root_dir):
        print(f"Error: '{root_dir}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    files = list(iter_files(root_dir))
    if not files:
        print("No files found to scan.")
        sys.exit(0)

    scored = []
    for abs_p, rel_p in files:
        s = score_file(rel_p, args.query, abs_p)
        scored.append((s, abs_p, rel_p))

    scored.sort(key=lambda t: t[0], reverse=True)

    N = max(0, args.n)
    top = scored[:N] if N > 0 else []

    uzb_dir = ensure_clean_uzb(root_dir)

    used_names = set()
    copied = []
    for score, abs_p, rel_p in top:
        dest_name = unique_flat_name(rel_p, used_names)
        dest_path = os.path.join(uzb_dir, dest_name)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        try:
            shutil.copy2(abs_p, dest_path)
            copied.append((rel_p, dest_name, score))
        except Exception as e:
            print(f"Failed to copy '{rel_p}': {e}", file=sys.stderr)

    if not copied:
        print("No files copied (no matches or -n 0).")
    else:
        print(f"Copied {len(copied)} file(s) to: {uzb_dir}\n")
        for rel_p, dest_name, score in copied:
            print(f"- {rel_p}  ->  uzb/{dest_name}  (score: {score:.3f})")

if __name__ == "__main__":
    main()
