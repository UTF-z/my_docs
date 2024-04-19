# Linux 操作系统相关问题

## 时间问题

### 校准系统时间

校准系统时间一般依赖NTP服务器，在linux中下载ntpdate软件，使用如下命令进行校准
```ntpdate time.nist.gov```

### 修改系统时间

`timedatectl` 命令可以查看和修改系统时间和时区，具体使用方法如下
- 读取系统时间：`timedatectl`
- 设置系统时间：`timedatectl set-time "YYYY-MM-DD HH:MM:SS`
- 列出所有时区：`timedatectl list-timezones`
- 设置系统时区：`timedatectl set-timezone <时区名>`
- 是否和NTP服务器同步: `timedatectl set-ntp yea // no`

一般来讲，全世界有个统一的世界协调时间UTC，它接近格林尼治时间GMT，中国北京时间CST=UTC+8。
如果想把时间从CST改成UTC, 可以直接把上面的设置系统时区命令中的时区名写成UTC


### 同步硬件时间RTC和系统时间
sudo权限使用`hwclock`命令可以查看和修改硬件时间

### 修改文件时间
- 修改为当前系统时间：`touch <文件名>`
- 修改为指定时间：`touch -t <YYYYMMDDhhmm.ss> <文件名>`




