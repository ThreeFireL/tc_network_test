# tc_network_test
基于Linux TC的弱网自动化脚本

支持功能
* 支持自定义每组弱网测试时常
* 支持自定义弱网类别测试（丢包、延时 + 丢包、带宽、抖动等）
* 当前支持日志 输出各组弱网测试 测试时间，方便查询上报数据

使用方式
* xx.py 上/下行、ip（待测设备IP）、 module（loss、delay+loss、jitter、rate） 测试时常

可以根据自己业务场景灵活进行调整
