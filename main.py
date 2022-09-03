import _thread
import net
from misc import Power
import checkNet
import log
import modem
import pm
import umqtt
import utime
from machine import UART, Pin, Timer, RTC, ExtInt

# =========================Configuration===================================
# 项目信息
PROJECT_NAME = "camera014"
PROJECT_VERSION = "1.0.0"
checknet = checkNet.CheckNetwork(PROJECT_NAME, PROJECT_VERSION)

# 设置日志输出级别
log.basicConfig(level=log.INFO)
NB_IoT_log = log.getLogger("NB_IoT")

# 打印网络信息
NB_IoT_log.info("net work: {}\r\n".format(checknet))
# 全局变量
wake_up = 0
sleep_now = False  # 睡眠状态
judge_minute = 999
send_once_flag = 0
alarm_set_sec = 0
alarm_wake_sec = 0
alarm_sleep_sec = 0
alarm_callback_sta = 0
time_list = ""
rtc = RTC()
date_e = list(rtc.datetime())
sleep_time = 60  # 60分钟拍照一次
sleep_flag = 0  # 判断是否开始休眠


# openmv_offline_pin = Pin(Pin.GPIO15, Pin.IN, Pin.PULL_UP, 0)


# def openmv_offline_callback(args):
#     print('### interrupt  {} ###'.format(args))
#
#
# extint = ExtInt(ExtInt.GPIO15, ExtInt.IRQ_FALLING, ExtInt.PULL_UP, openmv_offline_callback)


# ==========================String func====================================
# @brief         判断字符串是否为int型变量
# @param         str_list    需要判断的字符串
# @return        布尔值，是int变量为True
# @Sample Usage  is_int("12")
# @Modify Time   2022/7/12
def is_int(str_list: list) -> bool:
    try:
        for list_e in str_list:
            int(list_e)
        return True
    except ValueError:
        return False


# ============================== RTC class ====================================
class Rtc:
    rtc = None

    @classmethod
    def nowtime(cls):
        return cls.rtc.datetime()


# 判断什么时候开始休眠
# 专门判断休眠一小时的
# 实际应该根据sleep_time设置的分钟数来决定什么时候休眠
# 设置成59分启动，0分的时候开始拍照上传，留2min上传时间，然后休眠57min到59min，循环流程
def sleep_judge():
    global sleep_time
    global rtc
    global sleep_flag
    global wake_up  # 只刷新judge mintue一次的标志位
    global judge_minute  # 决定拍照的时间
    if wake_up is 0:  # 执行到这里说明设备已经连上网
        judge_minute = rtc.datetime()[5] + 1  # 设定为联网成功1min后开始拍照
        if judge_minute >= 60:
            judge_minute = judge_minute - 60
        if judge_minute >= 10:  # 只会影响第一次启动（除非联网超过10min，不过这种情况多半没流量了，不太会出现），不加这两句程序设备无论什么时候启动1min后就立刻拍照进入休眠，随后进入1h一次拍照周期
            judge_minute = 999
        else:
            wake_up = 1  # judge_minute除了在安装的时候正常运行每次只更新一次
    now_minute = rtc.datetime()[5]  # 不断检查现在的时间
    shoot_time = 2  # 两分钟时间拍照上传
    if now_minute is judge_minute and sleep_flag is 0 and wake_up is 1:
        Openmv.power_on()  # 上电自动拍照
        sleep_flag = 1
    elif now_minute is not judge_minute:
        sleep_flag = 0
    if now_minute == judge_minute + shoot_time:
        dev_sleep(0, 0, 59-shoot_time-judge_minute, 0)  # 休眠约57分至59分，若联网时间过长也会小于57min


def date_manage():
    global date_e
    if date_e[6] >= 60:
        date_e[6] = date_e[6] - 60  # 秒
        date_e[5] = date_e[5] + 1  # 分
    if date_e[5] >= 60:
        date_e[5] = date_e[5] - 60  # 分
        date_e[4] = date_e[4] + 1  # 小时
    if date_e[4] >= 24:
        date_e[4] = date_e[4] - 24  # 小时
        date_e[2] = date_e[2] + 1  # 天
    if date_e[1] == 2:  # 特殊处理二月
        if date_e[2] == 30 and ((date_e[0] % 4 == 0 and date_e[0] % 100 != 0) or (date_e[0] % 400 == 0)):  # 闰年2月
            date_e[2] = 1  # 天
            date_e[1] = 3  # 月
        if date_e[2] == 29 and (not ((date_e[0] % 4 == 0 and date_e[0] % 100 != 0) or (date_e[0] % 400 == 0))):  # 非闰年2月
            date_e[2] = 1  # 天
            date_e[1] = 3  # 月
    elif date_e[1] == 1 or date_e[1] == 3 or date_e[1] == 5 or date_e[1] == 7 or date_e[1] == 8 or date_e[1] == 10 or \
            date_e[1] == 12:
        if date_e[2] == 32:  # 大月
            date_e[2] = 1  # 天
            date_e[1] = date_e[1] + 1  # 月
        if date_e[1] == 13:  # 过年咯
            date_e[1] = 1  # 月
            date_e[0] = date_e[0] + 1  # 年
    else:
        if date_e[2] == 31:  # 小月
            date_e[2] = 1  # 天
            date_e[1] = date_e[1] + 1  # 月


def callback(args):
    global rtc
    global sleep_now
    global send_once_flag
    global alarm_wake_sec
    global alarm_set_sec
    global alarm_sleep_sec
    global alarm_callback_sta
    global time_list
    alarm_callback_sta = 0
    nowtime = rtc.datetime()
    alarm_wake_sec = nowtime[6] + (nowtime[5] * 60) + (nowtime[4] * 3600) + (nowtime[2] * 86400)
    NB_IoT_log.info("wake up time:{},".format(rtc.datetime()))
    if alarm_wake_sec - alarm_set_sec < alarm_sleep_sec:
        NB_IoT_log.info("--------FAIL TO SET ALARM-------------")
        alarm_callback_sta = -1
    else:
        NB_IoT_log.info("--------SUCCESSFULLLY SET ALARM-------")
        Openmv.power_on()
        _thread.start_new_thread(_mqtt_send, ())
        _thread.start_new_thread(_mqtt_listen, ())
        _thread.start_new_thread(_mqtt_ping, ())
        alarm_callback_sta = 1
    alarm_sleep_sec = 0
    alarm_set_sec = 0
    alarm_wake_sec = 0
    sleep_now = False
    send_once_flag = 0
    rtc.enable_alarm(0)
    if alarm_callback_sta == -1:
        NB_IoT_log.info("--------RESETTING ALARM---------------")
        sleep_now = True
        dev_sleep(int(time_list[0]), int(time_list[1]), int(time_list[2]), int(time_list[3]))


# ============================== sleep ========================================
# @brief         设备进入睡眠状态，在固定时间后唤醒
# @param         day  hour  min  sec  天、小时、分钟、秒
# @return        None
# @Sample Usage  dev_sleep(14, 14, 14, 14)
# @Modify Time   2022/7/12
def dev_sleep(day, hour, min, sec):
    global rtc
    global send_once_flag
    global alarm_set_sec
    global alarm_sleep_sec
    global date_e
    alarm_sleep_sec = sec + (min * 60) + (hour * 3600) + (day * 86400)
    date_e = list(rtc.datetime())
    alarm_set_sec = date_e[6] + (date_e[5] * 60) + (date_e[4] * 3600) + (date_e[2] * 86400)
    date_e[2] += day
    date_e[4] += hour
    date_e[5] += min
    date_e[6] += sec
    date_manage()
    rtc.set_alarm(date_e)
    NB_IoT_log.info("NOW time:{},".format(rtc.datetime()))
    NB_IoT_log.info("ALARM time:{},".format(date_e))
    rtc.register_callback(callback)
    rtc.enable_alarm(1)
    utime.sleep(1)

    NB_IoT_log.info("Entering DeepSleep Mode...")
    Openmv.power_down()
    Power.powerDown()


# ============================== Timer class ==================================
# 使用计数器计算超时
class TimeoutTimer:
    sec = 0
    wait_time = 30
    status = True
    period = 1000
    timer = None
    mode = None
    fun = None

    @classmethod
    def refresh(cls):
        cls.sec = 0
        cls.status = True
        NB_IoT_log.info("Timer refresh")

    @classmethod
    def start(cls):
        cls.sec = 0
        cls.status = True
        TimeoutTimer.timer.start(period=cls.period, mode=cls.mode, callback=cls.fun)
        NB_IoT_log.info("Timer start")

    @classmethod
    def stop(cls):
        TimeoutTimer.timer.stop()
        NB_IoT_log.info("Timer stop")


def TimeoutTimer_callback(timer):
    TimeoutTimer.sec += 1
    if TimeoutTimer.sec >= TimeoutTimer.wait_time:
        TimeoutTimer.status = False
        NB_IoT_log.info("Time out")


# =============================== Openmv class ===================================
class Openmv:
    openmv_ppin = None

    @classmethod
    def power_on(cls):
        ret = cls.openmv_ppin.write(1)
        NB_IoT_log.info("OpenMV power on. return={}".format(ret))

    @classmethod
    def power_down(cls):
        ret = cls.openmv_ppin.write(0)
        NB_IoT_log.info("OpenMV power down. return={}".format(ret))


# =============================== UART class ===================================
class Uart:
    uart = None

    @classmethod
    def close(cls):
        ret = cls.uart.close()
        NB_IoT_log.info("uart close. return={}".format(ret))

    @classmethod
    def send(cls, msg):
        ret = cls.uart.write(msg)
        NB_IoT_log.info("uart send. return={}, send={}, time={}".format(ret, msg, Rtc.nowtime()))

    @classmethod
    def receive(cls):
        msg = cls.uart.read()
        NB_IoT_log.info("uart receive, len={}, time={}，msg={}".format(len(msg), Rtc.nowtime(), msg))
        return msg

    @classmethod
    def is_data_recv(cls):  # 是否有数据缓存
        if cls.uart.any():
            return True
        else:
            return False

    @classmethod
    def cache_data(cls):  # 缓存数据大小
        return cls.uart.any()


# ====================================init======================================
Rtc.rtc = RTC()

TimeoutTimer.timer = Timer(Timer.Timer1)
TimeoutTimer.mode = TimeoutTimer.timer.PERIODIC
TimeoutTimer.fun = TimeoutTimer_callback

Uart.uart = UART(UART.UART1, 9600, 8, 0, 1, 0)
Openmv.openmv_ppin = Pin(Pin.GPIO14, Pin.OUT, Pin.PULL_DISABLE, 0)


# =====================================MQTT=====================================
def sub_cb(topic, msg):
    """
    MQTT接收消息回调函数, NB模块会根据上位机发来的信息进行处理或透传
    """
    global sleep_now
    global time_list
    NB_IoT_log.info("MQTT Receive:{}".format(msg))

    if len(msg) > 11 and msg[0:11] == b"BC25+SLEEP=":
        time_list = msg[11:].decode().split(',')
        if len(time_list) == 4 and is_int(time_list):
            sleep_now = True
            dev_sleep(int(time_list[0]), int(time_list[1]), int(time_list[2]), int(time_list[3]))
        else:
            try:
                mqtt.publish(b"/img/collection/get/{}".format(PROJECT_NAME), b"Sleep time setting error\r\n")
                NB_IoT_log.info("mqtt publish: time error")
            except AttributeError as e:
                NB_IoT_log.info("Mqtt has disconnected: {}".format(e))

    elif msg == b"AT*GPO=1,1#":
        Openmv.power_down()
        utime.sleep_ms(100)
        Openmv.power_on()

    elif msg == b"AT*GPO=1,0#":
        try:
            mqtt.publish(b"/img/collection/get/{}".format(PROJECT_NAME), b"OK\r\n")
            NB_IoT_log.info("mqtt publish:{}".format(b"OK\r\n"))
        except AttributeError as e:
            NB_IoT_log.info("Mqtt has disconnected: {}".format(e))
    else:
        try:
            Uart.send(msg)
        except TypeError as e:
            NB_IoT_log.info("Uart send error:{}".format(e))


def _mqtt_send():
    global sleep_now
    global send_once_flag
    rdata = ""
    while True:
        if sleep_now and send_once_flag == 0:
            send_once_flag = 1
            NB_IoT_log.info("Mqtt send close.")
            _thread.stop_thread(0)
        else:
            utime.sleep_ms(100)
            if Uart.is_data_recv():
                utime.sleep_ms(50)
                rdata = Uart.receive()
                if rdata == "":
                    pass

            while rdata:
                send_len = min(512, len(rdata))
                send_data = rdata[0:send_len]
                rdata = rdata[send_len:]
                try:
                    mqtt.publish(b"/img/collection/get/{}".format(PROJECT_NAME), send_data)
                # NB_IoT_log.info("mqtt publish. length={} \r\ntime={}".format(len(send_data), Rtc.nowtime()))
                except AttributeError as e:
                    NB_IoT_log.info("Mqtt has disconnected: {}".format(e))


def _mqtt_listen():
    global sleep_now
    global send_once_flag
    while True:
        if sleep_now and send_once_flag == 1:
            send_once_flag = 2
            NB_IoT_log.info("Mqtt listen close.")
            _thread.stop_thread(0)
        else:
            mqtt.wait_msg()


def _mqtt_ping():
    """
    每一分钟发一次数据，保证mqtt不会被踢掉
    """
    global sleep_now
    global send_once_flag
    global rtc
    send_ping = 0
    while True:
        sleep_judge()
        utime.sleep(1)
        if sleep_now and send_once_flag == 2:
            send_once_flag = 3
            send_ping = 0
            NB_IoT_log.info("Mqtt ping close.")
            _thread.stop_thread(0)
        else:
            send_ping += 1

        if send_ping == 200:
            send_ping = 0
            try:
                mqtt.publish(b"/bc25/ping", b"device:{}, time:{}\r\n".format(PROJECT_NAME, Rtc.nowtime()))
                NB_IoT_log.info("mqtt ping.")
            except AttributeError as e:
                NB_IoT_log.info("Mqtt has disconnected: {}".format(e))


# =======================================main=======================================
if __name__ == '__main__':

    # 打印开机信息
    checknet.poweron_print_once()
    NB_IoT_log.info("now time:{}".format(rtc.datetime()))
    # 等待BC25网络就绪
    NB_IoT_log.info("Waiting net connect...")
    stagecode, subcode = checknet.wait_network_connected(30)

    if stagecode == 3 and subcode == 1:
        wake_up = 0
        judge_minute = 999
        NB_IoT_log.info('Network connection successfully!')

        mqtt = umqtt.MQTTClient(modem.getDevImei(), "47.96.233.95", 1883, user=PROJECT_NAME, keepalive=60)
        mqtt.set_callback(sub_cb)
        mqtt.connect()
        mqtt.subscribe(b"/img/collection/control/{}".format(PROJECT_NAME))

        mqtt_send = _thread.start_new_thread(_mqtt_send, ())
        mqtt_listen = _thread.start_new_thread(_mqtt_listen, ())
        mqtt_ping = _thread.start_new_thread(_mqtt_ping, ())
        print("thread send:{}, thread listen:{}, mqtt ping:{}".format(mqtt_send, mqtt_listen, mqtt_ping))

    else:
        NB_IoT_log.info('Network connection failed! stagecode = {}, subcode = {}'.format(stagecode, subcode))
