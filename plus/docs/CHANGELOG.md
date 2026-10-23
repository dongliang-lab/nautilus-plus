# 版本日志

## 0.4.2 — 2026-10-24

**名称列按当前目录最长文件名定宽;描述字号调小**

- 名称列宽改按**数据**算:遍历视图 model 取全部文件名(含滚动区外),用真实 Label 的 Pango 布局量宽度;名称列的固定开销(图标/间距/padding)从已渲染单元格反推
- 上限:名称列不超过视图宽度的 50%(`NAME_SHARE`),超长文件名用省略号
- 一行都没渲染时不写宽度(否则全变「…」),等下一次刷新补
- 每进一个目录重算;拖动结果保留到换目录为止
- 描述列字号改为 `0.85em`(`DESC_FONT_SCALE`),通过 `nth-child` CSS 规则只作用于该列
- 修复:`WeakKeyDictionary` 记状态在 PyGObject 下必然失效(包装对象被回收重建),改为强引用 + 每轮清理
- 修复:列头宽度误测了会被拉伸填满的 `GtkColumnViewTitle`,导致宽度自锁
- 修复:图标↔列表切换不重算(切换新建视图且不重跑 provider),改监听 gsettings `default-folder-viewer`,并在 250ms 后补一次
- 单测 60 → 74

## 0.4.1 — 2026-10-24

**列表视图「描述」列紧贴名称列**

- 问题:nautilus 只让名称列 `expand=TRUE`,描述列被推到最右且拖不窄;`Nautilus.Column` 没有宽度属性
- 处理:插件在进程内找到 `Gtk.ColumnView`,描述列可见时把名称列改成内容自然宽度(`expand=FALSE` + `fixed-width`),描述列 `expand=TRUE`;描述列隐藏或用户手动拖动后不再改写
- 顺带:去掉 `Gdk` 的 PyGIWarning(显式 `require_version`)
- 单测 51 → 60

## 0.4.0 — 2026-10-23

**删除归档与 history-paths,C 层全部还原为上游原样(纯插件)**

- 删除功能:分组视图、归档切换、隐藏归档、隐藏汇总卡片、history-paths 自动记录
- 删除 C 改动:全部 `src/`、`data/`、`meson.build`、`test/meson.build` 还原到上游基底 `3671384a2`;fork 新增的 8 个 C 文件删除
- 删除 fork 构建:`plus/meson.build`、`plus/gschema/`、`plus/desktop/`、`plus/icons/`、`plus/dev/deploy.sh`
- 新增 `plus/install.sh`:复制插件到 `~/.local/share/nautilus-python/extensions/` 并重启 nautilus,不需要构建和 pkexec
- 列表视图描述改由 `Nautilus.ColumnProvider` 提供「描述」列(右键列头勾选),不再需要 name-cell 的 C 改动
- `.folder.yaml` 现在只有 `desc`、`file-desc` 两个键;残留的 `archived`/`history-paths` 不读不写、原样保留
- Python 单测 84 → 51(删除归档/history/plus-schema 用例,新增 ColumnProvider 用例)
- 文档同步:删除 6 篇设计文档,重写 AGENTS.md、plus/README.md、research.md、pitfalls.md、requirements.md、folder-yaml skill

## 0.3.0 — 2026-08-19

**fork 独立身份(nautilus-plus)✅ 已实现**,设计见 `design/plus-identity.md`

- 新增 meson `profile=Plus` 构建:`meson setup build --prefix=/usr -Dprofile=Plus -Ddocs=false`
- 二进制 `nautilus-plus`、Application ID `org.gnome.NautilusPlus`(D-Bus 名互不抢占)
- fork 自有的桌面文件与 metainfo(`plus/desktop/`):显示名 `nautilus-plus` / zh_CN「文件管理器增强版」
- **不安装、不注册 `org.freedesktop.FileManager1`**:fork 不抢系统默认文件管理器角色
- 预览器/搜索提供者/FileOperations2 路径自动带 Plus 后缀(PROFILE 机制),与系统实例无交集
- GSettings schema、libnautilus-extension soname、翻译、stock 扩展与系统共享(内容相同,协作非冲突)
- C 改动:devel CSS 类仅 Devel profile;Plus 时跳过 freedesktop D-Bus(含调用点 NULL 守卫)
- 验证:Plus 与默认两个 profile 均构建通过,21/21 测试全绿,desktop/appdata 校验通过
- 安装(需 root,交互式):`sudo ninja -C build-plus install`;启动 `nautilus-plus`
- **Python 扩展挂进 meson(2026-08-19)**:Plus 构建 `install_data` 装 `project-name-zh.py` 到 `/usr/share/nautilus-python/extensions/`(所有用户生效);新电脑依赖清单与完整安装流程见 `plus/README.md`;系统装后需删 `~/.local/...` 旧副本避免双菜单
- **右键修改中文项目名(2026-08-21)**:单个本地文件夹菜单打开 GTK4 单行编辑窗口,预填已有 `name-zh`;支持缺失 `.project.yaml` 时创建,已有文件按 YAML 节点位置局部更新并原子写回,保留其他字段与注释;清空输入确认 = 移除 `name-zh` 键,文件再无数据时连文件一起删除;格式错误和写入失败均保留输入并提示
- **右键归档切换(2026-08-22)**:文件夹(支持多选)右键「归档」/「取消归档」动态标签;写入/移除 `archived: true`,复用注释保留的局部更新与原子写回;幂等跳过已处目标态的文件夹;批量失败汇总弹窗,成功项照常刷新分组视图。设计见 `design/archive-toggle.md`
- **隐藏归档(2026-08-22)**:空白处右键「隐藏归档/显示归档」(仅 fork 显示);C 层新增 `NautilusArchivedFilter` 与 slot 过滤器组合接入视图模型,归档文件夹从图标/列表/搜索/树形模式完全消失(组头随条目消失);Python 开关 ↔ C 过滤器状态走 gsettings fork-only 键 `org.gnome.nautilus.preferences.hide-archived`(默认显示)。设计见 `design/hide-archived.md`
- **隐藏归档汇总卡片(2026-08-26)**:开启隐藏归档且有归档条目时,视图末尾出现独立汇总卡片(网格占一格/列表占一行):分组名「已归档」+ 数量 + 至多 3 条名称(中文名优先);点击临时显示被隐藏条目(不动持久化设置),导航到其他目录自动恢复隐藏。实现为独立卡片对象 `NautilusHiddenGroupCard` 挂 auxiliary `NautilusViewItem` 走 `GtkFlattenListModel` 尾部拼接,不伪造文件、不可选中、不进文件排序/过滤管线;选中转发器排除尾部位置。设计见 `design/hidden-group-card.md`;**修复(2026-08-26)**:扩展属性异步就绪晚于 items 进模型,初始加载/重进路径时归档先放行且无人重评估——`files_view_file_changed`/`end_file_changes` 现在以 idle 合并触发 `gtk_filter_changed(DIFFERENT)` 全量重评(卡片与过滤同源刷新);且 `match` 对「目录 + 属性检索中」的条目保守隐藏(`nautilus_file_is_extension_info_pending`),归档文件夹不再闪现一帧,非归档在属性就绪后正常回归;**再修复(2026-08-26)**:保守隐藏令「纯文件夹目录」在属性就绪前显示为空,重评估放行后条目数变化在 `end_file_changes` 之外——refilter idle 同步刷新空状态页与工具栏,修复打开 `/home/dongliang/projects` 等全文件夹目录显示「Folder is Empty」;**排序/首屏优化(2026-08-26)**:ready 判定补上 `REQUEST_EXTENSION_INFO`,隐藏归档首次加载等待完整文件列表和扩展属性后再安装 monitor/渲染,避免未知分组先显示再重排;共享分组比较器将「已归档」固定置底,普通组以及组内原有名称/日期/大小排序保持不变;**修复(2026-08-26)**:全局切换「显示归档/隐藏归档」时清除卡片点击产生的临时显示状态并即时刷新当前文件夹,避免切回隐藏后仍保留归档条目

## 0.3.9 — 2026-09-29

**新增 skill:`folder-yaml`**

- `plus/skills/folder-yaml/SKILL.md`:把 `.folder.yaml` 的格式与四类操作(给文件夹加描述、给文件加注释、归档文件夹、迁移/改名文件夹)写成一份**面向操作**的技能包,含不变量与"不要做"清单;原理仍留在 `design/` 各文档里
- 目的:让操作文件夹的 agent 有权威依据,而不是从用户私有的 `~/.agents/AGENTS.md` 或开发者向的设计文档里拼凑
- `AGENTS.md` 增加「操作 `.folder.yaml` 之前(必做)」指针;用户级 `~/.agents/AGENTS.md` 的对应长节同步瘦身为指针
- 可安装:`npx skills add dongliang/nautilus-plus --skill folder-yaml -g`(符合 `vercel-labs/skills` 规范:目录含 `SKILL.md`,frontmatter 有 `name` + `description`)
- `plus/dev/deploy.sh` 修正:先以当前用户身份 `ninja -C build` 构建完再 `pkexec` 安装 —— 此前整个 ninja 以 root 运行,会在 `build/` 留下 root 属主产物,导致你之后的构建写不动(见 pitfalls #19)

## 0.3.8 — 2026-09-27

**修复:`meson test` 清空开发者书签的根因**

- **根因**:`test-bookmarks.c` 构造真实的 `NautilusBookmarkList` 并 add 书签,而它保存到 `$XDG_CONFIG_HOME/gtk-3.0/bookmarks` —— 测试进程没隔离配置目录,每跑一次测试就把开发者的真实书签覆盖成它自己的(跑完为空)列表。开发流程每轮都跑 `meson test`,所以表现为"每开发一个功能书签就清空"
- **验证**:只跑 `meson test -C build test-bookmarks`,书签从 41 字节变 0;修复后跑完整套件(21/21)字节数不变
- **修复**:`test/meson.build` 的 `test_env` 增加 `XDG_CONFIG_HOME=<构建根目录>`,测试的用户级配置一律落在构建目录内
- `pitfalls.md` #18 记录排查过程(此前误判为安装/启动导致)

## 0.3.7 — 2026-09-27

**自动记录 `history-paths`(C 提供移动事件,Python 写规则)**

- 新增 C 层**通用能力**:`src/nautilus-plus-events.{c,h}` 在 `nautilus_directory_notify_files_moved()` 里,把每一对 (from, to) 通过 D-Bus 信号 `Moved(from_uri, to_uri)` 广播出去(总线名 `org.gnome.NautilusPlus`)。**C 不含任何业务语义**
- Python 层订阅该信号并实现规则:目标端是本地目录、且不含该路径时,把**旧路径**追加进 `.folder.yaml` 的 `history-paths`(没有 yaml 则创建,字段缺失则新建);重复路径不追加
- 用途:文件夹移动后,靠这些旧路径找回并改写各 coding agent 会话记录里的路径,让会话跟着文件夹迁移
- 覆盖范围:GUI 改名/拖动/剪切粘贴 ✅;nautilus-plus 正显示的目录内的终端移动 ✅;跨目录且两端不在同一被监视目录 ❌(由 agent 规则兜底);创建文件夹不受影响
- **分层原则的表述随之更正**(`AGENTS.md` 决策 3/5、`plus/README.md`、`research.md`、`grouped-view.md`):C 只提供**通用能力**,业务规则永远在 Python —— 而不是"C 只做某个功能"
- Python 单测 70 → 84;设计见 `design/history-paths.md`

## 0.3.6 — 2026-09-26

**部署期给书签加一层临时保险**

- **缘起**:开发若干轮后侧栏书签被清空。排查确认:书签文件只在用户改动时写入,安装流程不碰它(实测退出→安装→启动后 inode/大小/mtime 未变);清空来自某次应用内的保存,而那一刻内存里的列表是空的
- **做法**:新增 `plus/dev/deploy.sh` 作为开发部署入口——安装前把书签临时复制一份,安装后条目数变少就还原,用完即清。不留历史目录、不留常驻单元、不做启发式判断
- `AGENTS.md` 的安装与验收环节改用该脚本;`pitfalls.md` #17 记录排查结论与这层保险的边界

## 0.3.5 — 2026-09-26

**文件注释能跟着文件走了**

- **问题**:注释以文件名为键存在父文件夹的 yaml 里,文件一旦重命名或移动就与注释失联——新位置没有注释,原文件夹留下悬空条目(且同名新文件会静默继承旧注释)
- **令牌**:写注释时额外给文件自身写扩展属性 `user.nautilus-plus.desc`(JSON:`folder` / `name` / `desc`)。yaml 仍是唯一人读来源,令牌只是搬运工。必须同时记文件夹与文件名——只看文件夹无法区分"同目录改名"与"同目录手删"
- **跟随**:刷新时对账(`_resolve_annotation()` 四条规则)——yaml 与令牌不一致时 yaml 为准并重写令牌(手改 yaml 后自动同步);文件被改名或搬来而 yaml 无条目时采用令牌并写回当前文件夹的 yaml;条目被手删且令牌指向的就是此处时不采用并作废令牌(避免"复活")
- **清理**:加载文件夹元数据时删掉指向已不存在文件的条目;缓存键加入文件夹 mtime,否则文件搬走后不会触发重算
- 边界:跨盘/不支持 xattr 的位置(U 盘、网盘、FAT、未带 `-a` 的 `cp`)令牌丢失,退化为"不跟随 + 清理";移出后又移回且中途从未打开中间文件夹的角落情况会丢注释
- Python 单测 62 → 70(新增 `AnnotationTokenTests`,xattr 不可用时自动跳过);设计见 `design/file-desc.md`

## 0.3.4 — 2026-09-25

**文件注释 `file-desc`**

- `.folder.yaml` 新增顶层键 `file-desc`(文件名 → 注释),给文件夹内的文件加注释;右键单个文件「修改注释」编辑
- 显示复用文件夹描述那条通道(`desc` 扩展属性),**C 层零改动**;受同一个「显示/隐藏描述」开关控制
- 只对文件生效:子文件夹仍由它自己的 `.folder.yaml` 描述,避免同一显示位两个来源
- YAML 局部更新助手由「仅顶层键」重构为「面向任意映射节点」,顶层行为不变(现有测试即回归);新增嵌套写入/移除,`file-desc` 空则连键删、文件空则连文件删
- 已知限制:注释以文件名为键,重命名或移出后失效(不报错、不自动跟随)
- Python 单测 41 → 62(`FileDescYamlTests`、`ApplyAnnotationTests`,后者首次覆盖 `_apply`);设计见 `design/file-desc.md`

## 0.3.3 — 2026-09-25

**「中文名」概念整体改称「描述」(`desc`)**

- **理由**:用途不限于中文(可以是任意语言的文件夹说明),且元数据文件已改名 `.folder.yaml`,「中文名」已不贴合
- 字段与属性:YAML 顶层键 `name-zh` → `desc`;扩展属性 `name-zh` → `desc`(图标视图副标题、列表视图描述行、隐藏归档卡片明细三处共用)
- 插件改名:`project-name-zh.py` → `nautilus-meta.py`(目录同名);配置目录 `~/.config/nautilus-project-zh/` → `~/.config/nautilus-meta/`;菜单 ID `ProjectNameZh::*` → `FolderMeta::*`;类名 `ProjectNameZh*` → `FolderMeta*`
- 界面文案:菜单与对话框「修改中文名」→「修改描述」,背景开关「隐藏/显示中文项目名」→「隐藏/显示描述」,相关报错同步
- **captions 迁移**:图标视图 captions 及备份里的 `name-zh` 会被就地归一化为 `desc` 并去重——不做这步会残留一条解析不出值的空 caption,还会把用户的原始备份覆盖掉
- **磁盘迁移**:13 个 `.folder.yaml` 的 `name-zh:` 键改写为 `desc:`(保留注释与其他键);配置目录整体迁移;旧装的 `project-name-zh.py` 必须删除(否则双菜单,pitfalls #5)
- 不留旧名回退;Python 单测 36 → 41(新增 captions 迁移用例)
- 另记:构建期改 `.blp` 可能不触发重编译,见 pitfalls #16

## 0.3.2 — 2026-09-24

**元数据文件改名 `.project.yaml` → `.folder.yaml`**

- **理由**:用途是通用文件夹元数据(`notes/` 里存的是文件夹别名,不是项目);且 `.project.yaml` 与 MuleSoft PDK 的文件同名,`.folder.yaml` 经检索基本无人占用(仅一个个人站点仓库,且是 `.yml` 变体另有其人)
- 代码:`YAML_NAME` 常量 + 文案/文档共 26 处替换;磁盘 14 个文件一次性迁移(11 个用户目录 + 3 个 dev-demo 夹具)
- **不留旧名回退**:迁移已完成,代码只认 `.folder.yaml`
- 本条目之前的历史记录中出现的 `.project.yaml` 即今 `.folder.yaml`

## 0.3.1 — 2026-09-14

**修复 pacman 全量更新后闪退 ✅**

- **根因**:fork 把 `hide-archived` 键加在 `org.gnome.nautilus.preferences`(文件路径由发行版 `nautilus` 包拥有),系统升级把 schema 换回上游版本 → 键消失 → C/Python 读取时 `g_error()` 直接 abort,nautilus-plus 一开窗口就退出
- **迁移**:**fork 专属设置改用独立文件** `plus/gschema/org.gnome.NautilusPlus.gschema.xml`(schema id `org.gnome.NautilusPlus.preferences`);上游 schema 恢复与官方发行版逐字节一致,fork 不再修改任何发行版包拥有的文件 → 以后升级不受影响
- **防御**:C(`g_settings_schema_source_lookup` + `has_key` + `new_full`)与 Python(同样先 lookup 再 `Settings.new_full`)都改为缺失时降级为「显示归档」并打印一次警告,绝不 abort;schema 不可用时背景菜单不再提供该开关
- Python 单测 32 → 36(schema 缺失降级、菜单不提供);设计文档与 `pitfalls.md` #15 同步
- 一次性副作用:`hide-archived` 随 schema id 迁移回默认值(显示归档),重新切换一次即可

## 0.1.0 — 2026-08-17

**中文项目名显示(name-zh)✅ 已上线**

- 图标视图在文件夹英文名下方显示 `.project.yaml` 顶层 `name-zh` 的中文名
- 磁盘名/路径/F2 改名不受影响;改中文名直接编辑 yaml
- 右键空白处菜单全局开关(动作式标签:隐藏/显示中文项目名),切换即时生效
- captions 自动配置并备份恢复;状态存 `~/.config/nautilus-project-zh/state`
- 在 `2.nautilus-ex` 项目完成(原提交 `d0a969f`),本仓库引入并建立文档体系

**归档功能探索(未上线)**

- 排序置底:验证不可行(纯插件,gvfs 只存 `metadata::` 命名空间)——详见 `research.md` 死路清单
- emblem 角标:实现后用户决定撤销——详见 `pitfalls.md`(index.theme、双菜单等坑)
- 字段约定:`archived: true`(保留备用)

## 0.2.0 — 计划中

- **决策(2026-08-18)**:fork 基底 = **`gnome-50` 稳定分支**(`main` 开发线要求未发布的 glib ≥ 2.89,在稳定系统上无法构建);本地 `main` 已重置为 gnome-50 并保留全部文档提交(GitHub fork 的 main 未动)
- **初始构建成功(2026-08-18)**:`meson setup build -Ddocs=false && ninja`,404 目标全过,产物 `build/src/nautilus`(约 16 核 2 分钟内;1 条无害警告,上游 GI 绑定自带)

- **决策(2026-08-17)**:显示名覆盖钩子**已否决**——底部 caption 方案更优(理由:心智一致性/零 fork 成本/信息更全/无边界怪癖,详见 `research.md` 第 1 节)。fork 唯一动机 = **分组视图**
- **分组机制已实现(2026-08-19)**,设计见 `design/grouped-view.md`:
  - C 钩子:新增 `nautilus-grouped-view.c`(分组键读取 + 3 个 sorter 工厂)、`nautilus_file_get_extension_attribute` 访问器(绕开 `group` 属性名与 POSIX 组名的内建冲突)、`nautilus_view_model_sort` 补发 `sections-changed`(修复 GtkSortListModel 无位移重排静默)
  - 图标视图:单元格顶部组头横条(仅组内第一项,同组其余项预留等高空位对齐);列表视图:原生 `gtk_column_view_set_header_factory` 组头
  - 未分组条目排最前、不渲染任何"未分组"组头;组间按分组键 strcmp 升序,`reversed` 只影响组内
  - 列表视图:原生 header factory 整行组头;图标视图:**每个分组项图标中央显示分组名徽章**(GtkGridView 无 section 感知、无法让分组另起一行——源码级确认;徽章半透明黑底白字+描边,按文件夹图标形状居中,`can-target: false` 点击穿透)
  - Python 测试驱动:`archived: true`(严格布尔)→ `group` 扩展属性 `已归档`;**分组与 name-zh 开关解耦**(开关只控制中文名)
  - 构建验证通过(2026-08-19);扩展安装 `~/.local/share/nautilus-python/extensions/` 实测加载正常
- **列表视图中文项目名(2026-08-19)**:`nautilus-name-cell` 名称单元格在英文 `display-name` 后追加 `name-zh` 中文名 label,样式沿用网格视图 caption 的 `caption + dim-label`(同一颜色);`file-changed`/bind 时随 `update_labels` 刷新,无中文名时隐藏
- 扩展重组(后续):改名 `nautilus-meta.py`(菜单 ID、配置目录同步),纳入 `plus/extensions/python/`
