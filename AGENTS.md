# nautilus-plus 项目指南

nautilus(GNOME Files)的定制 fork。上游 C 代码 + `plus/` 目录存放全部 fork 专属内容(文档体系 + Python 扩展)。

本文件是**唯一权威的项目规则**(opencode 的 AGENTS.md)。Claude Code 读 `.claude/CLAUDE.md`、Codex 读 `.codex/AGENTS.md`,两者均为指向本文件的引用,不要在其中复制内容。

## 开工前必读(按顺序)

1. `plus/docs/requirements.md` — 原始需求(短而笼统)
2. `plus/docs/research.md` — 技术调研:已验证机制 / 死路清单 / fork 钩子蓝图 / 架构决策(全部有源码依据)
3. `plus/docs/pitfalls.md` — 踩坑记录(避免重复踩)
4. `plus/docs/CHANGELOG.md` — 版本日志与当前进度
5. `plus/README.md` — 目录结构与 C/Python 分层说明
6. `plus/docs/design/` — 各功能设计文档(`desc` / `file-desc` / `history-paths` / `grouped-view` / `archive-toggle` / `hide-archived` / `hidden-group-card` / `plus-identity`)

## 操作 `.folder.yaml` 之前(必做)

给文件夹加描述、给文件加注释、归档文件夹、移动或改名文件夹 —— **动手前先加载 `plus/skills/folder-yaml/SKILL.md`**。格式、不变量、四类操作的具体做法都在那里;本文只留指针,不重复其内容(避免两处规则漂移)。

该 skill 也可装给任意 agent:`npx skills add dongliang/nautilus-plus --skill folder-yaml -g`。

## 当前状态

fork 已独立成型:Plus 构建产出 `nautilus-plus`(独立应用 ID,与系统 nautilus 并行不冲突),见 `design/plus-identity.md`。

已上线功能(实现细节见各自设计文档):

- **文件夹描述**:`.folder.yaml` 的 `desc` 显示在图标视图副标题与列表视图描述行;右键「修改描述」编辑
- **文件注释**:`.folder.yaml` 的 `file-desc` 给文件夹内的文件加注释,显示位置同描述;右键文件「修改注释」编辑。注释跟着文件走(重命名/移动自动跟随,见 `design/file-desc.md`)
- **历史路径**:`.folder.yaml` 的 `history-paths` 自动记录文件夹用过的旧路径(供 agent 迁移会话);C 层广播移动事件,规则在 Python(见 `design/history-paths.md`)
- **分组视图**:`archived: true` 的文件夹归入「已归档」组(图标徽章 / 列表组头),该组固定排在普通组之后,组内沿用原有排序
- **归档切换**:右键文件夹「归档 / 取消归档」(支持多选)
- **隐藏归档**:空白处右键开关,归档文件夹从图标/列表/搜索/树形模式中消失;C 过滤器实现,状态走 fork 自有 gsettings(见决策 6)
- **隐藏汇总卡片**:隐藏归档时视图末尾显示「已归档」卡片(数量 + 部分名称,点击临时显示,导航后恢复)

版本与逐条进度以 `plus/docs/CHANGELOG.md` 为准。

## 已定决策(除非用户明确改变,不要推翻)

1. **显示名覆盖钩子已否决**(2026-08-17)——描述用 caption 第二行方案:真名在上、描述在下。不要重新提议"替换显示名"
2. `.folder.yaml` 是文件夹元数据文件:文件夹内 dotfile(随文件夹移动、工具无关),顶层键 `desc`(字符串)、`archived: true`(布尔,备用)、`file-desc`(映射:文件名 → 注释)、`history-paths`(列表:用过的旧路径,扩展自动维护)。**改名记录(2026-09-24)**:原名 `.project.yaml`,因用途是通用文件夹元数据而非项目专用、且 `.project.yaml` 与 MuleSoft PDK 的文件重名,改为 `.folder.yaml`;磁盘上的旧文件已一次性迁移,代码不留旧名回退
3. 架构分层:**C 只提供通用能力(不写业务),业务规则全部在 Python 扩展**;钩子保持"数据源可换"(只认扩展属性,不认写属性者)
4. 扩展已改名 `nautilus-meta.py`(2026-09-25 完成):目录、菜单 ID(`FolderMeta::*`)、配置目录 `~/.config/nautilus-meta/`、类名同步;同日「中文名」概念整体改称「描述」`desc`
5. **C 层只提供通用能力,业务永远在 Python**(2026-09-27 修订):fork 的 C 改动只在"Python 扩展够不到"时才引入,且必须做成**通用能力**、不为某个具体功能定制;读什么、写什么、怎么判断,一律留在 Python。已提供的能力:**分组/排序与视图过滤**(视图模型 Python 够不到)、**文件移动事件广播**(C 层 D-Bus 信号,Python 够不到 nautilus 内部对象)。反面例子:不要在 C 里解析 `.folder.yaml`、判断某个功能的开关或决定业务行为。另:描述、归档标记纯插件可达(扩展 API 已验证),无需 C
6. **fork 专属设置必须放 fork 自有的 schema 文件**(2026-09-25):`plus/gschema/org.gnome.NautilusPlus.gschema.xml`,id `org.gnome.NautilusPlus.preferences`。**不得**加进发行版包拥有的文件(如上游 `data/org.gnome.nautilus.gschema.xml`)——系统升级会覆盖该文件,键消失后 `g_settings_get_boolean()` 直接 `g_error()` abort,表现为整个文件管理器开窗即闪退。读取侧一律先 `lookup()` + `has_key()` 再取设置对象,缺失时降级而非崩溃(详见 pitfalls #15)

## 开发约定

- **开工铁律:开发任何功能前,必须先读完「开工前必读」的全部文档**(requirements → research → pitfalls → CHANGELOG → README → design/),确认已验证的机制与死路后再动手;不能跳过、不能凭印象开工
- **Python 扩展**:改 `plus/extensions/python/nautilus-meta/`;按下方验收流程**本地安装到系统**生效;快速迭代也可临时装 `~/.local/share/nautilus-python/extensions/`,但**系统副本必须删除**,两者同存会双菜单(pitfalls #5);改后 `nautilus-plus -q` 重启生效;错误输出在 nautilus stderr
- **C 改动**:标准 meson 构建(上游约定);fork 基底是上游 `gnome-50` 稳定分支,需要对照上游时自行添加 `upstream` 远端(GNOME/nautilus);fork 专属内容只放 `plus/`,不碰上游目录(`docs/`、`extensions/` 是上游的)
- **提权**:一律用 `pkexec`(如 `pkexec ninja -C build install`,会弹图形密码框);**禁用 sudo/su/doas**;pkexec 失败就停下问用户
- **提交前必跑**:`ninja -C build`、`meson test -C build`(21 个)、`python3 -m unittest discover -s plus/extensions/python/nautilus-meta -p 'test_*.py'`(41 个)、`git diff --check`
- **改了 gsettings schema 或 `.blp` 必须重新构建安装**才生效;`.blp` 改动可能不触发重编译,需 `touch` 该文件(见 pitfalls #16)
- 新功能先写设计文档(`plus/docs/design/`)再动代码
- 环境:nautilus 50.x + nautilus-python 4.1,GI 版本号 `4.1`,依赖 PyYAML

## 每个开发任务的验收环节(必做)

任何 C/Python 改动完成后,必须**本地安装到系统**,再打开 `plus/dev-demo/` 人工验收:

1. **构建**:`meson setup build --prefix=/usr -Dprofile=Plus -Ddocs=false`(prefix 必须为 /usr,见 pitfalls.md 第 12 条;已配置时 `ninja -C build` 增量即可)
2. **本地安装**:`plus/dev/deploy.sh`(内部即 `pkexec ninja -C build install`,额外在安装前后临时备份书签文件、条目变少则还原,见 pitfalls #17)
3. **打开**:`nautilus-plus plus/dev-demo`(fork 是独立应用 ID,与系统 nautilus 并行不冲突,无需退出系统实例;重启 fork 用 `nautilus-plus -q`)
4. **验收内容**:`plus/dev-demo/` 含 `alpha-project`(desc + archived)、`beta-project`(仅 desc)、`gamma-project`(仅 archived)、`plain-dir`(无 yaml)、`notes.txt`(普通文件);分别用图标视图和列表视图检查描述显示与分组效果;再验空白处右键的「隐藏归档」及其汇总卡片
5. 验收后如无遗留需求可退出窗口,不强制清理

## 安装到系统

- fork 身份安装:`meson setup build --prefix=/usr -Dprofile=Plus -Ddocs=false && ninja -C build && plus/dev/deploy.sh`(等价于 `pkexec ninja -C build install`,外加书签兜底),启动 `nautilus-plus`(设计见 `plus/docs/design/plus-identity.md`);新电脑先装依赖(`plus/README.md` 有完整清单)
- **Python 扩展随 install 自动装到 `/usr/share/nautilus-python/extensions/`**(Plus 构建,所有用户生效);开发迭代仍装 `~/.local/share/nautilus-python/extensions/`,两者同存会双菜单(pitfalls #5),系统装后删用户副本