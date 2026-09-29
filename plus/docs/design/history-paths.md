# 功能设计:文件夹历史路径(history-paths)

状态:**已实现**(C 提供移动事件 + Python 记录规则,2026-09-27)

## 背景

`.folder.yaml` 的 `history-paths` 记录该文件夹**曾经用过的绝对路径**。用途不在界面:文件夹被移动后,靠这些旧路径去各 coding agent 的会话记录(Claude Code / Codex / opencode 等的 json/db)里搜索并改写到新路径,让 agent 的会话跟着文件夹一起迁移。

这原本靠 agent 手工维护(移动前先追加当前路径)。本功能让 nautilus-plus 自动记录。

## 为什么需要 C 介入

nautilus-python **只有** InfoProvider / MenuProvider / ColumnProvider / PropertiesModelProvider 四个扩展点,**没有文件操作钩子**;而且 Python 够不到 nautilus 内部对象(`NautilusDirectory`/`NautilusApplication` 都不在 GI 暴露的类型里),挂在它们上面的 GObject 信号也连不上。所以"移动发生了"这个事实必须由 C 层广播出来。

nautilus 内部早有一条现成通路:

```
nautilus-monitor.c(G_FILE_MONITOR_WATCH_MOVES)
    处理 MOVED_IN / MOVED_OUT / RENAMED
    → nautilus_file_changes_queue_file_moved(源, 目标)
    → nautilus_directory_notify_files_moved(GList<GFilePair*>)
        pair->from / pair->to  ← 旧路径与新路径都在
```

## 分层

**C 只报事实,不写业务**(见 `AGENTS.md` 决策 5):

- `src/nautilus-plus-events.c` 在 `nautilus_directory_notify_files_moved()` 里,对每个 (from, to) 广播 D-Bus 信号:
  - 总线名 `org.gnome.NautilusPlus`,对象路径 `/org/gnome/NautilusPlus`
  - 接口 `org.gnome.NautilusPlus.FileMonitor`,信号 `Moved(ss)` = `from_uri`、`to_uri`
  - C **不判断是不是目录、不碰 `.folder.yaml`、不认 history-paths**

**Python 拿事实写规则**(`nautilus-meta.py` 订阅该信号):

```
两端都是本地路径吗             → 否则忽略
to 是目录吗                    → 否则忽略(只管文件夹)
to 没有 .folder.yaml           → 创建它
   from 已在 history-paths 里   → 不加
   否则                        → 追加 from(字段缺失则新建该字段)
```

- **追加的是旧路径**:那才是"找旧会话"要用的东西,也与 agent 手工规则(移动前记当前路径)一致
- 同目录改名与跨目录移动走同一条规则
- 写入沿用既有做法:`_append_history_entry()` 做局部更新(块式追加 / 流式插入 / 字段缺失时新建 / 裸键补值),保留注释与其他字段;路径按**序列项上下文**加引号(`- /a: b` 会被解析成映射,必须写成 `- '/a: b'`),写完再整体回读校验一次,宁可报错也不留下读不回来的文件

## 覆盖范围

关键不是"谁发起的移动",而是"nautilus-plus 是否在监视那里、GLib 能否把前后两半配对":

| 情形 | 是否记录 |
|---|---|
| nautilus-plus GUI 里改名 / 拖动 / 剪切粘贴 | ✅ 即时精确 |
| 终端 `mv` 在**正显示的目录内**改名或同目录移动 | ✅ 监视器能配对 |
| 终端 `mv` 到**另一个目录**(跨目录) | ❌ GLib 不提供跨监视器配对 |
| 其他程序 / 系统**新建**文件夹 | ❌ 不受影响(只监听移动,不监听创建) |
| 其他未被 nautilus-plus 显示的目录里的改名 | ❌ 那里没在监视 |
| nautilus-plus 没运行时发生的一切 | ❌ 无信号 |

跨目录移动的缺口多半是 agent 自己干的,而 agent 知道自己做了什么 → 现行 agent 规则正好补上。

## 已知边界

- 移动后被记录之前,目标文件夹需被 nautilus-plus 显示过一次(信号是即时收到的,记录立即执行;不需要额外浏览)
- 不支持会话总线时静默跳过(历史不自动记录,不报错)
- 路径里含换行会被拒绝(写入前校验)
- 同一路径重复出现不重复追加

## 关键文件

- `src/nautilus-plus-events.{c,h}` —— 通用事件出口
- `src/nautilus-directory.c` —— `nautilus_directory_notify_files_moved()` 里发信号
- `plus/extensions/python/nautilus-meta/nautilus-meta.py` —— `_subscribe_move_signal()` / `_on_move_signal()` / `_record_move()` / `_append_history_entry()`

## 验证

- Python 单测(`HistoryPathTests`):字段新建 / 块式追加 / 流式插入 / 空 `[]` / 裸键 / 特殊路径加引号 / 注释与其他字段保留 / 重复不追加 / 非目录忽略 / 远程 URI 忽略
- 端到端(实测通过):
  - `gdbus monitor --session --dest org.gnome.NautilusPlus` 能看到 `Moved` 信号
  - 在 GUI 里改名一个带 yaml 的文件夹 → 它的 `.folder.yaml` 出现 `history-paths`,内容为旧路径
  - 改名一个**没有** yaml 的文件夹 → 创建 `.folder.yaml` 并写入旧路径
