#!/usr/bin/env python
import socket
import sys
import subprocess
import re
from binascii import hexlify
import time

flow_index_min = 10
flow_index_max = 100

def check_ip(ipaddr):
    compile_ip = re.compile(r'^(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|[1-9])\.'
                            r'(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|\d)\.'
                            r'(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|\d)\.'
                            r'(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|\d)$')
    return bool(compile_ip.match(ipaddr))

def get_flowid_for_host(hostip, interface):
    flowid = ''
    handle = ''
    flowid_array = []

    packed_ip_addr = socket.inet_aton(hostip)
    hexStr = hexlify(packed_ip_addr)

    status, output = subprocess.getstatusoutput(f'sudo tc filter show dev {interface}')
    if status != 0:
        print(output)
        return flowid, flowid_array, handle
    
    array = output.split('filter')
    for line in array:
        block_array = line.split(' ')
        if '*flowid' in block_array:
            flowid_array.append(block_array[block_array.index('*flowid') + 1])
            if line.find(bytes.decode(hexStr)) != -1:
                flowid = block_array[block_array.index('*flowid') + 1]
                handle = block_array[block_array.index('fh') + 1]
    return flowid, flowid_array, handle

def generate_new_flowid(flowid_array):
    flow_index_array = [int(flowid.split(':')[1]) for flowid in flowid_array]
    
    for index in range(flow_index_min, flow_index_max):
        if index not in flow_index_array:
            return f"1:{index}"
    return ""

# 封装记录时间函数
def log_time(action, condition, percentage):
    current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"{action} {condition} test with {percentage}% at {current_time}")

# 统一封装 命令执行以及错误处理
def execute_command(command):
    status, output = subprocess.getstatusoutput(command)
    if status != 0:
        print(f"Command failed: {command}")
        print(f"Error: {output}")
    return status == 0

# 定义弱网条件列表
loss_range = [30, 30, 40, 40, 50, 50 ,60 ,70]
delay_range = [50, 100, 50,100, 50, 100, 50, 50]
rate_range = [1000, 600, 300]
jitter_range = [100, 200, 500, 1000]

# 封装清除弱网条件
def delete_tc_settings(interface, flowid, handle):
    flowid, flowid_array, handle = get_flowid_for_host(hostip, interface)
    del_filter_cmd = f'sudo tc filter del dev {interface} protocol ip prio 3 handle {handle} u32'
    del_class_cmd = f'sudo tc class del dev {interface} parent 1:1 classid {flowid}'
    
    execute_command(del_filter_cmd)
    execute_command(del_class_cmd)

# 封装基础设置命令
def setup_tc(interface, flowid, direction, hostip, rate, delay=0, jitter=0, loss=0):
    set_rate_cmd = f'sudo tc class add dev {interface} parent 1:1 classid {flowid} htb rate {rate}kbit'
    print (set_rate_cmd)
    if not execute_command(set_rate_cmd):
        return False

    if direction == 'up':
        add_filter_cmd = f'sudo tc filter add dev {interface} protocol ip parent 1:0 prio 3 u32 match ip src {hostip} match ip protocol 17 0xff flowid {flowid}'
    else:
        add_filter_cmd = f'sudo tc filter add dev {interface} protocol ip parent 1:0 prio 3 u32 match ip dst {hostip} match ip protocol 17 0xff flowid {flowid}'
    print (add_filter_cmd)
    if not execute_command(add_filter_cmd):
        return False

    handle = str(int(flowid.split(":")[1]) + 10)
    set_delay_loss_cmd = f'sudo tc qdisc add dev {interface} parent {flowid} handle {handle}: netem delay {delay}ms {jitter}ms loss {loss} limit 2000'
    print (set_delay_loss_cmd)
    
    return execute_command(set_delay_loss_cmd)

# 弱网具体执行
def run_tests(hostip, interface, direction, module, test_time):
    # 丢包
    newloss_range = [10, 20, 30, 40, 50, 60, 70]
    if module in ['all', 'loss']:
        for loss in newloss_range:
            # 判定是否存在flowid，如果没有，则创建新的，确保每一组弱网测试时，生成新flowid
            flowid, flowid_array, handle = get_flowid_for_host(hostip, interface)
            if not flowid:
                flowid = generate_new_flowid(flowid_array) 
            print(f"Running loss test with {loss}% packet loss")
            if setup_tc(interface, flowid, direction, hostip, rate=500000, loss=loss):
                 # 记录开始时间
                log_time("Started", "loss", loss)
                time.sleep (test_time)
                # 记录结束时间
                log_time("Ended", "loss", loss)
            
                # 清除弱网设置
                delete_tc_settings(interface, flowid, handle)

                # 清除设置之后，等待2分钟，在进行下一个弱网设置
                print ("Wait two minutes for the next set of tests")
                time.sleep(10)

        print (f"loss test completed.")

    # 丢包+延时
    if module in ['all', 'delay']:
        for i in range(len(loss_range)):
            loss = loss_range[i]
            delay = delay_range[i]

            flowid, flowid_array, handle = get_flowid_for_host(hostip, interface)
            if not flowid:
                flowid = generate_new_flowid(flowid_array) 
            print(f"Running loss+delay test with {loss}% packet loss and {delay}ms delay")
            if setup_tc(interface, flowid, direction, hostip, rate=500000, delay=delay, loss=loss):
                log_time("Started", "loss+delay", f"{loss}% loss and {delay}ms delay")
                time.sleep(test_time)
                log_time("Ended", "loss+delay", f"{loss}% loss and {delay}ms delay")
                    
                delete_tc_settings(interface, flowid,handle)
                
                print ("Wait two minutes for the next set of tests")
                time.sleep(10)

        print (f"loss + delay test completed.")
    
    # 抖动
    if module in ['all', 'jitter']:
        for jitter in jitter_range:
            delay = jitter/2
            jitter = jitter/2

            flowid, flowid_array, handle = get_flowid_for_host(hostip, interface)
            if not flowid:
                flowid = generate_new_flowid(flowid_array)
            print(f"Running jitter test with {jitter} packet jitter")
            if setup_tc(interface, flowid, direction, hostip, rate=500000, delay=delay, jitter=jitter):
                log_time("Started", "jitter", f"{jitter}% jitter ms delay")
                time.sleep(test_time)
                log_time("Ended", "jitter", f"{jitter}% jitter ms delay")

                delete_tc_settings(interface, flowid, handle)
                print ( "Wait two minutes for the next set of tests")
                time.sleep(10)
        print (f"jitter test completed")
    

    # 带宽
    if direction == 'down':
        if module in ['all', 'rate']:
            for rate in rate_range:
                print(f"Running rate test with {rate}kbit bandwidth")
                flowid, flowid_array, handle = get_flowid_for_host(hostip, interface)
                if not flowid:
                    flowid = generate_new_flowid(flowid_array) 
                if setup_tc(interface, flowid, direction, hostip, rate=rate):
                    log_time("Started", "rate", f"{rate}kbit bandwidth")

                    time.sleep(test_time)
                
                    log_time("Ended", "rate", f"{rate}kbit bandwidth")

                    delete_tc_settings(interface, flowid,handle)
                    
                    print ("Wait two minutes for the next set of tests")
                    time.sleep(10)
            print(f"rate test completed.")


    print(f"{module} test completed.")

if __name__ == '__main__':
    if len(sys.argv) != 5:
        print("Usage: script.py direction(up.down) hostip module(all,loss,delay,rate,jitter) time(s)")
        sys.exit(1)
    
    direction = sys.argv[1]
    hostip = sys.argv[2]
    module = sys.argv[3]
    test_time = int(sys.argv[4])
    if direction not in ['up', 'down']:
        print("Error: direction must be 'up' or 'down'")
        sys.exit(1)

    if module not in ['all', 'loss', 'delay', 'rate', 'jitter']:
        print("Error: module must be 'all', 'loss', 'delay', or 'rate' or 'jitter'")
        sys.exit(1)

    if not check_ip(hostip):
        print(f"Error: {hostip} is not a valid IP address")
        sys.exit(1)

    interface = 'ifb0' if direction == 'up' else 'eth1' # 需要根据自己的弱网环境确定网卡名字
    flowid, flowid_array, handle = get_flowid_for_host(hostip, interface)

    run_tests(hostip, interface, direction, module, test_time)
