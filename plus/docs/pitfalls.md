# 踩坑记录

按严重度排列,全部为实际踩过或源码级验证的坑。fork/归档/构建相关的历史条目已随 C 层删除,需要时看 git 历史。

## 1. GFileEnumerator 不是上下文管理器

- **现象**:`with children:` 抛 `TypeError: object does not support the context manager protocol`
- **原因**:pygobject 的 `Gio.FileEnumerator` 只有 `__iter__`/`__next__`,没有 `__enter__`/`__exit__`
- **处理**:直接 `for info in children:` 迭代,`finally` 里 `children.close(None)`(包 GLib.Error)

## 2. 菜单标签冻结(nautilus 只构建一次扩展菜单)

- **现象**:切换开关后,右键菜单标签不更新,一直显示旧状态
- **原因**:nautilus 的扩展菜单模型只在视图加载时构建一次(`nautilus-files-view.c:8173`),之后复用;`popup-menu-changed` 信号是死代码(全树无人发出);`items-updated` 信号同样无人监听
- **处理**:切换后对当前文件夹重加一次扩展属性 → `nautilus_file_changed` → 视图调度菜单重建,标签约 0.5s 内翻转

## 3. gvfs 只存储 metadata:: 命名空间(排序置底死路)

- **现象**:`Gio.File.set_attribute_int32('standard::sort-order', …)` 报 `not supported`
- **原因**:本地文件的未知命名空间属性委托给 gvfs,但 `g_daemon_vfs_local_file_set_attributes`(`gdaemonvfs.c:1202`)只处理 `metadata` 命名空间;且查询合并时强制给存储键加 `metadata::` 前缀(`gdaemonvfs.c:1054`)
- **结论**:插件无法影响 nautilus 的 `sort_order`(`nautilus-file.c:2743` 只读 `standard::sort-order`)

## 4. 旧安装文件残留 → 双菜单

- **现象**:插件改名/换目录后,右键菜单出现两份相同菜单项
- **原因**:nautilus-python 同时加载用户目录和系统目录下所有扩展文件,旧文件名残留即重复加载
- **处理**:改名/迁移时删除旧路径的安装文件(`~/.local/share/nautilus-python/extensions/`、`/usr/share/nautilus-python/extensions/`)

## 5. 扩展属性没有 remove

- **现象**:开关关闭后,已显示的 caption/标记不消失
- **原因**:`add_string_attribute` 只有 add;`invalidate_extension_info` 会清空扩展数据再重跑 provider,但仅在被触发时
- **处理**:置空串 `add_string_attribute(attr, '')` 清显示;用进程内集合(`_shown`)追踪"曾设置过"的文件夹,避免每次列目录重复写入

## 6. `__pycache__` 残留

- **现象**:`python3 -m py_compile` 在源码目录生成 `__pycache__/`
- **处理**:.gitignore 忽略;安装目录出现时手动清理

## 7. 无热重载

- **现象**:修改插件后不生效
- **处理**:`nautilus -q` 重启(加载错误在 stderr,启动时重定向到日志可捕获)

## 8. 注释跟随依赖 xattr,不支持的文件系统会退化

- **现象**:U 盘(exFAT)、网盘上,文件移动/改名后注释不跟随
- **原因**:`user.*` 扩展属性需要文件系统支持;不支持时 `os.setxattr` 抛 `OSError`
- **处理**:写入令牌失败时静默跳过(`_write_token` 吞掉 OSError),退化为"不跟随 + 懒清理",不报错、不留垃圾

## 9. 名称列霸占宽度,扩展 API 改不了列宽

- **现象**:加了「描述」列后,它被推到很右边,拖动也缩不回来
- **原因**:`src/nautilus-list-view.c` 对所有列 `set_expand(FALSE)`,只给 `name` 列 `set_expand(TRUE)`;多出来的宽度全进名称列。`Nautilus.Column` 只有 name/attribute/label/description/xalign/sort-order/visible,没有宽度或 expand
- **处理**:插件在进程内遍历 `Gtk.Window.get_toplevels()`,找到 `Gtk.ColumnView`,把名称列 `expand=FALSE` + `fixed-width` 设为内容自然宽度(名称单元格 `measure()` 与第一个列头取大),描述列 `expand=TRUE`。用户拖动过的列不再改写(比较 fixed-width 与上次自己写的值)
- **注意**:自然宽度必须在控件完成布局后测;太早测会得到 0,此时只切 expand、不写 fixed-width,等下一次刷新再补
- **调试手法**:无截图工具时,可在插件里用 `Gtk.WidgetPaintable` + `render_texture()` 把窗口直接存成 PNG,便于核对布局
