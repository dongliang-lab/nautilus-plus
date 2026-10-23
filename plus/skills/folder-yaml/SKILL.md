---
name: folder-yaml
description: Read and write `.folder.yaml`, the per-folder metadata file that nautilus-meta (a nautilus-python extension) renders. Covers folder descriptions (`desc`) and per-file annotations (`file-desc`). Use when adding a description to a folder, annotating a file, or when you need the exact format of `.folder.yaml`.
---

# `.folder.yaml`

A folder may hold one `.folder.yaml`: a hidden YAML file **inside the folder**, so it travels with the folder when it is moved or copied. nautilus-meta reads it and renders it; any other tool can read and write it too.

## When this applies

- The fields below are rendered by **nautilus-meta**. Without it installed the file is still valid data — there is just no UI effect.
- Edit the file in place rather than rewriting it blind: it may hold comments and keys you do not know about.

## Format

Every key is optional and top-level:

| Key | Type | Meaning |
|---|---|---|
| `desc` | string | Folder description, shown under the folder name in icon view and in the「描述」column of list view. Any language. Absent = nothing shown. |
| `file-desc` | mapping: file name → string | Annotation for a file **inside this folder**, shown on that file where `desc` would be shown. |

```yaml
desc: 我的项目
file-desc:
  notes.txt: 会议记录
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
- The annotation follows the file: nautilus-meta keeps a token in the file's own extended attribute (`user.nautilus-plus.desc`), so renaming or moving a file **inside nautilus** carries the annotation along. Moving files with other tools leaves the entry behind — delete it there and add one at the destination.
- To remove an annotation, delete its entry; if `file-desc` then has no entries left, delete the key too.

## Invariants

- **Preserve everything else**: comments, other keys, key order, quoting style. Change only the key you came for. Never round-trip the file through a YAML dumper — that drops comments.
- UTF-8, and the name is exactly `.folder.yaml`.
- `file-desc` keys are file **names**, never paths.
- A folder without a `.folder.yaml` simply has no metadata. Create the file when you have something to record.

## Don't

- Rewrite the whole file (comments are lost).
- Key `file-desc` by path, or annotate a subfolder there — a subfolder describes itself with its own `desc`.

## Deeper background

The repository's design documents explain why each field works the way it does:
`plus/docs/design/desc.md`, `file-desc.md`.
