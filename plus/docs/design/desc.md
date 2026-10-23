# 功能设计:文件夹描述显示(desc)

状态:**已实现**(扩展 `nautilus-meta.py`,v0.1.0);字段名 2026-09-25 由 `name-zh`(中文名)改为 `desc`(描述)。**文件级注释**见 `file-desc.md`

## 背景

nautilus 50 的扩展 API **无法修改文件夹的显示名**(见 `research.md` 死路清单),因此 v0.1.0 采用"第二行 caption"方案:描述显示在文件夹名**下方**的一行灰字里,不替换原名。磁盘名、路径、F2 改名完全不受影响。

## 机制

- 图标视图的名字标签是独立控件(captions 之上的第一行,绑定 `display-name` 属性)
- captions 是名字下方的额外行,由 gsettings `org.gnome.nautilus.icon-view` 的 `captions` 键驱动
- captions 值可以是**任意属性名**;nautilus 对未知属性名会回落到扩展属性表(`nautilus-file.c` `nautilus_file_get_string_attribute_q` 的末尾查找)
- 因此:插件 `add_string_attribute('desc', 描述)` + captions 配置 `['desc']` → 描述成为图标下第二行

## 架构

```
InfoProvider.update_file_info(每个可见文件)
  └─ 目录? → 读 <dir>/.folder.yaml(PyYAML,顶层 desc)
       ├─ 有值且开关开 → add_string_attribute('desc', 值)
       └─ 曾显示过且现在无值 → add_string_attribute('desc', '') 清空

MenuProvider.get_background_items(右键空白处)
  ├─ 菜单项标签 = 当前状态的**动作**(隐藏/显示描述)
  └─ 激活 → 翻转状态文件 → 同步 captions → 刷新当前目录 → 触发菜单重建
```

## 关键组件

| 组件 | 说明 |
|---|---|
| 状态文件 | `~/.config/nautilus-meta/state`(`on`/`off`,默认 on,mtime 缓存) |
| captions 同步 | 开关开:`['desc']` + 备份原值;关:恢复原值(原子写入) |
| 实时刷新 | 枚举当前目录子项 → `Nautilus.FileInfo.lookup_for_uri` → `invalidate_extension_info()`(nautilus 会清空扩展属性/角标后重跑 provider) |
| 菜单标签翻转 | 对当前文件夹重加一次扩展属性 → `nautilus_file_changed` → 视图调度菜单重建(约 0.5s) |
| yaml 缓存 | `{path: (mtime, name)}`,上限 1024,解析失败缓存 None |

## 列表视图「描述」列

- `FolderMetaColumns(Nautilus.ColumnProvider)` 注册列 `FolderMeta::Desc`,属性 `desc`
- **列宽**:nautilus 让名称列 `expand=TRUE`、其余列 `expand=FALSE`(`src/nautilus-list-view.c`),描述列因此被推到最右且拖不窄。`Nautilus.Column` 没有宽度/expand 属性,所以在进程内改 GTK 控件:
  - 描述列可见时:名称列 `expand=FALSE` 并 `fixed-width` = 内容自然宽度(取名称单元格与列头中较宽者);描述列 `expand=TRUE` 吃掉剩余空间
  - 描述列隐藏时:恢复 nautilus 原样(名称列 `expand=TRUE`、`fixed-width=-1`)
  - 用户手动拖动过名称列后不再改写它的宽度(记住最后一次自己设的值,发现被改过就认作拖动)
  - 触发点:`InfoProvider.update_file_info` 末尾 `GLib.idle_add` 合并调度,每次进目录/刷新都会校正一次
  - 失败静默:找不到控件或上游结构变化时退化为原样,不报错

## 已知边界

- 图标最小缩放档只显示名字一行,captions 隐藏(nautilus 自身行为)
- 列表视图通过 ColumnProvider 单独提供「描述」列(见下);列宽由插件在进程内调整,描述紧贴名称列
- 非 `file:` URI(网络挂载)跳过

## 右键修改描述

### 范围

- 单个本地文件夹的文件右键菜单显示「修改描述」
- 多选、普通文件、远程位置不显示该菜单项
- 不改变磁盘上的文件夹名、路径或 Nautilus 的 F2 重命名行为

### 交互

- 激活菜单后打开异步 GTK4 编辑窗口,使用单行输入框
- 输入框预填已有 `.folder.yaml` 顶层 `desc`,没有元信息时为空
- 确认时去除首尾空白;空值表示清除描述——移除顶层 `desc` 键(保留其他字段与注释),若文件再无任何数据则连同删除整个 `.folder.yaml`
- 写入失败弹出错误提示,编辑窗口和原有输入保持不变,用户可修正后重试
- 保存成功后关闭窗口并立即失效目标文件的扩展信息

### YAML 更新

- `.folder.yaml` 不存在时创建包含顶层 `desc` 的 UTF-8 文件
- 已存在文件先用 PyYAML 校验;根节点必须是 mapping,解析失败或文件超过大小限制时拒绝覆盖
- 通过 YAML 节点位置只替换顶层 `desc` 的值;缺少该键时在文档末尾添加
- 保留其他字段、键顺序、注释、空行和原有格式
- 输入限定为单行文本;序列化值必须能被 PyYAML 再次解析为原输入
- 使用同目录临时文件和 `os.replace` 原子替换,写入失败时原文件不变

### 刷新链路

```
文件右键菜单
  └─ Gtk.Window 保存
       ├─ 局部更新 <folder>/.folder.yaml
       ├─ 清除 _yaml_cache
       ├─ _apply(file)
       └─ file.invalidate_extension_info()
            └─ caption / 分组属性即时重算
```

### 验证

- 纯函数测试覆盖新建、已有键更新、缺少键追加、注释与其他字段保留、非法 YAML、非 mapping 和超大文件
- 菜单过滤覆盖单文件夹、多选、普通文件和远程 URI
- 手工验收覆盖已有 `desc` 预填、无 yaml 创建、保存后 caption 刷新、空值提示和写入失败重试
