/*
 * Copyright (C) 2026 The GNOME project contributors
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Fork-only: a generic event outlet for the Python extension layer.
 */

#pragma once

#include <gio/gio.h>

G_BEGIN_DECLS

/* Publish the fact that nautilus observed `from` being moved to `to`. */
void nautilus_plus_events_emit_file_moved (GFile *from,
                                           GFile *to);

G_END_DECLS
