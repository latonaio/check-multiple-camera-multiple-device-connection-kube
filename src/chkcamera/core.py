# coding: utf-8

# Copyright (c) 2019-2020 Latona. All rights reserved.

import os
import subprocess
from datetime import datetime, timedelta
from time import sleep

import aion.mysql as mysql
from aion.logger import lprint
from aion.microservice import main_decorator, Options

SERVICE_NAME = "check-multiple-camera-multiple-device-connection"
EXECUTE_INTERVAL = 1
OUTPUT_INTERVAL = 10  # 別端末への連携頻度(およそEXECUTE_INTERVAL * OUTPUT_INTERVAL[秒]に1回連携)
METADATA_KEY = "device_list"
DEVICE_NAME = os.environ.get("DEVICE_NAME")
DEST_DEVICE_NAME = os.environ.get("DEST_DEVICE_NAME", "")

TIMESTAMP_MIN_DIFF = 1  # 現在からTIMESTAMP_MIN_DIFF(s)前までのステータスを有効扱いにする
TIMESTAMP_MAX_DIFF = 10  # 現在からTIMESTAMP_MAX_DIFF(s)後までのステータスを有効扱いにする


class DeviceMonitorByGstreamer:
    def __init__(self, device_class):
        self.cmd = "v4l2-ctl --list-devices"
        self.cmd_id = "ls -l /dev/v4l/by-id"

    def get_device_list(self):
        device_list = {}
        p = subprocess.Popen(self.cmd.split(), stdout=subprocess.PIPE)
        ret = p.communicate()[0].decode()
        ret = list(filter(None, ret.split("\n")))
        for itr in range(0, len(ret), 2):
            device_list[ret[itr]] = ret[itr + 1].replace("\t", "")
        return device_list

    def get_device_list_id(self):
        devices = {}
        try:
            res = subprocess.check_output(self.cmd_id.split())
            by_id = res.decode()
        except Exception as e:
            print(e)
            return {}
        for line in by_id.split('\n'):
            if ('../../video' in line):
                lst = line.split(' ')
                name = ''.join(lst[-3].split('-')[1:-2])
                deviceId = lst[-1]
                deviceId = deviceId.replace('../../', '/dev/')
                devices[name] = deviceId
        return devices


class UpdateDeviceStateToDB(mysql.BaseMysqlAccess):
    def __init__(self):
        super().__init__("PeripheralDevice")

    def update_up_device_state(self, serial, path):
        sql = """
            INSERT INTO cameras(serial, path, state)
                VALUES (%(serial)s,%(path)s, %(state)s)
            ON DUPLICATE KEY UPDATE
                path = IF(path = %(path)s, path, values(path)),
                state = IF(state = %(state)s, state, values(state)),
                timestamp = CURRENT_TIMESTAMP()
            """
        args = {"serial": serial, "path": path, "state": 1}
        self.set_query(sql, args)

    def update_down_device_state(self):
        now = datetime.now() - timedelta(seconds=1)
        sql = """
            UPDATE cameras
            SET path = '', state = 0
            WHERE timestamp < now() - interval %(min)s second 
                or timestamp > now() + interval %(max)s second;
            """
        args = {
            "min": TIMESTAMP_MIN_DIFF,
            "max": TIMESTAMP_MAX_DIFF,
        }
        self.set_query(sql, args)

    def check_usage(self, serial):
        sql = """
            SELECT * FROM `usage`
            INNER JOIN cameras ON `usage`.id = cameras.usage_id
            WHERE cameras.serial = %(serial)s;
            """
        args = {"serial": serial}
        return self.get_query(sql, args)


@main_decorator(SERVICE_NAME)
def main(opt: Options):
    conn = opt.get_conn()
    num = opt.get_number()
    # get cache kanban
    kanban = conn.set_kanban(SERVICE_NAME, num)

    dm = DeviceMonitorByGstreamer("Video/Source")
    devices = {METADATA_KEY: {}}
    start_cameras = {}
    output_count = 0

    while True:
        device_list = dm.get_device_list_id()
        if devices[METADATA_KEY] != device_list:
            lprint("change device status: ", device_list)
            devices = {METADATA_KEY: device_list}
        sleep(EXECUTE_INTERVAL)
        try:
            with UpdateDeviceStateToDB() as my:
                for device_id, path in device_list.items():
                    my.update_up_device_state(device_id, path)
                my.update_down_device_state()
                my.commit_query()
        except Exception as e:
            lprint(str(e))

        with UpdateDeviceStateToDB() as my:
            for serial, path in device_list.items():
                if not start_cameras.get(serial):
                    use = my.check_usage(serial)
                    lprint(use)
                    if use:
                        start_cameras[serial] = True
                        metadata = {
                            METADATA_KEY: {serial: path}
                        }
                        lprint("start camera :", metadata, use)
                        conn.output_kanban(
                            result=True,
                            metadata=metadata,
                            connection_key=use.get('use'),
                        )

        output_count = (output_count + 1) % OUTPUT_INTERVAL

        if DEST_DEVICE_NAME is not None and DEST_DEVICE_NAME != '' and output_count == 0:
            conn.output_kanban(
                result=True,
                metadata={
                    'previous_device': DEVICE_NAME,
                    'device_list': device_list,
                },
                connection_key='output',
                device_name=DEST_DEVICE_NAME,
            )
