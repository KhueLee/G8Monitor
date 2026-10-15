"""Gửi dữ liệu mẫu giống RCS để thử tool (không cần RCS thật).
  python simulate.py                 -> gửi 1 lượt (robot, cảnh báo, task) tới http://127.0.0.1:5502
  python simulate.py --loop          -> gửi liên tục mỗi 5 giây (Ctrl+C để dừng)
  python simulate.py --url http://192.168.x.x:5502
"""
import argparse, json, random, time, urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://127.0.0.1:5502")
ap.add_argument("--loop", action="store_true")
a = ap.parse_args()


def post(path, body):
    req = urllib.request.Request(a.url + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.read().decode()


SPOTS = [[-81599, 70802], [28362, -16150], [60000, 20000], [90000, -30000], [10000, 30000], [20000, 70000], [-120000, 75000], [100000, 45000]]


def once(i):
    robots = []
    for n in range(1, 6):
        st = random.choice([1, 4, 4, 5]) if not (n == 3 and i >= 1) else 2
        robots.append({"deviceCode": f"EA3090{n}", "deviceName ": f"000{n} ", "deviceStatus ": st, "state": {1: "Idle", 4: "InTask", 5: "InCharging", 2: "Fault"}[st],
                       "battery ": str(random.randint(15, 95)), "devicePosition": "21073637",
                       "devicePostionRec": SPOTS[(n * 2 + (i if n != 5 else 0)) % len(SPOTS)], "orderId": f"Manual_{i}" if st == 4 else "",
                       "speed": random.randint(0, 1200)})
    print("agv", post("/ics/agv-status", robots))
    if i == 1:
        print("alarm", post("/ics/alarm", {"deviceNum": "0003", "alarmDesc": "Starting point [260712268] backorder connectivity cannot fulfill device passing requirement (8039)",
                                          "alarmType": 8, "areaId": 2, "alarmReadFlag": 0, "channelDeviceId": "260712268", "alarmSource": "rcs",
                                          "channelName": "1. Kiem tra map \\r\\n 2. Dinh vi lai", "alarmDate": 538227704, "alarmGrade": 2}))
        print("task", post("/ics/task-status", {"orderId": "Manual_1", "status": 7, "errorDesc": "33000513 task point does not exist", "deviceNum": "0003",
                                               "qrContent": "10005155", "modelProcessCode": "liftMoveShelf2", "subTaskStatus": "4"}))
    print("task", post("/ics/task-status", {"orderId": f"Manual_{i}", "status": 6, "deviceNum": "0001", "qrContent": "21073637", "modelProcessCode": "liftMoveShelf2"}))


i = 0
while True:
    once(i)
    i += 1
    if not a.loop:
        break
    time.sleep(5)
