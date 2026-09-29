# When adding new tests, it is useful to set some environment variables.
# You can do it like so:
#
# test(
#   name,
#   executable,
#   env: [
#     test_env,
#     'G_TEST_BUILDDIR=@0@'.format(meson.current_build_dir()),
#     'G_TEST_SRCDIR=@0@'.format(meson.current_source_dir())
#   ]
# )
#
# G_TEST_BUILDDIR and G_TEST_SRCDIR cannot be preset, since
# the test sources are scattered.
test_env = [
  'GTK_A11Y=none',
  'GSK_DEBUG=fallback',
  'GSETTINGS_BACKEND=memory',
  'GSETTINGS_SCHEMA_DIR=@0@'.format(join_paths(meson.project_build_root(), 'data')),
  # Tests must never touch the real user configuration: test-bookmarks.c
  # builds a NautilusBookmarkList, which saves to
  # $XDG_CONFIG_HOME/gtk-3.0/bookmarks — left pointing at the real home, it
  # wipes the developer's own bookmarks every time the suite runs.
  'XDG_CONFIG_HOME=@0@'.format(meson.project_build_root()),
]

subdir('automated')
