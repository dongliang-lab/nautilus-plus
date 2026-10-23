# 功能设计:文件注释(file-desc)

状态:**已实现**(Python 扩展,2026-09-25)

## 背景

`.folder.yaml` 原本只能描述文件夹自身(`desc`)。实际使用中经常需要给**文件夹内的某个文件**加一句说明——「这份是会议记录」「这是最终版」——而不改文件名、不造额外的说明文件。

## 需求决策(用户已确认)

1. **注释同样显示**:复用文件夹描述那条显示通道(`desc` 扩展属性 → 图标视图副标题 + 列表视图描述行),因此 **C 层零改动**
2. **只对文件生效**:子文件夹仍由它自己的 `.folder.yaml` 描述。避免同一显示位有两个来源
3. **顶层键名 `file-desc`**:值为「文件名 → 注释」的映射

## 数据格式

```yaml
desc: 我的项目          # 文件夹自身的描述
file-desc:              # 文件夹内文件的注释
  notes.txt: 会议记录
  report.pdf: 季度报告
```

- 键为**同级文件名**(basename),不含路径
- 读取侧接受块式(默认)与流式(`{a.txt: x}`)两种写法;写入侧统一产出块式
- 空值或纯空白的注释视为无注释,不显示

## 实现

### 显示(nautilus-meta.py)

`_apply()` 分两条路径:

- **文件夹** → 读自身 `.folder.yaml` 的 `desc`
- **文件** → 读**父目录** `.folder.yaml` 的 `file-desc[basename]`,有值且开关打开则 `add_string_attribute('desc', 注释)`

`_yaml_cache` 因此按目录缓存整份解析结果(desc / file_descs),以 mtime 失效——同目录下 N 个文件只解析一次。`_refresh_folder()` 本来就对每个子项调用 `_apply()`,注释随刷新自动生效。

受同一个「隐藏/显示描述」开关控制:关掉后文件夹描述与文件注释一起消失(`_shown` 统一追踪"曾显示过的路径",路径唯一,文件夹与文件可共用一个集合)。

### 编辑(右键菜单)

单选一个本地文件 → 「修改注释」;单选一个本地文件夹是「修改描述」;多选不显示菜单项。

`_open_editor()` 是两种编辑共用的 GTK4 单行窗口(标题、字段标签、初值、保存回调参数化),按 URI 去重、Escape 关闭、写入失败时保留窗口与输入。保存路径:

- 非空 → `_write_file_desc(父目录, 文件名, 值)`
- 空 → `_remove_file_desc_in_folder(父目录, 文件名)`

### YAML 局部更新

现有 `_replace_yaml_key()` / `_remove_yaml_key()` 只处理顶层键。本次把它们重构为「面向任意映射节点」的 `_put_in_mapping()` / `_remove_from_mapping()`,顶层调用保持原语义(现有测试即回归保障),嵌套调用则以 `file-desc` 的值节点为目标:

- 插入位置取该映射的 `end_mark`(实测 PyYAML 的块映射节点跨度**包含末尾换行**);缩进取自首个条目
- 键名转义不手写:`yaml.safe_dump({名: 值}, default_flow_style=True).strip()` 去掉花括号后的内文,块式与流式下都是合法的 `<键>: <值>`
- `file-desc` 不存在则新建;移除最后一个条目后连键一起删;文件再无数据则连同 `.folder.yaml` 一起删(沿用既有语义)
- `file-desc` 存在但不是映射时**报错拒绝写入**,不覆盖用户数据

## 身份与跟随(注释怎么跟着文件走)

注释以「文件名」为键存在父文件夹的 yaml 里,而 nautilus-python **没有文件操作钩子**(只有 InfoProvider / MenuProvider / ColumnProvider / PropertiesModelProvider 四个扩展点),拦截不到重命名或移动事件。因此改为在**刷新时对账**:

**令牌**:写注释时,除了 yaml 条目,还给文件自身写一个不可见的扩展属性 `user.nautilus-plus.desc`,值为 JSON `{"folder": 写入时所在文件夹, "name": 写入时的文件名, "desc": 注释文本}`。yaml 始终是唯一人读来源,令牌只是"搬运工"。

**`_resolve_annotation()` 的四条规则**:

| yaml 条目 | 令牌 | 动作 |
|---|---|---|
| 有 | 缺失或不一致 | yaml 为准,重写令牌(自愈:手改 yaml 后下次刷新即同步) |
| 有 | 一致 | 正常显示 |
| 无 | 有,且 `folder` 或 `name` 与现状不同 | 文件是改名或搬来的 → **采用**:注释写回当前文件夹的 yaml,令牌改写为现状 |
| 无 | 有,且 `folder`、`name` 都与现状相同 | 条目在这里被手删了 → 清掉令牌,不采用(否则手删会被"复活") |

令牌必须同时记 `folder` 和 `name`:只看文件夹的话,"同目录改名"与"同目录手删"完全无法区分。

**自动清理**:加载某文件夹的元数据时核对每个条目对应的文件是否存在,不存在的条目一次性删除——这就是"移走的文件不在原处留下悬空条目"的实现。清理是**懒触发**的:只有该文件夹的元数据被加载时才发生,所以移动后如果从没再打开过源文件夹,那条悬空条目会留到下次打开为止。

缓存键因此从「yaml mtime」改为「(yaml mtime, 文件夹 mtime)」:文件增删改名会改文件夹 mtime,否则 yaml 没变就永远命中缓存、清理永不触发。

## 已知边界

- **跨盘 / 复制到不支持 xattr 的位置**(U 盘、网盘、FAT、未带 `-a` 的 `cp`)→ 令牌丢失,退化为"不跟随 + 清理条目";这是 xattr 方案的固有代价
- **移出后又移回、且中途从未打开过中间文件夹** → 令牌仍是原目录原文件名,会被当作"这里手删了"清掉,注释丢失(角落情况,重加一句即可)
- nautilus 自身复制文件若带 `G_FILE_COPY_ALL_METADATA`,副本会连令牌一起复制 → 副本在新位置继承注释(通常正是期望行为)
- 令牌是扩展自维护的隐藏属性,不进 yaml;手改 yaml 后下次刷新以 yaml 为准同步令牌
- 同一目录内文件名唯一,键不会冲突
- 每个文件刷新时会对父目录的 `.folder.yaml` 做一次 mtime 检查(缓存命中即一次 stat),并读一次令牌;量级与现有文件夹路径相同

## 关键文件

- `plus/extensions/python/nautilus-meta/nautilus-meta.py` —— `_yaml_data()` / `_yaml_file_descs()`、`_set_file_desc()` / `_remove_file_desc()`、`_write_file_desc()` / `_remove_file_desc_in_folder()` / `_drop_file_descs()`、`_put_in_mapping()` / `_remove_from_mapping()`、令牌 helper(`_read_token()` / `_write_token()` / `_clear_token()`)、`_resolve_annotation()`、`_apply()`、`get_file_items()`、`_open_editor()`
- `plus/extensions/python/nautilus-meta/test_nautilus_meta.py` —— `FileDescYamlTests`、`ApplyAnnotationTests`

## 验证

- Python 单测:嵌套写入(新建键 / 追加 / 替换并留注释 / 流式 / 特殊文件名加引号 / 重复键与非法结构报错)、嵌套移除(留下其余、空键连删、空文件连删、不存在则不动)、`_apply` 的文件分支(设值 / 无注释不设 / 空白不设 / 开关关闭不设 / 移除后清空)
- 手工验收:`plus/dev-demo` 下给 `notes.txt` 加注释 → 图标视图副标题与列表视图「描述」列均显示;清空后消失;关闭「显示描述」开关后一并隐藏;手改 `.folder.yaml` 加注释后刷新亦生效
- 跟随验收:同目录改名、跨文件夹移动后注释仍在(且在新位置的 yaml 里出现);删除文件后条目自动消失;手删 yaml 条目后刷新不被复活
