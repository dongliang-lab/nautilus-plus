# 技术调研

本文件汇总全部**经过源码验证**的调研结论(nautilus 50 / nautilus-python 4.1 时代)。所有结论都有源码依据,标注了文件和行号。

## 环境事实

| 项 | 值 |
|---|---|
| Nautilus | 50.2.2(扩展 API 版本 `4.1`,GI 绑定) |
| nautilus-python | 4.1.0-3(已安装) |
| 扩展目录 | 用户 `~/.local/share/nautilus-python/extensions/`、系统 `/usr/share/nautilus-python/extensions/`(加载器源码 `nautilus-python.c:227-239` 确认) |
| 扩展加载 | 无热重载,改插件后 `nautilus -q` 重启;错误输出到 nautilus stderr |
| PyYAML | 6.0.3(插件依赖) |

## 已验证可复用的机制

1. **第二行 caption**:`add_string_attribute('desc', …)` + captions gsettings 配置任意属性名;captions 变化实时生效(视图监听 `changed::captions`)
2. **扩展信息失效即清空**:`invalidate_extension_info()` → `nautilus_file_invalidate_extension_info_internal`(`nautilus-file.c:7716`)先清空扩展 emblems/属性,再重跑所有 InfoProvider → 开关关闭时旧标记自动消失
3. **菜单重建触发**:nautilus 的扩展菜单模型只在视图加载时构建一次;对当前文件夹重加扩展属性 → `nautilus_file_changed` → `view_directory_changed_callback`(`nautilus-files-view.c:8578-8584`)→ 调度菜单重建(约 0.5s)。`popup-menu-changed` 信号是死代码,从未被发出
4. **属性无 remove 的清理**:`add_string_attribute(attr, '')` 置空串清掉显示(扩展属性 API 只有 add)

## 已验证的死路(不要重复尝试)

| 尝试 | 结论 | 依据 |
|---|---|---|
| `add_string_attribute("name", …)` 覆盖显示名 | ❌ `"name"` 被特判为真实显示名,扩展属性表在特判之后 | `nautilus-file.c:6437` |
| 用 GIO 写 `standard::sort-order` 让文件夹排后 | ❌ gvfs 只存储 `metadata::` 命名空间,其他命名空间拒绝;合并查询时强制加 `metadata::` 前缀 | `gdaemonvfs.c:1202`、`gdaemonvfs.c:1054` |
| 图标视图分组(现成方案) | ❌ GtkGridView **没有** header factory API(仅 GtkListView 有) | `/usr/include/gtk-4.0/gtk/gtkgridview.h` |
| C 扩展获得更多权限 | ❌ C 与 Python 面对同一扩展 ABI;nautilus 内部符号隐藏编译,进程内也调不到 | `nm -D /usr/bin/nautilus` |
| 分组/分区(纯扩展) | ❌ 普通文件视图无 section 渲染;`GtkSectionModel` 只被网络视图/应用选择器使用 | `nautilus-view-model.c:105` |

## fork 钩子落点蓝图(构建 nautilus-meta 的核心)

> **现状(2026-08-17)**:fork 的唯一动机是**分组视图**(见第 2 节)。
> 显示名覆盖已否决(第 1 节);描述、归档标记全部纯插件可达。

### 1. 显示名覆盖 ~~(约 10 行,零新 ABI)~~ — **已否决 2026-08-17**

> **决策**:不实现显示名覆盖。用户确认"底部 caption 显示描述"方案更优。
> 否决理由:
> 1. 开发者心智一致性——终端/编辑器用真实英文名,nautilus 同时显示英文名 + 中文标注,两边对得上
> 2. 零 fork 成本——该功能纯插件可达,不值得为它维护 fork
> 3. 信息更全——真名(可操作)+ 语义名(可识别)同时可见,贴合"整理思绪"的原始诉求
> 4. 无边界怪癖——替换方案有"只改属性 getter 则列表视图/路径栏英文、图标视图中文"的不一致权衡
>
> 保留以下分析作为历史记录与参考:

- 落点:`PROP_DISPLAY_NAME` getter(`nautilus-file.c:8422`)或 `nautilus_file_get_display_name`(`nautilus-file.c:4269`)
- 形态:优先读 `extension_attributes["name"]`,有值则用之
- 插件侧用**现有 API** `add_string_attribute("name", …)` 写入 → nautilus-python 原样可用,零 ABI 变更
- 注意:图标视图标签绑定 `display-name` 属性(`nautilus-grid-cell.blp`);路径栏直接调 `nautilus_file_get_display_name`——**只改属性 getter 可保持路径栏英文**,改函数则全局生效

### 2. 分组机制(骨架全在)

- `GtkSectionModel` 已实现于视图模型(`nautilus-view-model.c:105`);`nautilus_view_model_set_section_sorter` 已存在(`nautilus-view-model.c:508`)——网络视图是完整模板(`nautilus-network-view.c:246-314`)
- **主排序器必须"分组优先"**:GtkSortListModel 分区 = 相邻且 section-sorter 判等;主排序不先按分组排则各组交错。网格视图排序器:`nautilus-grid-view.c:385`;列表视图:`GtkMultiSorter`(`nautilus-list-view.c:1067`)
- 列表视图标题:GTK4.22 的 `gtk_list_view_set_header_factory` 原生支持
- **图标视图**:GtkGridView 无 header factory → 需每格自绘标题(检查"组内第一个":`gtk_section_model_get_section` 判 `start == p`),标题宽度 = 格子宽;全宽标题需实测 GtkGridView 异质尺寸或自绘布局
- 折叠 = 过滤:视图模型 `root_filter_model` 是 GtkFilterListModel(`nautilus-view-model.c:49`),每分组一个 GtkCustomFilter;标题栏不过滤
- 分组键建议由扩展属性提供(插件 `add_string_attribute('group', …)`),sorter 读 `nautilus_file_get_string_attribute_q`——fork 只加机制,数据逻辑留 Python

### 3. 归档排后(在 fork 内可行)

- 扩展路径已死(gvfs 限制);但 fork 内 `nautilus-file.c:2743` 的 `sort_order` 来源是 C 代码,可直接改为读取自有元数据源

## 架构决策

- **分层**:**C 只提供通用能力(不写业务),业务规则全部在 Python 扩展**。判断标准:这项改动是"Python 够不到的能力"还是"业务规则"?前者才考虑 C,且必须做成通用能力(顺带:改动频率低的能力也更适合 C)
- **钩子抽象**:钩子只认"扩展属性 = 值",不认写属性者——为将来 C 原生读 `.folder.yaml` 留迁移路径(规则稳定后,把读 yaml 搬进 C,Python 层收缩或消失)
- **`.folder.yaml` 定位**:文件夹内 dotfile——随文件夹移动而存活(mv/cp/rsync 携带)、工具无关(Windows 的 `desktop.ini` 同架构,已存活 30 年)
- **打包**:PKGBUILD 把扩展装到 `/usr/share/nautilus-python/extensions/`,`depends=(nautilus-python python-yaml)`,与 fork 版本锁步;装包前删用户目录旧副本防双菜单;开发用 `~/.local` 副本快速迭代
- **fork 基底(2026-08-18 定)**:`gnome-50` 稳定分支——`main` 开发线要求未发布的 glib ≥ 2.89,稳定系统无法构建;稳定分支依赖实测匹配(glib 2.88.3 / gtk4 4.22.4 / libadwaita 1.9.3)

## 市场调研摘要

| 需求 | Windows | macOS | Linux |
|---|---|---|---|
| 显示名别名(不重命名) | ✅ `desktop.ini` `LocalizedResourceName=` | ✅ `.localized` | ❌ 无(nautilus 3.x 扩展 API 曾是唯一实现,46 版移除) |
| 元数据驱动分组 | ✅ `desktop.ini` `Prop5=Tags` → Group by(未文档化,有怪癖);第三方 XYplorer 脚本列可读文件夹内文件 | ❌ | ❌(Dolphin 分组不可折叠;深度管理器固定维度) |

Linux 上"文件夹内配置文件驱动显示与组织"是空白市场;`nautilus-meta` 可考虑兼容读取 `desktop.ini`/`.localized`,让其他平台用户的配置资产可迁移。

## 命名决策记录

- fork 品牌候选(未定):**Verne**(谱系:Nautilus 潜艇 → Nemo 船长 → Verne 作者,推荐)、Argo(撞 Argo CD)、Dory、Nauti、Ammon、Ceph(撞 Ceph 存储)
- 功能/机制名:**nautilus-meta**(元数据驱动,可扩展);当前扩展暂保持原名 `nautilus-meta.py`,改名列入重构计划
- 二进制/包名保持 `nautilus`(低摩擦,IgnorePkg),品牌名独立
