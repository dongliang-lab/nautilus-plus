import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from urllib.parse import unquote, urlparse


class _Settings:
    def __init__(self):
        self.values = {'captions': []}

    @classmethod
    def new(cls, schema):
        return cls()

    def get_strv(self, key):
        return list(self.values.get(key, []))

    def set_strv(self, key, value):
        self.values[key] = list(value)


class _MenuItem:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def connect(self, *_args):
        pass


class _Column:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FileInfo:
    def __init__(self, uri, directory=True):
        self.uri = uri
        self.directory = directory
        self.attributes = {}

    def is_directory(self):
        return self.directory

    def get_uri(self):
        return self.uri

    def add_string_attribute(self, name, value):
        self.attributes[name] = value

    def invalidate_extension_info(self):
        pass


class _GObject:
    class GObject:
        def __init__(self):
            pass


class _Nautilus:
    class InfoProvider:
        pass

    class MenuProvider:
        pass

    class ColumnProvider:
        pass

    MenuItem = _MenuItem
    Column = _Column
    FileInfo = _FileInfo


class _Gio:
    Settings = _Settings
    FileQueryInfoFlags = types.SimpleNamespace(NONE=0)

    class Application:
        @staticmethod
        def get_default():
            return None


class _GLib:
    class Error(Exception):
        pass

    idle_queue = []

    @classmethod
    def idle_add(cls, func, *args):
        cls.idle_queue.append((func, args))
        return len(cls.idle_queue)

    @classmethod
    def run_idle(cls):
        """Run queued idle callbacks until the queue is empty."""
        while cls.idle_queue:
            func, args = cls.idle_queue.pop(0)
            func(*args)

    @staticmethod
    def filename_from_uri(uri):
        parsed = urlparse(uri)
        return unquote(parsed.path), None


class _Column:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _ColumnViewColumn:
    def __init__(self, column_id, visible=True):
        self._id = column_id
        self._visible = visible
        self._expand = False
        self._fixed_width = -1

    def get_id(self):
        return self._id

    def get_visible(self):
        return self._visible

    def set_visible(self, visible):
        self._visible = visible

    def get_expand(self):
        return self._expand

    def set_expand(self, expand):
        self._expand = expand

    def get_fixed_width(self):
        return self._fixed_width

    def set_fixed_width(self, width):
        self._fixed_width = width


class _Widget:
    """Minimal widget: a chain of children plus a measured natural width."""

    natural = 0

    def __init__(self, children=()):
        self._children = list(children)
        for index, child in enumerate(self._children):
            child._next_sibling = (self._children[index + 1]
                                   if index + 1 < len(self._children) else None)

    def get_first_child(self):
        return self._children[0] if self._children else None

    def get_next_sibling(self):
        return getattr(self, '_next_sibling', None)

    def measure(self, orientation, size):
        return (self.natural, self.natural, self.natural, self.natural)


# The fitting code recognizes widgets by class name (the real ones are C
# types it cannot import), so the stubs carry the production names.
NautilusNameCell = type('NautilusNameCell', (_Widget,), {'natural': 0})
GtkColumnViewTitle = type('GtkColumnViewTitle', (_Widget,), {'natural': 0})


class _ColumnView(_Widget):
    def __init__(self, columns, children=()):
        super().__init__(children)
        self._columns = list(columns)

    def get_columns(self):
        return self._columns


class _ListModel:
    def __init__(self, items):
        self._items = list(items)

    def get_n_items(self):
        return len(self._items)

    def get_item(self, index):
        return self._items[index]


class _Toplevel(_Widget):
    """Stand-in for a top-level window (named apart from the dialog stub)."""

    toplevels = []

    @classmethod
    def get_toplevels(cls):
        return _ListModel(cls.toplevels)


class _Gtk:
    Orientation = types.SimpleNamespace(VERTICAL=1, HORIZONTAL=2)
    Align = types.SimpleNamespace(END=1)
    ColumnView = _ColumnView
    Window = _Toplevel
    Orientation = types.SimpleNamespace(VERTICAL=1, HORIZONTAL=2)


class _Gdk:
    KEY_Escape = 65307


def _load_extension():
    temp_home = tempfile.TemporaryDirectory()
    os.environ['HOME'] = temp_home.name
    repository = types.ModuleType('gi.repository')
    repository.Gdk = _Gdk
    repository.Gio = _Gio
    repository.GLib = _GLib
    repository.GObject = _GObject
    repository.Gtk = _Gtk
    repository.Nautilus = _Nautilus
    gi = types.ModuleType('gi')
    gi.repository = repository
    # The real gi exposes this; the extension calls it to pin GI versions.
    gi.require_version = lambda name, version: None
    sys.modules['gi'] = gi
    sys.modules['gi.repository'] = repository

    path = Path(__file__).with_name('nautilus-meta.py')
    spec = importlib.util.spec_from_file_location('nautilus_meta', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._test_home = temp_home
    return module


nautilus_meta = _load_extension()


class FolderYamlTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / nautilus_meta.YAML_NAME

    def tearDown(self):
        self.folder.cleanup()

    def test_creates_yaml(self):
        nautilus_meta._write_desc(self.folder.name, '新项目')
        self.assertEqual(self.path.read_text(encoding='utf-8'), 'desc: 新项目\n')

    def test_replaces_value_and_preserves_comments_and_fields(self):
        original = '# header\ndesc: old  # keep this\nother: y\n'
        self.path.write_text(original, encoding='utf-8')
        nautilus_meta._write_desc(self.folder.name, '新项目')
        self.assertEqual(
            self.path.read_text(encoding='utf-8'),
            '# header\ndesc: 新项目  # keep this\nother: y\n',
        )

    def test_appends_missing_key_before_document_end(self):
        self.path.write_text('other: y\n...\n', encoding='utf-8')
        nautilus_meta._write_desc(self.folder.name, '新项目')
        self.assertEqual(
            self.path.read_text(encoding='utf-8'),
            'other: y\ndesc: 新项目\n...\n',
        )

    def test_replaces_block_scalar_with_single_line_value(self):
        original = 'desc: >\n  old\nother: y\n'
        self.path.write_text(original, encoding='utf-8')
        nautilus_meta._write_desc(self.folder.name, '新项目')
        self.assertEqual(
            self.path.read_text(encoding='utf-8'),
            'desc: 新项目\nother: y\n',
        )

    def test_rejects_duplicate_name_keys_without_overwriting(self):
        original = 'desc: one\ndesc: two\n'
        self.path.write_text(original, encoding='utf-8')
        with self.assertRaises(ValueError):
            nautilus_meta._write_desc(self.folder.name, '新项目')
        self.assertEqual(self.path.read_text(encoding='utf-8'), original)

    def test_updates_flow_mapping(self):
        self.path.write_text('{other: y}\n', encoding='utf-8')
        nautilus_meta._write_desc(self.folder.name, '新项目')
        self.assertEqual(
            self.path.read_text(encoding='utf-8'),
            '{other: y, desc: 新项目}\n',
        )

    def test_rejects_invalid_yaml_without_overwriting(self):
        original = 'other: [\n'
        self.path.write_text(original, encoding='utf-8')
        with self.assertRaises(ValueError):
            nautilus_meta._write_desc(self.folder.name, '新项目')
        self.assertEqual(self.path.read_text(encoding='utf-8'), original)

    def test_rejects_non_mapping_without_overwriting(self):
        original = '- one\n- two\n'
        self.path.write_text(original, encoding='utf-8')
        with self.assertRaises(ValueError):
            nautilus_meta._write_desc(self.folder.name, '新项目')
        self.assertEqual(self.path.read_text(encoding='utf-8'), original)

    def test_empty_value_removes_key_and_file(self):
        self.path.write_text('desc: 旧名\n', encoding='utf-8')
        nautilus_meta._remove_key_in_folder(self.folder.name,
                                              nautilus_meta.ATTR)
        self.assertFalse(self.path.exists())

    def test_empty_value_keeps_other_fields(self):
        original = '# header\ndesc: old  # keep\nother: y\n'
        self.path.write_text(original, encoding='utf-8')
        nautilus_meta._remove_key_in_folder(self.folder.name,
                                              nautilus_meta.ATTR)
        self.assertEqual(
            self.path.read_text(encoding='utf-8'),
            '# header\nother: y\n',
        )

    def test_remove_without_key_leaves_file_alone(self):
        original = 'other: y\n'
        self.path.write_text(original, encoding='utf-8')
        nautilus_meta._remove_key_in_folder(self.folder.name,
                                              nautilus_meta.ATTR)
        self.assertEqual(self.path.read_text(encoding='utf-8'), original)

    def test_remove_missing_file_is_noop(self):
        nautilus_meta._remove_key_in_folder(self.folder.name,
                                              nautilus_meta.ATTR)
        self.assertFalse(self.path.exists())

    def test_rejects_blank_and_multiline_values(self):
        with self.assertRaises(ValueError):
            nautilus_meta._write_desc(self.folder.name, 'one\ntwo')
        self.assertFalse(self.path.exists())


class CaptionsMigrationTests(unittest.TestCase):
    """Captions written before the name-zh -> desc rename are carried over.

    Missing this would leave an unresolvable caption line behind *and* make
    the code clobber the user's original caption backup.
    """

    def setUp(self):
        self._saved = nautilus_meta._captions()
        nautilus_meta._clear_captions_backup()

    def tearDown(self):
        nautilus_meta._set_captions(self._saved)
        nautilus_meta._clear_captions_backup()

    def test_legacy_caption_is_renamed_in_place(self):
        nautilus_meta._set_captions(['name-zh'])
        nautilus_meta._sync_captions(True)
        self.assertEqual(nautilus_meta._captions(), ['desc'])

    def test_rename_does_not_clobber_the_backup(self):
        nautilus_meta._save_captions_backup(['none', 'none', 'none'])
        nautilus_meta._set_captions(['name-zh'])
        nautilus_meta._sync_captions(True)
        self.assertEqual(nautilus_meta._load_captions_backup(),
                         ['none', 'none', 'none'])

    def test_backup_with_legacy_name_is_normalized(self):
        nautilus_meta._save_captions_backup(['name-zh', 'size'])
        self.assertEqual(nautilus_meta._load_captions_backup(),
                         ['desc', 'size'])

    def test_duplicates_collapse(self):
        nautilus_meta._set_captions(['name-zh', 'desc'])
        nautilus_meta._sync_captions(True)
        self.assertEqual(nautilus_meta._captions(), ['desc'])

    def test_disabling_drops_the_legacy_caption(self):
        nautilus_meta._set_captions(['name-zh', 'size'])
        nautilus_meta._sync_captions(False)
        self.assertEqual(nautilus_meta._captions(), ['size'])


class MenuFilterTests(unittest.TestCase):
    def test_only_single_local_folder_gets_menu(self):
        menu = nautilus_meta.FolderMetaMenu()
        folder = _FileInfo('file:///tmp/project')
        remote_folder = _FileInfo('sftp://host/project')
        items = menu.get_file_items([folder])
        labels = [item.kwargs['label'] for item in items]
        self.assertEqual(labels, ['修改描述'])
        self.assertEqual(menu.get_file_items([folder, remote_folder]), [])
        self.assertEqual(menu.get_file_items([remote_folder]), [])

    def test_multi_select_shows_nothing(self):
        menu = nautilus_meta.FolderMetaMenu()
        folders = [_FileInfo('file:///tmp/a'), _FileInfo('file:///tmp/b')]
        self.assertEqual(menu.get_file_items(folders), [])

    def test_single_local_file_gets_annotation_menu(self):
        menu = nautilus_meta.FolderMetaMenu()
        regular_file = _FileInfo('file:///tmp/notes.txt', directory=False)
        items = menu.get_file_items([regular_file])
        self.assertEqual([item.kwargs['label'] for item in items], ['修改注释'])

    def test_remote_file_gets_nothing(self):
        menu = nautilus_meta.FolderMetaMenu()
        remote_file = _FileInfo('sftp://host/notes.txt', directory=False)
        self.assertEqual(menu.get_file_items([remote_file]), [])


class ColumnsTests(unittest.TestCase):
    def test_one_column_fed_by_the_desc_attribute(self):
        columns = nautilus_meta.FolderMetaColumns().get_columns()
        self.assertEqual(len(columns), 1)
        self.assertEqual(columns[0].kwargs['attribute'], nautilus_meta.ATTR)
        self.assertEqual(columns[0].kwargs['label'], '描述')
        self.assertEqual(columns[0].kwargs['name'], nautilus_meta.DESC_COLUMN)

    def tearDown(self):
        _Toplevel.toplevels = []
        nautilus_meta._name_widths.clear()
        nautilus_meta._user_widths.clear()

    def _view(self, desc_visible=True, name_natural=240, title_natural=30):
        name = _ColumnViewColumn('name')
        name.set_expand(True)  # what nautilus itself sets up
        desc = _ColumnViewColumn(nautilus_meta.DESC_COLUMN,
                                 visible=desc_visible)
        size = _ColumnViewColumn('size')
        cells = [NautilusNameCell() for _ in range(3)]
        for cell in cells:
            cell.natural = name_natural
        title = GtkColumnViewTitle()
        title.natural = title_natural
        body = _Widget(cells)
        view = _ColumnView([name, desc, size], children=[title, body])
        _Toplevel.toplevels = [_Toplevel([view])]
        return name, desc, size

    def test_desc_visible_sizes_name_to_its_content(self):
        name, desc, size = self._view()
        nautilus_meta._fit_columns()
        self.assertFalse(name.get_expand())
        self.assertTrue(desc.get_expand())
        self.assertFalse(size.get_expand())
        self.assertEqual(name.get_fixed_width(), 240)

    def test_name_width_never_below_the_header(self):
        name, _desc, _size = self._view(name_natural=10, title_natural=90)
        nautilus_meta._fit_columns()
        self.assertEqual(name.get_fixed_width(), 90)

    def test_desc_hidden_restores_nautilus_layout(self):
        name, desc, _size = self._view(desc_visible=False)
        nautilus_meta._fit_columns()
        self.assertTrue(name.get_expand())
        self.assertFalse(desc.get_expand())
        self.assertEqual(name.get_fixed_width(), -1)

    def test_hiding_the_desc_column_later_restores_name_expand(self):
        name, desc, _size = self._view()
        nautilus_meta._fit_columns()
        self.assertFalse(name.get_expand())
        desc.set_visible(False)
        nautilus_meta._fit_columns()
        self.assertTrue(name.get_expand())
        self.assertEqual(name.get_fixed_width(), -1)

    def test_hand_dragged_width_is_kept(self):
        name, _desc, _size = self._view()
        nautilus_meta._fit_columns()
        name.set_fixed_width(500)  # user drags the divider
        nautilus_meta._fit_columns()
        self.assertEqual(name.get_fixed_width(), 500)
        # A later refresh keeps respecting it, even with longer names.
        for cell in _Toplevel.toplevels[0]._children[0]._children[1]._children:
            cell.natural = 700
        nautilus_meta._fit_columns()
        self.assertEqual(name.get_fixed_width(), 500)

    def test_view_without_our_column_is_untouched(self):
        name = _ColumnViewColumn('name')
        name.set_expand(True)
        size = _ColumnViewColumn('size')
        _Toplevel.toplevels = [_Toplevel([_ColumnView([name, size])])]
        nautilus_meta._fit_columns()
        self.assertTrue(name.get_expand())
        self.assertEqual(name.get_fixed_width(), -1)

    def test_nested_view_is_found(self):
        name = _ColumnViewColumn('name')
        name.set_expand(True)
        desc = _ColumnViewColumn(nautilus_meta.DESC_COLUMN)
        title = GtkColumnViewTitle()
        title.natural = 40
        view = _ColumnView([name, desc], children=[title])
        inner = _Widget([view])
        _Toplevel.toplevels = [_Toplevel([_Widget([inner])])]
        nautilus_meta._fit_columns()
        self.assertFalse(name.get_expand())
        self.assertTrue(desc.get_expand())
        self.assertEqual(name.get_fixed_width(), 40)

    def test_missing_columns_never_raises(self):
        class Boom:
            def get_columns(self):
                raise RuntimeError('internals changed')

        _Toplevel.toplevels = [_Toplevel([Boom()])]
        nautilus_meta._fit_columns()  # must not raise

    def test_schedule_fits_once_per_idle_pass(self):
        _GLib.idle_queue.clear()
        name, desc, _size = self._view()
        nautilus_meta._fit_scheduled = False
        nautilus_meta._schedule_fit()
        nautilus_meta._schedule_fit()
        nautilus_meta._schedule_fit()
        self.assertEqual(len(_GLib.idle_queue), 1)
        _GLib.run_idle()
        self.assertFalse(name.get_expand())
        self.assertTrue(desc.get_expand())
        # A later refresh schedules again.
        nautilus_meta._schedule_fit()
        self.assertEqual(len(_GLib.idle_queue), 1)


class FileDescYamlTests(unittest.TestCase):
    """file-desc holds per-file annotations in the folder's .folder.yaml."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / nautilus_meta.YAML_NAME

    def tearDown(self):
        self.folder.cleanup()

    def read(self):
        return self.path.read_text(encoding='utf-8')

    def test_creates_block_mapping(self):
        nautilus_meta._write_file_desc(self.folder.name, 'notes.txt', '会议记录')
        self.assertEqual(self.read(), 'file-desc:\n  notes.txt: 会议记录\n')

    def test_appends_to_existing_block_mapping(self):
        self.path.write_text('desc: 项目\nfile-desc:\n  a.txt: 甲\n',
                             encoding='utf-8')
        nautilus_meta._write_file_desc(self.folder.name, 'b.txt', '乙')
        self.assertEqual(self.read(),
                         'desc: 项目\nfile-desc:\n  a.txt: 甲\n  b.txt: 乙\n')

    def test_replaces_one_entry_and_keeps_its_comment(self):
        self.path.write_text('file-desc:\n  a.txt: 旧  # keep\n  b.txt: 乙\n',
                             encoding='utf-8')
        nautilus_meta._write_file_desc(self.folder.name, 'a.txt', '新')
        self.assertEqual(self.read(),
                         'file-desc:\n  a.txt: 新  # keep\n  b.txt: 乙\n')

    def test_extends_flow_mapping(self):
        self.path.write_text('file-desc: {a.txt: 甲}\n', encoding='utf-8')
        nautilus_meta._write_file_desc(self.folder.name, 'b.txt', '乙')
        self.assertEqual(self.read(), 'file-desc: {a.txt: 甲, b.txt: 乙}\n')

    def test_quotes_awkward_file_names(self):
        nautilus_meta._write_file_desc(self.folder.name, 'a: b.txt', '含冒号')
        self.assertEqual(self.read(), "file-desc:\n  'a: b.txt': 含冒号\n")

    def test_rejects_duplicate_entries_without_overwriting(self):
        original = 'file-desc:\n  a.txt: 甲\n  a.txt: 乙\n'
        self.path.write_text(original, encoding='utf-8')
        with self.assertRaises(ValueError):
            nautilus_meta._write_file_desc(self.folder.name, 'a.txt', '新')
        self.assertEqual(self.read(), original)

    def test_rejects_non_mapping_file_desc(self):
        original = 'file-desc:\n  - a.txt\n'
        self.path.write_text(original, encoding='utf-8')
        with self.assertRaises(ValueError):
            nautilus_meta._write_file_desc(self.folder.name, 'a.txt', '甲')
        self.assertEqual(self.read(), original)

    def test_rejects_blank_annotation(self):
        self.path.write_text('file-desc:\n  a.txt: 甲\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            nautilus_meta._write_file_desc(self.folder.name, 'a.txt', '   ')

    def test_removing_an_entry_keeps_the_others(self):
        self.path.write_text(
            'desc: 项目\nfile-desc:\n  a.txt: 甲\n  b.txt: 乙\n',
            encoding='utf-8')
        nautilus_meta._remove_file_desc_in_folder(self.folder.name, 'a.txt')
        self.assertEqual(self.read(), 'desc: 项目\nfile-desc:\n  b.txt: 乙\n')

    def test_removing_the_last_entry_drops_the_key(self):
        self.path.write_text('desc: 项目\nfile-desc:\n  a.txt: 甲\n',
                             encoding='utf-8')
        nautilus_meta._remove_file_desc_in_folder(self.folder.name, 'a.txt')
        self.assertEqual(self.read(), 'desc: 项目\n')

    def test_removing_the_last_entry_drops_an_empty_file(self):
        self.path.write_text('file-desc:\n  a.txt: 甲\n', encoding='utf-8')
        nautilus_meta._remove_file_desc_in_folder(self.folder.name, 'a.txt')
        self.assertFalse(self.path.exists())

    def test_removing_an_unknown_entry_keeps_the_file(self):
        original = 'file-desc:\n  a.txt: 甲\n'
        self.path.write_text(original, encoding='utf-8')
        nautilus_meta._remove_file_desc_in_folder(self.folder.name, 'zzz.txt')
        self.assertEqual(self.read(), original)

    def test_removal_without_a_yaml_file_does_nothing(self):
        nautilus_meta._remove_file_desc_in_folder(self.folder.name, 'a.txt')
        self.assertFalse(self.path.exists())

    def test_lookup_skips_blank_annotations(self):
        for name in ('a.txt', '空.txt', 'b.txt'):
            (Path(self.folder.name) / name).write_text('', encoding='utf-8')
        self.path.write_text(
            'file-desc:\n  a.txt: 甲\n  空.txt: "  "\n  b.txt: 乙\n',
            encoding='utf-8')
        self.assertEqual(nautilus_meta._yaml_file_descs(self.folder.name),
                         {'a.txt': '甲', 'b.txt': '乙'})


class ApplyAnnotationTests(unittest.TestCase):
    """A file's annotation is read from its parent folder's .folder.yaml."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / nautilus_meta.YAML_NAME
        self.addCleanup(self.folder.cleanup)
        for cache in (nautilus_meta._shown, nautilus_meta._yaml_cache):
            cache.clear()
        self.addCleanup(nautilus_meta._shown.clear)
        self.addCleanup(nautilus_meta._yaml_cache.clear)

    def item(self, name='notes.txt'):
        uri = 'file://' + os.path.join(self.folder.name, name)
        return _FileInfo(uri, directory=False)

    def write(self, text):
        self.path.write_text(text, encoding='utf-8')
        nautilus_meta._yaml_cache.clear()

    def touch(self, name):
        """Annotations only survive for files that exist."""
        (Path(self.folder.name) / name).write_text('', encoding='utf-8')
        nautilus_meta._yaml_cache.clear()

    def test_annotation_becomes_the_description_attribute(self):
        self.touch('notes.txt')
        self.write('file-desc:\n  notes.txt: 会议记录\n')
        item = self.item()
        nautilus_meta._apply(item)
        self.assertEqual(item.attributes.get('desc'), '会议记录')

    def test_file_without_annotation_gets_none(self):
        self.write('desc: 项目\n')
        item = self.item()
        nautilus_meta._apply(item)
        self.assertNotIn('desc', item.attributes)

    def test_blank_annotation_is_not_shown(self):
        self.touch('notes.txt')
        self.write('file-desc:\n  notes.txt: "  "\n')
        item = self.item()
        nautilus_meta._apply(item)
        self.assertNotIn('desc', item.attributes)

    def test_switch_off_hides_annotations(self):
        self.touch('notes.txt')
        self.write('file-desc:\n  notes.txt: 会议记录\n')
        nautilus_meta._set_enabled(False)
        self.addCleanup(nautilus_meta._set_enabled, True)
        item = self.item()
        nautilus_meta._apply(item)
        self.assertNotIn('desc', item.attributes)

    def test_removed_annotation_clears_a_shown_one(self):
        self.touch('notes.txt')
        self.write('file-desc:\n  notes.txt: 会议记录\n')
        item = self.item()
        nautilus_meta._apply(item)
        self.assertEqual(item.attributes.get('desc'), '会议记录')
        self.write('desc: 项目\n')
        nautilus_meta._apply(item)
        self.assertEqual(item.attributes.get('desc'), '')

    def test_other_files_in_the_folder_are_unaffected(self):
        self.touch('notes.txt')
        self.write('file-desc:\n  notes.txt: 会议记录\n')
        other = self.item('other.txt')
        nautilus_meta._apply(other)
        self.assertNotIn('desc', other.attributes)

    def test_entry_whose_file_is_gone_is_dropped(self):
        self.touch('here.txt')
        self.write('desc: 项目\nfile-desc:\n  gone.txt: 会议记录\n  here.txt: 备注\n')
        nautilus_meta._apply(self.item('here.txt'))
        self.assertEqual(
            self.path.read_text(encoding='utf-8'),
            'desc: 项目\nfile-desc:\n  here.txt: 备注\n',
        )


class _Entry:
    def __init__(self, text):
        self._text = text

    def get_text(self):
        return self._text


class _Window:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def _xattrs_supported(directory):
    probe = Path(directory) / 'xattr-probe'
    probe.write_text('', encoding='utf-8')
    try:
        os.setxattr(str(probe), 'user.nautilus-plus.probe', b'x')
        os.removexattr(str(probe), 'user.nautilus-plus.probe')
    except OSError:
        return False
    return True


class AnnotationTokenTests(unittest.TestCase):
    """Annotations travel with the file, through renames and moves."""

    def setUp(self):
        self.here = tempfile.TemporaryDirectory()
        self.addCleanup(self.here.cleanup)
        if not _xattrs_supported(self.here.name):
            self.skipTest('filesystem does not support user xattrs')
        self.there = tempfile.TemporaryDirectory()
        self.addCleanup(self.there.cleanup)
        for cache in (nautilus_meta._shown, nautilus_meta._yaml_cache):
            cache.clear()
        self.addCleanup(nautilus_meta._shown.clear)
        self.addCleanup(nautilus_meta._yaml_cache.clear)

    def yaml_text(self, folder):
        path = Path(folder) / nautilus_meta.YAML_NAME
        return path.read_text(encoding='utf-8') if path.exists() else ''

    def touch(self, folder, name):
        path = Path(folder) / name
        path.write_text('', encoding='utf-8')
        nautilus_meta._yaml_cache.clear()
        return str(path)

    def item(self, path):
        return _FileInfo('file://' + path, directory=False)

    def annotate(self, folder, name, text):
        """What saving through the dialog leaves behind: yaml entry, token."""
        path = self.touch(folder, name)
        nautilus_meta._write_file_desc(folder, name, text)
        nautilus_meta._apply(self.item(path))
        return path

    def test_annotation_leaves_a_token_on_the_file(self):
        path = self.annotate(self.here.name, 'notes.txt', '会议记录')
        self.assertEqual(nautilus_meta._read_token(path), {
            'folder': self.here.name, 'name': 'notes.txt', 'desc': '会议记录',
        })

    def test_annotation_follows_a_rename_in_place(self):
        path = self.annotate(self.here.name, 'notes.txt', '会议记录')
        renamed = os.path.join(self.here.name, 'renamed.txt')
        os.rename(path, renamed)
        nautilus_meta._yaml_cache.clear()

        item = self.item(renamed)
        nautilus_meta._apply(item)

        self.assertEqual(item.attributes.get('desc'), '会议记录')
        self.assertEqual(self.yaml_text(self.here.name),
                         'file-desc:\n  renamed.txt: 会议记录\n')
        self.assertEqual(nautilus_meta._read_token(renamed), {
            'folder': self.here.name, 'name': 'renamed.txt', 'desc': '会议记录',
        })

    def test_annotation_follows_a_move_to_another_folder(self):
        path = self.annotate(self.here.name, 'notes.txt', '会议记录')
        moved = os.path.join(self.there.name, 'notes.txt')
        os.rename(path, moved)
        nautilus_meta._yaml_cache.clear()

        item = self.item(moved)
        nautilus_meta._apply(item)

        self.assertEqual(item.attributes.get('desc'), '会议记录')
        self.assertEqual(self.yaml_text(self.there.name),
                         'file-desc:\n  notes.txt: 会议记录\n')

        # The folder it left behind drops the stale entry the next time its
        # metadata is loaded (nothing else would ever revisit it).
        nautilus_meta._yaml_file_descs(self.here.name)
        self.assertEqual(self.yaml_text(self.here.name), '')

    def test_hand_deleted_entry_is_not_resurrected(self):
        path = self.annotate(self.here.name, 'notes.txt', '会议记录')
        nautilus_meta._remove_file_desc_in_folder(self.here.name, 'notes.txt')
        nautilus_meta._yaml_cache.clear()

        item = self.item(path)
        nautilus_meta._apply(item)

        self.assertEqual(item.attributes.get('desc', ''), '')
        self.assertIsNone(nautilus_meta._read_token(path))
        self.assertNotIn('notes.txt', self.yaml_text(self.here.name))

    def test_yaml_wins_over_a_stale_token(self):
        path = self.annotate(self.here.name, 'notes.txt', '会议记录')
        nautilus_meta._write_token(path, self.here.name, 'notes.txt', '旧文本')
        nautilus_meta._apply(self.item(path))
        self.assertEqual(nautilus_meta._read_token(path)['desc'], '会议记录')

    def test_saving_through_the_dialog_writes_the_token(self):
        path = self.touch(self.here.name, 'notes.txt')
        nautilus_meta.FolderMetaMenu()._save_file_desc(
            _Window(), _Entry('会议记录'), self.item(path),
            self.here.name, 'notes.txt')
        self.assertEqual(nautilus_meta._read_token(path)['desc'], '会议记录')

    def test_clearing_through_the_dialog_removes_the_token(self):
        path = self.annotate(self.here.name, 'notes.txt', '会议记录')
        window = _Window()
        nautilus_meta.FolderMetaMenu()._save_file_desc(
            window, _Entry('   '), self.item(path),
            self.here.name, 'notes.txt')
        self.assertTrue(window.closed)
        self.assertIsNone(nautilus_meta._read_token(path))
        self.assertNotIn('notes.txt', self.yaml_text(self.here.name))
