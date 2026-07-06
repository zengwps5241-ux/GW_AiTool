# AGENTS.md

## 1.本项目规范

- 使用中文进行交互。
- 给代码增加必要的中文注释。
- 每次完成任务自动提交相关的变更，非本次任务相关的变更不要提交。

## Commit 规范
commit message必须以feat,fix,docs,style,refactor,test,chore,revert,Merge,deploy开头。
示例: feat:添加用户登录功能

## Command Output  Protect context usage. **Any command with unknown or potentially large output must be byte-capped.**
Default pattern: 
COMMAND 2>&1 | head -c 4000 