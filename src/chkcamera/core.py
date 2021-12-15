# coding: utf-8

# Copyright (c) 2019-2020 Latona. All rights reserved.

import logging
import os
import subprocess
from datetime import datetime, timedelta
from asyncio import sleep

import MySQLdb

from custom_logger import init_logger
from rabbitmq_client import RabbitmqClient

SERVICE_NAME = "check-multiple-camera-multiple-device-connection"
EXECUTE_INTERVAL = 1
OUTPUT_INTERVAL = 10  # 別端末への連携頻度(およそEXECUTE_INTERVAL * OUTPUT_INTERVAL[秒]に1回連携)
METADATA_KEY = "device_list"
DEVICE_NAME = os.environ.get("DEVICE_NAME")
DEST_DEVICE_NAME = os.environ.get("DEST_DEVICE_NAME", "")

RABBITMQ_URL = os.environ.get("RABBITMQ_URL")
QUEUE_TO_CAMERA_1 = os.environ.get("QUEUE_TO_CAMERA_1")
QUEUE_TO_CAMERA_2 = os.environ.get("QUEUE_TO_CAMERA_2")
QUEUE_TO_OUTPUT = os.environ.get("QUEUE_TO_OUTPUT")

MYSQL_HOST = os.environ.get("MYSQL_HOST")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE")

TIMESTAMP_MIN_DIFF = 1  # 現在からTIMESTAMP_MIN_DIFF(s)前までのステータスを有効扱いにする
TIMESTAMP_MAX_DIFF = 10  # 現在からTIMESTAMP_MAX_DIFF(s)後までのステータスを有効扱いにする


logger = logging.getLogger(__name__)


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


class UpdateDeviceStateToDB():
    def __init__(self):
        self.connection = MySQLdb.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            passwd=MYSQL_PASSWORD,
            db=MYSQL_DATABASE,
            charset="utf8mb4")
        self.cursor = self.connection.cursor(MySQLdb.cursors.DictCursor)

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        self.connection.close()

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
        self.cursor.execute(sql, args)

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
        self.cursor.execute(sql, args)

    def check_usage(self, serial):
        sql = """
            SELECT * FROM `usage`
            INNER JOIN cameras ON `usage`.id = cameras.usage_id
            WHERE cameras.serial = %(serial)s;
            """
        args = {"serial": serial}
        self.cursor.execute(sql, args)
        return self.cursor.fetchone()

    def commit_query(self):
        self.connection.commit()


async def main():
    init_logger()

    client = await RabbitmqClient.create(
        RABBITMQ_URL,
        [],
        [QUEUE_TO_CAMERA_1, QUEUE_TO_CAMERA_2, QUEUE_TO_OUTPUT]
    )

    dm = DeviceMonitorByGstreamer("Video/Source")
    devices = {METADATA_KEY: {}}
    start_cameras = {}
    output_count = 0

    while True:
        device_list = dm.get_device_list_id()
        if devices[METADATA_KEY] != device_list:
            logger.info("change device status: %s", device_list)
            devices = {METADATA_KEY: device_list}
        await sleep(EXECUTE_INTERVAL)
        try:
            with UpdateDeviceStateToDB() as my:
                for device_id, path in device_list.items():
                    my.update_up_device_state(device_id, path)
                my.update_down_device_state()
                my.commit_query()
        except Exception as e:
            logger.error(str(e))

        with UpdateDeviceStateToDB() as my:
            for serial, path in device_list.items():
                if not start_cameras.get(serial):
                    use = my.check_usage(serial)
                    logger.info(use)
                    if use:
                        start_cameras[serial] = True
                        metadata = {
                            METADATA_KEY: {serial: path}
                        }
                        logger.info("start camera : %s %s", metadata, use)

                        use_queue = {
                            'camera-1': QUEUE_TO_CAMERA_1,
                            'camera-2': QUEUE_TO_CAMERA_2,
                        }.get(use.get('use'))
                        await client.send(use_queue, metadata)
                        # conn.output_kanban(
                        #     result=True,
                        #     metadata=metadata,
                        #     connection_key=use.get('use'),
                        # )

        output_count = (output_count + 1) % OUTPUT_INTERVAL

        if DEST_DEVICE_NAME is not None and DEST_DEVICE_NAME != '' and output_count == 0:
            await client.send(QUEUE_TO_OUTPUT, {
                'previous_device': DEVICE_NAME,
                'device_list': device_list,
            })
            # conn.output_kanban(
            #     result=True,
            #     metadata={
            #         'previous_device': DEVICE_NAME,
            #         'device_list': device_list,
            #     },
            #     connection_key='output',
            #     device_name=DEST_DEVICE_NAME,
            # )
