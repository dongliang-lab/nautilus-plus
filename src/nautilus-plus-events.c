/*
 * Copyright (C) 2026 The GNOME project contributors
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "nautilus-plus-events.h"

/* Fork-only: a generic D-Bus event outlet.
 *
 * Business rules live in the Python extension; this file only publishes
 * facts about what nautilus observed. File moves are reported here because
 * the extension ABI gives Python no way to observe them: the extension API
 * exposes only FileInfo/MenuItem/providers, never the directory or
 * application objects, so no nautilus signal is reachable from Python.
 * See plus/docs/design/history-paths.md. */

#define PLUS_EVENTS_INTERFACE "org.gnome.NautilusPlus.FileMonitor"
#define PLUS_EVENTS_PATH "/org/gnome/NautilusPlus"

void
nautilus_plus_events_emit_file_moved (GFile *from,
                                      GFile *to)
{
    g_autofree char *from_uri = NULL;
    g_autofree char *to_uri = NULL;
    GApplication *application;
    GDBusConnection *connection;

    g_return_if_fail (G_IS_FILE (from));
    g_return_if_fail (G_IS_FILE (to));

    /* The application's own connection carries the well-known name, so
     * subscribers can match on it. Borrowed reference. */
    application = g_application_get_default ();
    if (application == NULL)
    {
        return;
    }

    connection = g_application_get_dbus_connection (application);
    if (connection == NULL)
    {
        return;
    }

    from_uri = g_file_get_uri (from);
    to_uri = g_file_get_uri (to);

    g_dbus_connection_emit_signal (connection,
                                   NULL,
                                   PLUS_EVENTS_PATH,
                                   PLUS_EVENTS_INTERFACE,
                                   "Moved",
                                   g_variant_new ("(ss)", from_uri, to_uri),
                                   NULL);
}
