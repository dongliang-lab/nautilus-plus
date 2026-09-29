---
name: folder-yaml
description: Read and write `.folder.yaml`, the per-folder metadata file that nautilus-plus (a GNOME Files fork) renders. Covers folder descriptions (`desc`), per-file annotations (`file-desc`), archiving (`archived`), and move history (`history-paths`). Use when adding a description to a folder, annotating a file, archiving or unarchiving a folder, moving or renaming a folder in a managed tree, or when you need the exact format of `.folder.yaml`.
---

# `.folder.yaml`

A folder may hold one `.folder.yaml`: a hidden YAML file **inside the folder**, so it travels with the folder when it is moved, copied or archived. nautilus-plus reads it and renders it; any other tool can read and write it too.

## When this applies

- The fields below are rendered by **nautilus-plus**. Without it installed the file is still valid data — there is just no UI effect.
- Edit the file in place rather than rewriting it blind: it may hold comments and keys you do not know about.

## Format

Every key is optional and top-level:

| Key | Type | Meaning |
|---|---|---|
| `desc` | string | Folder description, shown under the folder name in icon view and after it in list view. Any language. Absent = nothing shown. |
| `archived` | boolean | `true` puts the folder in the trailing「已归档」group; with hide-archived switched on, it is hidden from the views. Write only `true`/`false`. Absent = not archived. |
| `file-desc` | mapping: file name → string | Annotation for a file **inside this folder**, shown on that file where `desc` would be shown. |
| `history-paths` | list of absolute paths | Places this folder has lived before. Not rendered — it exists so an agent can find the folder's old sessions after a move. |

```yaml
desc: 我的项目
archived: false
file-desc:
  notes.txt: 会议记录
history-paths:
  - /home/me/old-place/my-project
```

## Describe a folder

Set or update the top-level `desc` key, leaving everything else in the file untouched:

```yaml
desc: 我的项目
```

To remove the description, delete the `desc` key — and the whole file if nothing else remains.

## Annotate a file

`file-desc` maps the **file name only** (no path) to the annotation:

```yaml
file-desc:
  notes.txt: 会议记录
```

- The key is the name as it appears in this folder: `report.pdf`, not `sub/report.pdf`.
- Write it into the `.folder.yaml` of the folder that contains the file.
- The annotation follows the file: nautilus-plus keeps a token in the file's own extended attribute (`user.nautilus-plus.desc`), so renaming or moving a file **inside nautilus-plus** carries the annotation along. Moving files with other tools leaves the entry behind — delete it there and add one at the destination.
- To remove an annotation, delete its entry; if `file-desc` then has no entries left, delete the key too.

## Archive a folder

```yaml
archived: true
```

- Only the YAML boolean `true` counts. PyYAML is YAML 1.1, so `yes`/`on` also parse as true — write the boolean `true`/`false` and nothing else.
- Unarchiving = delete the key.
- Archiving is independent of the hide-archived switch: an archived folder stays visible in the「已归档」group until that switch hides it.

## Move or rename a folder

**Before moving, append the folder's current absolute path to `history-paths`** — append, never replace, and skip it if that path is already listed:

```yaml
history-paths:
  - /home/me/old-place/my-project
  - /home/me/projects/my-project
```

Why: after a move, those old paths are the only lead back to the folder's previous coding-agent sessions. Searching the session records of the agents you use for an old path tells you which records to rewrite to the new path — so the sessions follow the folder. (Claude Code, for example, keeps them as `.jsonl` under `~/.claude/projects/<escaped-path>/`.)

nautilus-plus records the moves it observes by itself: renames, drags and cut-paste in its own windows, plus moves inside a directory it is displaying. It cannot see moves elsewhere or while it is not running — **that gap is what you cover** by appending the path yourself.

## Invariants

- **Preserve everything else**: comments, other keys, key order, quoting style. Change only the key you came for. Never round-trip the file through a YAML dumper — that drops comments.
- UTF-8, and the name is exactly `.folder.yaml`.
- `file-desc` keys are file **names**, never paths.
- `history-paths` is a list of past paths: append, dedupe, never treat it as the current location.
- A folder without a `.folder.yaml` simply has no metadata. Create the file when you have something to record.

## Don't

- Rewrite the whole file (comments are lost).
- Write `archived: yes`, `archived: "true"` or `archived: 1` — only the boolean `true`.
- Key `file-desc` by path, or annotate a subfolder there — a subfolder describes itself with its own `desc`.

## Deeper background

The repository's design documents explain why each field works the way it does:
`plus/docs/design/desc.md`, `file-desc.md`, `history-paths.md`, `archive-toggle.md`, `hide-archived.md`.
