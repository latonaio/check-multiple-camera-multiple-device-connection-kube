import subprocess



cmd = 'ls -l /dev/v4l/by-id'
res = subprocess.check_output(cmd.split())
by_id = res.decode()

cmd = 'ls -la /dev/v4l/by-path'
res = subprocess.check_output(cmd.split())
by_path = res.decode()


# get device name
deviceName = {}
for line in by_id.split('\n'):
    if ('../../video' in line):
        lst = line.split(' ')
        # print(lst[9])
        # print(lst[-1])
        tmp = lst[-1]
        deviceId = tmp.replace('../../video', '')
        deviceName[deviceId] = ''.join(lst[-3].split('-')[1:-2])

print(deviceName)
print(by_id)
print(by_path)

