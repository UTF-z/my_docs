# Git命令
## 一、本地命令
### 新建、查看
1. `git init` 新建本地仓库
2. `git log` 查看提交记录
3. `git reflog` 查看简要提交记录
4. `git blame <file>` 查看指定文件修改记录
### 本地暂存区相关
1. `git add <file>` 添加当前工作区更改到暂存区中
2. `git restore <file>` 将当前工作区文件恢复到上一次暂存的状态（如果没有暂存就是上一次提交的状态）
3. `git restore --staged <file>` 将暂存区的指定文件清除（到上一次提交的状态），工作区不变
4. `git rm <file>` 从暂存区和工作区中删除指定文件（-r 递归删除，-f 强制删除）
5. `git rm --cached <file>` 从暂存区中删除文件，但工作区中保留
### 本地仓库相关
1. `git commit -m '<msg>'` 将暂存区更改进行提交到本地仓库
2. `git reset <commitID>` 回到指定commit，暂存区和工作区的变化由下列参数指定 

    > --soft 仓库指针变化，当前暂存区和工作区都不变

    > --mixed 仓库指针变化，暂存区也清空（变成新的commit），当前工作区不变

    > --hard 仓库指针，暂存区，工作区，都变成新的commit
3. `git revert <commitID>` 检查对应的commit和他的父节点的diff，反做这部分diff，从而创建一次新的提交，后面的commit内容不会受影响（但是可能和这次反做有冲突）
    > -n 参数可以避免自动提交，

    > 如果想要revert合并提交，需要-m参数指定回到的父节点
### 分支相关
1. `git branch` 列出所有分支
2. `git branch <br-name>` 创建一个分支
3. `git branch -d` 删除一个已经合并的分支
4. `git branch -D` 强行删除一个分支，即使没有合并
5. `git checkout <br-name>` 切换到指定分支
6. `git checkout -b <br-name>` 创建并切换到指定分支
7. `git merge <br-name>` 把指定分支最后一个提交合并到当前分支上来

## 二、远程命令
### 初始化、远程仓库增删查
1. `git config --global user.name <username>` 设置用户名
2. `git config --global user.email <emailaddr>` 设置邮箱地址
3. `git remote add <远程仓库别名> <远程仓库地址>` 添加一个远程仓库
4. `git remote -v` 查看远程仓库信息
5. `git remote rm <远程仓库别名>` 删除一个远程仓库

### 远程到本地
1. `git clone <远程仓库地址>` 获取一个远程仓库
2. `git clone -b <远程分支名> <远程仓库地址>` 获取远程仓库指定分支
3. `git pull <远程仓库别名> <远程分支名>:<本地分支名>` 将远程仓库指定分支fetch下来再和本地分支merge或者rebase

### 本地到远程
4. `git push <远程仓库别名> <本地分支名>:<远程分支名>` 将本地对应分支推到远程仓库指定分支，没有则新建，若两个分支相同，冒号可以省略
5. `git push -u <远程仓库别名> <本地分支名>:<远程分支名>` 除上条之外，为当前本地分支设置默认远程分支，之后在该本地分支上，push/pull命令可以简写
