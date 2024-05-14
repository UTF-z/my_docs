## 烧录系统

硬件准备：
- 32G SD卡
- SD读卡器。

软件准备：
- SD卡格式化工具[SD Card Formatter](https://www.sdcard.org/downloads/formatter/)
- 烧录工具[balenaEtcher](https://etcher.balena.io/)

资源准备：
- 英伟达的[Jpack](https://developer.nvidia.cn/jetson-nano-sd-card-image)，这是一个打包好的Linux镜像，包含了cuda cudnn tensorRT等众多库和工具

步骤：
1. SD卡装入读卡器，插到电脑USB3口上
2. 用SD Card Formatter格式化SD卡
3. 用烧录工具烧录镜像（USB3口会快很多，10min左右）

## 启动并连接(无需显示器鼠标键盘)

硬件准备：
- micro-USB线（有数据传输功能）
- Jaston Nano 供电器
- (可选)以太网线，路由器

软件准备：
- Putty

### 通过串口连接

步骤:
1. 插入SD card
2. 跳线帽短接J48，插入电源线
3. micro-USB连接板子和电脑，还是插电脑USB3口
4. 查找你的串口设备，Windows系统上，右键“开始”，“设备管理器”，“端口（COM和LPT）”，找硬件ID“VID_0955&PID_7020”的设备，看它是哪个COM口。
5. 用Putty串口连接该端口，波特率是115200
7. 如果session打开一直黑屏，把板子断电重启，反复，直到成功连上。
6. 开始初始化系统，之后才可以ssh登录

### 通过ssh连接(三种方式)

**micro-USB**:
1. 用micro-USB连接笔记本和板子
2. 你会发现多了一个`192.168.55.0/24`的网段，这里头的`192.168.55.1`设备就是你的板子
3. ssh登录它

**以太网线**：
1. 先在笔记本上把wifi设置成共享的，共享给“以太网”
2. 用网线连接
3. 笔记本上将多出来的以太网设置成手动分配ip，ipv4设置成你喜欢的网段里的第一个，掩码是/24
4. 在板子一侧（现在假如是micro-USB连接状态），配置以太网卡eth0：
    - 首先nmcli dev查看网络设备，发现eth0 disconnected
    - ifconfig设置eth0的ip地址，注意要和你的笔记本在一个网段里，并且不要冲撞

    ```sudo ifconfig eth0 <ip>```

    - ifconfig设置子网掩码

    ```sudo ifconfig eth0 netmask 255.255.255.0```

    - 启动以太网卡

    ```sudo ifconfig eth0 up```

5. 电脑侧ping一下ip，测试连通，然后就可以ssh登录啦

**路由器**：
1. 先把你的路由器设置好，手机或者电脑连上路由器，登录管理页面设置名称密码
2. 在板子一侧，配置wlan0：
    - 启动wlan0网络设备

    ```sudo ifconfig wlan0 up```

    - 使用nmcli工具连接wifi，确保和笔记本连接的同一个路由器

    ```sudo nmcli dev wifi con "<wifi的ssid，就是wifi名>" password "wifi密码"```

    - ifconfig查看一下设备在wlan里的ip地址
3. 笔记本ping一下板子的ip，ssh登它！
4. 取下所有笔记本和板子的连接线，You are free!

