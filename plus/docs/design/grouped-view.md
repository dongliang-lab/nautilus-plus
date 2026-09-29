# 功能设计:分组视图(底层支持 + 归档分组测试)

状态:**已实现**(C 钩子 + Python 测试驱动,0.2.0,2026-08-19)

## 背景

分组能力是 fork 提供的第一项 C 层通用能力(`research.md` 第 2 节蓝图;分层原则见 `AGENTS.md` 决策 5)。nautilus-python 扩展 API 没有任何能影响视图模型/排序/分组的扩展点(只有 Column/Info/Menu/PropertiesModel 四类 provider),GtkGridView 也没有 header factory——Python 够不到,因此必须由 fork 在 C 层提供。

本次范围(用户已定):**图标 + 列表两视图**都支持分组;不做折叠交互;图标视图在**每个分组项的图标中央**显示分组名徽章(列表视图保留整行组头);Python 层用 `archived: true` 作为 `已归档` 分组做端到端测试。**未分组条目正常显示在最前,不渲染任何"未分组"组头**。

## 机制

### 数据路径(分组键从哪来)

```
Python: add_string_attribute('group', '已归档')
  └─ NautilusFileInfo::add_string_attribute → details->extension_attributes 哈希表(GQuark 键)
C 侧:   nautilus_file_get_extension_attribute(file, quark("group"))  ← 新增访问器,只查扩展属性表
```

⚠️ **不能用 `nautilus_file_get_string_attribute_q` 读分组键**:内建 `attribute_group_q = "group"`(`nautilus-file.c` 8744)会先返回 **POSIX 组名**(6706-6709),遮蔽扩展属性。专用访问器 `nautilus_file_get_extension_attribute` 只查 `pending_extension_attributes` / `extension_attributes` 两张表。

### 排序与分区(section)

- 主 sorter 包装为 `GtkMultiSorter[group, 现有排序]`:
  - 图标视图:`[group, custom(nautilus_grid_view_sort)]`
  - 列表视图:`[group, directories, column_view_sorter]`(group 必须在 directories 之前)
- section sorter(经 `nautilus_view_model_set_section_sorter`,比较 `GtkTreeListRow`)必须提供**全序**而非仅相等判定——已从 GTK 4.22 源码验证 `gtk_sort_list_model_ensure_real_sorter` 实际按 `[section_sorter, sorter]` 组合排序,section sorter 就是主排序键(网络视图 `sort_network_sections` 返回枚举序同为此因)
- 分组键归一化:`NULL` 与 `""` 都算**未分组**(相等、排最前);非空键 strcmp 升序。组顺序固定:未分组永远最前,`reversed` 只影响组内

### 触发链(属性到达后如何重排/刷新)

`add_string_attribute` 末尾调用 `nautilus_file_changed`(nautilus-file.c 9098)→ 目录 files-changed → `files_view_end_file_changes` → **`nautilus_view_model_sort`**(nautilus-view-model.c 514)。链路已存在,无需新接线。

唯一缺口:**GtkSortListModel 在重排无位移时不发任何信号**——组键到达但顺序未变(如单文件目录)时列表组头不刷新。修复:`nautilus_view_model_sort` 在 `gtk_sorter_changed` 后补发全范围 `sections-changed`(GtkListView/ColumnView 的 item manager 会据此重建 header)。

### 分组可视化

- **列表视图**:整行组头。`gtk_column_view_set_header_factory`(GTK 4.22 原生),照抄网络视图模板(`nautilus-network-view.c` 250-302):setup 建 `heading` 样式 label(xalign 0),bind 从 `gtk_list_header_get_item` → `GtkTreeListRow` → item → file 取组键;**未分组 section 渲染零高 header**(隐藏 child,若残留 1px 则改置空 child)
- **图标视图**:组名徽章。GtkGridView 无 header API、也无法让分组从新行开始(GTK 4.22 源码确认:行纯按 `n_columns` 数量切分,`if (i >= self->n_columns)` 才换行,无 section 感知、无强制换行/列定位 API;虚拟组行/占位项也无效——列数随窗口宽度在布局期才确定,模型层无法感知)。曾评估"整行背景条 + 顶部空带"近似(组首行画横贯背景条),用户否决。最终方案:**每个属于分组的项,在其图标中央叠加分组名徽章**——同组项彼此可见、不依赖行首,窗口任意宽度下语义一致
  - 徽章是 `NautilusGridCell` 模板里的叠加 label(`group_header`),不参与布局(measure/size_allocate 手写,叠加层在 size_allocate 里 measure 后居中分配),`can-target: false` 事件穿透
  - 定位按文件夹图标形状:垂直居中于图标"身体"(避开 `icon_size/5 + 2` 的"翻盖"区)
  - 样式 `.group-badge`(`style.css`):半透明黑底(`alpha(#000, 0.4)`)白字、圆角、1.1em 加粗、四向黑描边(text-shadow)——亮暗主题、浅色图标上均清晰
  - 刷新:item `file-changed`/bind 即覆盖(徽章只依赖 item 的组键,不依赖位置/section)

## 架构

```
C 钩子(能力)                     Python 扩展(规则)
─────────────────────────────    ─────────────────────────
nautilus-file.c                  nautilus-meta.py
  get_extension_attribute          _yaml_info → (name, archived)
nautilus-grouped-view.c             archived is True → add_string_attribute('group', '已归档')
  get_group_string / 3 个 sorter 工厂  否则 → add_string_attribute('group', '') 清空
nautilus-view-model.c            (分组与 desc 开关解耦:开关只控制描述)
  sort() 补发 sections-changed
nautilus-list-view.c
  header factory + [group, dirs, col] + section sorter
nautilus-grid-view.c / grid-cell
  [group, custom] + 图标中央分组名徽章
```

分组契约(属性名 `"group"`、NULL/`""` = 未分组)收口在 `nautilus-grouped-view.c`,钩子只认"扩展属性 = 值",不认写属性者(数据源可换原则)。

## 关键组件

| 组件 | 说明 |
|---|---|
| `nautilus_grouped_view_get_group_string` | 读 `group` 扩展属性的 allocated 字符串 |
| `nautilus_grouped_view_create_group_sorter` | 比较 `NautilusViewItem` 组键(空键相等且最小,非空 strcmp) |
| `nautilus_grouped_view_create_sorter` | `GtkMultiSorter[group, fallback]`(fallback 取引用) |
| `nautilus_grouped_view_create_section_sorter` | 比较 `GtkTreeListRow`,同全序比较 |
| `nautilus_view_model_sort` | 补发全范围 `sections-changed`(修复静默重排) |
| 列表 header factory | `setup_group_header` / `bind_group_header`,未分组零高 |
| 网格 `update_group_header` | 组键非空 → 显示徽章 label 并设文字(item bind/file-changed 触发) |
| `.group-badge` 样式 | `style.css`:半透明黑底白字、圆角、1.1em 加粗、黑描边 |
| Python `_yaml_info` | 缓存 `(mtime, name, archived)`;`archived` 严格 `is True` |

## 已知边界与坑

- `group` 属性名与 POSIX 组名冲突 → 专用访问器隔离;列表 "group" 列仍显示 POSIX 组名
- section sorter 必须带全序(GTK 组合排序依据);只判相等会得到任意组间顺序
- GtkSortListModel 无位移重排零信号 → `nautilus_view_model_sort` 补发 `sections-changed`
- 全未分组目录 → 与现状一致(单 section、无组头、排序不变、无徽章)
- 列表零高 header 需实测(隐藏 child 是否残留 1px;备选:置空 child)
- 徽章是叠加层,不占布局空间,图标最小缩放档也不受影响;`can-target: false` 保证点击穿透
- GtkGridView 无法让分组从新行开始(源码级限制)——图标视图用"每项徽章"而非组头表达分组
- 网络视图不受影响(独立视图类,自有 sorter/header factory)
- 树形展开模式:子行同样按组键分组(一致行为)
- YAML 1.1:`archived: yes/on` 解析为 `True`(按约定只写 `true`/`false`;Python 侧严格 `is True`,字符串 `'true'` 不算)

## 验证清单

- 构建:`meson setup build -Ddocs=false --prefix=/usr && ninja`
- 夹具:子项含 `archived: true` / `false` / `yes` / 字符串 `'true'` / 无 yaml 文件夹 / 普通文件
- 矩阵(图标 + 列表 × 全未分组/混合/全分组):未分组在前无组头无徽章、`已归档` 组在后;图标视图每个归档项图标中央有"已归档"徽章;列表视图有整行组头
- 退化用例:单子项且 `archived: true` → 徽章/组头必须出现(验证 sections-changed 补发)
- 开关切换 → 描述消失但分组与徽章保持(解耦);分组状态切排序 → 分区保持、组内跟随;改 yaml → 实时更新
- 徽章在亮/暗主题与浅色图标上的可读性;窗口任意宽度下分组语义一致
- 回归:网络视图分区、列表 "group" 列、图标 caption desc
