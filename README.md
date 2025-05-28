# Automatic-login
河南职业技术学院校园网自动登录！（可用账号密码请自行测试）
其中six.txt为项目创建时拿到的全校6K多学号
通过CheckAccount.py跑出来成功登陆的(即使用147258默认密码)储存到了successful.json
如果你发现successful的多半都寄了，请自行重新跑可用校园网。
## 如何使用？
在windows环境下，管理员运行Start.bat，将自行添加脚本到后台任务，并保持开机自启动。
auth_monitor.py会持续性检测网络可用性，一旦发现网络不可用就执行login.py
