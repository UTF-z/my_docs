<head>
<style>
    .tech-tutorial {
        font-family: 'Segoe UI', Consolas, monospace;
        padding: 2rem;
        border-radius: 10px;
        border: 1px solid #00ff9d;
        box-shadow: 0 0 20px rgba(0, 255, 157, 0.1);
    }
    h1 {
        text-align: center;
    }
    h2 {
        color: #00ff9d;
        padding-bottom: 0.5rem;
    }
    p {
        font-family: 'Roboto', sans-serif; /* 你可以选择其他现代感的字体 */
        font-weight: 300; /* 轻量的字体，可以增加科技感 */
        font-size: 18px; /* 字体大小可以根据需要调整 */
        line-height: 1.6; /* 增加行间距，使文本更易读 */
        margin-top: 20px; /* 上边距 */
        margin-bottom: 60px; /* 下边距 */
        letter-spacing: 0.5px; /* 字母间距稍微增大，增加科技感 */
        color:rgb(0, 0, 0); /* 科技感的字体颜色，你可以选择其他冷色调 */
        padding: 10px; /* 内边距，增加文字与段落边框的距离 */
    }
    pre {
        padding: 1rem;
        border-left: 3px solid #00ff9d;
        overflow-x: auto;
    }
    figure {
        box-shadow: 0 0 10px rgba(0, 255, 157, 0.2);
        display: block;
        width: 70%;
        margin: 0 auto;
    }
    .warning {
        color: #ff5555;
        background: #2d1a1a;
        padding: 1rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
    .terminal {
        font-family: Consolas;
        background: #000;
        color: #00ff9d;
        padding: 1rem;
        border-radius: 5px;
    }
    .banner {
        width: 100%;
    }
</style>
</head>

<div class="tech-tutorial">

# 🚀 Windows系统VSCode C/C++开发环境配置指南
<figure src=figures/banner.jpg class='banner'>
</figure>

## 🔍 环境预检
### 1. 安装VSCode
访问[VSCode官网](https://code.visualstudio.com/)下载安装最新版本

### 2. 检测编译套件
```powershell
# 通过Windows下方搜索栏搜索Power shell，打开PowerShell执行
gcm g++
```

✅ **预期结果**：  
若报错则继续下一步  
![检测结果](figures/nog++.png)
若发现已安装，请记录`Source`路径（如图示）并跳至第7步  
![检测到g++](figures/g++.png)

---

## ⚙️ 编译套件部署
### 3. 获取MinGW套件
可以直接[官方下载](https://github.com/.../winlibs-x86_64-...r3.zip)  
如果官方下载很慢，可以用[校内镜像](https://oc.sjtu.edu.cn/.../download?download_frd=1)  

### 4. 解压安装
```
压缩包解压之后，把里面的mingw64文件夹移动到一个你喜欢的地方，并记住它的路径，备用
推荐路径：`C:\Program Files\mingw64`
```
<div class='warning'>
📌 重要提示：路径禁止包含中文/空格！
</div>

![安装路径](figures/mingwpath.png)

---

## 🌐 系统环境配置
### 5. 添加PATH变量
```markdown
1. Windows下方搜索栏搜索"环境变量" → 选择"编辑系统环境变量"
2. "环境变量..." → 下方的“系统变量（S）”栏 → 下拉,找到并双击“Path”
3. 点击新建，添加bin路径：`<刚才mingw64的路径>\bin`
```
<div class='warning'>
📌 上面尖括号中的内容替换成你刚才mingw64的路径，不要原样粘贴。比如刚才我的路径是C:\Program Files\mingw64，这里我就填入C:\Program Files\mingw64\bin
</div>

![环境变量配置](figures/addpath.png)

### 6. 验证安装
```powershell
# 新开PowerShell窗口执行
gcm g++
```
<div class='warning'>
📌 注意这一步要重新打开一个新的PowerShell，刚改的环境变量在老窗口里没生效
</div>
✅ 成功标志：显示g++.exe路径  

![验证成功](figures/haveg++.png)

---

## 🔧 VSCode配置
### 7. 工作区设置
```markdown
1. 创建纯英文路径文件夹（如 D:\CPP_Project）
2. 在VSCode中打开该文件夹(窗口左上角File->Open Folder...->选择你的文件夹)
3. 新建example.cpp文件(Folders边栏的右上角新建图标，或者在边栏区域右键->New File...)
```

### 8. 编写测试代码
```cpp
// example.cpp
#include<iostream>
using namespace std;

int main() {
    cout << "Hello World!" << endl;
    return 0;
}
```

### 9. 配置智能感知
```markdown
1. Ctrl+Shift+P → 输入`C/C++: Edit Configurations (UI)`->回车
2. 设置Compiler Path为刚才bin目录下的的g++路径
3. IntelliSense Mode选择`windows-gcc-x64`
```
![编译器配置](figures/edit%20compiler%20path.png)

---

## 🚦 运行验证
### 10. 执行测试程序
```markdown
点击右上角▶️按钮 → 选择"C/C++: g++.exe"开头的选项
```
✅ **成功输出**：  
![终端输出](figures/success.png)

<div class="warning">
⚠️ 常见问题排查：  
</div>

1. “报错说找不到一个明明存在的路径” → 检查所有路径是否含中文  

2. “明明按照步骤安装好了，但是还是编译不了” → 重启VSCode/PowerShell  

3. 其它问题 → 找助教

</div>
