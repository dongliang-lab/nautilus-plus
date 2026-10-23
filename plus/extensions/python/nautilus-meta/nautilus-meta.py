#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nautilus extension: show folder descriptions from .folder.yaml.

For every folder whose `.folder.yaml` has a top-level `desc` key, the
description is shown as a caption line right below the folder name in
icon view. The real folder name (and path) is never changed, and normal
renaming (F2) is unaffected — edit `.folder.yaml` to change the
description.

The extension also registers a "描述" column (Nautilus.ColumnProvider), so
list view can show the same description next to the name. It is a stock
nautilus extension: no C changes, no fork build.

A global on/off switch lives in the background context menu (right-click
empty space in a folder). Toggling takes effect immediately, and the menu
label flips to match within a moment. The switch state is stored in
~/.config/nautilus-meta/state (default: on).

Install:
    cp nautilus-meta.py ~/.local/share/nautilus-python/extensions/
    nautilus -q        # restart nautilus
"""

import json
import os
import re
import stat
import tempfile
import traceback

import yaml

import gi
gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
gi.require_version('Nautilus', '4.1')
from gi.repository import Gdk, Gio, GLib, GObject, Gtk, Nautilus

CONFIG_DIR = os.path.expanduser('~/.config/nautilus-meta')
STATE_FILE = os.path.join(CONFIG_DIR, 'state')
CAPTIONS_BACKUP = os.path.join(CONFIG_DIR, 'captions-backup.json')

ICON_VIEW_SCHEMA = 'org.gnome.nautilus.icon-view'
CAPTIONS_KEY = 'captions'
ATTR = 'desc'
# Per-file annotations live in a nested mapping of the same .folder.yaml.
FILES_KEY = 'file-desc'
# File annotations also travel inside the file itself, as an extended
# attribute, so moving or renaming a file keeps them. The yaml stays the
# human-facing source of truth; this is only the carrier.
XATTR_KEY = 'user.nautilus-plus.desc'
# Attribute name used before the rename to 'desc'; captions written by an
# older build still carry it and are carried over on sight (see
# _normalize_captions).
LEGACY_ATTRS = ('name-zh',)
# Name of the list-view column registered below. Also used to find the column
# back inside nautilus's own GtkColumnView (see _fit_columns).
DESC_COLUMN = 'FolderMeta::Desc'
YAML_NAME = '.folder.yaml'
YAML_MAX_SIZE = 1024 * 1024

_settings = Gio.Settings.new(ICON_VIEW_SCHEMA)

# folder_path -> (mtime, desc | None, {name: annotation})
_yaml_cache = {}
# items (folder or file) we ever showed a description for; the source of
# truth for clearing stale captions (yaml deleted / key removed / switch off)
_shown = set()
# (mtime, unused, raw text) — the state file is now multi-line key=value
_state_cache = (None, None, '')


# --- switch state ---------------------------------------------------------

def _read_state():
    """State file text, or '' when missing. Cached by mtime."""
    global _state_cache
    try:
        mtime = os.path.getmtime(STATE_FILE)
    except OSError:
        return ''
    if _state_cache[0] == mtime:
        return _state_cache[2]
    try:
        with open(STATE_FILE, encoding='utf-8') as f:
            text = f.read()
    except OSError:
        return ''
    _state_cache = (mtime, None, text)
    return text


def _write_state(text):
    global _state_cache
    os.makedirs(CONFIG_DIR, exist_ok=True)
    _atomic_write(STATE_FILE, text)
    try:
        _state_cache = (os.path.getmtime(STATE_FILE), None, text)
    except OSError:
        _state_cache = (None, None, '')


def _enabled():
    """Whether descriptions are shown. Defaults to on."""
    first_line = _read_state().splitlines()[0].strip() \
        if _read_state().splitlines() else ''
    # Missing file / legacy formats without a leading on|off default to on.
    return first_line != 'off'


def _set_enabled(on):
    lines = _read_state().splitlines()
    value = 'on' if on else 'off'
    if lines and lines[0].strip() in ('on', 'off'):
        lines[0] = value
    else:
        lines.insert(0, value)
    _write_state('\n'.join(lines) + '\n')


def _atomic_write(path, text, mode=None):
    parent = os.path.dirname(path) or '.'
    fd, tmp = tempfile.mkstemp(prefix='.' + os.path.basename(path) + '.',
                               dir=parent)
    try:
        if mode is not None:
            os.fchmod(fd, mode)
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# --- .folder.yaml --------------------------------------------------------

def _parse_yaml(yaml_path):
    """(desc, file_descs) from one .folder.yaml."""
    desc = None
    file_descs = {}
    try:
        if os.path.getsize(yaml_path) <= YAML_MAX_SIZE:
            with open(yaml_path, encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                value = data.get(ATTR)
                if isinstance(value, str) and value.strip():
                    desc = value.strip()
                per_file = data.get(FILES_KEY)
                if isinstance(per_file, dict):
                    for entry, annotation in per_file.items():
                        if (isinstance(entry, str) and isinstance(annotation, str)
                                and annotation.strip()):
                            file_descs[entry] = annotation.strip()
    except (yaml.YAMLError, UnicodeDecodeError, OSError, ValueError):
        pass
    return (desc, file_descs)


def _yaml_data(folder_path):
    """(desc, file_descs) from the folder's .folder.yaml.

    Cached by the yaml's and the folder's mtime: this runs for every file
    in the folder, so it is parsed once per change, not once per item.
    Annotations whose file is gone are dropped here — that is what keeps a
    moved or deleted file from leaving a stale entry behind.
    """
    yaml_path = os.path.join(folder_path, YAML_NAME)
    try:
        yaml_mtime = os.path.getmtime(yaml_path)
    except OSError:
        _yaml_cache.pop(folder_path, None)
        return (None, {})
    try:
        # A file appearing or disappearing is what makes an entry stale,
        # and that is exactly what the directory mtime records.
        dir_mtime = os.path.getmtime(folder_path)
    except OSError:
        dir_mtime = None

    key = (yaml_mtime, dir_mtime)
    hit = _yaml_cache.get(folder_path)
    if hit is not None and hit[0] == key:
        return hit[1]

    data = _parse_yaml(yaml_path)
    stale = [entry for entry in data[1]
             if not os.path.lexists(os.path.join(folder_path, entry))]
    if stale:
        try:
            _drop_file_descs(folder_path, stale)
        except (ValueError, OSError):
            traceback.print_exc()
        else:
            try:
                yaml_mtime = os.path.getmtime(yaml_path)
            except OSError:
                yaml_mtime = None
            key = (yaml_mtime, dir_mtime)
            data = _parse_yaml(yaml_path)

    _yaml_cache[folder_path] = (key, data)
    if len(_yaml_cache) > 1024:
        _yaml_cache.pop(next(iter(_yaml_cache)))
    return data


def _yaml_info(folder_path):
    """desc from the folder's .folder.yaml. Cached by mtime."""
    return _yaml_data(folder_path)[0]


def _yaml_file_descs(folder_path):
    """{file name: annotation} from the folder's .folder.yaml, cached."""
    return _yaml_data(folder_path)[1]


def _yaml_scalar(value):
    if '\n' in value or '\r' in value:
        raise ValueError('描述不能包含换行')
    lines = yaml.safe_dump(value, allow_unicode=True,
                           default_flow_style=True,
                           sort_keys=False).splitlines()
    if len(lines) == 2 and lines[1] == '...':
        scalar = lines[0]
    elif len(lines) == 1:
        scalar = lines[0]
    else:
        raise ValueError('描述无法写入 YAML')
    parsed = yaml.safe_load(f'{ATTR}: {scalar}\n')
    if not isinstance(parsed, dict) or parsed.get(ATTR) != value:
        raise ValueError('描述无法写入 YAML')
    return scalar


def _compose_mapping(text):
    """The root mapping node of `text`, validated."""
    try:
        data = yaml.safe_load(text)
        node = yaml.compose(text)
    except (yaml.YAMLError, UnicodeDecodeError, ValueError) as error:
        raise ValueError('现有 .folder.yaml 格式无效') from error
    if not isinstance(data, dict) or not isinstance(node, yaml.MappingNode):
        raise ValueError('.folder.yaml 顶层必须是对象')
    return node


def _find_key_nodes(mapping_node, key):
    """(key_node, value_node) pairs whose key is the string `key`."""
    return [
        (key_node, value_node)
        for key_node, value_node in mapping_node.value
        if (isinstance(key_node, yaml.ScalarNode)
            and key_node.tag == 'tag:yaml.org,2002:str'
            and key_node.value == key)
    ]


def _child_mapping(node, key):
    """The mapping stored at `key`, or None when absent.

    Raises when the key exists but does not hold a mapping: silently
    replacing the user's data would be worse than refusing to write.
    """
    matches = _find_key_nodes(node, key)
    if len(matches) > 1:
        raise ValueError(f'.folder.yaml 中存在重复的 {key}')
    if not matches:
        return None
    value_node = matches[0][1]
    if not isinstance(value_node, yaml.MappingNode):
        raise ValueError(f'.folder.yaml 中的 {key} 必须是对象')
    return value_node


def _block_indent(text, mapping_node):
    """Leading whitespace of a block mapping's first entry."""
    first_key = mapping_node.value[0][0]
    line_start = text.rfind('\n', 0, first_key.start_mark.index) + 1
    return ' ' * (first_key.start_mark.index - line_start)


def _insert_block_entry(text, node, entry, before_document_end):
    """Insert `entry` (newline-terminated) at the end of block `node`."""
    newline = '\r\n' if '\r\n' in text else '\n'
    if before_document_end:
        # A `...` marker ends the document; the entry belongs before it.
        marker = re.search(
            r'(?m)^[ \t]*\.\.\.[ \t]*(?:#.*)?(?:\r?\n|$)',
            text[node.end_mark.index:],
        )
        insert_at = (node.end_mark.index + marker.start()
                     if marker is not None else len(text))
    else:
        insert_at = node.end_mark.index
    before = text[:insert_at]
    if before and not before.endswith(('\n', '\r')):
        before += newline
    return before + entry + text[insert_at:]


def _put_in_mapping(text, node, key, value_text, indent='',
                    before_document_end=False, entry_body=None):
    """Text with `key` set to `value_text` inside mapping `node`.

    An existing entry keeps its surroundings (comments, order, line
    endings) and only its value is swapped. A new one is appended as
    `entry_body`, which defaults to "<key>: <value_text>" and may be
    overridden when the entry needs a shape of its own (a nested mapping).
    """
    value_nodes = [value_node
                   for _key_node, value_node in _find_key_nodes(node, key)]
    if len(value_nodes) > 1:
        raise ValueError(f'.folder.yaml 中存在重复的 {key}')

    newline = '\r\n' if '\r\n' in text else '\n'
    if value_nodes:
        value_node = value_nodes[0]
        start = value_node.start_mark.index
        end = value_node.end_mark.index
        replacement = value_text
        if '\n' in text[start:end] or '\r' in text[start:end]:
            replacement += newline
        return text[:start] + replacement + text[end:]

    if entry_body is None:
        entry_body = f'{key}: {value_text}'

    if node.flow_style:
        close = text.rfind('}', node.start_mark.index, node.end_mark.index)
        if close < 0:
            raise ValueError('无法定位 .folder.yaml 的顶层对象')
        # A trailing comma before '}' is valid YAML; don't double it.
        prefix = text[:close].rstrip()
        if prefix.endswith(','):
            separator = ' '
        elif node.value:
            separator = ', '
        else:
            separator = ''
        return text[:close] + f'{separator}{entry_body}' + text[close:]

    entry = f'{indent}{entry_body}{newline}'
    return _insert_block_entry(text, node, entry, before_document_end)


def _remove_from_mapping(text, node, key):
    """Text minus the `key` entry of mapping `node`.

    Returns '' when nothing remains (caller deletes the file); None when
    the key was absent.
    """
    matches = _find_key_nodes(node, key)
    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError(f'.folder.yaml 中存在重复的 {key}')

    key_node, value_node = matches[0]
    if node.flow_style:
        # Flow style has no line structure: excise the entry plus one
        # adjacent comma (either the one after it, or the one before it
        # when removing the last entry).
        start = key_node.start_mark.index
        end = value_node.end_mark.index
        comma_after = text.find(',', end, node.end_mark.index)
        if comma_after >= 0:
            end = comma_after + 1
        else:
            comma_before = text.rfind(',', 0, start)
            if comma_before < 0:
                return ''  # Sole entry: nothing remains.
            start = comma_before
        result = text[:start] + text[end:]
        try:
            empty = not yaml.safe_load(result)
        except yaml.YAMLError as error:
            raise ValueError('无法安全移除条目') from error
        return '' if empty else result

    # Block style: excise the entry's whole physical line(s), trailing
    # comment included.
    line_start = text.rfind('\n', 0, key_node.start_mark.index) + 1
    newline_at = text.find('\n', value_node.end_mark.index)
    line_end = len(text) if newline_at < 0 else newline_at + 1
    result = text[:line_start] + text[line_end:]
    try:
        empty = not yaml.safe_load(result)
    except yaml.YAMLError as error:
        raise ValueError('无法安全移除条目') from error
    return '' if empty else result


def _replace_yaml_key(text, key, scalar):
    """Text with the top-level `key` value replaced by `scalar`.

    Missing keys are appended (before a trailing `...` in block style,
    inside the braces in flow style). Comments, other fields, key order
    and line endings are preserved.
    """
    node = _compose_mapping(text)
    return _put_in_mapping(text, node, key, scalar, before_document_end=True)


def _remove_yaml_key(text, key):
    """Text minus the top-level `key` entry.

    Returns '' when nothing remains (caller deletes the file); None when
    the key was absent.
    """
    node = _compose_mapping(text)
    return _remove_from_mapping(text, node, key)


def _read_token(path):
    """The move token of a file: {"folder", "name", "desc"}, or None.

    The recorded folder *and* name are what tell "the annotation arrived
    with a moved or renamed file" apart from "the entry was deleted here
    by hand" — the two cases look identical from the yaml alone.
    """
    try:
        raw = os.getxattr(path, XATTR_KEY)
    except OSError:
        return None  # No token, or a filesystem without xattrs.
    try:
        token = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        return None
    return token if isinstance(token, dict) else None


def _write_token(path, folder, name, value):
    """Record where an annotation was written, next to the file itself."""
    try:
        payload = json.dumps({'folder': folder, 'name': name, 'desc': value})
        os.setxattr(path, XATTR_KEY, payload.encode('utf-8'))
    except (OSError, TypeError, ValueError):
        pass  # Fat/network filesystems: annotations simply do not travel.


def _clear_token(path):
    try:
        os.removexattr(path, XATTR_KEY)
    except OSError:
        pass


def _token_matches(token, folder, name, value):
    return (token is not None
            and token.get('folder') == folder
            and token.get('name') == name
            and token.get('desc') == value)


def _yaml_pair(name, value):
    """`<name>: <value>`, both sides quoted the way YAML requires.

    Handles file names that need quoting (`a: b.txt`, leading dashes,
    trailing spaces) without hand-rolled escaping: dump a one-entry
    mapping and take the text between the braces.
    """
    if not value:
        raise ValueError('注释不能为空')
    if '\n' in value or '\r' in value:
        raise ValueError('注释不能包含换行')
    dumped = yaml.safe_dump({name: value}, default_flow_style=True,
                            allow_unicode=True, sort_keys=False,
                            width=10 ** 9).strip()
    if not (dumped.startswith('{') and dumped.endswith('}')):
        raise ValueError('注释无法写入 YAML')
    pair = dumped[1:-1]
    if yaml.safe_load('{' + pair + '}') != {name: value}:
        raise ValueError('注释无法写入 YAML')
    return pair


def _set_file_desc(text, filename, value):
    """Text with file-desc.<filename> set to `value`."""
    pair = _yaml_pair(filename, value)
    newline = '\r\n' if '\r\n' in text else '\n'

    if not text:
        return f'{FILES_KEY}:{newline}  {pair}{newline}'

    node = _compose_mapping(text)
    files_node = _child_mapping(node, FILES_KEY)
    if files_node is not None:
        indent = '' if files_node.flow_style else _block_indent(text, files_node)
        return _put_in_mapping(text, files_node, filename, value, indent=indent)

    # No file-desc yet: create it. A flow document has no line structure
    # to grow a block mapping into, so it gets a flow one instead.
    if node.flow_style:
        entry = f'{FILES_KEY}: {{{pair}}}'
    else:
        entry = f'{FILES_KEY}:{newline}  {pair}'
    return _put_in_mapping(text, node, FILES_KEY, value, entry_body=entry,
                           before_document_end=True)


def _remove_file_desc(text, filename):
    """Text minus file-desc.<filename>; the key goes when it empties.

    Returns '' when nothing remains (caller deletes the file); None when
    there was nothing to remove.
    """
    if not text:
        return None
    node = _compose_mapping(text)
    files_node = _child_mapping(node, FILES_KEY)
    if files_node is None:
        return None
    result = _remove_from_mapping(text, files_node, filename)
    if result is None:
        return None
    try:
        data = yaml.safe_load(result)
    except yaml.YAMLError as error:
        raise ValueError('无法安全移除条目') from error
    if isinstance(data, dict) and not data.get(FILES_KEY):
        # Last annotation gone: the empty key goes with it.
        result = _remove_yaml_key(result, FILES_KEY)
    return result


def _drop_file_descs(folder_path, names):
    """Remove several annotations at once: one rewrite, not one per name."""
    def update(text):
        result = text
        for name in names:
            removed = _remove_file_desc(result, name)
            if removed is not None:
                result = removed
        return result

    _update_existing_yaml_file(folder_path, update)


def _update_existing_yaml_file(folder_path, update):
    """Apply update(text) -> new text to an existing .folder.yaml.

    Like _update_yaml_file, but never creates the file: removal has
    nothing to do when there is no file to remove from.
    """
    yaml_path = os.path.join(folder_path, YAML_NAME)
    try:
        file_stat = os.stat(yaml_path)
    except FileNotFoundError:
        return
    if file_stat.st_size > YAML_MAX_SIZE:
        raise ValueError('.folder.yaml 文件过大')
    with open(yaml_path, encoding='utf-8', newline='') as f:
        original = f.read()
    result = update(original)
    if result is None:
        return
    if result == '':
        os.unlink(yaml_path)
    else:
        _atomic_write(yaml_path, result, stat.S_IMODE(file_stat.st_mode))


def _write_file_desc(folder_path, filename, value):
    """Set the annotation of one file inside `folder_path`."""
    value = value.strip()
    if not value:
        raise ValueError('注释不能为空')

    def update(text):
        return _set_file_desc(text, filename, value)

    _update_yaml_file(folder_path, update)


def _remove_file_desc_in_folder(folder_path, filename):
    """Drop one file's annotation; empty keys and files follow the usual rules."""
    _update_existing_yaml_file(
        folder_path, lambda text: _remove_file_desc(text, filename))


def _update_yaml_file(folder_path, update):
    """Apply update(original_text) -> new text to .folder.yaml atomically.

    An update returning '' deletes the file; None is a no-op. Missing file
    starts from '' (the updater produces the initial content).
    """
    yaml_path = os.path.join(folder_path, YAML_NAME)
    try:
        file_stat = os.stat(yaml_path)
    except FileNotFoundError:
        _atomic_write(yaml_path, update(''), 0o644)
        return
    if file_stat.st_size > YAML_MAX_SIZE:
        raise ValueError('.folder.yaml 文件过大')
    with open(yaml_path, encoding='utf-8', newline='') as f:
        original = f.read()
    result = update(original)
    if result is None:
        return
    if result == '':
        os.unlink(yaml_path)
    else:
        _atomic_write(yaml_path, result, stat.S_IMODE(file_stat.st_mode))


def _write_desc(folder_path, value):
    value = value.strip()
    if not value:
        raise ValueError('描述不能为空')
    scalar = _yaml_scalar(value)

    def update(text):
        return f'{ATTR}: {scalar}\n' if text == '' else _replace_yaml_key(
            text, ATTR, scalar)

    _update_yaml_file(folder_path, update)


def _remove_key_in_folder(folder_path, key):
    """Drop a top-level key; delete .folder.yaml if nothing else remains."""
    _update_existing_yaml_file(
        folder_path, lambda text: _remove_yaml_key(text, key))


# --- icon-view captions ---------------------------------------------------
# The name label under the icon is always shown; captions are extra lines
# below it. Making 'desc' the first caption puts the description directly
# under the name.

def _captions():
    return list(_settings.get_strv(CAPTIONS_KEY))


def _set_captions(captions):
    _settings.set_strv(CAPTIONS_KEY, captions)


def _save_captions_backup(captions):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    _atomic_write(CAPTIONS_BACKUP, json.dumps(captions))


def _load_captions_backup():
    try:
        with open(CAPTIONS_BACKUP, encoding='utf-8') as f:
            backup = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(backup, list) or not all(isinstance(c, str) for c in backup):
        return None
    normalized = _normalize_captions(backup)
    if normalized != backup:
        _save_captions_backup(normalized)
    return normalized


def _clear_captions_backup():
    try:
        os.remove(CAPTIONS_BACKUP)
    except OSError:
        pass


def _normalize_captions(captions):
    """Carry captions written by older builds over to today's attribute name.

    'name-zh' became 'desc'. Without this the stale entry would linger as a
    caption nothing resolves, and the list still holding the old name would
    look like "the attribute is not set yet" -- making the code overwrite the
    user's original backup.
    """
    if not any(c in LEGACY_ATTRS for c in captions):
        return captions
    seen = set()
    normalized = []
    for caption in captions:
        caption = ATTR if caption in LEGACY_ATTRS else caption
        if caption not in seen:
            seen.add(caption)
            normalized.append(caption)
    return normalized


def _sync_captions(enabled):
    """On: make 'desc' the first caption. Off: restore what the user had."""
    captions = _captions()
    normalized = _normalize_captions(captions)
    if normalized != captions:
        # Write the rename through, so the stale attribute is gone for good.
        _set_captions(normalized)
        captions = normalized

    if enabled:
        if ATTR not in captions:
            _save_captions_backup(captions)
            _set_captions([ATTR] + [c for c in captions if c not in ('none', ATTR)])
    else:
        if ATTR in captions:
            backup = _load_captions_backup()
            if backup is not None:
                _clear_captions_backup()
                _set_captions(backup)
            else:
                _set_captions([c for c in captions if c != ATTR])


# --- applying the name ----------------------------------------------------

def _local_path(file):
    """Local filesystem path of `file`, or None when it has none."""
    uri = file.get_uri()
    if not uri.startswith('file:'):
        return None
    try:
        return GLib.filename_from_uri(uri)[0]
    except GLib.Error:
        return None


def _local_folder_path(file):
    if not file.is_directory():
        return None
    return _local_path(file)


def _local_file_target(file):
    """(parent folder, file name) for a local plain file, else None."""
    if file.is_directory():
        return None
    path = _local_path(file)
    if path is None:
        return None
    return os.path.dirname(path), os.path.basename(path)


def _resolve_annotation(path, folder, name):
    """The annotation to show for one file, kept in step with its token.

    The yaml is the source of truth; the token in the file's own extended
    attribute is what lets an annotation follow the file to a new name or
    a new folder.
    """
    annotation = _yaml_file_descs(folder).get(name)
    token = _read_token(path)

    if annotation is None:
        if token is None:
            return None
        if token.get('folder') != folder or token.get('name') != name:
            # The file was renamed or moved here: adopt the annotation into
            # this folder's yaml, so it is grep-able and hand-editable again.
            adopted = token.get('desc')
            if not (isinstance(adopted, str) and adopted.strip()):
                _clear_token(path)
                return None
            try:
                _write_file_desc(folder, name, adopted)
            except (ValueError, OSError):
                traceback.print_exc()
            else:
                _yaml_cache.pop(folder, None)
            # Record where it lives now, so the next refresh sees a match.
            _write_token(path, folder, name, adopted)
            return adopted
        # Dropped here by hand: the token must not bring it back.
        _clear_token(path)
        return None

    if not _token_matches(token, folder, name, annotation):
        _write_token(path, folder, name, annotation)
    return annotation


def _apply(file):
    """Set/clear the desc extension attribute for one item.

    A folder's desc is its own .folder.yaml; a plain file's annotation is
    looked up in its parent folder's.
    """
    path = _local_path(file)
    if path is None:
        return

    if not file.is_directory():
        annotation = _resolve_annotation(
            path, os.path.dirname(path), os.path.basename(path))
        if _enabled() and annotation:
            file.add_string_attribute(ATTR, annotation)
            _shown.add(path)
        elif path in _shown:
            file.add_string_attribute(ATTR, '')
        return

    name = _yaml_info(path)
    if _enabled() and name:
        file.add_string_attribute(ATTR, name)
        _shown.add(path)
    elif path in _shown:
        # Extension attributes have no removal: an empty value clears the
        # line. Needed when desc is removed or the switch is turned off.
        file.add_string_attribute(ATTR, '')


def _refresh_folder(folder):
    """Re-apply extension info for every child of folder, live."""
    gfile = folder.get_location()
    try:
        children = gfile.enumerate_children('standard::name',
                                            Gio.FileQueryInfoFlags.NONE,
                                            None)
    except GLib.Error:
        return
    try:
        for info in children:
            file_info = Nautilus.FileInfo.lookup_for_uri(
                gfile.get_child(info.get_name()).get_uri())
            if file_info is not None:
                _apply(file_info)
                file_info.invalidate_extension_info()
    finally:
        try:
            children.close(None)
        except GLib.Error:
            pass


# --- nautilus extension points -------------------------------------------

# --- list-view column widths ----------------------------------------------
# nautilus gives the name column expand=TRUE and every other column expand=FALSE
# (src/nautilus-list-view.c), so the description column is pushed far to the
# right and cannot be pulled in. Nautilus.Column has no width/expand property,
# so this is fixed in-process on the GTK widgets:
#
#   desc column visible  -> name column is sized to the longest file name of
#                           the current folder (read from the view's model, so
#                           rows that were never scrolled into view count too),
#                           and the description column expands into the rest
#   desc column hidden   -> nautilus's own layout is restored
#
# The name width is only written while the user has not dragged the column;
# dragging wins until the folder changes.

# Largest share of the view the name column may take, so one absurd file name
# cannot squeeze the description out.
NAME_SHARE = 0.5
# List-view description text, relative to the row font.
DESC_FONT_SCALE = '0.85em'
# Nautilus writes the chosen view here every time the user switches, which is
# the only reliable signal that a new list view was built (see _watch_view_mode).
VIEW_MODE_SCHEMA = 'org.gnome.nautilus.preferences'
VIEW_MODE_KEY = 'default-folder-viewer'

# Gtk.ColumnView -> per-view bookkeeping. The keys are held strongly on
# purpose: PyGObject throws its wrapper away as soon as the last Python
# reference goes, so a weak key never matches on the next pass. Views that no
# longer exist are dropped at the end of every pass.
_view_states = {}
_desc_css_added = False
_view_mode_watched = False
_view_mode_settings = None
_fit_scheduled = False


def _state_for(view):
    """Bookkeeping for one list view, created on first sight."""
    state = _view_states.get(view)
    if state is None:
        state = {
            'applied': None,     # fixed width we last wrote on the name column
            'user': False,       # the user dragged the name column
            'folder': None,      # folder the width was computed for
            'desc_class': None,  # css class currently carried by the view
            'model': None,       # model whose items-changed we listen to
            'handler': None,     # that handler's id
            'hooked': False,     # notify::model already connected
            'cache': None,       # (n_items, folder, {name: width})
        }
        _view_states[view] = state
    return state


def _column_views(widget):
    """Every Gtk.ColumnView below `widget`, depth first."""
    found = []
    child = widget.get_first_child()
    while child is not None:
        if isinstance(child, Gtk.ColumnView):
            found.append(child)
        found.extend(_column_views(child))
        child = child.get_next_sibling()
    return found


def _walk_in_order(widget, visit):
    """Depth-first walk that keeps sibling order (headers come out in order)."""
    visit(widget)
    child = widget.get_first_child()
    while child is not None:
        _walk_in_order(child, visit)
        child = child.get_next_sibling()


def _first_label(widget):
    """First non-empty Gtk.Label at or below `widget`, or None."""
    found = []

    def visit(node):
        if found:
            return
        if isinstance(node, Gtk.Label) and node.get_text():
            found.append(node)

    _walk_in_order(widget, visit)
    return found[0] if found else None


def _file_of(model, index):
    """NautilusFile behind one model row, or None."""
    try:
        row = model.get_item(index)
    except Exception:
        return None
    if row is None:
        return None
    try:
        # List view wraps items in a GtkTreeListRow (rows expand into trees).
        item = row.get_item() if hasattr(row, 'get_item') else row
    except Exception:
        item = row
    try:
        return item.get_property('file')
    except Exception:
        return None


def _folder_key(model):
    """Parent URI of the first row; None for an empty model."""
    if model is None:
        return None
    try:
        if model.get_n_items() == 0:
            return None
        file = _file_of(model, 0)
        if file is None:
            return None
        uri = file.get_uri()
    except Exception:
        return None
    return uri.rsplit('/', 1)[0] if '/' in uri else uri


def _name_widths_in(state, model, font_label):
    """{file name: pixel width} for every row, cached per model snapshot."""
    try:
        count = model.get_n_items()
    except Exception:
        return {}
    key = _folder_key(model)
    cached = state['cache']
    if cached is not None and cached[0] == count and cached[1] == key:
        return cached[2]

    widths = {}
    for index in range(count):
        file = _file_of(model, index)
        if file is None:
            continue
        try:
            name = file.get_name()
        except Exception:
            continue
        if not name:
            continue
        try:
            # Same font as nautilus uses for names: measure with a real one.
            widths[name] = font_label.create_pango_layout(name).get_pixel_size()[0]
        except Exception:
            continue
    state['cache'] = (count, key, widths)
    return widths


def _name_cell_metrics(view):
    """(overhead, font label) from one realized name cell, or (None, None).

    overhead = cell width minus its file-name label: icon, spacing and padding,
    everything the column needs on top of the text itself.
    """
    cells = []

    def visit(widget):
        if type(widget).__name__ == 'NautilusNameCell':
            cells.append(widget)

    _walk_in_order(view, visit)
    for cell in cells:
        label = _first_label(cell)
        if label is None:
            continue
        try:
            cell_width = cell.measure(Gtk.Orientation.HORIZONTAL, -1)[1]
            label_width = label.measure(Gtk.Orientation.HORIZONTAL, -1)[1]
        except Exception:
            continue
        if cell_width <= 0:
            continue
        return max(0, cell_width - label_width), label
    return None, None


def _header_width(view):
    """Width of the first column header's text (the name column's title).

    The title widget itself is as wide as the column, so measuring it would
    feed the current width back in; the label inside it is what matters.
    """
    titles = []

    def visit(widget):
        if type(widget).__name__ == 'GtkColumnViewTitle':
            titles.append(widget)

    _walk_in_order(view, visit)
    if not titles:
        return 0
    label = _first_label(titles[0])
    if label is None:
        return 0
    try:
        return label.measure(Gtk.Orientation.HORIZONTAL, -1)[1]
    except Exception:
        return 0


def _name_column_width(view):
    """Width the name column needs for this folder, or None while unknown."""
    overhead, font_label = _name_cell_metrics(view)
    if overhead is None:
        # Nothing laid out yet: measuring now would truncate every name.
        return None
    model = view.get_model()
    widths = (_name_widths_in(_state_for(view), model, font_label)
              if model is not None else {})
    needed = overhead + max(widths.values() or [0])
    needed = max(needed, _header_width(view))
    try:
        view_width = view.get_width()
    except Exception:
        view_width = 0
    if view_width > 0:
        needed = min(needed, max(120, int(view_width * NAME_SHARE)))
    return needed


def _visible_index(columns, column):
    """1-based position of `column` among the visible ones, 0 if not found."""
    position = 0
    for candidate in columns:
        if not candidate.get_visible():
            continue
        position += 1
        if candidate is column:
            return position
    return 0


def _desc_css():
    """Smaller font for the description column, one rule per visible position.

    Rows only hold cells for visible columns, so the column's position among
    the visible ones is its :nth-child. Rules are pre-generated because the
    position changes when the user reorders or hides columns.
    """
    global _desc_css_added
    if _desc_css_added:
        return
    _desc_css_added = True
    rules = []
    for index in range(1, 17):
        rules.append(
            'columnview.folder-meta-desc-%d row > cell:nth-child(%d) label'
            ' { font-size: %s; }' % (index, index, DESC_FONT_SCALE))
    try:
        provider = Gtk.CssProvider()
        provider.load_from_string('\n'.join(rules))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    except Exception:
        # Older GTK or no display: the text simply keeps the default size.
        pass


def _set_desc_class(view, index):
    """Mark the view so the description cell at `index` renders smaller."""
    state = _state_for(view)
    wanted = 'folder-meta-desc-%d' % index if index else None
    applied = state['desc_class']
    if applied == wanted:
        return
    if applied is not None:
        try:
            view.remove_css_class(applied)
        except Exception:
            pass
    if wanted is not None:
        try:
            view.add_css_class(wanted)
        except Exception:
            pass
    state['desc_class'] = wanted


def _hook_view(view):
    """Watch this view's model so entering a folder re-measures the names."""
    state = _state_for(view)
    if not state['hooked']:
        state['hooked'] = True
        try:
            view.connect('notify::model', _on_model_changed)
        except Exception:
            pass
    try:
        model = view.get_model()
    except Exception:
        return
    if model is None or state['model'] is model:
        return
    old_model = state['model']
    if old_model is not None and state['handler'] is not None:
        try:
            old_model.disconnect(state['handler'])
        except Exception:
            pass
    state['model'] = model
    state['handler'] = None
    try:
        state['handler'] = model.connect('items-changed', _on_items_changed)
    except Exception:
        pass


def _on_model_changed(_view, _pspec):
    _schedule_fit()


def _on_items_changed(_model, _position, _removed, _added):
    _schedule_fit()


def _fit_one(view):
    """Place the description column right after the name. Never raises."""
    name_column = None
    desc_column = None
    columns = []
    for column in view.get_columns():
        columns.append(column)
        column_id = column.get_id()
        if column_id == 'name':
            name_column = column
        elif column_id == DESC_COLUMN:
            desc_column = column

    if name_column is None or desc_column is None:
        return

    state = _state_for(view)

    if not desc_column.get_visible():
        # Hidden description: hand the width back to the name column, exactly
        # as nautilus set it up, and forget any hand-made width.
        state['applied'] = None
        state['user'] = False
        _set_desc_class(view, 0)
        if not name_column.get_expand():
            name_column.set_fixed_width(-1)
            name_column.set_expand(True)
        return

    # A different folder: whatever the user dragged last time no longer applies.
    key = _folder_key(view.get_model())
    if key is not None and state['folder'] != key:
        state['folder'] = key
        state['user'] = False
        state['applied'] = None

    if not state['user']:
        needed = _name_column_width(view)
        applied = state['applied']
        current = name_column.get_fixed_width()
        if applied is not None and current != applied:
            # The width changed behind our back: the user dragged it.
            state['user'] = True
        elif needed is not None and current != needed:
            name_column.set_fixed_width(needed)
            state['applied'] = needed

    if not desc_column.get_expand():
        desc_column.set_expand(True)
    if name_column.get_expand():
        name_column.set_expand(False)

    _set_desc_class(view, _visible_index(columns, desc_column))


def _forget_view(view):
    """Drop bookkeeping for a view that is gone (window closed)."""
    state = _view_states.pop(view, None)
    if state is None:
        return
    model = state['model']
    if model is not None and state['handler'] is not None:
        try:
            model.disconnect(state['handler'])
        except Exception:
            pass


def _fit_columns():
    """Re-balance column widths in every open window. Never raises."""
    _desc_css()
    _watch_view_mode()
    seen = set()
    try:
        toplevels = Gtk.Window.get_toplevels()
        for index in range(toplevels.get_n_items()):
            window = toplevels.get_item(index)
            if window is None:
                continue
            for view in _column_views(window):
                seen.add(view)
                try:
                    _hook_view(view)
                    _fit_one(view)
                except Exception:
                    # One odd view must not stop the others.
                    pass
    except Exception:
        # Nautilus internals changed, or a window went away mid-walk: the
        # columns simply stay as nautilus made them.
        pass
    for view in [v for v in _view_states if v not in seen]:
        _forget_view(view)


def _schedule_fit():
    """Coalesce column fixes: one idle pass per main-loop iteration."""
    global _fit_scheduled
    if _fit_scheduled:
        return
    _fit_scheduled = True

    def run():
        global _fit_scheduled
        _fit_scheduled = False
        _fit_columns()
        return False

    GLib.idle_add(run)


def _on_view_mode_changed(_settings, _key):
    """The user switched icon <-> list view: a brand new list view exists.

    Switching calls no provider on the files already loaded, so nothing else
    would measure the fresh columns. The view is still being laid out when
    the preference changes, though, so the first pass finds no rows; a
    second one follows shortly after to pick the width up.
    """
    _schedule_fit()

    def again():
        _schedule_fit()
        return False

    try:
        GLib.timeout_add(250, again)
    except Exception:
        pass


def _watch_view_mode():
    """Re-fit when the window switches between icon and list view.

    The GSettings object is held at module level on purpose: PyGObject drops
    its wrapper (and with it the signal connection) once the last Python
    reference goes.
    """
    global _view_mode_watched, _view_mode_settings
    if _view_mode_watched:
        return
    _view_mode_watched = True
    try:
        _view_mode_settings = Gio.Settings.new(VIEW_MODE_SCHEMA)
        _view_mode_settings.connect('changed::' + VIEW_MODE_KEY,
                                    _on_view_mode_changed)
    except Exception:
        # Schema missing (unusual nautilus build): other triggers still run.
        _view_mode_settings = None


def _active_window():
    application = Gio.Application.get_default()
    if application is not None:
        try:
            window = application.get_active_window()
        except AttributeError:
            window = None
        if window is not None:
            return window
    for window in Gtk.Window.list_toplevels():
        if window.is_active():
            return window
    return None


class FolderMetaInfoProvider(GObject.GObject, Nautilus.InfoProvider):
    """Shows folder descriptions and file annotations as captions."""

    def __init__(self):
        super().__init__()

    def update_file_info(self, file):
        _apply(file)
        # Cheap and idempotent: makes sure a freshly built list view gets the
        # description column placed right after the name.
        _schedule_fit()


class FolderMetaMenu(GObject.GObject, Nautilus.MenuProvider):
    """Provides the project-name action and the global caption switch."""

    def __init__(self):
        super().__init__()
        self._dialogs = {}
        self._alerts = set()

    def get_file_items(self, files):
        # Editing a description or an annotation targets one item.
        items = []
        if len(files) == 1:
            file = files[0]
            if _local_folder_path(file) is not None:
                items.append(Nautilus.MenuItem(
                    name='FolderMeta::EditDesc',
                    label='修改描述',
                    tip='编辑文件夹 .folder.yaml 中的 desc',
                    icon=None,
                ))
                items[-1].connect('activate', self._on_edit_name, file)
            else:
                target = _local_file_target(file)
                if target is None:
                    return []
                items.append(Nautilus.MenuItem(
                    name='FolderMeta::EditFileDesc',
                    label='修改注释',
                    tip='编辑所属文件夹 .folder.yaml 中的 file-desc',
                    icon=None,
                ))
                items[-1].connect('activate', self._on_edit_file_desc,
                                  file, *target)
        return items

    def _on_edit_name(self, _item, file):
        folder = _local_folder_path(file)
        if folder is None:
            return
        desc = _yaml_info(folder)
        self._open_editor(
            file, '修改描述', '描述', desc,
            lambda window, entry: self._save_desc(window, entry, file, folder))

    def _on_edit_file_desc(self, _item, file, folder, filename):
        annotation = _yaml_file_descs(folder).get(filename)
        self._open_editor(
            file, '修改注释', '注释', annotation,
            lambda window, entry: self._save_file_desc(
                window, entry, file, folder, filename))

    def _open_editor(self, file, title, field_label, initial, on_save):
        """A one-line editor window, shared by both description kinds.

        `on_save(window, entry)` is called on save; it owns closing the
        window so a failed write can keep it open with the input intact.
        """
        uri = file.get_uri()
        existing = self._dialogs.get(uri)
        if existing is not None:
            existing.present()
            return

        window = Gtk.Window(title=title)
        window.set_default_size(420, 120)
        window.set_modal(True)
        window.set_destroy_with_parent(True)
        parent = _active_window()
        if parent is not None and parent is not window:
            window.set_transient_for(parent)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for margin in ('top', 'bottom', 'start', 'end'):
            getattr(box, f'set_margin_{margin}')(18)
        label = Gtk.Label(label=field_label)
        label.set_xalign(0)
        entry = Gtk.Entry()
        entry.set_hexpand(True)
        entry.set_activates_default(True)
        entry.set_text(initial or '')
        entry.set_position(-1)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        buttons.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label='取消')
        save = Gtk.Button(label='保存')
        buttons.append(cancel)
        buttons.append(save)
        box.append(label)
        box.append(entry)
        box.append(buttons)
        window.set_child(box)
        window.set_default_widget(save)

        cancel.connect('clicked', lambda _button: window.close())
        save.connect('clicked', lambda _button: on_save(window, entry))
        window.connect('close-request', self._on_editor_close, uri)
        key_controller = Gtk.EventControllerKey()
        key_controller.connect('key-pressed', self._on_editor_key, window)
        window.add_controller(key_controller)

        self._dialogs[uri] = window
        window.present()
        entry.grab_focus()

    def _on_editor_close(self, _window, uri):
        self._dialogs.pop(uri, None)
        return False

    def _on_editor_key(self, _controller, keyval, _keycode, _state, window):
        if keyval == Gdk.KEY_Escape:
            window.close()
            return True
        return False

    def _show_error(self, message, detail, parent=None):
        alert = Gtk.AlertDialog()
        alert.set_message(message)
        alert.set_detail(detail)
        alert.set_buttons(['确定'])
        self._alerts.add(alert)
        if parent is None:
            parent = _active_window()

        def on_alert_done(_alert, result, _user_data):
            try:
                alert.choose_finish(result)
            except GLib.Error:
                pass
            self._alerts.discard(alert)

        alert.choose(parent, None, on_alert_done, None)

    def _save_desc(self, window, entry, file, folder):
        value = entry.get_text().strip()
        try:
            if value:
                _write_desc(folder, value)
            else:
                # Empty input clears the description; the yaml file goes
                # with it when no other data remains.
                _remove_key_in_folder(folder, ATTR)
            _yaml_cache.pop(folder, None)
            _apply(file)
            file.invalidate_extension_info()
        except Exception as error:
            traceback.print_exc()
            self._show_error('无法修改描述',
                             str(error) or '写入 .folder.yaml 失败。',
                             parent=window)
            return
        window.close()

    def _save_file_desc(self, window, entry, file, folder, filename):
        value = entry.get_text().strip()
        try:
            if value:
                _write_file_desc(folder, filename, value)
            else:
                # Empty input clears the annotation; an emptied file-desc
                # mapping and an emptied yaml file both go with it. The
                # token goes too, or the next refresh would adopt it back.
                _remove_file_desc_in_folder(folder, filename)
                _clear_token(os.path.join(folder, filename))
            _yaml_cache.pop(folder, None)
            _apply(file)
            file.invalidate_extension_info()
        except Exception as error:
            traceback.print_exc()
            self._show_error('无法修改注释',
                             str(error) or '写入 .folder.yaml 失败。',
                             parent=window)
            return
        window.close()

    def get_background_items(self, current_folder):
        item = Nautilus.MenuItem(
            name='FolderMeta::ToggleDesc',
            label='隐藏描述' if _enabled() else '显示描述',
            tip='在文件夹名下方显示 .folder.yaml 中的 desc',
            icon=None,
        )
        item.connect('activate', self._on_toggle, current_folder)
        return [item]

    def _on_toggle(self, _item, current_folder):
        try:
            on = not _enabled()
            _set_enabled(on)
            _sync_captions(on)
            _refresh_folder(current_folder)
            # Nautilus builds the extension menus once per folder view and
            # has no "rebuild now" API for them, but it does rebuild when
            # the current folder's own file changes: re-adding the attribute
            # fires nautilus_file_changed on it, which schedules a menu
            # refresh, so the label flips to match the new state.
            current_folder.add_string_attribute(
                ATTR, current_folder.get_string_attribute(ATTR) or '')
        except Exception:
            traceback.print_exc()


class FolderMetaColumns(GObject.GObject, Nautilus.ColumnProvider):
    """A "描述" list-view column fed by the same `desc` attribute."""

    def get_columns(self):
        return [Nautilus.Column(
            name=DESC_COLUMN,
            attribute=ATTR,
            label='描述',
            description='文件夹描述或文件注释(.folder.yaml)',
        )]


# Keep the icon-view captions in sync from the start (switch defaults to on).
_sync_captions(_enabled())
