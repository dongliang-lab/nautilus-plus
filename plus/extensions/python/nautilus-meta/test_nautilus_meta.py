import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from urllib.parse import unquote, urlparse


class _Settings:
    instances = []

    def __init__(self):
        self.values = {'captions': []}
        self.handlers = {}

    @classmethod
    def new(cls, schema):
        instance = cls()
        instance.schema = schema
        cls.instances.append(instance)
        return instance

    @classmethod
    def for_schema(cls, schema):
        """The instance the extension itself created for this schema."""
        for instance in reversed(cls.instances):
            if instance.schema == schema:
                return instance
        return None

    @classmethod
    def forget(cls):
        cls.instances = []

    def connect(self, signal, callback):
        self.handlers[signal] = callback
        return len(self.handlers)

    def emit(self, signal):
        """Pretend the user changed a preference."""
        callback = self.handlers.get(signal)
        if callback is not None:
            callback(self, signal.split('::')[-1])

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
    timeout_queue = []

    @classmethod
    def timeout_add(cls, delay, func, *args):
        cls.timeout_queue.append((delay, func, args))
        return len(cls.timeout_queue)

    @classmethod
    def run_timeouts(cls):
        """Fire every queued timeout, as the main loop eventually would."""
        while cls.timeout_queue:
            _delay, func, args = cls.timeout_queue.pop(0)
            func(*args)

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


class _PangoLayout:
    """Text measured at a fixed 10px per character, so widths stay readable."""

    def __init__(self, text):
        self._text = text

    def get_pixel_size(self):
        return (len(self._text) * 10, 18)


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


class _Label(_Widget):
    """Label stub; its natural width is 10px per character."""

    def __init__(self, text=''):
        super().__init__()
        self._text = text
        self.natural = len(text) * 10

    def get_text(self):
        return self._text

    def create_pango_layout(self, text=None):
        return _PangoLayout(self._text if text is None else text)


# The fitting code recognizes cells by class name (the real ones are C types
# it cannot import), so these stubs carry the production names.
class NautilusNameCell(_Widget):
    """Name cell stub: an icon plus the file name label."""

    def __init__(self, file_name='', overhead=88):
        label = _Label(file_name)
        super().__init__([_Widget(), label])
        self.natural = overhead + label.natural


class NautilusLabelCell(_Widget):
    """Plain text cell stub (type, size, dates, and our own description)."""

    def __init__(self, text=''):
        super().__init__([_Label(text)])
        self.natural = 12 + len(text) * 10


class GtkColumnViewTitle(_Widget):
    def __init__(self, text='', natural=0):
        super().__init__([_Label(text)])
        self.natural = natural or len(text) * 10


class _File:
    def __init__(self, name, folder='file:///tmp/demo'):
        self._name = name
        self._uri = '%s/%s' % (folder, name)

    def get_name(self):
        return self._name

    def get_uri(self):
        return self._uri


class _ViewItem:
    def __init__(self, file):
        self._file = file

    def get_property(self, name):
        if name != 'file':
            raise TypeError('no such property: %s' % name)
        return self._file


class _TreeListRow:
    def __init__(self, file):
        self._file = file

    def get_item(self):
        return _ViewItem(self._file)


class _ViewRowModel:
    """List-view model: every row wraps a view item carrying the file."""

    def __init__(self, names=(), folder='file:///tmp/demo'):
        self.folder = folder
        self.names = list(names)
        self.handlers = {}

    def get_n_items(self):
        return len(self.names)

    def get_item(self, index):
        return _TreeListRow(_File(self.names[index], self.folder))

    def connect(self, signal, callback):
        self.handlers[signal] = callback
        return len(self.handlers)

    def set_names(self, names, folder=None):
        """Swap the folder contents, as entering another folder does."""
        self.names = list(names)
        if folder is not None:
            self.folder = folder
        callback = self.handlers.get('items-changed')
        if callback is not None:
            callback(self, 0, 0, len(self.names))


class _ColumnView(_Widget):
    def __init__(self, columns, children=(), model=None, width=1000):
        super().__init__(children)
        self._columns = list(columns)
        self._model = model
        self._width = width
        self._css = set()
        self.handlers = {}

    def get_columns(self):
        return self._columns

    def get_model(self):
        return self._model

    def set_model(self, model):
        self._model = model
        callback = self.handlers.get('notify::model')
        if callback is not None:
            callback(self, None)

    def get_width(self):
        return self._width

    def connect(self, signal, callback):
        self.handlers[signal] = callback
        return len(self.handlers)

    def add_css_class(self, name):
        self._css.add(name)

    def remove_css_class(self, name):
        self._css.discard(name)

    def has_css_class(self, name):
        return name in self._css


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


class _CssProvider:
    def __init__(self):
        self.text = ''

    def load_from_string(self, text):
        self.text = text


class _StyleContext:
    added = []

    @classmethod
    def add_provider_for_display(cls, display, provider, priority):
        cls.added.append(provider)


class _Gtk:
    Orientation = types.SimpleNamespace(VERTICAL=1, HORIZONTAL=2)
    Align = types.SimpleNamespace(END=1)
    ColumnView = _ColumnView
    Window = _Toplevel
    Label = _Label
    CssProvider = _CssProvider
    StyleContext = _StyleContext
    STYLE_PROVIDER_PRIORITY_APPLICATION = 600


class _Display:
    @classmethod
    def get_default(cls):
        return cls()


class _Gdk:
    KEY_Escape = 65307
    Display = _Display


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
    """The description column is placed right after a fitted name column."""

    def test_one_column_fed_by_the_desc_attribute(self):
        columns = nautilus_meta.FolderMetaColumns().get_columns()
        self.assertEqual(len(columns), 1)
        self.assertEqual(columns[0].kwargs['attribute'], nautilus_meta.ATTR)
        self.assertEqual(columns[0].kwargs['label'], '描述')
        self.assertEqual(columns[0].kwargs['name'], nautilus_meta.DESC_COLUMN)

    def setUp(self):
        _Toplevel.toplevels = []
        _StyleContext.added = []
        nautilus_meta._view_states.clear()
        nautilus_meta._desc_css_added = False

    def tearDown(self):
        _Toplevel.toplevels = []

    def _view(self, desc_visible=True, names=('agent-home', 'AGENTS.md'),
              overhead=88, width=1000, title='名称'):
        """A list view holding a name cell and a description cell per row."""
        name = _ColumnViewColumn('name')
        name.set_expand(True)  # what nautilus itself sets up
        desc = _ColumnViewColumn(nautilus_meta.DESC_COLUMN,
                                 visible=desc_visible)
        size = _ColumnViewColumn('size')
        rows = []
        for file_name in names:
            rows.append(_Widget([NautilusNameCell(file_name, overhead),
                                 NautilusLabelCell('一段描述')]))
        body = _Widget(rows)
        view = _ColumnView([name, desc, size],
                           children=[GtkColumnViewTitle(title), body],
                           model=_ViewRowModel(names), width=width)
        _Toplevel.toplevels = [_Toplevel([view])]
        return name, desc, size, view

    def test_desc_visible_sizes_name_to_the_longest_file_name(self):
        name, desc, size, _view = self._view()
        nautilus_meta._fit_columns()
        self.assertFalse(name.get_expand())
        self.assertTrue(desc.get_expand())
        self.assertFalse(size.get_expand())
        # overhead 88 + 'agent-home' (10 chars x 10px) = 188
        self.assertEqual(name.get_fixed_width(), 188)

    def test_names_outside_the_rendered_rows_count(self):
        # Only two rows are laid out, but the folder holds a longer name.
        _name, _desc, _size, view = self._view(names=('a', 'bb'))
        view.get_model().set_names(['a', 'bb', 'a-very-long-file-name'])
        nautilus_meta._fit_columns()
        # 'a-very-long-file-name' is 21 characters.
        self.assertEqual(_name.get_fixed_width(), 88 + 210)

    def test_long_names_are_capped_to_a_share_of_the_view(self):
        _name, _desc, _size, _view = self._view(
            names=('x' * 100,), width=1000)
        nautilus_meta._fit_columns()
        self.assertEqual(_name.get_fixed_width(),
                         int(1000 * nautilus_meta.NAME_SHARE))

    def test_name_width_never_below_the_header(self):
        name, _desc, _size, _view = self._view(names=('a',), title='名称' * 20)
        nautilus_meta._fit_columns()
        self.assertEqual(name.get_fixed_width(), 400)

    def test_no_laid_out_row_means_no_width_yet(self):
        # Nothing realized: measuring now would ellipsize every name.
        name, desc, _size, _view = self._view()
        _Toplevel.toplevels[0]._children[0]._children[1]._children = []
        nautilus_meta._fit_columns()
        self.assertFalse(name.get_expand())
        self.assertTrue(desc.get_expand())
        self.assertEqual(name.get_fixed_width(), -1)

    def test_desc_hidden_restores_nautilus_layout(self):
        name, desc, _size, _view = self._view(desc_visible=False)
        nautilus_meta._fit_columns()
        self.assertTrue(name.get_expand())
        self.assertFalse(desc.get_expand())
        self.assertEqual(name.get_fixed_width(), -1)

    def test_hiding_the_desc_column_later_restores_name_expand(self):
        name, desc, _size, _view = self._view()
        nautilus_meta._fit_columns()
        self.assertFalse(name.get_expand())
        desc.set_visible(False)
        nautilus_meta._fit_columns()
        self.assertTrue(name.get_expand())
        self.assertEqual(name.get_fixed_width(), -1)

    def test_hand_dragged_width_is_kept(self):
        name, _desc, _size, _view = self._view()
        nautilus_meta._fit_columns()
        name.set_fixed_width(500)  # user drags the divider
        nautilus_meta._fit_columns()
        self.assertEqual(name.get_fixed_width(), 500)

    def test_dragged_width_is_dropped_when_the_folder_changes(self):
        name, _desc, _size, view = self._view()
        nautilus_meta._fit_columns()
        name.set_fixed_width(500)
        nautilus_meta._fit_columns()
        self.assertEqual(name.get_fixed_width(), 500)
        # Enter another folder: its own longest name decides again.
        view.get_model().set_names(['another-folder'], 'file:///tmp/other')
        nautilus_meta._fit_columns()
        self.assertEqual(name.get_fixed_width(), 88 + 140)

    def test_view_mode_switch_schedules_two_passes(self):
        # Switching to list view builds a fresh view that is still being laid
        # out: one pass finds nothing, a delayed second one picks up the width.
        _GLib.idle_queue.clear()
        _GLib.timeout_queue.clear()
        nautilus_meta._view_mode_watched = False
        nautilus_meta._fit_scheduled = False
        _name, _desc, _size, _view = self._view()
        nautilus_meta._fit_columns()  # installs the preference watcher
        settings = _Settings.for_schema(nautilus_meta.VIEW_MODE_SCHEMA)
        self.assertIsNotNone(settings)
        self.assertIn('changed::' + nautilus_meta.VIEW_MODE_KEY,
                      settings.handlers)

        _GLib.idle_queue.clear()
        nautilus_meta._on_view_mode_changed(settings, nautilus_meta.VIEW_MODE_KEY)
        self.assertEqual(len(_GLib.idle_queue), 1)
        self.assertEqual(len(_GLib.timeout_queue), 1)
        _GLib.run_idle()
        _GLib.run_timeouts()
        self.assertEqual(len(_GLib.idle_queue), 1)  # the delayed second pass
        _GLib.run_idle()

    def test_view_mode_watcher_is_installed_once(self):
        _GLib.idle_queue.clear()
        _GLib.timeout_queue.clear()
        nautilus_meta._view_mode_watched = False
        _Settings.forget()
        _name, _desc, _size, _view = self._view()
        nautilus_meta._fit_columns()
        nautilus_meta._fit_columns()
        settings = _Settings.for_schema(nautilus_meta.VIEW_MODE_SCHEMA)
        self.assertEqual(len(settings.handlers), 1)

    def test_bookkeeping_outlives_the_local_view_reference(self):
        # PyGObject drops its wrapper once the last Python reference goes, so
        # state kept in a weak container would be gone by the next pass. The
        # bookkeeping holds the view strongly, so the same wrapper comes back.
        name, _desc, _size, view = self._view()
        nautilus_meta._fit_columns()
        name.set_fixed_width(420)  # the user drags the divider
        del view
        again = nautilus_meta._column_views(_Toplevel.toplevels[0])[0]
        self.assertIn(again, nautilus_meta._view_states)
        nautilus_meta._fit_columns()
        self.assertEqual(name.get_fixed_width(), 420)

    def test_closed_window_forgets_its_view(self):
        self._view()
        nautilus_meta._fit_columns()
        self.assertEqual(len(nautilus_meta._view_states), 1)
        _Toplevel.toplevels = []
        nautilus_meta._fit_columns()
        self.assertEqual(nautilus_meta._view_states, {})

    def test_entering_a_folder_reschedules_a_fit(self):
        _GLib.idle_queue.clear()
        _name, _desc, _size, view = self._view()
        nautilus_meta._fit_scheduled = False
        nautilus_meta._fit_columns()  # hooks the model
        _GLib.idle_queue.clear()
        view.get_model().set_names(['x'], 'file:///tmp/other')
        self.assertEqual(len(_GLib.idle_queue), 1)

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
        body = _Widget([_Widget([NautilusNameCell('abc')])])
        view = _ColumnView([name, desc], children=[body],
                           model=_ViewRowModel(['abc']))
        _Toplevel.toplevels = [_Toplevel([_Widget([view])])]
        nautilus_meta._fit_columns()
        self.assertFalse(name.get_expand())
        self.assertTrue(desc.get_expand())
        self.assertEqual(name.get_fixed_width(), 88 + 30)

    def test_missing_columns_never_raises(self):
        class Boom:
            def get_columns(self):
                raise RuntimeError('internals changed')

        _Toplevel.toplevels = [_Toplevel([Boom()])]
        nautilus_meta._fit_columns()  # must not raise

    def test_schedule_fits_once_per_idle_pass(self):
        _GLib.idle_queue.clear()
        name, desc, _size, _view = self._view()
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


class DescFontTests(unittest.TestCase):
    """The description column renders smaller, without touching other columns."""

    def setUp(self):
        _Toplevel.toplevels = []
        _StyleContext.added = []
        nautilus_meta._view_states.clear()
        nautilus_meta._desc_css_added = False

    def _view(self, desc_visible=True):
        columns = [_ColumnViewColumn('name'),
                   _ColumnViewColumn(nautilus_meta.DESC_COLUMN,
                                     visible=desc_visible),
                   _ColumnViewColumn('size')]
        rows = [_Widget([NautilusNameCell('abc'), NautilusLabelCell('desc')])]
        view = _ColumnView(columns, children=[_Widget(rows)],
                           model=_ViewRowModel(['abc']))
        _Toplevel.toplevels = [_Toplevel([view])]
        return view

    def test_css_rules_target_each_visible_position(self):
        self._view()
        nautilus_meta._fit_columns()
        self.assertEqual(len(_StyleContext.added), 1)
        text = _StyleContext.added[0].text
        self.assertIn('nth-child(2)', text)
        self.assertIn(nautilus_meta.DESC_FONT_SCALE, text)
        self.assertIn('row > cell', text)

    def test_css_is_installed_once(self):
        self._view()
        nautilus_meta._fit_columns()
        nautilus_meta._fit_columns()
        self.assertEqual(len(_StyleContext.added), 1)

    def test_view_gets_the_class_for_the_desc_position(self):
        view = self._view()
        nautilus_meta._fit_columns()
        self.assertTrue(view.has_css_class('folder-meta-desc-2'))

    def test_class_follows_a_reordered_column(self):
        view = self._view()
        nautilus_meta._fit_columns()
        # Move the description in front of the name column.
        columns = view.get_columns()
        desc = columns.pop(1)
        columns.insert(0, desc)
        nautilus_meta._fit_columns()
        self.assertTrue(view.has_css_class('folder-meta-desc-1'))
        self.assertFalse(view.has_css_class('folder-meta-desc-2'))

    def test_hidden_desc_column_removes_the_class(self):
        view = self._view(desc_visible=False)
        nautilus_meta._fit_columns()
        self.assertFalse(view.has_css_class('folder-meta-desc-2'))
        self.assertFalse(view.has_css_class('folder-meta-desc-1'))


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
