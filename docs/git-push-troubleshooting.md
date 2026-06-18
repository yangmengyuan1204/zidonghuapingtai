# Git 推送失败处理流程

用于以后遇到 `git commit` 已成功，但 `git push` 推不上去、卡住、超时或被远端拒绝时快速定位和处理。

## 先判断问题类型

1. 确认本地提交是否已经完成：

   ```powershell
   git status -sb
   git log -1 --oneline
   ```

2. 确认本地比远端多了几个提交：

   ```powershell
   git rev-list --left-right --count origin/<branch>...HEAD
   git log --oneline origin/<branch>..HEAD
   ```

3. 用 dry-run 看远端是否接受，不真正上传对象：

   ```powershell
   $env:GIT_TERMINAL_PROMPT='0'
   $env:GIT_TRACE='1'
   $env:GIT_CURL_VERBOSE='1'
   git push --dry-run --verbose origin <branch>
   ```

## 常见原因和处理

- 认证问题：日志里出现 `401 Unauthorized`、凭据弹窗、token 失效。处理方式是更新 GitHub 凭据或 PAT 后重试。
- 远端冲突：日志里出现 `non-fast-forward` 或 `rejected`。先 `git fetch origin`，再按项目策略 rebase/merge，确认后再推。
- 大文件或大历史：dry-run 能通过，但实际 push 长时间卡住或最终被 GitHub 拒绝。先检查待推对象：

  ```powershell
  git rev-list --objects origin/<branch>..HEAD |
    git cat-file --batch-check="%(objecttype) %(objectname) %(objectsize:disk) %(rest)" |
    Sort-Object { [int64](($_ -split ' ')[2]) } -Descending |
    Select-Object -First 20
  ```

  GitHub 单文件硬限制是 100MB。只要待推历史里出现超过 100MB 的对象，普通删除文件再提交也没用，因为大文件仍在历史里。

## 推荐兜底方案

当当前分支已经混入大文件历史，且只是要提交少量代码/文档改动时，不要继续在这个分支 push。新建干净分支只带目标改动：

```powershell
git fetch origin
git worktree add -b codex/<topic> D:\A_zidonghuapingtai_<topic> origin/master
Set-Location D:\A_zidonghuapingtai_<topic>
git cherry-pick <需要迁移的提交>
git rev-list --objects origin/master..HEAD |
  git cat-file --batch-check="%(objecttype) %(objectname) %(objectsize:disk) %(rest)" |
  Sort-Object { [int64](($_ -split ' ')[2]) } -Descending |
  Select-Object -First 20
git push -u origin codex/<topic>
```

如果 cherry-pick 会带入不该推的大文件，就不要 cherry-pick 整个提交，改为只复制需要的文件改动或重新应用 patch。

## 项目内注意事项

- 脏工作区里不要直接 `git add -A`，先用 `git status -sb` 和 `git diff --cached --stat` 确认只暂存目标文件。
- 不要把 `.venv/`、`ms-playwright/`、安装包、数据库、日志、报告目录提交进 Git。
- 如果必须清理已经写入历史的大文件，需要使用 `git filter-repo` 或 BFG 重写历史；执行前必须先确认，避免破坏其他人的分支。
- 推送成功后，把新分支或 PR 链接发出来；原来推不上去的本地分支不要强推，除非明确确认。
