# 技术调研

本文件汇总全部**经过源码验证**的调研结论(nautilus 50 / nautilus-python 4.1 时代)。所有结论都有源码依据,标注了文件和行号。

## 环境事实

| 项 | 值 |
|---|---|
| Nautilus | 50.2.2(扩展 API 版本 `4.1`,GI 绑定) |
| nautilus-python | 4.1.0-3 |
| 扩展目录 | 用户 `~/.local/share/nautilus-python/extensions/`、系统 `/usr/share/nautilus-python/extensions/`(加载器源码 `nautilus-python.c:227-239` 确认) |
| 扩展加载 | 无热重载,改插件后 `nautilus -q` 重启;错误输出到 nautilus stderr |
| PyYAML | 6.0.3(插件依赖) |

## 已验证可复用的机制

1. **第二行 caption**:`add_string_attribute('desc', …)` + captions gsettings 配置任意属性名;captions 变化实时生效(视图监听 `changed::captions`)
2. **扩展信息失效即清空**:`invalidate_extension_info()` → `nautilus_file_invalidate_extension_info_internal`(`nautilus-file.c:7716`)先清空扩展 emblems/属性,再重跑所有 InfoProvider → 开关关闭时旧标记自动消失
3. **菜单重建触发**:nautilus 的扩展菜单模型只在视图加载时构建一次;对当前文件夹重加扩展属性 → `nautilus_file_changed` → `view_directory_changed_callback`(`nautilus-files-view.c:8578-8584`)→ 调度菜单重建(约 0.5s)。`popup-menu-changed` 信号是死代码,从未被发出
4. **属性无 remove 的清理**:`add_string_attribute(attr, '')` 置空串清掉显示(扩展属性 API 只有 add)
5. **列表视图自定义列**:`Nautilus.ColumnProvider.get_columns()` 返回 `Nautilus.Column(name, attribute, label, description)`,列表视图右键列头即可勾选。上游 `src/nautilus-column-utilities.c:175` 会收集所有 ColumnProvider
6. **进程内改列宽/expand**:扩展与 nautilus 同进程同 GTK,插件可遍历 `Gtk.Window.get_toplevels()` 拿到 `Gtk.ColumnView`,对 `GtkColumnViewColumn` 调 `set_expand()` / `set_fixed_width()`;名称单元格是 `NautilusNameCell`(按类名识别),可 `measure()` 出自然宽度。`Nautilus.Column` 本身没有这两个属性
7. **从视图 model 读全部文件名**:`view.get_model()` 是 `NautilusViewModel`,每行 `GtkTreeListRow` → `get_item()` → `NautilusViewItem` → `get_property('file')` → `NautilusVFSFile.get_name()`。不依赖哪些行已渲染,滚动区外的名字也能拿到(实测确认)
8. **文字宽度与 nautilus 完全一致**:任一 `Gtk.Label` 的 `create_pango_layout(text).get_pixel_size()` 即可,不必自己拼 Pango
9. **GTK CSS 按列位置改样式**:GTK 4.24 支持 `:nth-child()`;列表行里只有可见列的单元格,故「描述列在可见列中的序号」= 其 cell 的 nth-child。配合 `Gtk.CssProvider` + `StyleContext.add_provider_for_display` 可只给描述列改字号
10. **槽位导航(自动化验证用)**:`NautilusWindowSlot` 上的 action group 前缀是 `slot`,`slot.open-location` 接受 URI 字符串。`location-open`、`open-location`(不带前缀)都不存在;`slot.files-view-mode` 接受 `u`(1=列表、2=图标,见 `nautilus-view-info.h`)
11. **视图模式切换的信号**:gsettings `org.gnome.nautilus.preferences` 的 `default-folder-viewer` 每次切换都会变(`change_files_view_mode` → `g_settings_set_enum`)。控件侧没有可用的信号(`child-added`、`notify::visible-child` 实测都不触发)

## 已验证的死路(不要重复尝试)

| 尝试 | 结论 | 依据 |
|---|---|---|
| `add_string_attribute("name", …)` 覆盖显示名 | ❌ `"name"` 被特判为真实显示名,扩展属性表在特判之后 | `nautilus-file.c:6437` |
| 用 GIO 写 `standard::sort-order` 让文件夹排后 | ❌ gvfs 只存储 `metadata::` 命名空间,其他命名空间拒绝;合并查询时强制加 `metadata::` 前缀 | `gdaemonvfs.c:1202`、`gdaemonvfs.c:1054` |
| 图标视图分组(现成方案) | ❌ GtkGridView **没有** header factory API(仅 GtkListView 有) | `/usr/include/gtk-4.0/gtk/gtkgridview.h` |
| C 扩展获得更多权限 | ❌ C 与 Python 面对同一扩展 ABI;nautilus 内部符号隐藏编译,进程内也调不到 | `nm -D /usr/bin/nautilus` |
| 分组/分区(纯扩展) | ❌ 普通文件视图无 section 渲染;`GtkSectionModel` 只被网络视图/应用选择器使用 | `nautilus-view-model.c:105` |
| 分组/归档视图(需 fork C) | ❌ 已放弃:需要修改 C 层,与"纯插件"目标冲突;相关 C 代码已删除 | 本仓库历史 |

## 架构决策

- **纯 Python 插件,不改 C**(2026-10-23 定):fork 的 C 改动全部还原为上游原样。业务全部在 `extensions/python/nautilus-meta/`;需要新能力时先找 nautilus-python 现有 API(InfoProvider / MenuProvider / ColumnProvider / PropertyPageProvider),够不到就不做,不再为单个功能维护 fork
- **`.folder.yaml` 定位**:文件夹内 dotfile——随文件夹移动而存活(mv/cp/rsync 携带)、工具无关(Windows 的 `desktop.ini` 同架构,已存活 30 年)
- **打包(可选)**:PKGBUILD 把扩展装到 `/usr/share/nautilus-python/extensions/`,`depends=(nautilus-python python-yaml)`;装包前删用户目录旧副本防双菜单;开发用 `~/.local` 副本快速迭代

## 市场调研摘要

| 需求 | Windows | macOS | Linux |
|---|---|---|---|
| 显示名别名(不重命名) | ✅ `desktop.ini` `LocalizedResourceName=` | ✅ `.localized` | ❌ 无(nautilus 3.x 扩展 API 曾是唯一实现,46 版移除) |
| 元数据驱动分组 | ✅ `desktop.ini` `Prop5=Tags` → Group by(未文档化,有怪癖);第三方 XYplorer 脚本列可读文件夹内文件 | ❌ | ❌(Dolphin 分组不可折叠;深度管理器固定维度) |

Linux 上"文件夹内配置文件驱动显示"是空白市场;`nautilus-meta` 可考虑兼容读取 `desktop.ini`/`.localized`,让其他平台用户的配置资产可迁移。
